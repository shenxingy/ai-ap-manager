"""Invoice upload, list, and detail API endpoints."""
import uuid
import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.deps import get_current_user, require_role
from app.db.session import get_session
from app.models.invoice import Invoice, InvoiceLineItem, ExtractionResult
from app.models.user import User
from app.schemas.invoice import (
    AuditLogOut,
    InvoiceDetail,
    InvoiceListItem,
    InvoiceListResponse,
    InvoiceUploadResponse,
)
from app.services import storage as storage_svc

logger = logging.getLogger(__name__)

router = APIRouter()

# ─── Constants ───

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
}
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB


# ─── Upload endpoint ───

@router.post(
    "/upload",
    response_model=InvoiceUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an invoice PDF or image",
)
async def upload_invoice(
    file: Annotated[UploadFile, File(description="PDF or image (JPEG/PNG), max 20 MB")],
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("AP_CLERK", "AP_ANALYST", "ADMIN"))],
):
    # Validate MIME type
    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{content_type}'. Allowed: PDF, JPEG, PNG.",
        )

    # Read file content
    content = await file.read()
    file_size = len(content)

    if file_size == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")
    if file_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds 20 MB limit ({file_size} bytes).",
        )

    # Generate invoice ID up-front so we can use it in the storage path
    invoice_id = uuid.uuid4()
    original_filename = file.filename or "invoice"
    object_name = f"invoices/{invoice_id}/{original_filename}"

    # Upload to MinIO
    try:
        storage_svc.upload_file(
            bucket=settings.MINIO_BUCKET_NAME,
            object_name=object_name,
            data=content,
            content_type=content_type,
        )
    except Exception as exc:
        logger.error("MinIO upload failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to store invoice file. Please try again.",
        )

    # Persist Invoice record
    invoice = Invoice(
        id=invoice_id,
        status="ingested",
        storage_path=object_name,
        file_name=original_filename,
        mime_type=content_type,
        file_size_bytes=file_size,
        source="upload",
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)

    # Enqueue Celery processing task (import here to avoid circular imports)
    try:
        from app.workers.tasks import process_invoice  # noqa: PLC0415
        process_invoice.delay(str(invoice_id))
    except Exception as exc:
        logger.warning("Failed to enqueue process_invoice task: %s", exc)
        # Not fatal — invoice is stored; can be requeued manually

    return InvoiceUploadResponse(
        invoice_id=invoice.id,
        status=invoice.status,
        message="Invoice uploaded successfully. Extraction queued.",
    )


# ─── List endpoint ───

@router.get(
    "",
    response_model=InvoiceListResponse,
    summary="List invoices with optional filters",
)
async def list_invoices(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    invoice_status: str | None = Query(default=None, alias="status"),
    vendor_id: uuid.UUID | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
):
    stmt = select(Invoice).where(Invoice.deleted_at.is_(None))

    if invoice_status:
        stmt = stmt.where(Invoice.status == invoice_status)
    if vendor_id:
        stmt = stmt.where(Invoice.vendor_id == vendor_id)
    if date_from:
        stmt = stmt.where(Invoice.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Invoice.created_at <= date_to)

    # Total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # Paginated results
    offset = (page - 1) * page_size
    stmt = stmt.order_by(Invoice.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(stmt)
    invoices = result.scalars().all()

    return InvoiceListResponse(
        items=[InvoiceListItem.model_validate(inv) for inv in invoices],
        total=total,
        page=page,
        page_size=page_size,
    )


# ─── Detail endpoint ───

@router.get(
    "/{invoice_id}",
    response_model=InvoiceDetail,
    summary="Get full invoice detail including line items and extraction results",
)
async def get_invoice(
    invoice_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    stmt = (
        select(Invoice)
        .where(Invoice.id == invoice_id, Invoice.deleted_at.is_(None))
        .options(
            selectinload(Invoice.line_items),
            selectinload(Invoice.extraction_results),
        )
    )
    result = await db.execute(stmt)
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")
    return InvoiceDetail.model_validate(invoice)


# ─── GL suggestions endpoint ───

@router.get(
    "/{invoice_id}/gl-suggestions",
    summary="Get GL account coding suggestions for invoice lines",
)
async def get_gl_suggestions(
    invoice_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("AP_CLERK", "AP_ANALYST", "ADMIN"))],
):
    from app.services.gl_coding import suggest_gl_codes
    from app.schemas.gl_coding import GLLineSuggestion, GLSuggestionResponse

    raw = await suggest_gl_codes(db, invoice_id)
    suggestions = [GLLineSuggestion(**item) for item in raw]
    return GLSuggestionResponse(invoice_id=invoice_id, suggestions=suggestions)


# ─── Audit history endpoint ───

@router.get(
    "/{invoice_id}/audit",
    response_model=list[AuditLogOut],
    summary="Full audit history for an invoice (chronological)",
)
async def get_invoice_audit(
    invoice_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("AP_CLERK", "AP_ANALYST", "AP_MANAGER", "APPROVER", "ADMIN", "AUDITOR"))],
):
    from app.models.audit import AuditLog
    stmt = (
        select(AuditLog)
        .where(AuditLog.entity_type == "invoice", AuditLog.entity_id == invoice_id)
        .order_by(AuditLog.created_at.asc())
    )
    logs = (await db.execute(stmt)).scalars().all()
    return logs
