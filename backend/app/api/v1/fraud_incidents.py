"""Fraud incidents API endpoints."""
import uuid
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role
from app.db.session import get_session
from app.models.fraud_incident import FraudIncident
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Schemas ───

class FraudIncidentOut(BaseModel):
    id: uuid.UUID
    invoice_id: uuid.UUID
    score_at_flag: int
    triggered_signals: list
    reviewed_by: uuid.UUID | None
    outcome: str
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FraudIncidentListResponse(BaseModel):
    items: list[FraudIncidentOut]
    total: int


class FraudIncidentUpdate(BaseModel):
    outcome: str | None = None   # genuine, false_positive, pending
    notes: str | None = None


# ─── GET /fraud-incidents ───

@router.get(
    "",
    response_model=FraudIncidentListResponse,
    summary="List fraud incidents (ADMIN, AP_ANALYST)",
)
async def list_fraud_incidents(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("ADMIN", "AP_ANALYST"))],
    outcome: str | None = Query(default=None, description="Filter by outcome: pending|genuine|false_positive"),
    skip: int = Query(default=0, ge=0, description="Number of records to skip"),
    limit: int = Query(default=50, ge=1, le=500, description="Number of records to return"),
):
    stmt = select(FraudIncident).order_by(FraudIncident.created_at.desc())
    if outcome:
        stmt = stmt.where(FraudIncident.outcome == outcome)

    # Get total count
    count_stmt = select(func.count()).select_from(FraudIncident)
    if outcome:
        count_stmt = count_stmt.where(FraudIncident.outcome == outcome)
    total = await db.scalar(count_stmt) or 0

    # Get paginated results
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    items = [FraudIncidentOut.model_validate(row) for row in result.scalars().all()]

    return FraudIncidentListResponse(items=items, total=total)


# ─── PATCH /fraud-incidents/{id} ───

@router.patch(
    "/{incident_id}",
    response_model=FraudIncidentOut,
    summary="Update fraud incident outcome and notes (ADMIN, AP_ANALYST)",
)
async def update_fraud_incident(
    incident_id: uuid.UUID,
    body: FraudIncidentUpdate,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("ADMIN", "AP_ANALYST"))],
):
    result = await db.execute(
        select(FraudIncident).where(FraudIncident.id == incident_id)
    )
    incident = result.scalars().first()

    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fraud incident not found.")

    valid_outcomes = {"genuine", "false_positive", "pending"}
    if body.outcome is not None:
        if body.outcome not in valid_outcomes:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"outcome must be one of: {', '.join(sorted(valid_outcomes))}",
            )
        incident.outcome = body.outcome
        incident.reviewed_by = current_user.id

    if body.notes is not None:
        incident.notes = body.notes

    await db.commit()
    await db.refresh(incident)
    return FraudIncidentOut.model_validate(incident)
