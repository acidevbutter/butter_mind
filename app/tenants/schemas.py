import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TenantCreate(BaseModel):
    name: str
    contact_email: str


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    contact_email: str
    created_at: datetime


class ApiKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    key_prefix: str
    active: bool
    created_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None


class ApiKeyIssuedRead(ApiKeyRead):
    """Returned only from the issuance call itself -- the plaintext key is
    never persisted and can't be retrieved again after this response."""

    api_key: str


class TenantWithApiKeyRead(BaseModel):
    tenant: TenantRead
    api_key: ApiKeyIssuedRead
