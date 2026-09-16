import json
import logging
from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

from app import main
from app.core import metrics
from app.core.dependencies import require_internal_api_key, require_service_api_key
from app.core.exceptions import NotFoundError
from app.core.llm.exceptions import LLMBudgetExceededError
from app.core.llm.schemas import LLMMessage
from app.core.metrics import configure_metrics, emit_metrics, route_template, status_class
from app.diagnosis.repository import DiagnosisRepository
from app.diagnosis.service import DiagnosisService
from app.knowledge.models import KnowledgeChunk
from app.llm_usage.repository import LLMUsageRepository
from app.llm_usage.service import LLMUsageService
from app.settings.config import settings


class FakeBudget:
    monthly_budget_brl = Decimal("1.00")


class FakeUsageRepository:
    async def get_budget(self, flow: str):
        return FakeBudget()

    async def monthly_cost(self, *, flow: str, start, end):
        return Decimal("0.99")


class FakeDiagnosisRepository:
    async def add_turn_metrics(self, **fields) -> None:
        return None


class FakeReadinessSession:
    def __init__(self, *, error: Exception | None = None):
        self.error = error
        self.executed = False

    async def execute(self, statement) -> None:
        self.executed = True
        if self.error:
            raise self.error


class FakeSessionContext:
    def __init__(self, session: FakeReadinessSession):
        self.session = session

    async def __aenter__(self) -> FakeReadinessSession:
        return self.session

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


async def test_emit_metrics_writes_one_json_line(monkeypatch, caplog):
    monkeypatch.setattr(settings, "environment", "staging")

    with caplog.at_level(logging.INFO, logger="metrics"):
        await emit_metrics(
            dimensions={
                "Method": "GET",
                "Route": "/diagnosis/sessions/{session_id}",
                "StatusClass": "2xx",
            },
            values={"RequestCount": (1, "Count")},
        )

    assert len(caplog.records) == 1
    payload = json.loads(caplog.records[0].message)
    assert payload["service.name"] == metrics.SERVICE_NAME
    assert payload["environment"] == "staging"
    assert payload["metric.namespace"] == "DevButter/ButterMind"
    assert payload["Method"] == "GET"
    assert payload["Route"] == "/diagnosis/sessions/{session_id}"
    assert payload["StatusClass"] == "2xx"
    assert payload["RequestCount"] == 1
    assert payload["RequestCount.unit"] == "Count"
    assert not {"CN", "Email", "AccountId"} & payload.keys()


def test_configure_metrics_is_callable_without_side_effects() -> None:
    configure_metrics()


async def test_emit_metrics_failure_does_not_raise(monkeypatch, caplog):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("stdout unavailable")

    monkeypatch.setattr(metrics, "_metrics_logger", type("_Boom", (), {"info": _boom})())

    with caplog.at_level(logging.ERROR):
        await emit_metrics(dimensions={}, values={})

    assert "Failed to emit metrics" in caplog.text


async def test_middleware_continues_when_metrics_sink_fails(client, monkeypatch):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("stdout unavailable")

    monkeypatch.setattr(metrics, "_metrics_logger", type("_Boom", (), {"info": _boom})())

    response = await client.get("/health")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]


async def test_readiness_checks_database_connection(client, monkeypatch):
    session = FakeReadinessSession()
    monkeypatch.setattr(main, "session_factory", lambda: FakeSessionContext(session))

    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert session.executed


async def test_readiness_emits_failure_when_database_is_unavailable(client, monkeypatch):
    emitted: list[dict[str, tuple[float, str]]] = []

    async def capture(*, dimensions, values):
        emitted.append(values)

    monkeypatch.setattr(
        main, "session_factory", lambda: FakeSessionContext(FakeReadinessSession(error=OSError()))
    )
    monkeypatch.setattr(main, "emit_metrics", capture)

    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert emitted == [{"HealthCheckFailure": (1, "Count")}]


async def test_auth_failures_emit_reason_without_secrets(monkeypatch):
    emitted: list[tuple[dict[str, str], dict[str, tuple[float, str]]]] = []

    async def capture(*, dimensions, values):
        emitted.append((dimensions, values))

    monkeypatch.setattr("app.core.dependencies.emit_metrics", capture)
    monkeypatch.setattr(settings, "internal_api_key", "internal-secret")
    monkeypatch.setattr(settings, "service_api_key", "service-secret")

    with pytest.raises(NotFoundError):
        await require_internal_api_key("wrong")
    with pytest.raises(NotFoundError):
        await require_service_api_key("wrong")

    assert emitted == [
        (
            {"AuthType": "internal_api_key", "Reason": "missing_or_invalid_key"},
            {"AuthFailure": (1, "Count")},
        ),
        (
            {"AuthType": "service_api_key", "Reason": "missing_or_invalid_key"},
            {"AuthFailure": (1, "Count")},
        ),
    ]
    assert all("secret" not in str(dimensions) for dimensions, _values in emitted)


async def test_budget_utilization_and_exceeded_are_emitted(monkeypatch):
    emitted: list[dict[str, tuple[float, str]]] = []

    async def capture(*, dimensions, values):
        emitted.append(values)

    monkeypatch.setattr("app.llm_usage.service.emit_metrics", capture)
    service = LLMUsageService(cast(LLMUsageRepository, FakeUsageRepository()))

    with pytest.raises(LLMBudgetExceededError):
        await service.ensure_budget(
            flow="diagnosis_chat",
            model="sabia-4",
            system="system",
            messages=[LLMMessage(role="user", content="hello")],
            max_tokens=1024,
        )

    assert emitted[0]["LLMBudgetUtilizationPercent"] == (99.0, "Percent")
    assert emitted[1] == {"LLMBudgetExceeded": (1, "Count")}


async def test_grounding_metrics_emit_chunk_count_and_score(monkeypatch):
    emitted: list[dict[str, tuple[float, str]]] = []

    async def capture(*, dimensions, values):
        emitted.append(values)

    monkeypatch.setattr("app.diagnosis.service.emit_metrics", capture)
    service = DiagnosisService(
        cast(DiagnosisRepository, FakeDiagnosisRepository()), None, None, None
    )

    await service._record_turn_metrics(
        session_id=uuid4(),
        assistant_message_id=uuid4(),
        retrieved=cast(
            "list[tuple[KnowledgeChunk, float]]",
            [
                (SimpleNamespace(id=uuid4()), 0.8),
                (SimpleNamespace(id=uuid4()), 0.6),
            ],
        ),
        input_tokens=1,
        cached_input_tokens=0,
        output_tokens=2,
        model="sabia-4",
    )

    assert emitted == [
        {
            "DiagnosisChunksUsed": (2, "Count"),
            "DiagnosisGroundingScore": (0.7, "None"),
        }
    ]


def test_route_and_status_helpers_use_templates_only():
    route = type("Route", (), {"path": "/items/{id}"})()
    request = type("Request", (), {"scope": {"route": route}})()

    assert route_template(request) == "/items/{id}"
    assert status_class(503) == "5xx"
