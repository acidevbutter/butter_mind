from app.core.dependencies import get_llm_provider, require_internal_api_key
from app.diagnosis.schemas import DiagnosisExtraction
from app.main import app
from tests.factories import FakeLLMProvider


async def test_internal_dashboard_aggregates_turn_metrics_and_persists_governance(client):
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(
        reply="ok",
        structured_response=DiagnosisExtraction(
            ready_to_submit=False,
            problem_summary="Precisa de um site",
            services_of_interest=["web"],
        ),
    )
    app.dependency_overrides[require_internal_api_key] = lambda: None

    created = await client.post("/diagnosis/sessions", json={"session_id": "dashboard-1"})
    session_id = created.json()["id"]
    turn = await client.post(
        f"/diagnosis/sessions/{session_id}/messages", json={"content": "Quero um site"}
    )
    assert turn.status_code == 201

    overview = await client.get("/diagnosis/internal/dashboard/overview")
    assert overview.status_code == 200
    assert overview.json()["diagnosis_sessions"] == 1
    assert overview.json()["assistant_turns"] == 1
    assert overview.json()["input_tokens"] == 1
    assert overview.json()["cached_input_tokens"] == 1
    assert overview.json()["output_tokens"] == 1

    updated = await client.patch(
        "/diagnosis/internal/dashboard/settings",
        json={
            "diagnosis_max_output_tokens": 768,
            "diagnosis_max_history_messages": 10,
            "diagnosis_max_turns": 20,
            "diagnosis_grounding_top_k": 4,
            "diagnosis_grounding_min_score": 0.5,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["uses_runtime_override"] is True
    assert updated.json()["diagnosis_max_output_tokens"] == 768

    read_back = await client.get("/diagnosis/internal/dashboard/settings")
    assert read_back.status_code == 200
    assert read_back.json()["diagnosis_grounding_min_score"] == 0.5
