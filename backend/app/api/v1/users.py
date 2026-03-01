"""User API endpoints."""
import copy
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_session
from app.models.user import User

router = APIRouter()

# ─── Default Notification Prefs ───

DEFAULT_PREFS: dict[str, Any] = {
    "email": {"approval_request": True, "fraud_alert": True, "exception_created": True},
    "slack": {"approval_request": False, "fraud_alert": True, "exception_created": False},
    "in_app": {"approval_request": True, "fraud_alert": True, "exception_created": True},
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep-merge override into base; returns new dict."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


# ─── Schemas ───

class CurrentUserResponse(BaseModel):
    """Current user information."""

    id: str
    email: str
    name: str
    role: str


class NotificationPrefsResponse(BaseModel):
    """User notification preferences."""

    email: dict[str, bool]
    slack: dict[str, bool]
    in_app: dict[str, bool]


class NotificationPrefsUpdate(BaseModel):
    """Partial update for notification preferences."""

    email: dict[str, bool] | None = None
    slack: dict[str, bool] | None = None
    in_app: dict[str, bool] | None = None


# ─── Endpoints ───

@router.get(
    "/me",
    response_model=CurrentUserResponse,
    summary="Get current authenticated user info",
)
async def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Return the authenticated user's profile information."""
    return CurrentUserResponse(
        id=str(current_user.id),
        email=current_user.email,
        name=current_user.name,
        role=current_user.role,
    )


@router.get(
    "/me/notification-prefs",
    response_model=NotificationPrefsResponse,
    summary="Get current user's notification preferences",
)
async def get_notification_prefs(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Return the user's notification preferences, or defaults if not set."""
    prefs = current_user.notification_prefs or {}
    merged = _deep_merge(DEFAULT_PREFS, prefs)
    return NotificationPrefsResponse(**merged)


@router.patch(
    "/me/notification-prefs",
    response_model=NotificationPrefsResponse,
    summary="Update current user's notification preferences",
)
async def update_notification_prefs(
    body: NotificationPrefsUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
):
    """Deep-merge the provided prefs with existing ones and save."""
    existing = current_user.notification_prefs or {}
    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    merged = _deep_merge(existing, update_data)

    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one()
    user.notification_prefs = merged
    await db.commit()
    await db.refresh(user)

    final = _deep_merge(DEFAULT_PREFS, user.notification_prefs or {})
    return NotificationPrefsResponse(**final)
