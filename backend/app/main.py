from contextlib import asynccontextmanager
import logging

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging import setup_logging
from app.middleware.request_id import RequestIdMiddleware
from app.middleware.metrics import PrometheusMiddleware, metrics_endpoint

setup_logging()

logger = logging.getLogger(__name__)

# Initialize Sentry error monitoring
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        environment=getattr(settings, 'APP_ENV', 'development'),
        send_default_pii=False,
    )
    logger.info("Sentry initialized")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — ensure MinIO bucket exists
    try:
        from app.services.storage import ensure_bucket
        ensure_bucket()
    except Exception as exc:
        logger.warning("MinIO bucket bootstrap failed (continuing): %s", exc)
    yield
    # Shutdown


app = FastAPI(
    title="AI AP Operations Manager",
    version="1.0.0",
    docs_url="/api/docs" if settings.APP_ENV != "production" else None,
    redoc_url="/api/redoc" if settings.APP_ENV != "production" else None,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(PrometheusMiddleware)
app.add_middleware(RequestIdMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s %s — %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


# ─── Routers ───
from app.api.v1.router import api_router  # noqa: E402

app.include_router(api_router, prefix="/api/v1")


# ─── Observability endpoints (no auth, app-level) ───

app.add_route("/metrics", metrics_endpoint, include_in_schema=False)


async def _check_db() -> str:
    """Run SELECT 1 via async session. Returns 'ok' or error message."""
    try:
        from sqlalchemy import text
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:
        logger.warning("Health DB check failed: %s", exc)
        return "error"


async def _check_redis() -> str:
    """Ping Redis. Returns 'ok' or error message."""
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        return "ok"
    except Exception as exc:
        logger.warning("Health Redis check failed: %s", exc)
        return "error"


def _check_minio() -> str:
    """Check MinIO bucket exists (sync). Returns 'ok' or error message."""
    try:
        from app.services.storage import get_client
        get_client().bucket_exists(settings.MINIO_BUCKET_NAME)
        return "ok"
    except Exception as exc:
        logger.warning("Health MinIO check failed: %s", exc)
        return "error"


@app.get("/health", include_in_schema=False)
async def health():
    """Detailed health check — DB, Redis, MinIO. Returns 503 if any component is degraded."""
    import asyncio
    db_status, redis_status = await asyncio.gather(_check_db(), _check_redis())
    minio_status = _check_minio()

    overall = (
        "ok"
        if all(s == "ok" for s in (db_status, redis_status, minio_status))
        else "degraded"
    )
    body = {
        "status": overall,
        "db": db_status,
        "redis": redis_status,
        "minio": minio_status,
        "version": app.version,
    }
    status_code = 200 if overall == "ok" else 503
    return JSONResponse(status_code=status_code, content=body)


@app.get("/health/ready", include_in_schema=False)
async def health_ready():
    """Readiness probe — checks all dependencies. Returns 503 if not ready."""
    return await health()


@app.get("/health/live", include_in_schema=False)
async def health_live():
    """Liveness probe — confirms process is alive (no dependency checks)."""
    return JSONResponse(status_code=200, content={"status": "ok"})
