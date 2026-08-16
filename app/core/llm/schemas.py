from typing import Literal

from pydantic import BaseModel


class LLMMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class LLMUsage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMResponse(BaseModel):
    content: str
    model: str
    usage: LLMUsage
