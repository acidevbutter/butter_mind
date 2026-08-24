"""add LLM usage events and monthly budgets

Revision ID: b7e8f9d0a2c4
Revises: f8c0b4e2d951
Create Date: 2026-08-24 03:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e8f9d0a2c4"
down_revision: str | None = "f8c0b4e2d951"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_usage_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("flow", sa.String(), nullable=False),
        sa.Column("operation", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_brl", sa.Numeric(14, 6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_llm_usage_events_flow"), "llm_usage_events", ["flow"])
    op.create_table(
        "llm_budget_limits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("flow", sa.String(), nullable=False),
        sa.Column("monthly_budget_brl", sa.Numeric(14, 2), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("flow"),
    )


def downgrade() -> None:
    op.drop_table("llm_budget_limits")
    op.drop_index(op.f("ix_llm_usage_events_flow"), table_name="llm_usage_events")
    op.drop_table("llm_usage_events")
