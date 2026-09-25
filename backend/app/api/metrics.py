"""HTTP metrics middleware and the /metrics endpoint that Prometheus reads."""

import time

from fastapi import APIRouter, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest
from prometheus_client.core import GaugeMetricFamily
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.metrics import HTTP_LATENCY, HTTP_REQUESTS

router = APIRouter(include_in_schema=False)


async def record_request_metrics(request: Request, call_next):
    """Count every request and time it, labelled by the ROUTE TEMPLATE (never the real id)."""
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        path = _route_template(request)
        if path != "/metrics":
            HTTP_REQUESTS.labels(method=request.method, route=path, status=str(status)).inc()
            HTTP_LATENCY.labels(method=request.method, route=path).observe(time.perf_counter() - started)


def _route_template(request: Request) -> str:
    """/api/v1/tickets/3f2a… -> /api/v1/tickets/{ticket_id}. Unknown paths (404s) are grouped as "unmatched",
    so random URLs from scanners can't create new metric series."""
    if request.scope.get("route") is None:
        return "unmatched"
    path = request.url.path
    for name, value in request.path_params.items():
        path = path.replace(str(value), "{" + name + "}")
    return path


class QueueLengthCollector:
    """Reads how many jobs wait in the Celery queue (a Redis list) each time Prometheus scrapes."""

    def __init__(self) -> None:
        settings = get_settings()
        self._redis = Redis(
            host=settings.redis_host, port=settings.redis_port, socket_timeout=1, socket_connect_timeout=1
        )

    def collect(self):
        gauge = GaugeMetricFamily("celery_queue_length", "Background jobs waiting to be picked up", labels=["queue"])
        try:
            gauge.add_metric(["celery"], self._redis.llen("celery"))
        except RedisError:
            pass  # Redis down: report nothing rather than a misleading 0
        yield gauge


_registered = False


def register_queue_collector() -> None:
    global _registered
    if not _registered:
        REGISTRY.register(QueueLengthCollector())
        _registered = True


@router.get("/metrics")
def metrics() -> Response:
    """Prometheus text format. In production, only the monitoring network should reach this."""
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
