"""Prometheus metrics middleware (pure ASGI — no BaseHTTPMiddleware)."""
import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

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


class PrometheusMiddleware:
    """Record request count and latency for every HTTP request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        if path in _SKIP_PATHS:
            await self.app(scope, receive, send)
            return

        method = scope["method"]
        start = time.perf_counter()
        status_code = 500  # default in case send is never called

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            latency = time.perf_counter() - start
            REQUEST_COUNT.labels(
                method=method,
                path=path,
                status_code=str(status_code),
            ).inc()
            REQUEST_LATENCY.labels(method=method, path=path).observe(latency)


# ─── Metrics endpoint handler ───

async def metrics_endpoint(request: Request) -> Response:
    """Expose Prometheus metrics in text/plain format."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )
