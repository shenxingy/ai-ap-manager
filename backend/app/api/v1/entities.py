"""Entity management API endpoints — CRUD for entities."""
import logging
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_role
from app.db.session import get_session
from app.models.entity import Entity
from app.services import audit as audit_svc

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Schemas ───


class EntityCreate(BaseModel):
    """Create a new entity."""

    name: str
    tax_id: str | None = None
    base_currency: str = "USD"
    timezone: str = "UTC"
    contact_info: str | None = None


class EntityOut(BaseModel):
    """Entity response schema."""

    id: uuid.UUID
    name: str
    tax_id: str | None
    base_currency: str
    timezone: str
    contact_info: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EntityListResponse(BaseModel):
    """List of entities."""

    items: list[EntityOut]
    total: int


# ─── List entities ───


@router.get(
    "",
    response_model=EntityListResponse,
    summary="List all entities (authenticated users)",
)
async def list_entities(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[Any, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    """List all non-deleted entities."""
    # Total count
    count_stmt = select(func.count()).select_from(
        select(Entity).where(Entity.deleted_at.is_(None)).subquery()
    )
    total = (await db.execute(count_stmt)).scalar_one()

    # Query with pagination
    offset = (page - 1) * page_size
    stmt = (
        select(Entity)
        .where(Entity.deleted_at.is_(None))
        .order_by(Entity.name.asc())
        .offset(offset)
        .limit(page_size)
    )
    entities = (await db.execute(stmt)).scalars().all()

    items = [EntityOut.model_validate(e) for e in entities]
    return EntityListResponse(items=items, total=total)


# ─── Create entity ───


@router.post(
    "",
    response_model=EntityOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new entity (ADMIN)",
)
async def create_entity(
    body: EntityCreate,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[Any, Depends(require_role("ADMIN"))],
):
    """Create a new entity."""
    # Check if entity with same name already exists
    existing = (
        await db.execute(
            select(Entity).where(Entity.name == body.name, Entity.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An entity with name '{body.name}' already exists.",
        )

    entity = Entity(
        name=body.name,
        tax_id=body.tax_id,
        base_currency=body.base_currency,
        timezone=body.timezone,
        contact_info=body.contact_info,
    )
    db.add(entity)
    await db.flush()  # Get ID before audit log

    audit_svc.log(
        db,
        action="entity_created",
        entity_type="entity",
        entity_id=entity.id,
        actor_id=current_user.id,
        actor_email=current_user.email,
        after=body.model_dump(exclude_none=True),
    )

    await db.commit()
    await db.refresh(entity)

    return EntityOut.model_validate(entity)
