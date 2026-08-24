"""add diagnosis runtime settings

Revision ID: e4b28d8d1c71
Revises: c1a92e5d8b3f
Create Date: 2026-08-24 01:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4b28d8d1c71"
down_revision: str | None = "c1a92e5d8b3f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "diagnosis_runtime_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("diagnosis_max_output_tokens", sa.Integer(), nullable=False),
        sa.Column("diagnosis_max_history_messages", sa.Integer(), nullable=False),
        sa.Column("diagnosis_max_turns", sa.Integer(), nullable=False),
        sa.Column("diagnosis_grounding_top_k", sa.Integer(), nullable=False),
        sa.Column("diagnosis_grounding_min_score", sa.Float(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("diagnosis_runtime_settings")
