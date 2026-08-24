"""Tests for docs/mapa-chat-widget-metricas-tokens.md §2.2/§2.3: grounding
retrieval, structured per-turn metrics, and fixed token/history/turn budgets
in the diagnosis flow.
"""
import json

from app.core.dependencies import (
    get_embeddings_provider,
    get_llm_provider,
    require_internal_api_key,
)
from app.diagnosis.schemas import DiagnosisExtraction
from app.diagnosis.service import DIAGNOSIS_SYSTEM_PROMPT
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.schemas import KnowledgeSourceCreate
from app.knowledge.service import KnowledgeIngestionService
from app.main import app
from app.settings.config import settings
from tests.factories import FakeEmbeddingsProvider, FakeLLMProvider


async def _ingest_chunk(db_session, text: str) -> None:
    service = KnowledgeIngestionService(KnowledgeRepository(db_session), FakeEmbeddingsProvider())
    source = await service.create_source(KnowledgeSourceCreate(source_type="faq", title="Precos"))
    await service.ingest(source_id=source.id, text=text)


async def test_send_message_grounds_reply_with_retrieved_chunks_and_records_metrics(
    client, db_session
):
    chunk_text = "Site institucional simples custa entre R$ 8.000 e R$ 12.000."
    await _ingest_chunk(db_session, chunk_text)

    fake_llm = FakeLLMProvider(
        reply="Um site institucional fica entre R$ 8.000 e R$ 12.000.",
        structured_response=DiagnosisExtraction(
            ready_to_submit=False,
            problem_summary="Quer um site institucional.",
            services_of_interest=["web-platform"],
        ),
    )
    app.dependency_overrides[get_llm_provider] = lambda: fake_llm
    app.dependency_overrides[get_embeddings_provider] = lambda: FakeEmbeddingsProvider()
    app.dependency_overrides[require_internal_api_key] = lambda: None

    created = await client.post("/diagnosis/sessions", json={"session_id": "grounding-1"})
    session_id = created.json()["id"]

    turn = await client.post(
        f"/diagnosis/sessions/{session_id}/messages", json={"content": chunk_text}
    )
    assert turn.status_code == 201
    assert chunk_text in fake_llm.calls[0]["system"]

    metrics = await client.get(f"/diagnosis/sessions/{session_id}/turn-metrics")
    assert metrics.status_code == 200
    body = metrics.json()
    assert len(body) == 1
    assert body[0]["chunks_used_count"] == 1
    assert body[0]["input_tokens"] == 1
    assert body[0]["cached_input_tokens"] == 1
    assert body[0]["output_tokens"] == 1


async def test_send_message_without_any_knowledge_content_grounds_nothing(client):
    """No knowledge_chunks exist at all -- grounding should no-op (not error,
    not call the embeddings provider) rather than pretend there's context.
    """
    fake_llm = FakeLLMProvider(
        reply="ok",
        structured_response=DiagnosisExtraction(
            ready_to_submit=False, problem_summary="x", services_of_interest=[]
        ),
    )
    app.dependency_overrides[get_llm_provider] = lambda: fake_llm

    created = await client.post("/diagnosis/sessions", json={"session_id": "no-kb-1"})
    session_id = created.json()["id"]

    turn = await client.post(
        f"/diagnosis/sessions/{session_id}/messages", json={"content": "Quanto custa um site?"}
    )
    assert turn.status_code == 201
    assert fake_llm.calls[0]["system"] == DIAGNOSIS_SYSTEM_PROMPT


async def test_send_message_uses_the_fixed_configured_max_tokens(client, monkeypatch):
    monkeypatch.setattr(settings, "diagnosis_max_output_tokens", 111)
    fake_llm = FakeLLMProvider(
        reply="ok",
        structured_response=DiagnosisExtraction(
            ready_to_submit=False, problem_summary="x", services_of_interest=[]
        ),
    )
    app.dependency_overrides[get_llm_provider] = lambda: fake_llm

    created = await client.post("/diagnosis/sessions", json={"session_id": "tokens-1"})
    session_id = created.json()["id"]
    await client.post(f"/diagnosis/sessions/{session_id}/messages", json={"content": "oi"})

    assert fake_llm.calls[0]["max_tokens"] == 111


async def test_send_message_bounds_history_to_the_configured_window(client, monkeypatch):
    monkeypatch.setattr(settings, "diagnosis_max_history_messages", 2)
    fake_llm = FakeLLMProvider(
        reply="ok",
        structured_response=DiagnosisExtraction(
            ready_to_submit=False, problem_summary="x", services_of_interest=[]
        ),
    )
    app.dependency_overrides[get_llm_provider] = lambda: fake_llm

    created = await client.post("/diagnosis/sessions", json={"session_id": "window-1"})
    session_id = created.json()["id"]

    for i in range(3):
        await client.post(
            f"/diagnosis/sessions/{session_id}/messages", json={"content": f"mensagem {i}"}
        )

    # Each turn appends two calls: complete() with the windowed history, then
    # complete_structured() for extraction with that same history plus the
    # reply just generated (see DiagnosisService.send_message) -- so calls[-1]
    # is always one message longer than the window by design. calls[-2] is
    # the actual windowed completion call this assertion means to check.
    assert len(fake_llm.calls[-2]["messages"]) <= 2


async def test_send_message_blocks_once_the_turn_cap_is_reached(client, monkeypatch):
    monkeypatch.setattr(settings, "diagnosis_max_turns", 1)
    fake_llm = FakeLLMProvider(
        reply="ok",
        structured_response=DiagnosisExtraction(
            ready_to_submit=False, problem_summary="x", services_of_interest=[]
        ),
    )
    app.dependency_overrides[get_llm_provider] = lambda: fake_llm

    created = await client.post("/diagnosis/sessions", json={"session_id": "cap-1"})
    session_id = created.json()["id"]

    first = await client.post(
        f"/diagnosis/sessions/{session_id}/messages", json={"content": "primeira"}
    )
    assert first.status_code == 201

    second = await client.post(
        f"/diagnosis/sessions/{session_id}/messages", json={"content": "segunda"}
    )
    assert second.status_code == 422


async def test_stream_message_emits_an_error_event_once_the_turn_cap_is_reached(
    client, monkeypatch
):
    monkeypatch.setattr(settings, "diagnosis_max_turns", 1)
    fake_llm = FakeLLMProvider(
        stream_deltas=["ok"],
        structured_response=DiagnosisExtraction(
            ready_to_submit=False, problem_summary="x", services_of_interest=[]
        ),
    )
    app.dependency_overrides[get_llm_provider] = lambda: fake_llm

    created = await client.post("/diagnosis/sessions", json={"session_id": "cap-stream-1"})
    session_id = created.json()["id"]
    await client.post(f"/diagnosis/sessions/{session_id}/messages", json={"content": "primeira"})

    events = []
    async with client.stream(
        "POST",
        f"/diagnosis/sessions/{session_id}/messages/stream",
        json={"content": "segunda"},
    ) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line.removeprefix("data: ")))

    assert len(events) == 1
    assert events[0]["type"] == "error"


async def test_submit_flags_possibly_ungrounded_when_no_turn_ever_retrieved_a_chunk(client):
    fake_llm = FakeLLMProvider(
        reply="ok",
        structured_response=DiagnosisExtraction(
            ready_to_submit=True,
            problem_summary="Quer um app.",
            services_of_interest=["ai-agents"],
            contact_name="Fulano",
            contact_email="fulano@example.com",
        ),
    )
    app.dependency_overrides[get_llm_provider] = lambda: fake_llm

    created = await client.post("/diagnosis/sessions", json={"session_id": "ungrounded-1"})
    session_id = created.json()["id"]
    await client.post(
        f"/diagnosis/sessions/{session_id}/messages", json={"content": "Quero um app."}
    )

    submitted = await client.post(f"/diagnosis/sessions/{session_id}/submit")
    assert submitted.status_code == 201
    assert submitted.json()["possibly_ungrounded"] is True


async def test_submit_does_not_flag_possibly_ungrounded_when_a_turn_retrieved_a_chunk(
    client, db_session
):
    chunk_text = "Agente de IA para atendimento custa a partir de R$ 5.000."
    await _ingest_chunk(db_session, chunk_text)

    fake_llm = FakeLLMProvider(
        reply="ok",
        structured_response=DiagnosisExtraction(
            ready_to_submit=True,
            problem_summary="Quer um agente de IA.",
            services_of_interest=["ai-agents"],
            contact_name="Fulano",
            contact_email="fulano@example.com",
        ),
    )
    app.dependency_overrides[get_llm_provider] = lambda: fake_llm
    app.dependency_overrides[get_embeddings_provider] = lambda: FakeEmbeddingsProvider()

    created = await client.post("/diagnosis/sessions", json={"session_id": "grounded-1"})
    session_id = created.json()["id"]
    await client.post(f"/diagnosis/sessions/{session_id}/messages", json={"content": chunk_text})

    submitted = await client.post(f"/diagnosis/sessions/{session_id}/submit")
    assert submitted.status_code == 201
    assert submitted.json()["possibly_ungrounded"] is False
