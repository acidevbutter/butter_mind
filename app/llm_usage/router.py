from fastapi import APIRouter

from app.core.dependencies import RequireInternalApiKey
from app.llm_usage.dependencies import LLMUsageServiceDep
from app.llm_usage.schemas import LLMBudgetLimitRead, LLMBudgetLimitUpdate, LLMUsageSummaryRead

router = APIRouter(
    prefix="/llm-usage/internal", tags=["llm-usage"], dependencies=[RequireInternalApiKey]
)


@router.get("/summary", response_model=LLMUsageSummaryRead, summary="Get monthly LLM usage by flow")
async def monthly_summary(service: LLMUsageServiceDep) -> LLMUsageSummaryRead:
    return await service.monthly_summary()


@router.get(
    "/budgets/{flow}", response_model=LLMBudgetLimitRead | None, summary="Get a flow budget"
)
async def get_budget(flow: str, service: LLMUsageServiceDep) -> LLMBudgetLimitRead | None:
    return await service.get_budget(flow=flow)


@router.put(
    "/budgets/{flow}", response_model=LLMBudgetLimitRead, summary="Set a monthly flow budget"
)
async def save_budget(
    flow: str, payload: LLMBudgetLimitUpdate, service: LLMUsageServiceDep
) -> LLMBudgetLimitRead:
    return await service.save_budget(flow=flow, payload=payload)
