"""Prometheus metrics middleware."""
import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ─── Metrics ───

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP request count",
    ["method", "path", "status_code"],
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

# ─── Middleware ───

# Paths that should not be tracked (noisy, not useful for SLO)
_SKIP_PATHS = {"/metrics", "/health", "/health/live", "/health/ready"}


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Record request count and latency for every HTTP request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if path in _SKIP_PATHS:
            return await call_next(request)

        method = request.method
        start = time.perf_counter()
        response = await call_next(request)
        latency = time.perf_counter() - start

        REQUEST_COUNT.labels(
            method=method,
            path=path,
            status_code=str(response.status_code),
        ).inc()
        REQUEST_LATENCY.labels(method=method, path=path).observe(latency)

        return response


# ─── Metrics endpoint handler ───

async def metrics_endpoint(request: Request) -> Response:
    """Expose Prometheus metrics in text/plain format."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
