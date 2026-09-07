import json

from app.core.dependencies import get_llm_provider
from app.diagnosis.schemas import DiagnosisExtraction
from app.main import app
from tests.diagnosis._turn2 import drive_to_ready, ready_extraction
from tests.factories import FakeLLMProvider


async def test_guided_flow_and_submit(client):
    fake = FakeLLMProvider(
        reply="Entendi, me conta mais sobre o problema.",
        structured_response=ready_extraction(
            problem_summary="Cliente precisa de um site institucional novo.",
            solution_kinds=["web-platform"],
            budget_ceiling="budget_10_30k",
            rush="time_1_3m",
        ),
    )
    app.dependency_overrides[get_llm_provider] = lambda: fake

    created = await client.post("/diagnosis/sessions", json={"session_id": "abc123"})
    assert created.status_code == 201
    session_id = created.json()["id"]

    selected = await drive_to_ready(client, session_id)
    assert selected["ready_to_submit"] is True
    assert selected["preview"]["stage"] == "ready"

    submitted = await client.post(f"/diagnosis/sessions/{session_id}/submit")
    assert submitted.status_code == 201
    body = submitted.json()
    assert body["problem_summary"] == "Cliente precisa de um site institucional novo."
    assert body["services_of_interest"] == ["web-platform"]
    assert body["selected_option_key"] == selected["preview"]["selected_option_key"]


async def test_submit_pulls_contact_fields_from_the_extraction_itself(client):
    """Contact details are no longer submit() call params -- the LLM is
    expected to have gathered them during the chat (see
    DIAGNOSIS_SYSTEM_PROMPT/EXTRACTION_SYSTEM_PROMPT) and DiagnosisExtraction
    carries them straight into the DiagnosisRequest.
    """
    fake = FakeLLMProvider(
        reply="Perfeito, vou preparar seu diagnostico.",
        structured_response=ready_extraction(
            problem_summary="Cliente precisa de uma plataforma de agendamento.",
            solution_kinds=["platform"],
            contact_name="Visitante Anonimo",
            contact_email="visitante@example.com",
            contact_phone="+5511988887777",
            company_name="Startup Visitante",
            cnpj="98765432000110",
        ),
    )
    app.dependency_overrides[get_llm_provider] = lambda: fake

    created = await client.post("/diagnosis/sessions", json={"session_id": "contact-1"})
    session_id = created.json()["id"]

    await drive_to_ready(client, session_id)

    submitted = await client.post(f"/diagnosis/sessions/{session_id}/submit")
    assert submitted.status_code == 201
    body = submitted.json()
    assert body["contact_name"] == "Visitante Anonimo"
    assert body["contact_email"] == "visitante@example.com"
    assert body["contact_phone"] == "+5511988887777"
    assert body["company_name"] == "Startup Visitante"
    assert body["cnpj"] == "98765432000110"


async def test_send_message_stream_emits_deltas_in_order_then_done(client):
    fake = FakeLLMProvider(
        stream_deltas=["Claro", ", ", "vamos", " conversar."],
        structured_response=DiagnosisExtraction(
            ready_to_submit=True,
            problem_summary="Cliente precisa de um app mobile.",
            solution_kinds=["ai-agents"],
            contact_name="Fulano",
            contact_email="fulano@example.com",
        ),
    )
    app.dependency_overrides[get_llm_provider] = lambda: fake

    created = await client.post("/diagnosis/sessions", json={"session_id": "stream-1"})
    session_id = created.json()["id"]

    events = []
    async with client.stream(
        "POST",
        f"/diagnosis/sessions/{session_id}/messages/stream",
        json={"content": "Preciso de um app mobile."},
    ) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line.removeprefix("data: ")))

    deltas = [e for e in events if e["type"] == "delta"]
    done_events = [e for e in events if e["type"] == "done"]

    assert [d["content"] for d in deltas] == ["Claro", ", ", "vamos", " conversar."]
    assert len(done_events) == 1
    # A bare turn only qualifies -- reaching ready needs a select-option call.
    assert done_events[0]["ready_to_submit"] is False
    assert "message_id" in done_events[0]


async def test_submit_without_conversation_returns_422(client):
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()

    created = await client.post("/diagnosis/sessions", json={"session_id": "abc456"})
    session_id = created.json()["id"]

    response = await client.post(f"/diagnosis/sessions/{session_id}/submit")
    assert response.status_code == 422


async def test_duplicate_submit_returns_409(client):
    fake = FakeLLMProvider(
        reply="ok",
        structured_response=ready_extraction(problem_summary="Resumo."),
    )
    app.dependency_overrides[get_llm_provider] = lambda: fake

    created = await client.post("/diagnosis/sessions", json={"session_id": "abc789"})
    session_id = created.json()["id"]
    await drive_to_ready(client, session_id)

    first = await client.post(f"/diagnosis/sessions/{session_id}/submit")
    assert first.status_code == 201

    second = await client.post(f"/diagnosis/sessions/{session_id}/submit")
    assert second.status_code == 409
