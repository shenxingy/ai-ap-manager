"""Exception queue API endpoints."""
import uuid
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, require_role
from app.db.session import get_session
from app.models.exception_record import ExceptionRecord
from app.models.invoice import Invoice
from app.models.user import User
from app.schemas.exception_record import (
    ExceptionDetail,
    ExceptionListItem,
    ExceptionListResponse,
    ExceptionPatch,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── GET /exceptions ───

@router.get(
    "",
    response_model=ExceptionListResponse,
    summary="List exception records with optional filters",
)
async def list_exceptions(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    exc_status: str | None = Query(default=None, alias="status"),
    exception_code: str | None = Query(default=None),
    invoice_id: uuid.UUID | None = Query(default=None),
    assigned_to: uuid.UUID | None = Query(default=None),
    severity: str | None = Query(default=None),
):
    """Return paginated exception records. AP_CLERK+ can read."""
    stmt = select(ExceptionRecord)

    if exc_status:
        stmt = stmt.where(ExceptionRecord.status == exc_status)
    if exception_code:
        stmt = stmt.where(ExceptionRecord.exception_code == exception_code)
    if invoice_id:
        stmt = stmt.where(ExceptionRecord.invoice_id == invoice_id)
    if assigned_to:
        stmt = stmt.where(ExceptionRecord.assigned_to == assigned_to)
    if severity:
        stmt = stmt.where(ExceptionRecord.severity == severity)

    # Total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # Paginated results
    offset = (page - 1) * page_size
    stmt = stmt.order_by(ExceptionRecord.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(stmt)
    exceptions = result.scalars().all()

    return ExceptionListResponse(
        items=[ExceptionListItem.model_validate(exc) for exc in exceptions],
        total=total,
        page=page,
        page_size=page_size,
    )


# ─── GET /exceptions/{id} ───

@router.get(
    "/{exception_id}",
    response_model=ExceptionDetail,
    summary="Get exception detail with invoice summary",
)
async def get_exception(
    exception_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    stmt = (
        select(ExceptionRecord)
        .where(ExceptionRecord.id == exception_id)
        .options(selectinload(ExceptionRecord.invoice))
    )
    result = await db.execute(stmt)
    exc = result.scalars().first()

    if exc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exception not found.")

    return ExceptionDetail.model_validate(exc)


# ─── PATCH /exceptions/{id} ───

@router.patch(
    "/{exception_id}",
    response_model=ExceptionDetail,
    summary="Update exception status, assignee, or resolution notes (AP_ANALYST+)",
)
async def patch_exception(
    exception_id: uuid.UUID,
    patch: ExceptionPatch,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("AP_ANALYST", "ADMIN"))],
):
    stmt = (
        select(ExceptionRecord)
        .where(ExceptionRecord.id == exception_id)
        .options(selectinload(ExceptionRecord.invoice))
    )
    result = await db.execute(stmt)
    exc = result.scalars().first()

    if exc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exception not found.")

    before = {
        "status": exc.status,
        "assigned_to": str(exc.assigned_to) if exc.assigned_to else None,
        "resolution_notes": exc.resolution_notes,
    }

    # Apply patch fields
    if patch.status is not None:
        exc.status = patch.status
        if patch.status == "resolved" and exc.resolved_at is None:
            exc.resolved_at = datetime.now(timezone.utc)
            exc.resolved_by = current_user.id
    if patch.assigned_to is not None:
        exc.assigned_to = patch.assigned_to
    if patch.resolution_notes is not None:
        exc.resolution_notes = patch.resolution_notes

    after = {
        "status": exc.status,
        "assigned_to": str(exc.assigned_to) if exc.assigned_to else None,
        "resolution_notes": exc.resolution_notes,
    }

    await db.commit()
    await db.refresh(exc)

    # Audit log (async version)
    from app.models.audit import AuditLog
    import json

    audit_entry = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="exception.updated",
        entity_type="exception",
        entity_id=exception_id,
        before_state=json.dumps(before, default=str),
        after_state=json.dumps(after, default=str),
        notes=f"Exception patched by {current_user.email}",
    )
    db.add(audit_entry)
    await db.commit()

    # Re-load with invoice relationship for response
    stmt2 = (
        select(ExceptionRecord)
        .where(ExceptionRecord.id == exception_id)
        .options(selectinload(ExceptionRecord.invoice))
    )
    result2 = await db.execute(stmt2)
    exc = result2.scalars().first()

    return ExceptionDetail.model_validate(exc)
