"""Vendor management API endpoints — CRUD for vendors, aliases, and compliance docs."""
import re
import uuid
import logging
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import require_role
from app.db.session import get_session
from app.models.vendor import Vendor, VendorAlias, VendorComplianceDoc
from app.services import audit as audit_svc
from app.schemas.vendor import (
    VendorAliasCreate,
    VendorAliasOut,
    VendorCreate,
    VendorDetail,
    VendorListItem,
    VendorListResponse,
    VendorUpdate,
    InvoiceStub,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── List vendors ───

@router.get(
    "",
    response_model=VendorListResponse,
    summary="List vendors with optional filters (AP_CLERK+)",
)
async def list_vendors(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[object, Depends(require_role("AP_CLERK", "AP_ANALYST", "AP_MANAGER", "APPROVER", "ADMIN", "AUDITOR"))],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    name: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
):
    from app.models.invoice import Invoice

    # invoice_count subquery
    inv_count_sq = (
        select(Invoice.vendor_id, func.count(Invoice.id).label("invoice_count"))
        .where(Invoice.deleted_at.is_(None), Invoice.vendor_id.is_not(None))
        .group_by(Invoice.vendor_id)
        .subquery()
    )

    stmt = (
        select(Vendor, func.coalesce(inv_count_sq.c.invoice_count, 0).label("invoice_count"))
        .outerjoin(inv_count_sq, Vendor.id == inv_count_sq.c.vendor_id)
        .where(Vendor.deleted_at.is_(None))
    )

    if name:
        stmt = stmt.where(Vendor.name.ilike(f"%{name}%"))
    if is_active is not None:
        stmt = stmt.where(Vendor.is_active == is_active)

    # Total count
    count_stmt = select(func.count()).select_from(
        select(Vendor).where(Vendor.deleted_at.is_(None)).subquery()
    )
    if name:
        count_stmt = select(func.count()).select_from(
            select(Vendor)
            .where(Vendor.deleted_at.is_(None), Vendor.name.ilike(f"%{name}%"))
            .subquery()
        )
    if is_active is not None:
        count_stmt = select(func.count()).select_from(
            select(Vendor)
            .where(
                Vendor.deleted_at.is_(None),
                Vendor.is_active == is_active,
                *([Vendor.name.ilike(f"%{name}%")] if name else []),
            )
            .subquery()
        )

    total = (await db.execute(count_stmt)).scalar_one()

    offset = (page - 1) * page_size
    stmt = stmt.order_by(Vendor.name.asc()).offset(offset).limit(page_size)
    rows = (await db.execute(stmt)).all()

    items = [
        VendorListItem(
            id=vendor.id,
            name=vendor.name,
            tax_id=vendor.tax_id,
            payment_terms=vendor.payment_terms,
            currency=vendor.currency,
            is_active=vendor.is_active,
            invoice_count=int(invoice_count),
        )
        for vendor, invoice_count in rows
    ]

    return VendorListResponse(items=items, total=total, page=page, page_size=page_size)


# ─── Get vendor detail ───

@router.get(
    "/{vendor_id}",
    response_model=VendorDetail,
    summary="Get vendor detail with aliases and recent invoices (AP_CLERK+)",
)
async def get_vendor(
    vendor_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[object, Depends(require_role("AP_CLERK", "AP_ANALYST", "AP_MANAGER", "APPROVER", "ADMIN", "AUDITOR"))],
):
    stmt = (
        select(Vendor)
        .where(Vendor.id == vendor_id, Vendor.deleted_at.is_(None))
        .options(selectinload(Vendor.aliases))
    )
    vendor = (await db.execute(stmt)).scalar_one_or_none()
    if vendor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found.")

    # Load recent 10 invoices
    from app.models.invoice import Invoice
    inv_stmt = (
        select(Invoice)
        .where(Invoice.vendor_id == vendor_id, Invoice.deleted_at.is_(None))
        .order_by(Invoice.created_at.desc())
        .limit(10)
    )
    recent_invoices = (await db.execute(inv_stmt)).scalars().all()

    detail = VendorDetail(
        id=vendor.id,
        name=vendor.name,
        tax_id=vendor.tax_id,
        bank_account=vendor.bank_account,
        bank_routing=vendor.bank_routing,
        currency=vendor.currency,
        payment_terms=vendor.payment_terms,
        email=vendor.email,
        address=vendor.address,
        is_active=vendor.is_active,
        created_at=vendor.created_at,
        updated_at=vendor.updated_at,
        aliases=[VendorAliasOut.model_validate(a) for a in vendor.aliases],
        recent_invoices=[InvoiceStub.model_validate(inv) for inv in recent_invoices],
    )
    return detail


# ─── Create vendor ───

@router.post(
    "",
    response_model=VendorDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new vendor (AP_ANALYST+)",
)
async def create_vendor(
    body: VendorCreate,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[object, Depends(require_role("AP_ANALYST", "AP_MANAGER", "ADMIN"))],
):
    # EIN format validation for USD vendors
    if body.currency == "USD" and body.tax_id:
        if not re.fullmatch(r"\d{2}-\d{7}", body.tax_id):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="For USD currency, tax_id must be in EIN format (XX-XXXXXXX).",
            )

    # 409 if tax_id already exists
    if body.tax_id:
        existing = (
            await db.execute(
                select(Vendor).where(Vendor.tax_id == body.tax_id, Vendor.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A vendor with tax_id '{body.tax_id}' already exists.",
            )

    vendor = Vendor(
        name=body.name,
        tax_id=body.tax_id,
        payment_terms=body.payment_terms,
        currency=body.currency,
        bank_account=body.bank_account,
        bank_routing=body.bank_routing,
        email=body.email,
        address=body.address,
        is_active=body.is_active,
    )
    db.add(vendor)
    await db.flush()  # get id before audit log

    audit_svc.log(
        db,
        action="vendor_created",
        entity_type="vendor",
        entity_id=vendor.id,
        actor_id=current_user.id,
        actor_email=current_user.email,
        after=body.model_dump(exclude_none=True),
    )

    await db.commit()
    await db.refresh(vendor)

    return VendorDetail(
        id=vendor.id,
        name=vendor.name,
        tax_id=vendor.tax_id,
        bank_account=vendor.bank_account,
        bank_routing=vendor.bank_routing,
        currency=vendor.currency,
        payment_terms=vendor.payment_terms,
        email=vendor.email,
        address=vendor.address,
        is_active=vendor.is_active,
        created_at=vendor.created_at,
        updated_at=vendor.updated_at,
        aliases=[],
        recent_invoices=[],
    )


# ─── Update vendor ───

@router.patch(
    "/{vendor_id}",
    response_model=VendorDetail,
    summary="Partially update a vendor (AP_ANALYST+)",
)
async def update_vendor(
    vendor_id: uuid.UUID,
    body: VendorUpdate,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[object, Depends(require_role("AP_ANALYST", "AP_MANAGER", "ADMIN"))],
):
    stmt = (
        select(Vendor)
        .where(Vendor.id == vendor_id, Vendor.deleted_at.is_(None))
        .options(selectinload(Vendor.aliases))
    )
    vendor = (await db.execute(stmt)).scalar_one_or_none()
    if vendor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found.")

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update.")

    before_state = {k: getattr(vendor, k) for k in updates}
    bank_account_changed = (
        "bank_account" in updates
        and updates["bank_account"] != vendor.bank_account
    )

    for field, value in updates.items():
        setattr(vendor, field, value)

    db.add(vendor)
    await db.flush()

    # Audit: vendor_updated
    audit_svc.log(
        db,
        action="vendor_updated",
        entity_type="vendor",
        entity_id=vendor_id,
        actor_id=current_user.id,
        actor_email=current_user.email,
        before=before_state,
        after=updates,
    )

    # Separate audit event for bank account change
    if bank_account_changed:
        audit_svc.log(
            db,
            action="bank_account_changed",
            entity_type="vendor",
            entity_id=vendor_id,
            actor_id=current_user.id,
            actor_email=current_user.email,
            before={"bank_account": before_state["bank_account"]},
            after={"bank_account": updates["bank_account"]},
        )

    await db.commit()
    await db.refresh(vendor)

    # Load recent invoices
    from app.models.invoice import Invoice
    inv_stmt = (
        select(Invoice)
        .where(Invoice.vendor_id == vendor_id, Invoice.deleted_at.is_(None))
        .order_by(Invoice.created_at.desc())
        .limit(10)
    )
    recent_invoices = (await db.execute(inv_stmt)).scalars().all()

    return VendorDetail(
        id=vendor.id,
        name=vendor.name,
        tax_id=vendor.tax_id,
        bank_account=vendor.bank_account,
        bank_routing=vendor.bank_routing,
        currency=vendor.currency,
        payment_terms=vendor.payment_terms,
        email=vendor.email,
        address=vendor.address,
        is_active=vendor.is_active,
        created_at=vendor.created_at,
        updated_at=vendor.updated_at,
        aliases=[VendorAliasOut.model_validate(a) for a in vendor.aliases],
        recent_invoices=[InvoiceStub.model_validate(inv) for inv in recent_invoices],
    )


# ─── Add alias ───

@router.post(
    "/{vendor_id}/aliases",
    response_model=VendorAliasOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add an alias to a vendor (AP_ANALYST+)",
)
async def add_vendor_alias(
    vendor_id: uuid.UUID,
    body: VendorAliasCreate,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[object, Depends(require_role("AP_ANALYST", "AP_MANAGER", "ADMIN"))],
):
    # Verify vendor exists
    vendor = (
        await db.execute(
            select(Vendor).where(Vendor.id == vendor_id, Vendor.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if vendor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found.")

    alias = VendorAlias(vendor_id=vendor_id, alias=body.alias_name)
    db.add(alias)
    await db.flush()

    audit_svc.log(
        db,
        action="vendor_alias_added",
        entity_type="vendor",
        entity_id=vendor_id,
        actor_id=current_user.id,
        actor_email=current_user.email,
        after={"alias": body.alias_name},
    )

    await db.commit()
    await db.refresh(alias)

    return VendorAliasOut.model_validate(alias)


# ─── Remove alias ───

@router.delete(
    "/{vendor_id}/aliases/{alias_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an alias from a vendor (AP_ANALYST+)",
)
async def remove_vendor_alias(
    vendor_id: uuid.UUID,
    alias_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[object, Depends(require_role("AP_ANALYST", "AP_MANAGER", "ADMIN"))],
):
    alias = (
        await db.execute(
            select(VendorAlias).where(
                VendorAlias.id == alias_id,
                VendorAlias.vendor_id == vendor_id,
            )
        )
    ).scalar_one_or_none()
    if alias is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alias not found.")

    audit_svc.log(
        db,
        action="vendor_alias_removed",
        entity_type="vendor",
        entity_id=vendor_id,
        actor_id=current_user.id,
        actor_email=current_user.email,
        before={"alias": alias.alias},
    )

    await db.delete(alias)
    await db.commit()


# ─── Compliance Documents ───


class ComplianceDocOut(BaseModel):
    """A vendor compliance document record."""

    id: uuid.UUID
    vendor_id: uuid.UUID
    doc_type: str
    file_key: str | None
    storage_path: str
    status: str
    expiry_date: date | None
    uploaded_by: uuid.UUID | None
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


@router.post(
    "/{vendor_id}/compliance-docs",
    response_model=ComplianceDocOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a compliance document for a vendor (ADMIN, AP_ANALYST+)",
)
async def upload_compliance_doc(
    vendor_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[object, Depends(require_role("AP_ANALYST", "AP_MANAGER", "ADMIN"))],
    doc_type: str = Form(..., description="W9 | W8BEN | VAT | insurance | other"),
    file: UploadFile = File(..., description="Document file"),
    expiry_date: date | None = Form(default=None),
    notes: str | None = Form(default=None),
):
    """Store a compliance document in MinIO and upsert VendorComplianceDoc record."""
    from app.core.config import settings
    from app.services import storage as storage_svc

    # Verify vendor exists
    vendor = (
        await db.execute(
            select(Vendor).where(Vendor.id == vendor_id, Vendor.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if vendor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found.")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file.")

    filename = file.filename or f"{doc_type}.pdf"
    object_key = f"compliance/{vendor_id}/{doc_type}/{filename}"

    # Upload to MinIO
    try:
        storage_svc.upload_file(
            bucket=settings.MINIO_BUCKET_NAME,
            object_name=object_key,
            data=content,
            content_type=file.content_type or "application/octet-stream",
        )
    except Exception as exc:
        logger.error("MinIO upload failed for compliance doc: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to store compliance document. Please try again.",
        )

    # Upsert VendorComplianceDoc (one active row per vendor+doc_type)
    existing = (
        await db.execute(
            select(VendorComplianceDoc).where(
                VendorComplianceDoc.vendor_id == vendor_id,
                VendorComplianceDoc.doc_type == doc_type,
            )
        )
    ).scalars().first()

    if existing:
        existing.file_key = object_key
        existing.storage_path = object_key
        existing.status = "active"
        existing.expiry_date = expiry_date
        existing.uploaded_by = current_user.id
        existing.notes = notes
        doc = existing
    else:
        doc = VendorComplianceDoc(
            vendor_id=vendor_id,
            doc_type=doc_type,
            file_key=object_key,
            storage_path=object_key,
            status="active",
            expiry_date=expiry_date,
            uploaded_by=current_user.id,
            notes=notes,
        )
        db.add(doc)

    audit_svc.log(
        db,
        action="compliance_doc.uploaded",
        entity_type="vendor",
        entity_id=vendor_id,
        actor_id=current_user.id,
        actor_email=current_user.email,
        after={"doc_type": doc_type, "file_key": object_key, "expiry_date": str(expiry_date)},
    )

    await db.commit()
    await db.refresh(doc)
    return ComplianceDocOut.model_validate(doc)


@router.get(
    "/{vendor_id}/compliance-docs",
    response_model=list[ComplianceDocOut],
    summary="List compliance documents for a vendor (AP_CLERK+)",
)
async def list_compliance_docs(
    vendor_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[object, Depends(require_role("AP_CLERK", "AP_ANALYST", "AP_MANAGER", "ADMIN", "AUDITOR"))],
):
    vendor = (
        await db.execute(
            select(Vendor).where(Vendor.id == vendor_id, Vendor.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if vendor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found.")

    docs = (
        await db.execute(
            select(VendorComplianceDoc)
            .where(VendorComplianceDoc.vendor_id == vendor_id)
            .order_by(VendorComplianceDoc.doc_type.asc())
        )
    ).scalars().all()
    return [ComplianceDocOut.model_validate(d) for d in docs]
