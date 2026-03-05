"""In-app notification center API endpoints."""
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_session
from app.models.notification import Notification
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Schemas ───

class NotificationOut(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    message: str
    invoice_id: uuid.UUID | None
    read_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── GET /notifications ───

@router.get("", response_model=list[NotificationOut], summary="List current user's notifications")
async def list_notifications(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[Notification]:
    """Return up to 50 notifications for the current user, unread first."""
    from sqlalchemy import case

    stmt = (
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(
            case((Notification.read_at.is_(None), 0), else_=1),
            Notification.created_at.desc(),
        )
        .limit(50)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ─── PATCH /notifications/{id}/read ───

@router.patch("/{notification_id}/read", response_model=NotificationOut, summary="Mark one notification as read")
async def mark_notification_read(
    notification_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Notification:
    """Mark a single notification as read."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notif = result.scalars().first()
    if notif is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    if notif.read_at is None:
        notif.read_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(notif)

    return notif


# ─── POST /notifications/read-all ───

@router.post("/read-all", summary="Mark all notifications as read")
async def mark_all_read(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Mark all unread notifications for the current user as read."""
    now = datetime.now(UTC)
    await db.execute(
        update(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.read_at.is_(None),
        )
        .values(read_at=now)
    )
    await db.commit()
    return {"ok": True}
