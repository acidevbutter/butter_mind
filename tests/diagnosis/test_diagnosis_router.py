from app.core.dependencies import get_llm_provider
from app.diagnosis.schemas import DiagnosisExtraction
from app.main import app
from tests.factories import FakeLLMProvider


async def test_guided_flow_and_submit(client):
    fake = FakeLLMProvider(
        reply="Entendi, me conta mais sobre o problema.",
        structured_response=DiagnosisExtraction(
            ready_to_submit=True,
            problem_summary="Cliente precisa de um site institucional novo.",
            services_of_interest=["web-platform"],
            budget_range="10-20k",
            timeline="2 meses",
        ),
    )
    app.dependency_overrides[get_llm_provider] = lambda: fake

    created = await client.post("/diagnosis/sessions", json={"session_id": "abc123"})
    assert created.status_code == 201
    session_id = created.json()["id"]

    turn = await client.post(
        f"/diagnosis/sessions/{session_id}/messages",
        json={"content": "Preciso de um site novo para minha empresa."},
    )
    assert turn.status_code == 201
    assert turn.json()["ready_to_submit"] is True

    submitted = await client.post(f"/diagnosis/sessions/{session_id}/submit")
    assert submitted.status_code == 201
    body = submitted.json()
    assert body["problem_summary"] == "Cliente precisa de um site institucional novo."
    assert body["services_of_interest"] == ["web-platform"]


async def test_submit_without_conversation_returns_422(client):
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider()

    created = await client.post("/diagnosis/sessions", json={"session_id": "abc456"})
    session_id = created.json()["id"]

    response = await client.post(f"/diagnosis/sessions/{session_id}/submit")
    assert response.status_code == 422


async def test_duplicate_submit_returns_409(client):
    fake = FakeLLMProvider(
        reply="ok",
        structured_response=DiagnosisExtraction(
            ready_to_submit=True,
            problem_summary="Resumo.",
            services_of_interest=["ai-agents"],
        ),
    )
    app.dependency_overrides[get_llm_provider] = lambda: fake

    created = await client.post("/diagnosis/sessions", json={"session_id": "abc789"})
    session_id = created.json()["id"]
    await client.post(f"/diagnosis/sessions/{session_id}/messages", json={"content": "Preciso de ajuda."})

    first = await client.post(f"/diagnosis/sessions/{session_id}/submit")
    assert first.status_code == 201

    second = await client.post(f"/diagnosis/sessions/{session_id}/submit")
    assert second.status_code == 409
