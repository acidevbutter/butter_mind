"""Structured `next_step` options attached to a qualification turn -- see
devbutter_app/docs/architecture/adr-0001-fluxo-cotacao-opcoes-selecionaveis.md.
"""

from app.core.dependencies import get_llm_provider
from app.diagnosis.schemas import BusinessMetric, DiagnosisExtraction
from app.diagnosis.service import _OPTION_CATALOG, _build_next_step
from app.main import app
from tests.factories import FakeLLMProvider


def test_build_next_step_expands_catalog_for_services():
    step = _build_next_step("services_of_interest", "Que solução?")
    assert step is not None
    assert step.field == "services_of_interest"
    assert step.selection_mode == "multi"
    assert step.allow_free_text is True
    assert [o.id for o in step.options] == [
        oid for oid, _ in _OPTION_CATALOG["services_of_interest"]
    ]


def test_build_next_step_single_for_non_service_fields():
    for field in ("business_type", "problem_area", "budget_range", "timeline"):
        step = _build_next_step(field, None)
        assert step is not None and step.selection_mode == "single"
        # Falls back to a canned prompt when the LLM gave none.
        assert step.prompt


def test_build_next_step_none_for_unknown_or_none_field():
    assert _build_next_step("none", "x") is None
    assert _build_next_step("something_else", "x") is None


def test_build_next_step_truncates_long_prompt():
    step = _build_next_step("timeline", "p" * 500)
    assert step is not None and len(step.prompt) <= 160


async def _run_turn(client, extraction: DiagnosisExtraction) -> dict:
    fake = FakeLLMProvider(reply="ok", structured_response=extraction)
    app.dependency_overrides[get_llm_provider] = lambda: fake
    created = await client.post("/diagnosis/sessions", json={"session_id": "ns-1"})
    session_id = created.json()["id"]
    turn = await client.post(
        f"/diagnosis/sessions/{session_id}/messages",
        json={"content": "tenho uma loja e quero automatizar o whatsapp"},
    )
    assert turn.status_code == 201
    return turn.json()


async def test_turn_carries_next_step_options_while_not_ready(client):
    body = await _run_turn(
        client,
        DiagnosisExtraction(
            ready_to_submit=False,
            problem_summary="Automatizar atendimento no WhatsApp.",
            services_of_interest=[],
            next_step_field="services_of_interest",
            next_step_prompt="Que tipo de solução você imagina?",
        ),
    )
    assert body["ready_to_submit"] is False
    step = body["preview"]["next_step"]
    assert step is not None
    assert step["selection_mode"] == "multi"
    assert len(step["options"]) >= 2
    assert {"id", "label"} <= step["options"][0].keys()


async def test_turn_carries_business_profile_and_progress(client):
    body = await _run_turn(
        client,
        DiagnosisExtraction(
            ready_to_submit=False,
            problem_summary="Automatizar atendimento no WhatsApp.",
            services_of_interest=["Agente de IA"],
            is_legal_entity=True,
            company_name="Loja Flor",
            business_segment="moda / varejo",
            daily_volume="~150 conversas/dia",
            scope_modules=["Agente treinado no catálogo", "Consulta de frete"],
        ),
    )
    bp = body["preview"]["business_profile"]
    assert bp["company_name"] == "Loja Flor"
    assert bp["is_legal_entity"] is True
    assert bp["segment"] == "moda / varejo"
    assert bp["volume"] == "~150 conversas/dia"
    assert bp["contact_ready"] is False
    progress = body["preview"]["progress"]
    # problem + who-they-are + volume + scope answered; budget/timeline still open.
    assert progress == {"answered": 4, "total": 5}


async def test_turn_carries_city_and_business_metrics(client):
    body = await _run_turn(
        client,
        DiagnosisExtraction(
            ready_to_submit=False,
            problem_summary="Automatizar atendimento no WhatsApp.",
            services_of_interest=["Agente de IA"],
            city="Curitiba PR",
            business_metrics=[
                BusinessMetric(label="conversas / dia", value="~150"),
                BusinessMetric(label="atendentes", value="2"),
                BusinessMetric(label="/ dia em repetição", value="~4h", computed=True),
            ],
        ),
    )
    bp = body["preview"]["business_profile"]
    assert bp["city"] == "Curitiba PR"
    assert [m["value"] for m in bp["metrics"]] == ["~150", "2", "~4h"]
    assert [m["label"] for m in bp["metrics"]][0] == "conversas / dia"
    assert bp["metrics"][2]["computed"] is True


async def test_business_metrics_count_toward_progress(client):
    # numbers checkpoint is satisfied by business_metrics even with no
    # daily_volume / pain_points -- problem + numbers => 2 of 5.
    body = await _run_turn(
        client,
        DiagnosisExtraction(
            ready_to_submit=False,
            problem_summary="Automatizar atendimento.",
            services_of_interest=[],
            business_metrics=[BusinessMetric(label="pedidos / mês", value="2 mil")],
        ),
    )
    assert body["preview"]["progress"] == {"answered": 2, "total": 5}


async def test_empty_turn_reports_zero_progress(client):
    body = await _run_turn(
        client,
        DiagnosisExtraction(
            ready_to_submit=False,
            problem_summary="",
            services_of_interest=[],
        ),
    )
    assert body["preview"]["progress"] == {"answered": 0, "total": 5}
    assert body["preview"]["business_profile"]["is_legal_entity"] is None


async def test_ready_turn_has_no_next_step(client):
    from tests.diagnosis._turn2 import drive_to_ready, ready_extraction

    fake = FakeLLMProvider(
        reply="ok",
        structured_response=ready_extraction(
            problem_summary="Site institucional de 5 páginas.",
            services_of_interest=["site institucional"],
            next_step_field="budget_range",  # ignored once choosing/ready
            next_step_prompt="Faixa?",
        ),
    )
    app.dependency_overrides[get_llm_provider] = lambda: fake
    created = await client.post("/diagnosis/sessions", json={"session_id": "ns-ready"})
    selected = await drive_to_ready(client, created.json()["id"])
    assert selected["ready_to_submit"] is True
    assert selected["preview"]["stage"] == "ready"
    assert selected["preview"]["next_step"] is None
