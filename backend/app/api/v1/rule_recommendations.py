"""Rule recommendations API — admin review of AI-generated rule suggestions."""
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role
from app.db.session import get_session
from app.models.feedback import AiFeedback, RuleRecommendation
from app.models.user import User
from app.schemas.feedback import (
    CorrectionStats,
    ReviewRequest,
    RuleRecommendationListResponse,
    RuleRecommendationOut,
)

router = APIRouter()


# ─── GET /admin/rule-recommendations ───

@router.get(
    "/rule-recommendations",
    response_model=RuleRecommendationListResponse,
    summary="List AI-generated rule recommendations (ADMIN only)",
)
async def list_rule_recommendations(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("ADMIN"))],
    rec_status: str | None = Query(default=None, alias="status"),
    rule_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    stmt = select(RuleRecommendation)
    if rec_status:
        stmt = stmt.where(RuleRecommendation.status == rec_status)
    if rule_type:
        stmt = stmt.where(RuleRecommendation.rule_type == rule_type)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    offset = (page - 1) * page_size
    stmt = stmt.order_by(RuleRecommendation.created_at.desc()).offset(offset).limit(page_size)
    recs = (await db.execute(stmt)).scalars().all()

    return RuleRecommendationListResponse(
        items=[RuleRecommendationOut.model_validate(r) for r in recs],
        total=total,
    )


# ─── POST /admin/rule-recommendations/{id}/accept ───

@router.post(
    "/rule-recommendations/{rec_id}/accept",
    response_model=RuleRecommendationOut,
    summary="Accept a rule recommendation (ADMIN only)",
)
async def accept_rule_recommendation(
    rec_id: uuid.UUID,
    body: ReviewRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("ADMIN"))],
):
    rec = (await db.execute(
        select(RuleRecommendation).where(RuleRecommendation.id == rec_id)
    )).scalar_one_or_none()
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found.")

    rec.status = "accepted"
    rec.reviewed_by = current_user.id
    rec.reviewed_at = datetime.now(timezone.utc)
    rec.review_notes = body.notes
    await db.commit()
    await db.refresh(rec)
    return RuleRecommendationOut.model_validate(rec)


# ─── POST /admin/rule-recommendations/{id}/reject ───

@router.post(
    "/rule-recommendations/{rec_id}/reject",
    response_model=RuleRecommendationOut,
    summary="Reject a rule recommendation (ADMIN only)",
)
async def reject_rule_recommendation(
    rec_id: uuid.UUID,
    body: ReviewRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("ADMIN"))],
):
    rec = (await db.execute(
        select(RuleRecommendation).where(RuleRecommendation.id == rec_id)
    )).scalar_one_or_none()
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found.")

    rec.status = "rejected"
    rec.reviewed_by = current_user.id
    rec.reviewed_at = datetime.now(timezone.utc)
    rec.review_notes = body.notes
    await db.commit()
    await db.refresh(rec)
    return RuleRecommendationOut.model_validate(rec)


# ─── GET /admin/ai-correction-stats ───

@router.get(
    "/ai-correction-stats",
    response_model=CorrectionStats,
    summary="Get AI correction statistics for the past N days (ADMIN only)",
)
async def get_correction_stats(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("ADMIN", "AP_ANALYST"))],
    period_days: int = Query(default=30, ge=1, le=365),
):
    from datetime import timedelta
    since = datetime.now(timezone.utc) - timedelta(days=period_days)

    rows = (await db.execute(
        select(
            AiFeedback.feedback_type,
            AiFeedback.field_name,
            func.count(AiFeedback.id).label("cnt"),
        )
        .where(AiFeedback.created_at >= since)
        .group_by(AiFeedback.feedback_type, AiFeedback.field_name)
    )).all()

    total = sum(r.cnt for r in rows)
    by_type: dict[str, int] = {}
    by_field: dict[str, int] = {}
    for r in rows:
        by_type[r.feedback_type] = by_type.get(r.feedback_type, 0) + r.cnt
        if r.field_name:
            by_field[r.field_name] = by_field.get(r.field_name, 0) + r.cnt

    return CorrectionStats(
        total_corrections=total,
        by_type=by_type,
        by_field=by_field,
        period_days=period_days,
    )
