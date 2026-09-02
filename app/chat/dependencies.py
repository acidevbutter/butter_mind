from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.chat.repository import ChatRepository
from app.chat.service import ChatService
from app.core.dependencies import DbSession, LLMProviderDep
from app.llm_usage.repository import LLMUsageRepository
from app.llm_usage.service import LLMUsageService


def get_chat_service(db: DbSession, llm_provider: LLMProviderDep) -> ChatService:
    return ChatService(ChatRepository(db), llm_provider, LLMUsageService(LLMUsageRepository(db)))


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
