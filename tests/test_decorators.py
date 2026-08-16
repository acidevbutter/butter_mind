import logging

import pytest

from app.core.decorators import log_call, log_errors


def test_log_call_sync_logs_debug_and_returns_value(caplog):
    @log_call
    def add(a, b):
        return a + b

    with caplog.at_level(logging.DEBUG):
        assert add(1, 2) == 3

    assert any(r.levelname == "DEBUG" and "add" in r.message for r in caplog.records)


def test_log_call_sync_raises_and_logs_error(caplog):
    @log_call
    def boom():
        raise ValueError("nope")

    with caplog.at_level(logging.DEBUG), pytest.raises(ValueError):
        boom()

    assert any(r.levelname == "ERROR" for r in caplog.records)


async def test_log_call_async_returns_value_and_logs(caplog):
    @log_call
    async def add_async(a, b):
        return a + b

    with caplog.at_level(logging.DEBUG):
        assert await add_async(1, 2) == 3

    assert any(r.levelname == "DEBUG" and "add_async" in r.message for r in caplog.records)
    assert all(getattr(r, "event", None) != "method_error" for r in caplog.records)


def test_log_call_records_carry_event_and_target(caplog):
    @log_call
    def ping():
        return "pong"

    with caplog.at_level(logging.DEBUG):
        ping()

    record = next(r for r in caplog.records if getattr(r, "event", None) == "method_call")
    assert record.target.endswith("ping")


def test_log_errors_wraps_public_methods_only(caplog):
    @log_errors
    class Service:
        def __init__(self):
            self.value = 1

        def public_method(self):
            return self.value

        def _private_method(self):
            return self.value

    service = Service()
    with caplog.at_level(logging.DEBUG):
        service.public_method()
        service._private_method()

    logged_targets = [getattr(r, "target", "") for r in caplog.records]
    assert any("public_method" in t for t in logged_targets)
    assert not any("_private_method" in t for t in logged_targets)
    assert not any("__init__" in t for t in logged_targets)
