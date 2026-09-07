import sys

from app.core.dependencies import get_embeddings_provider
from app.core.embeddings.disabled_provider import DisabledEmbeddingsProvider
from app.settings.config import settings


def test_embeddings_provider_is_disabled_without_importing_sentence_transformers(monkeypatch):
    monkeypatch.setattr(settings, "rag_enabled", False)
    sys.modules.pop("sentence_transformers", None)
    sys.modules.pop("app.core.embeddings.local_provider", None)

    provider = get_embeddings_provider()

    assert isinstance(provider, DisabledEmbeddingsProvider)
    assert "sentence_transformers" not in sys.modules
