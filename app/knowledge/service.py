from app.core.decorators import log_errors
from app.core.embeddings.provider import EmbeddingsProvider
from app.knowledge.models import KnowledgeChunk, KnowledgeSource
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.schemas import KnowledgeSourceCreate

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

    async def ingest(self, *, source_id, text: str) -> list[KnowledgeChunk]:
        await self.repository.get_source(source_id)
        chunks = _chunk_text(text)
        embeddings = self.embeddings_provider.embed_batch(chunks)
        return await self.repository.bulk_create_chunks(
            source_id=source_id, chunks=chunks, embeddings=embeddings
        )
