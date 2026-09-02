"""add diagnosis stage / product options / business profile (ADR-0004)

Revision ID: c9a1d3e5b7f2
Revises: b7e8f9d0a2c4
Create Date: 2026-09-02 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9a1d3e5b7f2"
down_revision: str | None = "b7e8f9d0a2c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "diagnosis_sessions",
        sa.Column("stage", sa.String(), nullable=False, server_default="qualifying"),
    )
    op.add_column(
        "diagnosis_sessions",
        sa.Column(
            "business_profile", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
        ),
    )
    op.add_column(
        "diagnosis_sessions",
        sa.Column("selected_option_key", sa.String(), nullable=True),
    )
    op.add_column(
        "diagnosis_sessions",
        sa.Column(
            "options_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
        ),
    )
    op.add_column(
        "diagnosis_requests",
        sa.Column("selected_option_key", sa.String(), nullable=True),
    )
    op.add_column(
        "diagnosis_requests",
        sa.Column(
            "business_profile", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
        ),
    )


def downgrade() -> None:
    op.drop_column("diagnosis_requests", "business_profile")
    op.drop_column("diagnosis_requests", "selected_option_key")
    op.drop_column("diagnosis_sessions", "options_snapshot")
    op.drop_column("diagnosis_sessions", "selected_option_key")
    op.drop_column("diagnosis_sessions", "business_profile")
    op.drop_column("diagnosis_sessions", "stage")
