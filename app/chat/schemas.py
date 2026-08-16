import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChatMessageCreate(BaseModel):
    content: str


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    created_at: datetime


class ChatConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: str
    channel: str
    created_at: datetime


class ChatConversationCreate(BaseModel):
    session_id: str
    channel: str = "general_chat"


class GenerateTextRequest(BaseModel):
    prompt: str
    context: dict[str, str] = {}
    max_tokens: int = 1024


class GenerateTextResponse(BaseModel):
    text: str
