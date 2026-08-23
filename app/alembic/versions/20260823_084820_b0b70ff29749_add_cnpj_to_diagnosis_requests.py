"""add cnpj to diagnosis_requests

Revision ID: b0b70ff29749
Revises: fa3693a4f9df
Create Date: 2026-08-23 08:48:20.000000

DiagnosisExtraction now asks the LLM to also capture cnpj (alongside the
existing contact_name/contact_email/contact_phone/company_name) from the
conversation itself, per devbutter_backend's
docs/plano-onboarding-conversa-primeiro.md, so devbutter_backend can create
a visitor's Company without a separate signup form.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b0b70ff29749'
down_revision: str | None = 'fa3693a4f9df'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('diagnosis_requests', sa.Column('cnpj', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('diagnosis_requests', 'cnpj')
