from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings.local_provider import LocalEmbeddingsProvider
from app.core.embeddings.provider import EmbeddingsProvider
from app.core.exceptions import NotFoundError
from app.core.llm.maritaca_provider import MaritacaProvider
from app.core.llm.provider import LLMProvider
from app.db.session import get_db_session
from app.settings.config import settings

DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def require_internal_api_key(
    x_internal_api_key: Annotated[str | None, Header()] = None,
) -> None:
    """Gate for internal/admin endpoints (e.g. listing leads) — a single shared
    key is enough for v1's small internal audience; not a substitute for real
    auth if this surface grows beyond the DevButter team.
    """
    if not settings.internal_api_key or x_internal_api_key != settings.internal_api_key:
        raise NotFoundError("Not found")


RequireInternalApiKey = Depends(require_internal_api_key)


def get_llm_provider() -> LLMProvider:
    return MaritacaProvider(
        api_key=settings.maritaca_api_key,
        base_url=settings.maritaca_base_url,
        model=settings.maritaca_model,
    )


LLMProviderDep = Annotated[LLMProvider, Depends(get_llm_provider)]

_embeddings_provider = LocalEmbeddingsProvider(
    model_name=settings.embeddings_model_name,
)


def get_embeddings_provider() -> EmbeddingsProvider:
    return _embeddings_provider


EmbeddingsProviderDep = Annotated[EmbeddingsProvider, Depends(get_embeddings_provider)]
