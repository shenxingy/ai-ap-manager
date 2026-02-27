"""User API endpoints."""
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter()


class CurrentUserResponse(BaseModel):
    """Current user information."""

    id: str
    email: str
    name: str
    role: str


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
