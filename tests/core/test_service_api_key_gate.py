"""Tests for docs/prompts/autenticar-endpoints-diagnostico-chat.md: the public
diagnosis/chat routes must require X-Service-Api-Key. tests/conftest.py
overrides `require_service_api_key` open by default for every other test file
(they exercise flow/domain behavior, not this gate) -- these tests remove
that override to exercise the real dependency end to end.
"""
import json

from app.core.dependencies import get_llm_provider, require_service_api_key
from app.diagnosis.schemas import DiagnosisExtraction
from app.main import app
from app.settings.config import settings
from tests.factories import FakeLLMProvider

HEADER = "X-Service-Api-Key"

# Minimal extraction so the per-turn complete_structured() call in the diagnosis
# flow doesn't blow up -- these tests only exercise the auth gate, not extraction.
# Empty fields keep ready_to_submit False and make an authenticated submit 422.
_EMPTY_EXTRACTION = DiagnosisExtraction(
    ready_to_submit=False,
    problem_summary="",
    solution_kinds=[],
)


def _disable_default_override():
    app.dependency_overrides.pop(require_service_api_key, None)


async def test_diagnosis_create_session_requires_service_api_key(client, monkeypatch):
    monkeypatch.setattr(settings, "service_api_key", "s3cret")
    _disable_default_override()

    without_header = await client.post("/diagnosis/sessions", json={"session_id": "gate-1"})
    assert without_header.status_code == 404

    wrong_header = await client.post(
        "/diagnosis/sessions", json={"session_id": "gate-1"}, headers={HEADER: "wrong"}
    )
    assert wrong_header.status_code == 404

    with_header = await client.post(
        "/diagnosis/sessions", json={"session_id": "gate-1"}, headers={HEADER: "s3cret"}
    )
    assert with_header.status_code == 201


async def test_diagnosis_send_message_and_submit_require_service_api_key(client, monkeypatch):
    monkeypatch.setattr(settings, "service_api_key", "s3cret")
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(
        reply="ok", structured_response=_EMPTY_EXTRACTION
    )

    created = await client.post(
        "/diagnosis/sessions", json={"session_id": "gate-2"}, headers={HEADER: "s3cret"}
    )
    assert created.status_code == 201
    session_id = created.json()["id"]

    _disable_default_override()

    turn_without_header = await client.post(
        f"/diagnosis/sessions/{session_id}/messages", json={"content": "oi"}
    )
    assert turn_without_header.status_code == 404

    turn_with_header = await client.post(
        f"/diagnosis/sessions/{session_id}/messages",
        json={"content": "oi"},
        headers={HEADER: "s3cret"},
    )
    assert turn_with_header.status_code == 201

    submit_without_header = await client.post(f"/diagnosis/sessions/{session_id}/submit")
    assert submit_without_header.status_code == 404

    # No contact info was gathered by the fake LLM, so a correctly authenticated
    # submit still fails validation (422) -- that's proof the gate let it through
    # to the domain logic, not proof the gate is absent.
    submit_with_header = await client.post(
        f"/diagnosis/sessions/{session_id}/submit", headers={HEADER: "s3cret"}
    )
    assert submit_with_header.status_code == 422


async def test_diagnosis_send_message_stream_requires_service_api_key(client, monkeypatch):
    monkeypatch.setattr(settings, "service_api_key", "s3cret")
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(
        stream_deltas=["ok"], structured_response=_EMPTY_EXTRACTION
    )

    created = await client.post(
        "/diagnosis/sessions", json={"session_id": "gate-3"}, headers={HEADER: "s3cret"}
    )
    session_id = created.json()["id"]

    _disable_default_override()

    without_header = await client.post(
        f"/diagnosis/sessions/{session_id}/messages/stream", json={"content": "oi"}
    )
    assert without_header.status_code == 404

    events = []
    async with client.stream(
        "POST",
        f"/diagnosis/sessions/{session_id}/messages/stream",
        json={"content": "oi"},
        headers={HEADER: "s3cret"},
    ) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line.removeprefix("data: ")))
    assert any(e["type"] == "done" for e in events)


async def test_chat_routes_require_service_api_key(client, monkeypatch):
    monkeypatch.setattr(settings, "service_api_key", "s3cret")
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(reply="Oi!")

    created = await client.post(
        "/chat/conversations", json={"session_id": "gate-chat-1"}, headers={HEADER: "s3cret"}
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    _disable_default_override()

    # create_conversation
    assert (await client.post("/chat/conversations", json={"session_id": "gate-chat-2"})).status_code == 404
    assert (
        await client.post(
            "/chat/conversations", json={"session_id": "gate-chat-2"}, headers={HEADER: "s3cret"}
        )
    ).status_code == 201

    # get_conversation
    assert (await client.get(f"/chat/conversations/{conversation_id}")).status_code == 404
    assert (
        await client.get(f"/chat/conversations/{conversation_id}", headers={HEADER: "s3cret"})
    ).status_code == 200

    # list_messages
    assert (await client.get(f"/chat/conversations/{conversation_id}/messages")).status_code == 404
    assert (
        await client.get(
            f"/chat/conversations/{conversation_id}/messages", headers={HEADER: "s3cret"}
        )
    ).status_code == 200

    # send_message
    assert (
        await client.post(
            f"/chat/conversations/{conversation_id}/messages", json={"content": "oi"}
        )
    ).status_code == 404
    assert (
        await client.post(
            f"/chat/conversations/{conversation_id}/messages",
            json={"content": "oi"},
            headers={HEADER: "s3cret"},
        )
    ).status_code == 201

    # generate_text
    assert (
        await client.post("/chat/generate", json={"prompt": "Escreva uma frase."})
    ).status_code == 404
    assert (
        await client.post(
            "/chat/generate", json={"prompt": "Escreva uma frase."}, headers={HEADER: "s3cret"}
        )
    ).status_code == 200


async def test_internal_routes_still_work_without_service_api_key_header(client, monkeypatch):
    """RequireInternalApiKey and RequireServiceApiKey are independent gates --
    an internal-only route must keep working through its own header, unaffected
    by this change, with no X-Service-Api-Key involved at all.
    """
    from app.core.dependencies import require_internal_api_key

    monkeypatch.setattr(settings, "service_api_key", "s3cret")
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(reply="ok")
    app.dependency_overrides[require_internal_api_key] = lambda: None

    created = await client.post(
        "/diagnosis/sessions", json={"session_id": "gate-internal-1"}, headers={HEADER: "s3cret"}
    )
    session_id = created.json()["id"]

    metrics = await client.get(f"/diagnosis/sessions/{session_id}/turn-metrics")
    assert metrics.status_code == 200
