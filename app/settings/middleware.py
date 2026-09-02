import logging
import time
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.metrics import emit_metrics, route_template, status_class
from app.settings.config import settings

logger = logging.getLogger("app.request")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, times the request, and logs one line per request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception:
            logger.exception(
                "request %s failed: %s %s", request_id, request.method, request.url.path
            )
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
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
            logger.info(
                "%s %s -> %s (%.1fms) [%s]",
                request.method,
                request.url.path,
                status_code,
                duration_ms,
                request_id,
            )


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
