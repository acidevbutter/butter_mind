import json
import logging
import logging.config
from datetime import UTC, datetime

# Attributes present on every stdlib LogRecord (plus the synthetic ones the
# default Formatter adds). Anything a call site passes via `extra=` shows up
# as additional attributes beyond this set, so diffing against it is how we
# discover and surface those fields without a fixed whitelist.
_RESERVED_RECORD_ATTRS = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {
    "message",
    "asctime",
}


class JsonFormatter(logging.Formatter):
    """Renders one JSON object per log record.

    Fields passed via `logger.info(..., extra={...})` are merged in as-is, so
    request middleware (and anything else) can attach structured context
    (request_id, route, status_code, duration_ms, ...) without this
    formatter needing to know about them ahead of time.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_ATTRS:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(level: str = "INFO") -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {"()": JsonFormatter},
            },
            "handlers": {
                "console": {"class": "logging.StreamHandler", "formatter": "json"},
            },
            "root": {"handlers": ["console"], "level": level},
            "loggers": {
                "sqlalchemy.engine": {"level": "WARNING", "propagate": True},
                # uvicorn's own access log would duplicate the single
                # structured completion event RequestContextMiddleware emits
                # per request (app.settings.middleware.RequestContextMiddleware).
                # Quiet it instead of letting both loggers describe the same
                # request.
                "uvicorn.access": {"level": "WARNING", "propagate": False},
            },
        }
    )
