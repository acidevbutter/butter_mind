import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EmailLog(Base):
    """One row per send attempt -- audit trail for a tenant's usage and the
    basis for any future per-tenant billing/quota. `sender_domain_id` ties
    the send back to the verified domain it was allowed to use."""

    __tablename__ = "email_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    sender_domain_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sender_domains.id"), index=True
    )
    from_email: Mapped[str]
    to_addresses: Mapped[list[str]] = mapped_column(JSON, default=list)
    subject: Mapped[str] = mapped_column(Text)
    provider_message_id: Mapped[str | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(default="sent")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
