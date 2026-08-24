"""add cached input token telemetry

Revision ID: f8c0b4e2d951
Revises: e4b28d8d1c71
Create Date: 2026-08-24 02:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f8c0b4e2d951"
down_revision: str | None = "e4b28d8d1c71"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chat_messages", sa.Column("cached_input_tokens", sa.Integer(), nullable=True))
    op.add_column(
        "diagnosis_turn_metrics", sa.Column("cached_input_tokens", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("diagnosis_turn_metrics", "cached_input_tokens")
    op.drop_column("chat_messages", "cached_input_tokens")
