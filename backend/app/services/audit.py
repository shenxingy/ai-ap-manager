"""Audit log helper — append-only writes to audit_logs table."""
import json
import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditLog

logger = logging.getLogger(__name__)


def log(
    db: Session,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str | None = None,
    actor_id: uuid.UUID | str | None = None,
    actor_email: str | None = None,
    before: Any | None = None,
    after: Any | None = None,
    notes: str | None = None,
) -> AuditLog:
    """Write a single audit log entry.

    Args:
        db: Sync SQLAlchemy session (Celery tasks) or async session (API layer).
            Pass a sync session here; async callers should use log_async instead.
        action: Short verb, e.g. 'invoice.uploaded', 'invoice.status_changed'.
        entity_type: Table/domain name, e.g. 'invoice', 'exception'.
        entity_id: PK of the affected record.
        actor_id: User who performed the action (None for system actions).
        actor_email: Denormalised email (preserved if user is later deleted).
        before: Dict snapshot of state before the action (JSON-serialisable).
        after: Dict snapshot of state after the action.
        notes: Free-text annotation.
    """
    entry = AuditLog(
        actor_id=uuid.UUID(str(actor_id)) if actor_id else None,
        actor_email=actor_email,
        action=action,
        entity_type=entity_type,
        entity_id=uuid.UUID(str(entity_id)) if entity_id else None,
        before_state=json.dumps(before, default=str) if before is not None else None,
        after_state=json.dumps(after, default=str) if after is not None else None,
        notes=notes,
    )
    db.add(entry)
    db.flush()  # get id without committing; caller controls the transaction
    logger.debug("Audit: %s %s/%s", action, entity_type, entity_id)
    return entry
