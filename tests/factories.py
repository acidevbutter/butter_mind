import hashlib
from collections.abc import AsyncIterator

from pydantic import BaseModel

from app.core.embeddings.provider import EmbeddingsProvider
from app.core.llm.provider import LLMProvider
from app.core.llm.schemas import (
    LLMMessage,
    LLMResponse,
    LLMStreamEvent,
    LLMStructuredResponse,
    LLMUsage,
)
from app.settings.config import settings


class FakeLLMProvider(LLMProvider):
    """In-memory stand-in for MaritacaProvider — avoids real API calls in tests.

    `calls` records one dict per invocation ({"system", "messages", "max_tokens"})
    so tests can assert on the grounded system prompt and the fixed token
    budget actually passed through, not just the message list.
    """

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
        self.calls: list[dict] = []

    async def complete(
        self, *, system: str, messages: list[LLMMessage], max_tokens: int = 4096
    ) -> LLMResponse:
        self.calls.append({"system": system, "messages": messages, "max_tokens": max_tokens})
        return LLMResponse(
            content=self.reply,
            model="sabia-4",
            usage=LLMUsage(input_tokens=1, cached_input_tokens=1, output_tokens=1),
        )

    async def complete_stream(
        self, *, system: str, messages: list[LLMMessage], max_tokens: int = 4096
    ) -> AsyncIterator[LLMStreamEvent]:
        self.calls.append({"system": system, "messages": messages, "max_tokens": max_tokens})
        for delta in self.stream_deltas:
            yield LLMStreamEvent(type="delta", content=delta)
        yield LLMStreamEvent(
            type="completed",
            response=LLMResponse(
                content="".join(self.stream_deltas),
                model="sabia-4",
                usage=LLMUsage(input_tokens=1, cached_input_tokens=1, output_tokens=1),
            ),
        )

    async def complete_structured(
        self,
        *,
        system: str,
        messages: list[LLMMessage],
        schema: type[BaseModel],
        max_tokens: int = 4096,
    ) -> LLMStructuredResponse:
        self.calls.append({"system": system, "messages": messages, "max_tokens": max_tokens})
        if self.structured_response is not None:
            return LLMStructuredResponse(
                data=self.structured_response,
                response=LLMResponse(
                    content=self.structured_response.model_dump_json(),
                    model="sabia-4",
                    usage=LLMUsage(input_tokens=1, cached_input_tokens=1, output_tokens=1),
                ),
            )
        raise NotImplementedError("Set structured_response on FakeLLMProvider before calling this")


class FakeEmbeddingsProvider(EmbeddingsProvider):
    """In-memory stand-in for LocalEmbeddingsProvider — avoids loading a real
    sentence-transformers model in tests. Deterministic per input text (same
    text always yields the same vector, via a hash, not a real semantic
    model), which is enough to exercise similarity ranking: identical text
    always scores a cosine similarity of 1.0 against itself.

    Defaults to settings.embeddings_dimension so vectors round-trip through
    KnowledgeChunk.embedding (a pgvector Vector(768) column, which rejects
    any other length -- even under sqlite, since pgvector validates
    dimension in its own bind processor, not via a DB-side constraint).
    Uses shake_256 rather than sha256 because sha256's digest is a fixed 32
    bytes -- slicing it for a dimension above 32 would silently return a
    short vector instead of the requested length.
    """

    def __init__(self, *, dimension: int = settings.embeddings_dimension):
        self.dimension = dimension

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        digest = hashlib.shake_256(text.encode("utf-8")).digest(self.dimension)
        return [b / 255 for b in digest]
