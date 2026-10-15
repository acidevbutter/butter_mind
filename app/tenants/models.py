import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Tenant(Base):
    """A client company we've issued relay access to -- the entity that
    api_keys, sender_domains and outbound emails all belong to. DevButter is
    the sole custodian: tenants are created/keys issued only through the
    internal-gated /tenants routes, never self-service."""

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str]
    contact_email: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ApiKey(Base):
    """A hashed credential a tenant's app uses to call the public relay
    routes. Only key_hash (sha256 of the full secret) is stored -- the
    plaintext is returned once, at issuance, and never again. key_prefix is
    the first few characters of the plaintext, kept unhashed so a key can be
    identified in logs/UI without exposing enough of it to be usable."""

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    key_prefix: Mapped[str] = mapped_column(index=True)
    key_hash: Mapped[str] = mapped_column(unique=True, index=True)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
