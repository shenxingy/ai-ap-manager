"""Admin user management and exception routing endpoints."""
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_role
from app.core.security import hash_password
from app.db.session import get_session
from app.models.user import User
from app.models.exception_routing import ExceptionRoutingRule
from app.schemas.admin_user import (
    AdminUserCreate,
    AdminUserListResponse,
    AdminUserOut,
    AdminUserUpdate,
)
from app.schemas.exception_routing import (
    ExceptionRoutingRuleIn,
    ExceptionRoutingRuleOut,
    ExceptionRoutingRuleUpdate,
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


# ─── GET /admin/exception-routing ───


@router.get(
    "/exception-routing",
    response_model=list[ExceptionRoutingRuleOut],
    summary="List all exception routing rules (ADMIN only)",
    dependencies=[Depends(require_role("ADMIN"))],
)
async def list_exception_routing_rules(
    db: Annotated[AsyncSession, Depends(get_session)],
):
    """Return all exception routing rules ordered by exception_code then priority."""
    result = await db.execute(
        select(ExceptionRoutingRule).order_by(
            ExceptionRoutingRule.exception_code,
            ExceptionRoutingRule.priority.desc(),
        )
    )
    rules = result.scalars().all()
    return [ExceptionRoutingRuleOut.model_validate(r) for r in rules]


# ─── POST /admin/exception-routing ───


@router.post(
    "/exception-routing",
    response_model=ExceptionRoutingRuleOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new exception routing rule (ADMIN only)",
    dependencies=[Depends(require_role("ADMIN"))],
)
async def create_exception_routing_rule(
    rule_data: ExceptionRoutingRuleIn,
    db: Annotated[AsyncSession, Depends(get_session)],
):
    """Create a new exception routing rule. ADMIN only."""
    rule = ExceptionRoutingRule(
        exception_code=rule_data.exception_code,
        target_role=rule_data.target_role,
        priority=rule_data.priority,
        is_active=rule_data.is_active,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return ExceptionRoutingRuleOut.model_validate(rule)


# ─── PATCH /admin/exception-routing/{id} ───


@router.patch(
    "/exception-routing/{rule_id}",
    response_model=ExceptionRoutingRuleOut,
    summary="Update an exception routing rule (ADMIN only)",
    dependencies=[Depends(require_role("ADMIN"))],
)
async def update_exception_routing_rule(
    rule_id: uuid.UUID,
    rule_data: ExceptionRoutingRuleUpdate,
    db: Annotated[AsyncSession, Depends(get_session)],
):
    """Update target_role, priority, or is_active on a routing rule. ADMIN only."""
    result = await db.execute(
        select(ExceptionRoutingRule).where(ExceptionRoutingRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Routing rule not found",
        )

    if rule_data.target_role is not None:
        rule.target_role = rule_data.target_role
    if rule_data.priority is not None:
        rule.priority = rule_data.priority
    if rule_data.is_active is not None:
        rule.is_active = rule_data.is_active

    await db.commit()
    await db.refresh(rule)
    return ExceptionRoutingRuleOut.model_validate(rule)


# ─── Email Ingestion ───


class EmailIngestionStatus(BaseModel):
    last_polled_at: Optional[str]
    total_ingested: int
    configured: bool


@router.get(
    "/email-ingestion/status",
    response_model=EmailIngestionStatus,
    summary="Get email ingestion status (ADMIN only)",
    dependencies=[Depends(require_role("ADMIN"))],
)
async def email_ingestion_status(
    db: Annotated[AsyncSession, Depends(get_session)],
):
    """Return email ingestion configuration status and total invoices ingested via email."""
    from app.core.config import settings
    from app.models.invoice import Invoice

    # Count invoices ingested via email
    count_result = await db.execute(
        select(func.count()).select_from(Invoice).where(
            Invoice.source == "email",
            Invoice.deleted_at.is_(None),
        )
    )
    total_ingested = count_result.scalar_one()

    email_host = getattr(settings, "EMAIL_HOST", None)
    email_user = getattr(settings, "EMAIL_USER", None)
    email_password = getattr(settings, "EMAIL_PASSWORD", None)
    configured = bool(email_host and email_user and email_password)

    return EmailIngestionStatus(
        last_polled_at=None,  # not persisted; Celery beat handles scheduling
        total_ingested=total_ingested,
        configured=configured,
    )


@router.post(
    "/email-ingestion/trigger",
    summary="Manually trigger email ingestion poll (ADMIN only)",
    dependencies=[Depends(require_role("ADMIN"))],
)
async def trigger_email_ingestion():
    """Enqueue a one-off poll_ap_mailbox Celery task."""
    from app.workers.email_ingestion import poll_ap_mailbox

    poll_ap_mailbox.delay()
    return {"status": "triggered"}
