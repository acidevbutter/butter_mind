from app.core.dependencies import get_llm_provider, require_internal_api_key
from app.main import app
from tests.factories import FakeLLMProvider


async def test_internal_budget_blocks_a_call_before_it_reaches_maritaca(client):
    fake_llm = FakeLLMProvider(reply="Texto")
    app.dependency_overrides[get_llm_provider] = lambda: fake_llm
    app.dependency_overrides[require_internal_api_key] = lambda: None

    saved = await client.put(
        "/llm-usage/internal/budgets/site_text_generation", json={"monthly_budget_brl": "0.01"}
    )
    assert saved.status_code == 200

    response = await client.post(
        "/chat/generate", json={"prompt": "Escreva uma frase.", "max_tokens": 5000}
    )
    assert response.status_code == 429
    assert fake_llm.calls == []


async def test_internal_summary_reports_cost_and_cached_tokens_by_flow(client):
    app.dependency_overrides[get_llm_provider] = lambda: FakeLLMProvider(reply="Texto")
    app.dependency_overrides[require_internal_api_key] = lambda: None

    generated = await client.post("/chat/generate", json={"prompt": "Escreva uma frase."})
    assert generated.status_code == 200

    summary = await client.get("/llm-usage/internal/summary")
    assert summary.status_code == 200
    flow = summary.json()["flows"][0]
    assert flow["flow"] == "site_text_generation"
    assert flow["input_tokens"] == 1
    assert flow["cached_input_tokens"] == 1
    assert flow["output_tokens"] == 1
    assert flow["estimated_cost_brl"] == "0.000021"
