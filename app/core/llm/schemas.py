from typing import Literal

from pydantic import BaseModel


class LLMMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class LLMUsage(BaseModel):
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None


class LLMResponse(BaseModel):
    content: str
    model: str
    usage: LLMUsage


class LLMStreamEvent(BaseModel):
    """A text fragment or the final usage report from a streamed response."""

    type: Literal["delta", "completed"]
    content: str = ""
    response: LLMResponse | None = None
