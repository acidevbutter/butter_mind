import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SenderDomainCreate(BaseModel):
    domain: str


class DnsRecordRead(BaseModel):
    record_type: str
    host_name: str
    value: str
    verified: bool


class SenderDomainRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    domain: str
    status: str
    dns_records: list[DnsRecordRead]
    verified_at: datetime | None
    created_at: datetime
