"""Shared helpers for the turno-2 flow (ADR-0004): a message turn now only
proposes paths -- reaching `ready` needs a `select-option` call and a complete
business profile."""

from httpx import AsyncClient

from app.diagnosis.schemas import DiagnosisExtraction, ProductOptionDraft

_DEFAULT_OPTIONS = [
    ProductOptionDraft(
        title="Caminho enxuto",
        summary="Escopo mínimo para validar rápido.",
        price_range="R$ 8k–15k",
        timeline="4–6 semanas",
        recommended=True,
    ),
    ProductOptionDraft(
        title="Caminho completo",
        summary="Escopo amplo com integrações.",
        price_range="R$ 20k–35k",
        timeline="8–12 semanas",
    ),
]


def ready_extraction(**overrides) -> DiagnosisExtraction:
    """An extraction that, after a turn + select-option, computes to stage
    'ready': it proposes 2 paths and carries business_name/segment/contact."""
    base = dict(
        ready_to_submit=True,
        problem_summary="Cliente precisa de uma solução.",
        solution_kinds=["web-platform"],
        ai_shape="ai_agent",
        surfaces=["surf_web"],
        contact_name="Fulano",
        contact_email="fulano@example.com",
        company_name="Empresa Fulano",
        business_segment="serviços",
        proposed_options=list(_DEFAULT_OPTIONS),
    )
    base.update(overrides)
    return DiagnosisExtraction(**base)


async def drive_to_ready(client: AsyncClient, session_id: str, *, content: str = "oi") -> dict:
    """Send one message turn, then pick the first proposed option. Returns the
    select-option response body (preview.stage should be 'ready')."""
    turn = await client.post(
        f"/diagnosis/sessions/{session_id}/messages", json={"content": content}
    )
    assert turn.status_code == 201, turn.text
    options = turn.json()["preview"]["options"]
    assert len(options) >= 2, turn.json()["preview"]
    chosen = next((o for o in options if o["recommended"]), options[0])
    selected = await client.post(
        f"/diagnosis/sessions/{session_id}/select-option",
        json={"option_key": chosen["key"]},
    )
    assert selected.status_code == 201, selected.text
    return selected.json()
