import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.knowledge.models import KnowledgeChunk, KnowledgeSource
from app.knowledge.schemas import KnowledgeSourceCreate


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
