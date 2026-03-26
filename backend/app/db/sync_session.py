"""Shared synchronous SQLAlchemy engine and session factory for Celery workers.

A single module-level engine is created at import time so that all Celery tasks
in a worker process share one connection pool instead of leaking a new engine on
every task invocation.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# Module-level engine — created once per Celery worker process
_sync_engine = create_engine(
    settings.DATABASE_URL_SYNC,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

_SyncSessionLocal = sessionmaker(bind=_sync_engine, expire_on_commit=False)


def get_sync_session() -> Session:
    """Return a new sync SQLAlchemy session from the shared engine.

    Callers are responsible for calling session.close() when done.
    """
    return _SyncSessionLocal()
