"""Audit log helper — append-only writes to audit_logs table."""
import json
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.audit import AuditLog

logger = logging.getLogger(__name__)


def _build_entry(
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str | None = None,
    actor_id: uuid.UUID | str | None = None,
    actor_email: str | None = None,
    before: Any | None = None,
    after: Any | None = None,
    notes: str | None = None,
) -> AuditLog:
    return AuditLog(
        actor_id=uuid.UUID(str(actor_id)) if actor_id else None,
        actor_email=actor_email,
        action=action,
        entity_type=entity_type,
        entity_id=uuid.UUID(str(entity_id)) if entity_id else None,
        before_state=json.dumps(before, default=str) if before is not None else None,
        after_state=json.dumps(after, default=str) if after is not None else None,
        notes=notes,
    )


def log(
    db: Session | AsyncSession,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str | None = None,
    actor_id: uuid.UUID | str | None = None,
    actor_email: str | None = None,
    before: Any | None = None,
    after: Any | None = None,
    notes: str | None = None,
) -> AuditLog:
    """Write a single audit log entry (sync path).

    For async callers (FastAPI routes), this adds the entry to the session
    without calling flush — the caller is responsible for awaiting db.flush()
    or db.commit() to persist.

    For sync callers (Celery tasks), this calls db.flush() to get the id.
    """
    entry = _build_entry(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        actor_email=actor_email,
        before=before,
        after=after,
        notes=notes,
    )
    db.add(entry)
    if not isinstance(db, AsyncSession):
        db.flush()
    logger.debug("Audit: %s %s/%s", action, entity_type, entity_id)
    return entry
