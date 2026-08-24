import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LLMUsageEvent(Base):
    __tablename__ = "llm_usage_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    flow: Mapped[str] = mapped_column(index=True)
    operation: Mapped[str]
    model: Mapped[str]
    input_tokens: Mapped[int | None]
    cached_input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    estimated_cost_brl: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LLMBudgetLimit(Base):
    __tablename__ = "llm_budget_limits"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    flow: Mapped[str] = mapped_column(unique=True)
    monthly_budget_brl: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (UniqueConstraint("flow"),)
