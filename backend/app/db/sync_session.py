"""Shared synchronous SQLAlchemy engine and session factory for Celery workers.

The engine is created lazily on first call to get_sync_session() so that
importing this module does not attempt a database connection at import time.
This keeps unit tests that mock create_engine working correctly.
"""
from __future__ import annotations

import threading

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

_lock = threading.Lock()
_sync_engine: Engine | None = None
_SyncSessionLocal: sessionmaker | None = None


def _ensure_engine() -> None:
    """Create the engine and session factory once (thread-safe)."""
    global _sync_engine, _SyncSessionLocal
    if _sync_engine is None:
        with _lock:
            if _sync_engine is None:
                from app.core.config import settings
                _sync_engine = create_engine(
                    settings.DATABASE_URL_SYNC,
                    pool_pre_ping=True,
                    pool_size=5,
                    max_overflow=10,
                )
                _SyncSessionLocal = sessionmaker(
                    bind=_sync_engine, expire_on_commit=False
                )


def get_sync_session() -> Session:
    """Return a new sync SQLAlchemy session from the shared engine.

    Callers are responsible for calling session.close() when done.
    """
    _ensure_engine()
    assert _SyncSessionLocal is not None
    session: Session = _SyncSessionLocal()
    return session
