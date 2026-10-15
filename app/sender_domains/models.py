import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SenderDomain(Base):
    """A domain a tenant has registered to send email from. `dns_records`
    snapshots what the email provider asked for (and, after a verify call,
    the per-record status) -- shown back to the tenant so they know exactly
    what to add at their registrar. `domain` is globally unique: once one
    tenant owns and verifies a domain, another tenant can't also claim it.
    """

    __tablename__ = "sender_domains"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    domain: Mapped[str] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(default="pending")
    provider_domain_id: Mapped[str | None] = mapped_column(default=None)
    dns_records: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (UniqueConstraint("domain"),)
