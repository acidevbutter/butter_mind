import pytest

from app.core.dependencies import get_embeddings_provider
from app.core.embeddings.disabled_provider import DisabledEmbeddingsProvider
from app.core.embeddings.unplugged_provider import UnpluggedEmbeddingsProvider
from app.settings.config import settings


def test_embeddings_provider_is_disabled_when_rag_disabled(monkeypatch):
    monkeypatch.setattr(settings, "rag_enabled", False)

    provider = get_embeddings_provider()

    assert isinstance(provider, DisabledEmbeddingsProvider)


def test_embeddings_provider_is_unplugged_when_rag_enabled(monkeypatch):
    monkeypatch.setattr(settings, "rag_enabled", True)

    provider = get_embeddings_provider()

    assert isinstance(provider, UnpluggedEmbeddingsProvider)
    with pytest.raises(NotImplementedError):
        provider.embed_batch(["hello"])
