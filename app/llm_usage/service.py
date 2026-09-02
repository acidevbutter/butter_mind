from datetime import UTC, datetime

from app.core.decorators import log_errors
from app.core.llm.exceptions import LLMBudgetExceededError, LLMPricingUnavailableError
from app.core.llm.pricing import actual_cost_brl, maximum_cost_brl
from app.core.llm.schemas import LLMMessage, LLMResponse
from app.core.metrics import emit_metrics
from app.llm_usage.repository import LLMUsageRepository
from app.llm_usage.schemas import (
    LLMBudgetLimitRead,
    LLMBudgetLimitUpdate,
    LLMFlowUsageRead,
    LLMUsageSummaryRead,
)


def _month_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = now or datetime.now(UTC)
    start = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


@log_errors
class LLMUsageService:
    def __init__(self, repository: LLMUsageRepository):
        self.repository = repository

    async def ensure_budget(
        self,
        *,
        flow: str,
        model: str,
        system: str,
        messages: list[LLMMessage],
        max_tokens: int,
        schema_text: str = "",
    ) -> None:
        budget = await self.repository.get_budget(flow)
        if budget is None:
            return
        maximum_cost = maximum_cost_brl(
            model=model,
            input_text="".join([system, schema_text, *(message.content for message in messages)]),
            max_output_tokens=max_tokens,
        )
        if maximum_cost is None:
            raise LLMPricingUnavailableError(model)
        start, end = _month_window()
        spent = await self.repository.monthly_cost(flow=flow, start=start, end=end)
        budget_amount = budget.monthly_budget_brl
        if budget_amount > 0:
            await emit_metrics(
                dimensions={"Flow": flow, "Model": model},
                values={
                    "LLMBudgetUtilizationPercent": (
                        float(spent / budget_amount * 100),
                        "Percent",
                    )
                },
            )
        if spent + maximum_cost > budget.monthly_budget_brl:
            await emit_metrics(
                dimensions={"Flow": flow, "Model": model},
                values={"LLMBudgetExceeded": (1, "Count")},
            )
            raise LLMBudgetExceededError(flow=flow, budget=budget.monthly_budget_brl, spent=spent)

    async def record(self, *, flow: str, operation: str, response: LLMResponse) -> None:
        estimated_cost_brl = actual_cost_brl(response.model, response.usage)
        await self.repository.add_event(
            flow=flow,
            operation=operation,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            cached_input_tokens=response.usage.cached_input_tokens,
            output_tokens=response.usage.output_tokens,
            estimated_cost_brl=estimated_cost_brl,
        )
        values: dict[str, tuple[float, str]] = {}
        if response.usage.input_tokens is not None:
            values["LLMInputTokens"] = (response.usage.input_tokens, "Count")
        if response.usage.cached_input_tokens is not None:
            values["LLMCachedInputTokens"] = (response.usage.cached_input_tokens, "Count")
        if response.usage.output_tokens is not None:
            values["LLMOutputTokens"] = (response.usage.output_tokens, "Count")
        if estimated_cost_brl is not None:
            values["LLMCostBRL"] = (float(estimated_cost_brl), "None")
        if values:
            await emit_metrics(
                dimensions={"Flow": flow, "Model": response.model},
                values=values,
            )

    async def save_budget(self, *, flow: str, payload: LLMBudgetLimitUpdate) -> LLMBudgetLimitRead:
        budget = await self.repository.save_budget(flow=flow, **payload.model_dump())
        return LLMBudgetLimitRead.model_validate(budget)

    async def get_budget(self, *, flow: str) -> LLMBudgetLimitRead | None:
        budget = await self.repository.get_budget(flow)
        return LLMBudgetLimitRead.model_validate(budget) if budget else None

    async def monthly_summary(self) -> LLMUsageSummaryRead:
        start, end = _month_window()
        values = await self.repository.monthly_summary(start=start, end=end)
        flows: list[LLMFlowUsageRead] = []
        for value in values:
            flow = str(value["flow"])
            budget = await self.repository.get_budget(flow)
            flows.append(
                LLMFlowUsageRead(
                    **value,
                    monthly_budget_brl=budget.monthly_budget_brl if budget else None,
                )
            )
        return LLMUsageSummaryRead(month=start.strftime("%Y-%m"), flows=flows)
