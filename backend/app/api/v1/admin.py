"""Admin user management endpoints."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_role
from app.core.security import hash_password
from app.db.session import get_session
from app.models.user import User
from app.schemas.admin_user import (
    AdminUserCreate,
    AdminUserListResponse,
    AdminUserOut,
    AdminUserUpdate,
)

router = APIRouter()


# ─── GET /admin/users ───


@router.get(
    "/users",
    response_model=AdminUserListResponse,
    summary="List users with pagination",
    dependencies=[Depends(require_role("ADMIN"))],
)
async def list_users(
    db: Annotated[AsyncSession, Depends(get_session)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    role: str | None = Query(default=None),
):
    """Return paginated list of users. ADMIN only."""
    stmt = select(User).where(User.deleted_at.is_(None))

    if role:
        stmt = stmt.where(User.role == role)

    # Total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # Paginated results
    offset = (page - 1) * page_size
    stmt = stmt.order_by(User.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(stmt)
    users = result.scalars().all()

    return AdminUserListResponse(
        items=[AdminUserOut.model_validate(user) for user in users],
        total=total,
        page=page,
        page_size=page_size,
    )


# ─── POST /admin/users ───


@router.post(
    "/users",
    response_model=AdminUserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user",
    dependencies=[Depends(require_role("ADMIN"))],
)
async def create_user(
    user_data: AdminUserCreate,
    db: Annotated[AsyncSession, Depends(get_session)],
):
    """Create a new user. ADMIN only."""
    # Check if email already exists
    result = await db.execute(
        select(User).where(User.email == user_data.email, User.deleted_at.is_(None))
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already exists",
        )

    # Create new user
    new_user = User(
        email=user_data.email,
        name=user_data.name,
        password_hash=hash_password(user_data.password),
        role=user_data.role,
        is_active=True,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return AdminUserOut.model_validate(new_user)


# ─── PATCH /admin/users/{id} ───


@router.patch(
    "/users/{user_id}",
    response_model=AdminUserOut,
    summary="Update a user",
    dependencies=[Depends(require_role("ADMIN"))],
)
async def update_user(
    user_id: uuid.UUID,
    user_data: AdminUserUpdate,
    db: Annotated[AsyncSession, Depends(get_session)],
):
    """Update user fields. ADMIN only."""
    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Update fields if provided
    if user_data.name is not None:
        user.name = user_data.name
    if user_data.role is not None:
        user.role = user_data.role
    if user_data.is_active is not None:
        user.is_active = user_data.is_active

    await db.commit()
    await db.refresh(user)

    return AdminUserOut.model_validate(user)
