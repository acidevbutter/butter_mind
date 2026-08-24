from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm_usage.models import LLMBudgetLimit, LLMUsageEvent


class LLMUsageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_budget(self, flow: str) -> LLMBudgetLimit | None:
        result = await self.session.execute(
            select(LLMBudgetLimit).where(LLMBudgetLimit.flow == flow)
        )
        return result.scalar_one_or_none()

    async def save_budget(self, *, flow: str, monthly_budget_brl: Decimal) -> LLMBudgetLimit:
        budget = await self.get_budget(flow)
        if budget is None:
            budget = LLMBudgetLimit(flow=flow, monthly_budget_brl=monthly_budget_brl)
            self.session.add(budget)
        else:
            budget.monthly_budget_brl = monthly_budget_brl
        await self.session.commit()
        await self.session.refresh(budget)
        return budget

    async def add_event(self, **fields: object) -> LLMUsageEvent:
        event = LLMUsageEvent(**fields)
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(event)
        return event

    async def monthly_cost(self, *, flow: str, start: datetime, end: datetime) -> Decimal:
        result = await self.session.scalar(
            select(func.coalesce(func.sum(LLMUsageEvent.estimated_cost_brl), 0)).where(
                LLMUsageEvent.flow == flow,
                LLMUsageEvent.created_at >= start,
                LLMUsageEvent.created_at < end,
            )
        )
        return Decimal(result or 0)

    async def monthly_summary(self, *, start: datetime, end: datetime) -> list[dict[str, object]]:
        result = await self.session.execute(
            select(
                LLMUsageEvent.flow,
                func.coalesce(func.sum(LLMUsageEvent.input_tokens), 0),
                func.coalesce(func.sum(LLMUsageEvent.cached_input_tokens), 0),
                func.coalesce(func.sum(LLMUsageEvent.output_tokens), 0),
                func.coalesce(func.sum(LLMUsageEvent.estimated_cost_brl), 0),
            )
            .where(LLMUsageEvent.created_at >= start, LLMUsageEvent.created_at < end)
            .group_by(LLMUsageEvent.flow)
            .order_by(LLMUsageEvent.flow)
        )
        return [
            {
                "flow": row[0],
                "input_tokens": int(row[1]),
                "cached_input_tokens": int(row[2]),
                "output_tokens": int(row[3]),
                "estimated_cost_brl": Decimal(row[4]),
            }
            for row in result.all()
        ]
