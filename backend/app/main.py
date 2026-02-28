from contextlib import asynccontextmanager
import logging

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

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
    version="0.1.0",
    docs_url="/api/docs" if settings.APP_ENV != "production" else None,
    redoc_url="/api/redoc" if settings.APP_ENV != "production" else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ───
from app.api.v1.router import api_router  # noqa: E402

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.APP_ENV}
