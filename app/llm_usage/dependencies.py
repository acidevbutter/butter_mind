from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.core.dependencies import DbSession
from app.llm_usage.repository import LLMUsageRepository
from app.llm_usage.service import LLMUsageService


def get_llm_usage_service(db: DbSession) -> LLMUsageService:
    return LLMUsageService(LLMUsageRepository(db))


LLMUsageServiceDep = Annotated[LLMUsageService, Depends(get_llm_usage_service)]
