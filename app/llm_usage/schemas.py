from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class LLMBudgetLimitUpdate(BaseModel):
    monthly_budget_brl: Decimal = Field(gt=0, max_digits=14, decimal_places=2)


class LLMBudgetLimitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    flow: str
    monthly_budget_brl: Decimal
    updated_at: datetime


class LLMFlowUsageRead(BaseModel):
    flow: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    estimated_cost_brl: Decimal
    monthly_budget_brl: Decimal | None


class LLMUsageSummaryRead(BaseModel):
    month: str
    flows: list[LLMFlowUsageRead]
