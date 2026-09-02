"""Turno-2 flow (ADR-0004): stage machine, product options, select-option,
business-profile patch."""

from app.core.dependencies import get_llm_provider
from app.diagnosis.schemas import ProductOptionDraft
from app.diagnosis.service import _sanitize_options, _slugify
from app.main import app
from tests.diagnosis._turn2 import drive_to_ready, ready_extraction
from tests.factories import FakeLLMProvider


def test_sanitize_options_keys_dedupes_and_forces_one_recommended():
    out = _sanitize_options(
        [
            ProductOptionDraft(title="Caminho A", summary="a", recommended=True),
            ProductOptionDraft(title="Caminho A", summary="dup"),  # same key -> dropped
            ProductOptionDraft(title="Caminho B", summary="b", recommended=True),
            ProductOptionDraft(title="Caminho C", summary="c"),
        ]
    )
    assert [o.key for o in out] == ["opt_caminho_a", "opt_caminho_b", "opt_caminho_c"]
    assert [o.recommended for o in out] == [True, False, False]


def test_sanitize_options_drops_a_lone_option():
    assert _sanitize_options([ProductOptionDraft(title="Só um", summary="x")]) == []


async def _new_session(client, sid: str) -> str:
    created = await client.post("/diagnosis/sessions", json={"session_id": sid})
    return created.json()["id"]


async def test_turn_proposes_options_and_sets_choosing_stage(client):
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(
        reply="ok", structured_response=ready_extraction()
    )
    session_id = await _new_session(client, "t2-choosing")
    turn = await client.post(
        f"/diagnosis/sessions/{session_id}/messages", json={"content": "oi"}
    )
    preview = turn.json()["preview"]
    assert turn.json()["ready_to_submit"] is False
    assert preview["stage"] == "choosing"
    assert len(preview["options"]) == 2
    assert preview["options"][0]["key"] == _slugify(preview["options"][0]["title"])
    assert preview["selected_option_key"] is None


async def test_select_unknown_option_returns_409(client):
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(
        reply="ok", structured_response=ready_extraction()
    )
    session_id = await _new_session(client, "t2-409")
    await client.post(f"/diagnosis/sessions/{session_id}/messages", json={"content": "oi"})
    bad = await client.post(
        f"/diagnosis/sessions/{session_id}/select-option",
        json={"option_key": "opt_does_not_exist"},
    )
    assert bad.status_code == 409


async def test_select_option_advances_to_ready_when_profile_complete(client):
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(
        reply="ok", structured_response=ready_extraction()
    )
    session_id = await _new_session(client, "t2-ready")
    selected = await drive_to_ready(client, session_id)
    assert selected["ready_to_submit"] is True
    assert selected["preview"]["stage"] == "ready"
    assert selected["preview"]["selected_option_key"] is not None
    # once chosen, the preview shows the single chosen option
    assert len(selected["preview"]["options"]) == 1


async def test_collecting_stage_when_profile_incomplete_then_patch_to_ready(client):
    # No company/segment/contact -> after choosing, stage stays "collecting".
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(
        reply="ok",
        structured_response=ready_extraction(
            company_name=None, business_segment=None, contact_name=None
        ),
    )
    session_id = await _new_session(client, "t2-collecting")
    turn = await client.post(
        f"/diagnosis/sessions/{session_id}/messages", json={"content": "oi"}
    )
    key = turn.json()["preview"]["options"][0]["key"]
    selected = await client.post(
        f"/diagnosis/sessions/{session_id}/select-option", json={"option_key": key}
    )
    assert selected.json()["preview"]["stage"] == "collecting"
    assert set(selected.json()["preview"]["missing_fields"]) == {
        "business_name",
        "segment",
        "contact_name",
    }

    patched = await client.patch(
        f"/diagnosis/sessions/{session_id}/business-profile",
        json={
            "business_name": "Loja Flor",
            "segment": "moda / varejo",
            "contact_name": "Ana",
        },
    )
    assert patched.status_code == 200
    assert patched.json()["preview"]["stage"] == "ready"
    assert patched.json()["preview"]["missing_fields"] == []
    assert patched.json()["preview"]["business_profile"]["company_name"] == "Loja Flor"


async def test_submit_carries_selected_option_and_profile(client):
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(
        reply="ok", structured_response=ready_extraction()
    )
    session_id = await _new_session(client, "t2-submit")
    selected = await drive_to_ready(client, session_id)
    chosen_key = selected["preview"]["selected_option_key"]

    submitted = await client.post(f"/diagnosis/sessions/{session_id}/submit")
    assert submitted.status_code == 201
    body = submitted.json()
    assert body["selected_option_key"] == chosen_key
    assert body["business_profile"]["segment"] == "serviços"
    # price/timeline come from the chosen option (free-text ranges).
    assert body["budget_range"] == "R$ 8k–15k"
    assert body["timeline"] == "4–6 semanas"
