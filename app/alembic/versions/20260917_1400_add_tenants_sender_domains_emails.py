"""add tenants, api_keys, sender_domains, email_logs (public email relay)

Revision ID: a3f7c2e91b04
Revises: c9a1d3e5b7f2
Create Date: 2026-09-17 14:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3f7c2e91b04"
down_revision: str | None = "c9a1d3e5b7f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("contact_email", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("key_prefix", sa.String(), nullable=False),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_index(op.f("ix_api_keys_tenant_id"), "api_keys", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_api_keys_key_prefix"), "api_keys", ["key_prefix"], unique=False)
    op.create_index(op.f("ix_api_keys_key_hash"), "api_keys", ["key_hash"], unique=False)

    op.create_table(
        "sender_domains",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("provider_domain_id", sa.String(), nullable=True),
        sa.Column("dns_records", sa.JSON(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("domain"),
    )
    op.create_index(
        op.f("ix_sender_domains_tenant_id"), "sender_domains", ["tenant_id"], unique=False
    )
    op.create_index(op.f("ix_sender_domains_domain"), "sender_domains", ["domain"], unique=False)

    op.create_table(
        "email_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("sender_domain_id", sa.Uuid(), nullable=False),
        sa.Column("from_email", sa.String(), nullable=False),
        sa.Column("to_addresses", sa.JSON(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("provider_message_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["sender_domain_id"], ["sender_domains.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_email_logs_tenant_id"), "email_logs", ["tenant_id"], unique=False)
    op.create_index(
        op.f("ix_email_logs_sender_domain_id"), "email_logs", ["sender_domain_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_email_logs_sender_domain_id"), table_name="email_logs")
    op.drop_index(op.f("ix_email_logs_tenant_id"), table_name="email_logs")
    op.drop_table("email_logs")

    op.drop_index(op.f("ix_sender_domains_domain"), table_name="sender_domains")
    op.drop_index(op.f("ix_sender_domains_tenant_id"), table_name="sender_domains")
    op.drop_table("sender_domains")

    op.drop_index(op.f("ix_api_keys_key_hash"), table_name="api_keys")
    op.drop_index(op.f("ix_api_keys_key_prefix"), table_name="api_keys")
    op.drop_index(op.f("ix_api_keys_tenant_id"), table_name="api_keys")
    op.drop_table("api_keys")

    op.drop_table("tenants")
