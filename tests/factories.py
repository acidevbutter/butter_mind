from collections.abc import AsyncIterator

from pydantic import BaseModel

from app.core.llm.provider import LLMProvider
from app.core.llm.schemas import LLMMessage, LLMResponse, LLMUsage


class FakeLLMProvider(LLMProvider):
    """In-memory stand-in for MaritacaProvider — avoids real API calls in tests."""

    def __init__(
        self,
        *,
        reply: str = "ok",
        structured_response: BaseModel | None = None,
        stream_deltas: list[str] | None = None,
    ):
        self.reply = reply
        self.structured_response = structured_response
        self.stream_deltas = stream_deltas if stream_deltas is not None else ["ok"]
        self.calls: list[list[LLMMessage]] = []

    async def complete(self, *, system: str, messages: list[LLMMessage], max_tokens: int = 4096) -> LLMResponse:
        self.calls.append(messages)
        return LLMResponse(content=self.reply, model="fake-model", usage=LLMUsage(input_tokens=1, output_tokens=1))

    async def complete_stream(
        self, *, system: str, messages: list[LLMMessage], max_tokens: int = 4096
    ) -> AsyncIterator[str]:
        self.calls.append(messages)
        for delta in self.stream_deltas:
            yield delta

    async def complete_structured(
        self, *, system: str, messages: list[LLMMessage], schema: type[BaseModel], max_tokens: int = 4096
    ) -> BaseModel:
        if self.structured_response is not None:
            return self.structured_response
        raise NotImplementedError("Set structured_response on FakeLLMProvider before calling this")
