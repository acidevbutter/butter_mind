import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.settings.config import settings


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_type: Mapped[str]
    uri: Mapped[str | None]
    title: Mapped[str]
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_sources.id"), index=True)
    chunk_index: Mapped[int]
    content: Mapped[str] = mapped_column(Text)
    # Dimension pinned to settings.embeddings_dimension (must match whatever embeddings
    # model core/embeddings/unplugged_provider.py eventually calls) — changing the model
    # later requires a migration + full re-embedding of existing chunks.
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embeddings_dimension))
    token_count: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # No similarity-search index (hnsw/ivfflat) yet — deliberately deferred until
    # retrieval is actually built; add one alongside the first search query.
    __table_args__ = (UniqueConstraint("source_id", "chunk_index"),)
