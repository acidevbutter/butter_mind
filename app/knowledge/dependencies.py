from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.core.dependencies import DbSession, EmbeddingsProviderDep
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.service import KnowledgeIngestionService


def get_knowledge_service(
    db: DbSession, embeddings_provider: EmbeddingsProviderDep
) -> KnowledgeIngestionService:
    return KnowledgeIngestionService(KnowledgeRepository(db), embeddings_provider)


KnowledgeServiceDep = Annotated[KnowledgeIngestionService, Depends(get_knowledge_service)]
