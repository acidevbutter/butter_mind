import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class KnowledgeSourceCreate(BaseModel):
    source_type: str
    uri: str | None = None
    title: str
    source_metadata: dict[str, str] = {}


class KnowledgeSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_type: str
    uri: str | None
    title: str
    created_at: datetime


class IngestRequest(BaseModel):
    text: str


class IngestResponse(BaseModel):
    chunk_count: int
