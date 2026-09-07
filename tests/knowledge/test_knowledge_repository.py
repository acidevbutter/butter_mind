import pytest

from app.core.exceptions import ValidationDomainError
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.schemas import KnowledgeSourceCreate
from app.knowledge.service import KnowledgeIngestionService
from app.settings.config import settings
from tests.factories import FakeEmbeddingsProvider


async def test_search_similar_ranks_the_matching_chunk_first(db_session, monkeypatch):
    monkeypatch.setattr(settings, "rag_enabled", True)
    repository = KnowledgeRepository(db_session)
    service = KnowledgeIngestionService(repository, FakeEmbeddingsProvider())

    source_a = await service.create_source(KnowledgeSourceCreate(source_type="faq", title="A"))
    source_b = await service.create_source(KnowledgeSourceCreate(source_type="faq", title="B"))
    await service.ingest(source_id=source_a.id, text="Fazemos plataformas web sob medida.")
    await service.ingest(
        source_id=source_b.id, text="Automatizamos processos internos com agentes de IA."
    )

    results = await service.search(
        query="Automatizamos processos internos com agentes de IA.", top_k=1
    )

    assert len(results) == 1
    chunk, score = results[0]
    assert chunk.content == "Automatizamos processos internos com agentes de IA."
    assert score == pytest.approx(1.0)


async def test_search_returns_empty_when_the_knowledge_base_is_empty(db_session, monkeypatch):
    monkeypatch.setattr(settings, "rag_enabled", True)
    repository = KnowledgeRepository(db_session)
    service = KnowledgeIngestionService(repository, FakeEmbeddingsProvider())

    results = await service.search(query="qualquer coisa", top_k=3)

    assert results == []


async def test_search_returns_empty_when_rag_is_disabled(db_session, monkeypatch):
    monkeypatch.setattr(settings, "rag_enabled", False)
    repository = KnowledgeRepository(db_session)
    service = KnowledgeIngestionService(repository, FakeEmbeddingsProvider())

    results = await service.search(query="qualquer coisa", top_k=3)

    assert results == []


async def test_ingest_rejects_when_rag_is_disabled(db_session, monkeypatch):
    monkeypatch.setattr(settings, "rag_enabled", False)
    repository = KnowledgeRepository(db_session)
    service = KnowledgeIngestionService(repository, FakeEmbeddingsProvider())
    source = await service.create_source(KnowledgeSourceCreate(source_type="faq", title="A"))

    with pytest.raises(ValidationDomainError, match="RAG is disabled"):
        await service.ingest(source_id=source.id, text="conteudo")
