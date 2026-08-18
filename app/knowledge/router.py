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
    description=(
        "Creates a record for a document or content source before any text is ingested "
        "into it. Use this to declare a new source (a page, PDF, or dataset) prior to "
        "uploading its content for embedding, e.g. onboarding a new FAQ page into the "
        "knowledge base. Requires the internal API key."
    ),
)
async def create_source(payload: KnowledgeSourceCreate, service: KnowledgeServiceDep) -> KnowledgeSourceRead:
    source = await service.create_source(payload)
    return KnowledgeSourceRead.model_validate(source)


@router.post(
    "/sources/{source_id}/ingest", response_model=IngestResponse,
    summary="Chunk, embed, and store text for a source (no retrieval yet)",
    description=(
        "Splits the given text into chunks, generates embeddings for each chunk via the "
        "embeddings provider, and persists them against the source. Use this to load or "
        "refresh the content that will later back retrieval-augmented answers, e.g. "
        "indexing an updated help article. Requires the internal API key."
    ),
)
async def ingest(source_id: uuid.UUID, payload: IngestRequest, service: KnowledgeServiceDep) -> IngestResponse:
    chunks = await service.ingest(source_id=source_id, text=payload.text)
    return IngestResponse(chunk_count=len(chunks))
