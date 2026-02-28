"""Audit log API endpoints."""
import csv
import io
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_role
from app.db.session import get_session
from app.models.audit import AuditLog
from app.models.user import User

router = APIRouter()


@router.get(
    "/export",
    summary="Export audit logs as CSV",
    description="Stream audit logs as CSV file with optional filters. Requires AUDITOR or ADMIN role.",
)
async def export_audit_logs(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("AUDITOR", "ADMIN"))],
    start_date: Annotated[datetime | None, Query(description="Filter logs from this date (ISO 8601)")] = None,
    end_date: Annotated[datetime | None, Query(description="Filter logs until this date (ISO 8601)")] = None,
    entity_type: Annotated[str | None, Query(description="Filter by entity type (e.g., 'invoice')")] = None,
):
    """Export audit logs as CSV with optional filtering.

    Query parameters:
    - start_date: ISO 8601 datetime to filter logs from (inclusive)
    - end_date: ISO 8601 datetime to filter logs until (inclusive)
    - entity_type: Filter by entity type (case-sensitive)

    Returns streaming CSV with columns: id, action, entity_type, entity_id, actor_email, created_at, notes
    """
    # Build query with optional filters
    query = select(AuditLog)

    if start_date:
        query = query.where(AuditLog.created_at >= start_date)
    if end_date:
        query = query.where(AuditLog.created_at <= end_date)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)

    # Order by created_at for consistent chronological output
    query = query.order_by(AuditLog.created_at.asc())

    logs = (await db.execute(query)).scalars().all()

    # Generate CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow(["id", "action", "entity_type", "entity_id", "actor_email", "created_at", "notes"])

    # Write rows
    for log in logs:
        writer.writerow([
            str(log.id),
            log.action,
            log.entity_type,
            str(log.entity_id) if log.entity_id else "",
            log.actor_email or "",
            log.created_at.isoformat() if log.created_at else "",
            log.notes or "",
        ])

    # Convert to bytes and stream
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit-logs.csv"},
    )
