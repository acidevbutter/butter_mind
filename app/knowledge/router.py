import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.dependencies import DbSession, EmbeddingsProviderDep, RequireInternalApiKey
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.schemas import (
    IngestRequest,
    IngestResponse,
    KnowledgeSourceCreate,
    KnowledgeSourceRead,
)
from app.knowledge.service import KnowledgeIngestionService

router = APIRouter(prefix="/knowledge", tags=["knowledge"], dependencies=[RequireInternalApiKey])


def get_knowledge_service(db: DbSession, embeddings_provider: EmbeddingsProviderDep) -> KnowledgeIngestionService:
    return KnowledgeIngestionService(KnowledgeRepository(db), embeddings_provider)


KnowledgeServiceDep = Annotated[KnowledgeIngestionService, Depends(get_knowledge_service)]


@router.post(
    "/sources", response_model=KnowledgeSourceRead,
    status_code=status.HTTP_201_CREATED, summary="Register a knowledge source",
)
async def create_source(payload: KnowledgeSourceCreate, service: KnowledgeServiceDep) -> KnowledgeSourceRead:
    source = await service.create_source(payload)
    return KnowledgeSourceRead.model_validate(source)


@router.post(
    "/sources/{source_id}/ingest", response_model=IngestResponse,
    summary="Chunk, embed, and store text for a source (no retrieval yet)",
)
async def ingest(source_id: uuid.UUID, payload: IngestRequest, service: KnowledgeServiceDep) -> IngestResponse:
    chunks = await service.ingest(source_id=source_id, text=payload.text)
    return IngestResponse(chunk_count=len(chunks))
