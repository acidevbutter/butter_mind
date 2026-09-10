from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from aws_embedded_metrics.config import get_config

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


class FakeMetricsLogger:
    def __init__(self, *, flush_error: bool = False):
        self.flush_error = flush_error
        self.namespace = ""
        self.dimension_sets: tuple[dict[str, str], ...] = ()
        self.values: dict[str, tuple[float, str]] = {}

    def set_namespace(self, namespace: str) -> None:
        self.namespace = namespace

    def set_dimensions(self, *dimension_sets: dict[str, str]) -> None:
        self.dimension_sets = dimension_sets

    def put_metric(self, name: str, value: float, unit: str) -> None:
        self.values[name] = (value, unit)

    async def flush(self) -> None:
        if self.flush_error:
            raise OSError("stdout unavailable")


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


async def test_emit_metrics_uses_low_cardinality_dimensions(monkeypatch):
    fake = FakeMetricsLogger()
    monkeypatch.setattr(metrics, "create_metrics_logger", lambda: fake)
    monkeypatch.setattr(settings, "environment", "staging")

    await emit_metrics(
        dimensions={
            "Method": "GET",
            "Route": "/diagnosis/sessions/{session_id}",
            "StatusClass": "2xx",
        },
        values={"RequestCount": (1, "Count")},
    )

    assert fake.namespace == "DevButter/ButterMind"
    assert fake.dimension_sets == (
        {"Environment": "staging", "Service": "butter_mind"},
        {
            "Environment": "staging",
            "Service": "butter_mind",
            "Method": "GET",
            "Route": "/diagnosis/sessions/{session_id}",
            "StatusClass": "2xx",
        },
    )
    assert fake.values == {"RequestCount": (1, "Count")}
    assert all(
        not {"CN", "Email", "AccountId"} & dimensions.keys() for dimensions in fake.dimension_sets
    )


def test_metrics_configuration_honors_emf_overrides(monkeypatch):
    monkeypatch.setenv("AWS_EMF_NAMESPACE", "Example/Namespace")
    monkeypatch.setenv("AWS_EMF_SERVICE_NAME", "example-service")
    monkeypatch.setenv("AWS_EMF_LOG_GROUP_NAME", "/example/log-group")

    configure_metrics()

    config = get_config()
    assert config.namespace == "Example/Namespace"
    assert config.service_name == "example-service"
    assert config.log_group_name == "/example/log-group"


async def test_middleware_continues_when_emf_flush_fails(client, monkeypatch):
    monkeypatch.setattr(
        metrics, "create_metrics_logger", lambda: FakeMetricsLogger(flush_error=True)
    )

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
