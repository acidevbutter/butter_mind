from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.core.dependencies import DbSession, EmbeddingsProviderDep, LLMProviderDep
from app.diagnosis.repository import DiagnosisRepository
from app.diagnosis.service import DiagnosisService
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.service import KnowledgeIngestionService
from app.llm_usage.repository import LLMUsageRepository
from app.llm_usage.service import LLMUsageService


def get_diagnosis_service(
    db: DbSession, llm_provider: LLMProviderDep, embeddings_provider: EmbeddingsProviderDep
) -> DiagnosisService:
    knowledge_service = KnowledgeIngestionService(KnowledgeRepository(db), embeddings_provider)
    return DiagnosisService(
        DiagnosisRepository(db),
        llm_provider,
        knowledge_service,
        LLMUsageService(LLMUsageRepository(db)),
    )


DiagnosisServiceDep = Annotated[DiagnosisService, Depends(get_diagnosis_service)]
