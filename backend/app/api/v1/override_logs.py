"""Override log API endpoints — admin-only override history."""
import uuid
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role
from app.db.session import get_session
from app.models.override_log import OverrideLog
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Schemas ───

class OverrideLogOut(BaseModel):
    id: uuid.UUID
    invoice_id: uuid.UUID
    rule_id: uuid.UUID | None
    field_name: str
    old_value: dict | None
    new_value: dict | None
    overridden_by: uuid.UUID
    overridden_by_email: str | None = None
    reason: str | None
    created_at: str

    model_config = {"from_attributes": True}


class OverrideHistoryResponse(BaseModel):
    items: list[OverrideLogOut]
    total: int
    page: int
    page_size: int


# ─── GET /admin/override-history ───

@router.get(
    "/override-history",
    response_model=OverrideHistoryResponse,
    summary="List override history (ADMIN only)",
)
async def list_override_history(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("ADMIN"))],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    invoice_id: uuid.UUID | None = Query(default=None),
):
    """Return paginated override log entries. ADMIN only.

    Filter by invoice_id to see all overrides for a specific invoice.
    """
    stmt = select(OverrideLog)

    if invoice_id is not None:
        stmt = stmt.where(OverrideLog.invoice_id == invoice_id)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    offset = (page - 1) * page_size
    stmt = stmt.order_by(OverrideLog.created_at.desc()).offset(offset).limit(page_size)
    logs = (await db.execute(stmt)).scalars().all()

    # Batch-load actor emails
    actor_ids = list({log.overridden_by for log in logs if log.overridden_by is not None})
    email_map: dict[uuid.UUID, str] = {}
    if actor_ids:
        user_rows = (await db.execute(
            select(User).where(User.id.in_(actor_ids))
        )).scalars().all()
        email_map = {u.id: u.email for u in user_rows}

    items = []
    for log in logs:
        out = OverrideLogOut(
            id=log.id,
            invoice_id=log.invoice_id,
            rule_id=log.rule_id,
            field_name=log.field_name,
            old_value=log.old_value,
            new_value=log.new_value,
            overridden_by=log.overridden_by,
            overridden_by_email=email_map.get(log.overridden_by),
            reason=log.reason,
            created_at=log.created_at.isoformat(),
        )
        items.append(out)

    return OverrideHistoryResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )
