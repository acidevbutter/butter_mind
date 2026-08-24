import math
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.knowledge.models import KnowledgeChunk, KnowledgeSource
from app.knowledge.schemas import KnowledgeSourceCreate


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    # pgvector's Vector type round-trips a stored embedding as a numpy array
    # (not a plain list) -- cast to a native float on the way out so the
    # score is JSON-serializable once it lands in DiagnosisTurnMetrics.
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


class KnowledgeRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_source(self, payload: KnowledgeSourceCreate) -> KnowledgeSource:
        source = KnowledgeSource(**payload.model_dump())
        self.session.add(source)
        await self.session.commit()
        await self.session.refresh(source)
        return source

    async def get_source(self, source_id: uuid.UUID) -> KnowledgeSource:
        source = await self.session.get(KnowledgeSource, source_id)
        if source is None:
            raise NotFoundError(f"Knowledge source {source_id} not found")
        return source

    async def bulk_create_chunks(
        self, *, source_id: uuid.UUID, chunks: list[str], embeddings: list[list[float]]
    ) -> list[KnowledgeChunk]:
        rows = [
            KnowledgeChunk(source_id=source_id, chunk_index=i, content=chunk, embedding=embedding)
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True))
        ]
        self.session.add_all(rows)
        await self.session.commit()
        for row in rows:
            await self.session.refresh(row)
        return rows

    async def has_any_chunks(self) -> bool:
        result = await self.session.execute(select(KnowledgeChunk.id).limit(1))
        return result.first() is not None

    async def search_similar(
        self, *, query_embedding: list[float], top_k: int
    ) -> list[tuple[KnowledgeChunk, float]]:
        """Cosine-similarity search done in Python rather than via pgvector's
        `<->` operator, so this behaves identically against Postgres+pgvector
        in production and the in-memory sqlite database the test suite uses
        (sqlite has no vector operators). Fine at the content volumes the
        knowledge base has today; revisit with a real ANN index (hnsw/ivfflat
        -- the KnowledgeChunk model comment already flags this) if a full
        table scan ever becomes the bottleneck.
        """
        result = await self.session.execute(select(KnowledgeChunk))
        chunks = list(result.scalars().all())
        if not chunks:
            return []
        scored = [
            (chunk, _cosine_similarity(query_embedding, list(chunk.embedding))) for chunk in chunks
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]
