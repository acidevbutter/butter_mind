from collections.abc import AsyncIterator
from typing import Protocol

from pydantic import BaseModel

from app.core.llm.schemas import LLMMessage, LLMResponse


class LLMProvider(Protocol):
    async def complete(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        max_tokens: int = 4096,
    ) -> LLMResponse:
        ...

    def complete_stream(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        ...

    async def complete_structured(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        schema: type[BaseModel],
        max_tokens: int = 4096,
    ) -> BaseModel:
        ...
