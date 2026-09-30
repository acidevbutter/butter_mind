import json
import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.settings.logging_config import JsonFormatter, setup_logging
from app.settings.middleware import RequestContextMiddleware


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/boom")
    async def boom() -> dict[str, str]:
        raise ValueError("something went wrong")

    return app


@pytest.fixture
async def logging_client():
    transport = ASGITransport(app=_build_app())
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


REQUEST_LOGGER = "app.request"


async def test_successful_request_emits_exactly_one_completion_event(logging_client, caplog):
    with caplog.at_level(logging.INFO, logger=REQUEST_LOGGER):
        response = await logging_client.get("/ok")

    assert response.status_code == 200
    records = [r for r in caplog.records if r.name == REQUEST_LOGGER]
    assert len(records) == 1

    record = records[0]
    assert record.levelname == "INFO"
    assert record.getMessage() == "request_completed"
    assert record.method == "GET"
    assert record.route == "/ok"
    assert record.status_code == 200
    assert isinstance(record.duration_ms, float)
    assert record.request_id
    assert record.service == "butter_mind"
    assert record.environment


async def test_failed_request_emits_exactly_one_event_with_traceback(logging_client, caplog):
    with caplog.at_level(logging.INFO, logger=REQUEST_LOGGER), pytest.raises(ValueError):
        await logging_client.get("/boom")

    records = [r for r in caplog.records if r.name == REQUEST_LOGGER]
    assert len(records) == 1

    record = records[0]
    assert record.levelname == "ERROR"
    assert record.getMessage() == "request_failed"
    assert record.route == "/boom"
    assert record.status_code == 500
    assert record.exc_info is not None

    # No prompt/response payloads, secrets, or PII ever get attached.
    formatted = JsonFormatter().format(record)
    payload = json.loads(formatted)
    assert "something went wrong" not in json.dumps(
        {k: v for k, v in payload.items() if k != "exception"}
    )


def test_json_formatter_produces_expected_shape():
    logger = logging.getLogger("test.json.formatter")
    record = logger.makeRecord(
        name="test.json.formatter",
        level=logging.INFO,
        fn="test",
        lno=1,
        msg="request_completed",
        args=(),
        exc_info=None,
        extra={
            "service": "butter_mind",
            "environment": "development",
            "request_id": "abc-123",
            "method": "GET",
            "route": "/health",
            "status_code": 200,
            "duration_ms": 1.2,
        },
    )

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.json.formatter"
    assert payload["event"] == "request_completed"
    assert payload["service"] == "butter_mind"
    assert payload["environment"] == "development"
    assert payload["request_id"] == "abc-123"
    assert payload["method"] == "GET"
    assert payload["route"] == "/health"
    assert payload["status_code"] == 200
    assert payload["duration_ms"] == 1.2
    assert "timestamp" in payload


def test_setup_logging_quiets_uvicorn_access_log():
    setup_logging("INFO")

    uvicorn_access = logging.getLogger("uvicorn.access")
    assert uvicorn_access.level == logging.WARNING
    assert uvicorn_access.propagate is False
