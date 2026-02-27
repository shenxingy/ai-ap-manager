"""Recurring invoice patterns API endpoints."""
import uuid
import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role
from app.db.session import get_session
from app.models.recurring_pattern import RecurringInvoicePattern
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Schemas ───

class RecurringPatternOut(BaseModel):
    id: uuid.UUID
    vendor_id: uuid.UUID
    frequency_days: int
    avg_amount: float
    tolerance_pct: float
    auto_fast_track: bool
    last_detected_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RecurringPatternListResponse(BaseModel):
    items: list[RecurringPatternOut]
    total: int


class RecurringPatternUpdate(BaseModel):
    auto_fast_track: bool | None = None
    tolerance_pct: float | None = None


# ─── GET /admin/recurring-patterns ───

@router.get(
    "/recurring-patterns",
    response_model=RecurringPatternListResponse,
    summary="List all recurring invoice patterns (ADMIN, AP_ANALYST)",
)
async def list_recurring_patterns(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("ADMIN", "AP_ANALYST"))],
    skip: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(default=50, ge=1, le=500, description="Number of records to return"),
):
    # Get total count
    total = await db.scalar(select(func.count()).select_from(RecurringInvoicePattern)) or 0

    # Get paginated results
    stmt = (
        select(RecurringInvoicePattern)
        .order_by(RecurringInvoicePattern.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    items = [RecurringPatternOut.model_validate(row) for row in result.scalars().all()]

    return RecurringPatternListResponse(items=items, total=total)


# ─── PATCH /admin/recurring-patterns/{id} ───

@router.patch(
    "/recurring-patterns/{pattern_id}",
    response_model=RecurringPatternOut,
    summary="Update auto_fast_track and/or tolerance_pct for a pattern (ADMIN, AP_ANALYST)",
)
async def update_recurring_pattern(
    pattern_id: uuid.UUID,
    body: RecurringPatternUpdate,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("ADMIN", "AP_ANALYST"))],
):
    result = await db.execute(
        select(RecurringInvoicePattern).where(RecurringInvoicePattern.id == pattern_id)
    )
    pattern = result.scalars().first()

    if pattern is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurring pattern not found.")

    if body.auto_fast_track is not None:
        pattern.auto_fast_track = body.auto_fast_track
    if body.tolerance_pct is not None:
        if not (0.0 <= body.tolerance_pct <= 1.0):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="tolerance_pct must be between 0.0 and 1.0",
            )
        pattern.tolerance_pct = body.tolerance_pct

    await db.commit()
    await db.refresh(pattern)
    return RecurringPatternOut.model_validate(pattern)


# ─── POST /admin/recurring-patterns/detect ───

@router.post(
    "/recurring-patterns/detect",
    summary="Dispatch Celery task to detect recurring invoice patterns (ADMIN)",
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_detect_recurring_patterns(
    current_user: Annotated[User, Depends(require_role("ADMIN"))],
):
    """Enqueue the detect_recurring_patterns Celery task.
    Falls back to synchronous inline execution if Celery is unavailable.
    """
    try:
        from app.workers.tasks import detect_recurring_patterns
        task = detect_recurring_patterns.delay()
        return {"status": "queued", "task_id": str(task.id)}
    except Exception as exc:
        logger.warning("Celery unavailable, running inline: %s", exc)
        # Inline fallback — import and run directly (no retry logic)
        try:
            from app.workers.tasks import detect_recurring_patterns
            result = detect_recurring_patterns()
            return {"status": "completed_inline", "result": result}
        except Exception as inline_exc:
            logger.exception("Inline detect_recurring_patterns failed: %s", inline_exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Pattern detection failed: {inline_exc}",
            )
