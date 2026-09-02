import logging
import os
from collections.abc import Mapping

from aws_embedded_metrics.config import get_config
from aws_embedded_metrics.logger.metrics_logger_factory import create_metrics_logger
from starlette.requests import Request

from app.settings.config import settings

logger = logging.getLogger(__name__)

NAMESPACE = "DevButter/ButterMind"
SERVICE_NAME = "butter_mind"
LOG_GROUP_NAME = "/ecs/devbutter/staging/mind"


def configure_metrics() -> None:
    """Configure EMF defaults while allowing deployment environment overrides.

    Forces the "Local" EMF environment (stdout sink) by default: this
    architecture ships metrics via the ECS `awslogs` log driver -> CloudWatch
    Logs auto-extraction, never a CloudWatch Agent sidecar. Without this
    override the library's environment autodetection falls through to the
    "Agent" sink (TCP to a nonexistent daemon), which drops every metric and
    spams "Connection refused"/"Broken pipe" on every request, locally and in
    production alike.
    """
    config = get_config()
    config.namespace = os.getenv("AWS_EMF_NAMESPACE", NAMESPACE)
    config.service_name = os.getenv("AWS_EMF_SERVICE_NAME", SERVICE_NAME)
    config.log_group_name = os.getenv("AWS_EMF_LOG_GROUP_NAME", LOG_GROUP_NAME)
    config.environment = os.getenv("AWS_EMF_ENVIRONMENT", "Local")


def route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unmatched"


def status_class(status_code: int) -> str:
    return f"{status_code // 100}xx"


async def emit_metrics(
    *,
    dimensions: Mapping[str, str],
    values: Mapping[str, tuple[float, str]],
) -> None:
    """Emit a batch of EMF metrics without allowing telemetry failures to propagate."""
    try:
        metrics = create_metrics_logger()
        metrics.set_namespace(get_config().namespace or NAMESPACE)
        metrics.set_dimensions(
            {"Environment": settings.environment, "Service": SERVICE_NAME},
            {"Environment": settings.environment, "Service": SERVICE_NAME, **dimensions},
        )
        for name, (value, unit) in values.items():
            metrics.put_metric(name, value, unit)
        await metrics.flush()
    except Exception:
        logger.exception("Failed to emit CloudWatch EMF metrics")
