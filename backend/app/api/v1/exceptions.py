"""Exception queue API endpoints."""
import uuid
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, require_role
from app.db.session import get_session
from app.models.exception_record import ExceptionComment, ExceptionRecord
from app.models.invoice import Invoice
from app.models.user import User
from app.schemas.exception_record import (
    ExceptionCommentCreate,
    ExceptionCommentOut,
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
    current_user: Annotated[User, Depends(require_role("AP_CLERK", "AP_ANALYST", "AP_MANAGER", "APPROVER", "ADMIN", "AUDITOR"))],
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

    # Correlated subquery: comment count per exception
    comment_count_sq = (
        select(func.count(ExceptionComment.id))
        .where(ExceptionComment.exception_id == ExceptionRecord.id)
        .correlate(ExceptionRecord)
        .scalar_subquery()
    )

    # Paginated results with comment count
    offset = (page - 1) * page_size
    paged_stmt = (
        stmt
        .add_columns(comment_count_sq.label("comment_count"))
        .order_by(ExceptionRecord.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = (await db.execute(paged_stmt)).all()

    # Batch-load assignee emails for all non-null assigned_to UUIDs
    assignee_ids = list({exc.assigned_to for exc, _ in rows if exc.assigned_to is not None})
    email_map: dict[uuid.UUID, str] = {}
    if assignee_ids:
        user_result = await db.execute(select(User).where(User.id.in_(assignee_ids)))
        for u in user_result.scalars().all():
            email_map[u.id] = u.email

    items = []
    for exc, count in rows:
        item = ExceptionListItem.model_validate(exc)
        item.comment_count = count
        item.assigned_to_email = email_map.get(exc.assigned_to) if exc.assigned_to else None
        items.append(item)

    return ExceptionListResponse(
        items=items,
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
    current_user: Annotated[User, Depends(require_role("AP_CLERK", "AP_ANALYST", "AP_MANAGER", "APPROVER", "ADMIN", "AUDITOR"))],
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

    # Log exception correction feedback
    if patch.status is not None and patch.status != before["status"]:
        from app.services.feedback import log_exception_correction  # noqa: PLC0415
        await log_exception_correction(
            db=db,
            exception_id=exception_id,
            invoice_id=exc.invoice_id,
            old_status=before["status"],
            new_status=patch.status,
            actor_id=current_user.id,
            actor_email=current_user.email,
        )

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


# ─── POST /exceptions/{id}/comments ───

@router.post(
    "/{exception_id}/comments",
    response_model=ExceptionCommentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a comment to an exception (AP_CLERK+)",
)
async def create_comment(
    exception_id: uuid.UUID,
    body: ExceptionCommentCreate,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("AP_ANALYST", "AP_CLERK", "ADMIN"))],
):
    # Verify exception exists
    exc_result = await db.execute(
        select(ExceptionRecord).where(ExceptionRecord.id == exception_id)
    )
    exc = exc_result.scalars().first()
    if exc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exception not found.")

    comment = ExceptionComment(
        exception_id=exception_id,
        author_id=current_user.id,
        body=body.body,
    )
    db.add(comment)
    await db.flush()

    # Audit log
    from app.models.audit import AuditLog
    import json

    audit_entry = AuditLog(
        actor_id=current_user.id,
        actor_email=current_user.email,
        action="exception.commented",
        entity_type="exception",
        entity_id=exception_id,
        before_state=None,
        after_state=json.dumps({"comment_id": str(comment.id), "body": body.body}, default=str),
        notes=f"Comment added by {current_user.email}",
    )
    db.add(audit_entry)
    await db.commit()
    await db.refresh(comment)

    return ExceptionCommentOut.model_validate(comment)


# ─── GET /exceptions/{id}/comments ───

@router.get(
    "/{exception_id}/comments",
    response_model=list[ExceptionCommentOut],
    summary="List comments for an exception (AP_CLERK+)",
)
async def list_comments(
    exception_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("AP_CLERK", "AP_ANALYST", "ADMIN", "APPROVER"))],
):
    # Verify exception exists
    exc_result = await db.execute(
        select(ExceptionRecord).where(ExceptionRecord.id == exception_id)
    )
    if exc_result.scalars().first() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exception not found.")

    result = await db.execute(
        select(ExceptionComment)
        .where(ExceptionComment.exception_id == exception_id)
        .order_by(ExceptionComment.created_at)
    )
    comments = result.scalars().all()
    return [ExceptionCommentOut.model_validate(c) for c in comments]


# ─── POST /exceptions/bulk-update ───

class BulkExceptionUpdateItem(BaseModel):
    exception_id: uuid.UUID
    status: str | None = None
    assigned_to: uuid.UUID | None = None
    resolution_notes: str | None = None


class BulkExceptionUpdateRequest(BaseModel):
    items: list[BulkExceptionUpdateItem]


class BulkExceptionUpdateResponse(BaseModel):
    updated: int
    skipped: int
    errors: int


@router.post(
    "/bulk-update",
    response_model=BulkExceptionUpdateResponse,
    summary="Bulk update exception statuses / assignments (AP_ANALYST+)",
)
async def bulk_update_exceptions(
    body: BulkExceptionUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("AP_ANALYST", "ADMIN"))],
):
    """Batch status/assignment change for up to 100 exceptions. Each item is audit-logged."""
    import json
    from app.models.audit import AuditLog

    if len(body.items) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bulk update limit is 100 items per request.",
        )

    updated = skipped = errors = 0

    for item in body.items:
        try:
            exc = (await db.execute(
                select(ExceptionRecord).where(ExceptionRecord.id == item.exception_id)
            )).scalars().first()

            if exc is None:
                errors += 1
                continue

            before = {
                "status": exc.status,
                "assigned_to": str(exc.assigned_to) if exc.assigned_to else None,
            }
            changed = False

            if item.status is not None and item.status != exc.status:
                exc.status = item.status
                if item.status == "resolved" and exc.resolved_at is None:
                    exc.resolved_at = datetime.now(timezone.utc)
                    exc.resolved_by = current_user.id
                changed = True
            if item.assigned_to is not None:
                exc.assigned_to = item.assigned_to
                changed = True
            if item.resolution_notes is not None:
                exc.resolution_notes = item.resolution_notes
                changed = True

            if not changed:
                skipped += 1
                continue

            after = {
                "status": exc.status,
                "assigned_to": str(exc.assigned_to) if exc.assigned_to else None,
            }
            db.add(AuditLog(
                actor_id=current_user.id,
                actor_email=current_user.email,
                action="exception.bulk_updated",
                entity_type="exception",
                entity_id=item.exception_id,
                before_state=json.dumps(before, default=str),
                after_state=json.dumps(after, default=str),
                notes=f"Bulk update by {current_user.email}",
            ))
            updated += 1

        except Exception as exc_err:
            logger.warning("bulk_update_exceptions: error on %s: %s", item.exception_id, exc_err)
            errors += 1

    await db.commit()
    return BulkExceptionUpdateResponse(updated=updated, skipped=skipped, errors=errors)
