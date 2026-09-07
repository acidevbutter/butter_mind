import uuid

from app.core.decorators import log_errors
from app.core.embeddings.provider import EmbeddingsProvider
from app.core.exceptions import ValidationDomainError
from app.knowledge.models import KnowledgeChunk, KnowledgeSource
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.schemas import KnowledgeSourceCreate
from app.settings.config import settings

# Naive fixed-size chunking, placeholder for future smarter (semantic/markdown-aware)
# chunking once retrieval is actually built.
_CHUNK_SIZE_CHARS = 2000
_CHUNK_OVERLAP_CHARS = 200


def _chunk_text(text: str) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + _CHUNK_SIZE_CHARS
        chunks.append(text[start:end])
        start = end - _CHUNK_OVERLAP_CHARS
    return chunks


@log_errors
class KnowledgeIngestionService:
    def __init__(self, repository: KnowledgeRepository, embeddings_provider: EmbeddingsProvider):
        self.repository = repository
        self.embeddings_provider = embeddings_provider

    async def create_source(self, payload: KnowledgeSourceCreate) -> KnowledgeSource:
        return await self.repository.create_source(payload)

    async def ingest(self, *, source_id: uuid.UUID, text: str) -> list[KnowledgeChunk]:
        if not settings.rag_enabled:
            raise ValidationDomainError(
                "RAG is disabled (RAG_ENABLED=false); embeddings and ingest are unavailable"
            )
        await self.repository.get_source(source_id)
        chunks = _chunk_text(text)
        embeddings = self.embeddings_provider.embed_batch(chunks)
        return await self.repository.bulk_create_chunks(
            source_id=source_id, chunks=chunks, embeddings=embeddings
        )

    async def search(
        self, *, query: str, top_k: int, min_score: float = 0.0
    ) -> list[tuple[KnowledgeChunk, float]]:
        """Retrieval side of the knowledge base -- the "no retrieval yet" gap
        this module used to have (see docs/mapa-chat-widget-metricas-tokens.md
        §1). Skips embedding entirely when RAG is off or the knowledge base is
        empty, so CPU hosts and tests that never ingest never load torch.
        """
        if not settings.rag_enabled:
            return []
        if not await self.repository.has_any_chunks():
            return []
        [query_embedding] = self.embeddings_provider.embed_batch([query])
        results = await self.repository.search_similar(query_embedding=query_embedding, top_k=top_k)
        return [(chunk, score) for chunk, score in results if score >= min_score]
