import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.email.schemas import EmailAddress


class EmailSendRequest(BaseModel):
    from_email: str
    from_name: str | None = None
    to: list[EmailAddress] = Field(min_length=1)
    subject: str
    html_content: str | None = None
    text_content: str | None = None
    reply_to: EmailAddress | None = None

    @model_validator(mode="after")
    def require_some_content(self) -> "EmailSendRequest":
        if not self.html_content and not self.text_content:
            raise ValueError("Provide html_content and/or text_content")
        return self


class EmailSendRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_message_id: str | None
    status: str
    created_at: datetime
