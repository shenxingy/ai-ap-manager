"""Invoice Template CRUD endpoints.

Endpoints:
  GET    /admin/invoice-templates          — list non-deleted templates
  POST   /admin/invoice-templates          — create a new template
  GET    /admin/invoice-templates/{id}     — get a single template
  DELETE /admin/invoice-templates/{id}     — soft-delete a template
"""
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role
from app.db.session import get_session
from app.models.invoice_template import InvoiceTemplate

router = APIRouter()


# ─── Schemas ───


class TemplateOut(BaseModel):
    id: uuid.UUID
    vendor_id: uuid.UUID
    name: str
    default_po_id: uuid.UUID | None
    line_items: list | None
    notes: str | None
    created_by: uuid.UUID | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TemplateCreate(BaseModel):
    vendor_id: uuid.UUID
    name: str
    default_po_id: uuid.UUID | None = None
    line_items: list | None = None
    notes: str | None = None


# ─── Endpoints ───


@router.get(
    "/admin/invoice-templates",
    response_model=list[TemplateOut],
    summary="List all non-deleted invoice templates",
)
async def list_templates(
    db: Annotated[AsyncSession, Depends(get_session)],
    _current_user: Annotated[Any, Depends(require_role("ADMIN", "AP_ANALYST"))],
):
    result = await db.execute(
        select(InvoiceTemplate)
        .where(InvoiceTemplate.deleted_at.is_(None))
        .order_by(InvoiceTemplate.created_at.desc())
    )
    return [TemplateOut.model_validate(t) for t in result.scalars().all()]


@router.post(
    "/admin/invoice-templates",
    response_model=TemplateOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new invoice template",
)
async def create_template(
    body: TemplateCreate,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[Any, Depends(require_role("ADMIN", "AP_ANALYST"))],
):
    template = InvoiceTemplate(
        vendor_id=body.vendor_id,
        name=body.name,
        default_po_id=body.default_po_id,
        line_items=body.line_items,
        notes=body.notes,
        created_by=current_user.id,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return TemplateOut.model_validate(template)


@router.get(
    "/admin/invoice-templates/{template_id}",
    response_model=TemplateOut,
    summary="Get a single invoice template",
)
async def get_template(
    template_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    _current_user: Annotated[Any, Depends(require_role("ADMIN", "AP_ANALYST"))],
):
    result = await db.execute(
        select(InvoiceTemplate).where(
            InvoiceTemplate.id == template_id,
            InvoiceTemplate.deleted_at.is_(None),
        )
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found.")
    return TemplateOut.model_validate(template)


@router.delete(
    "/admin/invoice-templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete an invoice template",
)
async def delete_template(
    template_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    _current_user: Annotated[Any, Depends(require_role("ADMIN"))],
):
    result = await db.execute(
        select(InvoiceTemplate).where(
            InvoiceTemplate.id == template_id,
            InvoiceTemplate.deleted_at.is_(None),
        )
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found.")
    template.deleted_at = datetime.now(timezone.utc)
    await db.commit()
