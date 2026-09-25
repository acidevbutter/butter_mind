import logging
import sys
import time
import uuid
from types import TracebackType
from typing import cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.metrics import SERVICE_NAME, emit_metrics, route_template, status_class
from app.settings.config import settings

logger = logging.getLogger("app.request")
_PROBE_PATHS = frozenset({"/health", "/health/ready"})


def _route_for_log(request: Request) -> str:
    """Matched route template when available, else the raw path.

    Unlike `route_template()` in app.core.metrics (which collapses unmatched
    requests to a fixed "unmatched" label to keep metric dimension
    cardinality low), a log line can carry the literal path for
    404s/unmatched requests without that concern.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else request.url.path


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, times the request, and logs exactly one
    structured event per request describing how it completed (or failed).
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()
        status_code = 500
        exc_info: tuple[type[BaseException], BaseException, TracebackType | None] | None = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            exc_info = cast(
                "tuple[type[BaseException], BaseException, TracebackType | None]",
                sys.exc_info(),
            )
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            if request.url.path not in _PROBE_PATHS:
                await emit_metrics(
                    dimensions={
                        "Method": request.method,
                        "Route": route_template(request),
                        "StatusClass": status_class(status_code),
                    },
                    values={
                        "RequestCount": (1, "Count"),
                        "Latency": (duration_ms, "Milliseconds"),
                        **(
                            {"5xxCount": (1, "Count")}
                            if status_code >= 500
                            else {"4xxCount": (1, "Count")}
                            if status_code >= 400
                            else {}
                        ),
                    },
                )
                log_extra = {
                    "service": SERVICE_NAME,
                    "environment": settings.environment,
                    "request_id": request_id,
                    "method": request.method,
                    "route": _route_for_log(request),
                    "status_code": status_code,
                    "duration_ms": round(duration_ms, 1),
                }
                if exc_info is not None:
                    # exc_info carries the traceback for correlation; never the
                    # request/response bodies (this service handles LLM prompts,
                    # which must never be logged) or any secret/PII.
                    logger.error("request_failed", extra=log_extra, exc_info=exc_info)
                else:
                    logger.info("request_completed", extra=log_extra)


def register_middleware(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_origin_regex=settings.cors_allowed_origin_regex,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)
