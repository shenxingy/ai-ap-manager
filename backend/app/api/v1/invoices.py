"""Invoice upload, list, and detail API endpoints."""
import uuid
import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.deps import get_current_user, require_role
from app.db.session import get_session
from app.models.invoice import Invoice, InvoiceLineItem, ExtractionResult
from app.models.approval import VendorMessage
from app.models.user import User
from app.schemas.invoice import (
    AuditLogOut,
    GLBulkUpdate,
    GLBulkUpdateResponse,
    InvoiceDetail,
    InvoiceListItem,
    InvoiceListResponse,
    InvoiceUploadResponse,
    StatusOverrideRequest,
    StatusOverrideResponse,
)
from app.services import storage as storage_svc
from app.services import audit as audit_svc

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


# ─── Request/Response schemas ───


class FieldCorrectionRequest(BaseModel):
    """Request to correct an invoice or line item field."""

    field_name: str
    corrected_value: Any


class FieldCorrectionResponse(BaseModel):
    """Response after field correction."""

    invoice_id: uuid.UUID
    field_name: str
    old_value: Any
    new_value: Any
    message: str


class GLCodingRequest(BaseModel):
    """Request to update GL account coding for a line item."""

    gl_account: str
    cost_center: str | None = None


class GLCodingResponse(BaseModel):
    """Response after GL coding update."""

    line_id: uuid.UUID
    gl_account: str
    cost_center: str | None
    status: str  # "confirmed" if matches suggestion, "overridden" if user input differs


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
    current_user: Annotated[User, Depends(require_role("AP_CLERK", "AP_ANALYST", "AP_MANAGER", "APPROVER", "ADMIN", "AUDITOR"))],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    invoice_status: str | None = Query(default=None, alias="status"),
    vendor_id: uuid.UUID | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    overdue: bool = Query(default=False, description="If true, return only overdue pending invoices"),
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
    if overdue:
        from sqlalchemy import func as sqlfunc
        stmt = stmt.where(
            Invoice.due_date < sqlfunc.now(),
            Invoice.status.in_(["ingested", "extracting", "extracted", "matching", "matched", "exception"]),
        )

    # Total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # Paginated results
    offset = (page - 1) * page_size
    stmt = stmt.order_by(Invoice.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(stmt)
    invoices = result.scalars().all()

    # Compute unread vendor messages for each invoice
    items = []
    for inv in invoices:
        item = InvoiceListItem.model_validate(inv)

        # Count inbound messages since the last outbound message
        # Subquery: max created_at of outbound messages
        outbound_max = select(func.max(VendorMessage.created_at)).where(
            VendorMessage.invoice_id == inv.id,
            VendorMessage.direction == "outbound",
        )

        # Count inbound messages after the last outbound (or all inbound if no outbound)
        unread_stmt = select(func.count()).select_from(VendorMessage).where(
            VendorMessage.invoice_id == inv.id,
            VendorMessage.direction == "inbound",
            VendorMessage.created_at > outbound_max.correlate(VendorMessage),
        )
        unread_result = await db.execute(unread_stmt)
        item.unread_vendor_messages = unread_result.scalar_one() or 0

        items.append(item)

    return InvoiceListResponse(
        items=items,
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
    current_user: Annotated[User, Depends(require_role("AP_CLERK", "AP_ANALYST", "AP_MANAGER", "APPROVER", "ADMIN", "AUDITOR"))],
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


# ─── Fraud score endpoint ───

@router.get(
    "/{invoice_id}/fraud-score",
    summary="Get fraud score and triggered signals for an invoice",
)
async def get_fraud_score(
    invoice_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("AP_ANALYST", "ADMIN", "AUDITOR"))],
):
    from app.models.invoice import Invoice
    stmt = select(Invoice).where(Invoice.id == invoice_id, Invoice.deleted_at.is_(None))
    invoice = (await db.execute(stmt)).scalars().first()
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    score = invoice.fraud_score or 0
    return {
        "invoice_id": str(invoice_id),
        "fraud_score": score,
        "risk_level": (
            "critical" if score >= settings.FRAUD_SCORE_CRITICAL_THRESHOLD
            else "high" if score >= settings.FRAUD_SCORE_HIGH_THRESHOLD
            else "medium" if score >= settings.FRAUD_SCORE_MEDIUM_THRESHOLD
            else "low"
        ),
    }


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


# ─── Field correction endpoint ───

@router.patch(
    "/{invoice_id}/fields",
    response_model=FieldCorrectionResponse,
    summary="Correct an invoice or line item field",
)
async def correct_invoice_field(
    invoice_id: uuid.UUID,
    body: FieldCorrectionRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("AP_ANALYST", "ADMIN"))],
):
    """Correct an invoice field value. Supports both Invoice and InvoiceLineItem fields."""
    # Load invoice
    stmt = select(Invoice).where(Invoice.id == invoice_id, Invoice.deleted_at.is_(None))
    invoice = (await db.execute(stmt)).scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")

    # Check if field exists on Invoice model
    invoice_fields = {
        "invoice_number",
        "total_amount",
        "vendor_name_raw",
        "invoice_date",
        "due_date",
        "currency",
        "subtotal",
        "tax_amount",
        "payment_terms",
        "vendor_address_raw",
        "remit_to",
        "notes",
    }

    old_value = None
    if body.field_name in invoice_fields:
        # Update Invoice field
        if hasattr(invoice, body.field_name):
            old_value = getattr(invoice, body.field_name)
            setattr(invoice, body.field_name, body.corrected_value)
            db.add(invoice)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Field '{body.field_name}' does not exist on Invoice.",
            )
    else:
        # Try to match to InvoiceLineItem field
        line_fields = {"description", "quantity", "unit_price", "unit", "line_total", "category"}
        if body.field_name not in line_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Field '{body.field_name}' not recognized on Invoice or InvoiceLineItem.",
            )
        # For line item fields, we cannot update without knowing which line — this is a limitation
        # of the PATCH endpoint. Return 400.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Line item field '{body.field_name}' requires line_id. Use PUT /invoices/{{id}}/lines/{{line_id}}/... endpoints.",
        )

    # Write audit log
    await db.execute(
        select(1)  # dummy select to ensure db session is ready for flush
    )
    audit_svc.log(
        db,
        action="field_corrected",
        entity_type="invoice",
        entity_id=invoice_id,
        actor_id=current_user.id,
        actor_email=current_user.email,
        before={body.field_name: old_value},
        after={body.field_name: body.corrected_value},
    )

    # Log AI feedback for correction pattern analysis
    from app.services.feedback import log_field_correction  # noqa: PLC0415
    await log_field_correction(
        db=db,
        invoice_id=invoice_id,
        field_name=body.field_name,
        old_value=old_value,
        new_value=body.corrected_value,
        actor_id=current_user.id,
        actor_email=current_user.email,
        vendor_id=invoice.vendor_id,
    )

    await db.commit()

    # Auto-trigger re-match if invoice is stuck in exception state
    if invoice.status == "exception":
        try:
            from app.workers.tasks import process_invoice  # noqa: PLC0415
            process_invoice.apply_async(args=[str(invoice_id)])
            logger.info(
                "correct_invoice_field: re-queued process_invoice for exception invoice %s",
                invoice_id,
            )
        except Exception as exc:
            logger.warning(
                "correct_invoice_field: failed to re-queue process_invoice for %s: %s",
                invoice_id, exc,
            )

    return FieldCorrectionResponse(
        invoice_id=invoice_id,
        field_name=body.field_name,
        old_value=old_value,
        new_value=body.corrected_value,
        message="Field corrected successfully.",
    )


# ─── GL coding endpoint ───

@router.put(
    "/{invoice_id}/lines/{line_id}/gl",
    response_model=GLCodingResponse,
    summary="Update GL account coding for an invoice line item",
)
async def update_gl_coding(
    invoice_id: uuid.UUID,
    line_id: uuid.UUID,
    body: GLCodingRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("AP_ANALYST", "ADMIN"))],
):
    """Update GL account and optionally cost center for an invoice line item."""
    # Load invoice
    stmt = select(Invoice).where(Invoice.id == invoice_id, Invoice.deleted_at.is_(None))
    invoice = (await db.execute(stmt)).scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")

    # Load line item
    stmt = select(InvoiceLineItem).where(
        InvoiceLineItem.id == line_id,
        InvoiceLineItem.invoice_id == invoice_id,
    )
    line_item = (await db.execute(stmt)).scalar_one_or_none()
    if line_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line item not found.")

    # Determine if this is a confirmation (matches suggestion) or override
    is_confirmed = line_item.gl_account_suggested and line_item.gl_account_suggested == body.gl_account
    status_str = "confirmed" if is_confirmed else "overridden"

    # Store old values for audit
    old_gl_account = line_item.gl_account
    old_cost_center = line_item.cost_center

    # Update fields
    line_item.gl_account = body.gl_account
    if body.cost_center is not None:
        line_item.cost_center = body.cost_center

    db.add(line_item)

    # Write audit log
    audit_svc.log(
        db,
        action="gl_coding_" + status_str,
        entity_type="invoice_line_item",
        entity_id=line_id,
        actor_id=current_user.id,
        actor_email=current_user.email,
        before={"gl_account": old_gl_account, "cost_center": old_cost_center},
        after={"gl_account": body.gl_account, "cost_center": body.cost_center},
    )

    # Log GL correction feedback for pattern analysis (only if overriding suggestion)
    if status_str == "overridden":
        from app.services.feedback import log_gl_correction  # noqa: PLC0415
        await log_gl_correction(
            db=db,
            invoice_id=invoice_id,
            line_id=line_id,
            old_gl_account=old_gl_account,
            new_gl_account=body.gl_account,
            actor_id=current_user.id,
            actor_email=current_user.email,
            vendor_id=invoice.vendor_id,
        )

    await db.commit()

    return GLCodingResponse(
        line_id=line_id,
        gl_account=body.gl_account,
        cost_center=body.cost_center,
        status=status_str,
    )


# ─── Bulk GL coding endpoint ───

@router.put(
    "/{invoice_id}/lines/gl-bulk",
    response_model=GLBulkUpdateResponse,
    summary="Bulk-update GL account coding for multiple invoice line items",
)
async def bulk_update_gl_coding(
    invoice_id: uuid.UUID,
    body: GLBulkUpdate,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("AP_ANALYST", "ADMIN"))],
):
    """Update GL account coding for multiple line items in one request."""
    # Verify invoice exists
    stmt = select(Invoice).where(Invoice.id == invoice_id, Invoice.deleted_at.is_(None))
    invoice = (await db.execute(stmt)).scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")

    updated = 0
    errors = 0

    for item in body.lines:
        stmt = select(InvoiceLineItem).where(
            InvoiceLineItem.id == item.line_id,
            InvoiceLineItem.invoice_id == invoice_id,
        )
        line_item = (await db.execute(stmt)).scalar_one_or_none()
        if line_item is None:
            errors += 1
            continue

        is_confirmed = line_item.gl_account_suggested and line_item.gl_account_suggested == item.gl_account
        status_str = "confirmed" if is_confirmed else "overridden"

        old_gl_account = line_item.gl_account
        old_cost_center = line_item.cost_center

        line_item.gl_account = item.gl_account
        if item.cost_center is not None:
            line_item.cost_center = item.cost_center

        db.add(line_item)

        audit_svc.log(
            db,
            action="gl_coding_" + status_str,
            entity_type="invoice_line_item",
            entity_id=item.line_id,
            actor_id=current_user.id,
            actor_email=current_user.email,
            before={"gl_account": old_gl_account, "cost_center": old_cost_center},
            after={"gl_account": item.gl_account, "cost_center": item.cost_center},
        )
        updated += 1

    await db.commit()

    return GLBulkUpdateResponse(updated=updated, errors=errors)


# ─── Status override endpoint ───

# Valid state machine transitions
_VALID_TRANSITIONS: dict[str, list[str]] = {
    "ingested":   ["extracting", "cancelled"],
    "extracting": ["extracted", "cancelled"],
    "extracted":  ["matching", "cancelled"],
    "matching":   ["matched", "exception", "cancelled"],
    "matched":    ["approved", "rejected", "cancelled"],
    "exception":  ["matched", "approved", "rejected", "cancelled"],
    "approved":   ["paid", "cancelled"],
    "paid":       [],
    "rejected":   ["cancelled"],
    "cancelled":  [],
}

_ALL_STATUSES = set(_VALID_TRANSITIONS.keys())


@router.patch(
    "/{invoice_id}/status",
    response_model=StatusOverrideResponse,
    summary="Admin-only forced status override for an invoice",
)
async def override_invoice_status(
    invoice_id: uuid.UUID,
    body: StatusOverrideRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("ADMIN"))],
):
    """Force an invoice to a new status. Validates against the state machine.
    Only ADMIN users may call this endpoint.
    """
    if body.status not in _ALL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status '{body.status}'. Must be one of: {sorted(_ALL_STATUSES)}.",
        )

    stmt = select(Invoice).where(Invoice.id == invoice_id, Invoice.deleted_at.is_(None))
    invoice = (await db.execute(stmt)).scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")

    old_status = invoice.status
    allowed = _VALID_TRANSITIONS.get(old_status, [])

    if body.status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid transition '{old_status}' → '{body.status}'. "
                f"Allowed next states: {allowed or ['(none — terminal state)']}"
            ),
        )

    invoice.status = body.status
    db.add(invoice)

    audit_svc.log(
        db,
        action="manual_status_override",
        entity_type="invoice",
        entity_id=invoice_id,
        actor_id=current_user.id,
        actor_email=current_user.email,
        before={"status": old_status},
        after={"status": body.status},
        notes=f"Admin forced status: {old_status} → {body.status}",
    )

    await db.commit()

    return StatusOverrideResponse(
        invoice_id=invoice_id,
        old_status=old_status,
        new_status=body.status,
        message=f"Invoice status updated from '{old_status}' to '{body.status}'.",
    )


# ─── Vendor Communication Hub ───


class SendMessageRequest(BaseModel):
    """Request to send a message to a vendor (or record an internal note)."""

    body: str
    sender_email: str
    is_internal: bool = False
    attachments: list = []


class MessageOut(BaseModel):
    """A vendor message record."""

    id: uuid.UUID
    invoice_id: uuid.UUID
    sender_id: uuid.UUID | None
    sender_email: str | None
    direction: str
    body: str
    is_internal: bool
    attachments: list
    created_at: datetime

    model_config = {"from_attributes": True}


@router.post(
    "/{invoice_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Send a message to the vendor (or record internal AP note)",
)
async def send_vendor_message(
    invoice_id: uuid.UUID,
    body: SendMessageRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("AP_ANALYST", "AP_MANAGER", "ADMIN"))],
):
    # Verify invoice exists
    stmt = select(Invoice).where(Invoice.id == invoice_id, Invoice.deleted_at.is_(None))
    invoice = (await db.execute(stmt)).scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")

    msg = VendorMessage(
        invoice_id=invoice_id,
        sender_id=current_user.id,
        sender_email=body.sender_email or current_user.email,
        direction="outbound",
        body=body.body,
        is_internal=body.is_internal,
        attachments=body.attachments or [],
    )
    db.add(msg)

    audit_svc.log(
        db,
        action="vendor_message.sent",
        entity_type="invoice",
        entity_id=invoice_id,
        actor_id=current_user.id,
        actor_email=current_user.email,
        after={
            "direction": "outbound",
            "is_internal": body.is_internal,
            "body_preview": body.body[:120],
        },
    )

    await db.flush()

    # Mock email send for external messages
    if not body.is_internal:
        reply_token = str(msg.id)
        logger.info(
            "[EMAIL MOCK] To: %s | Invoice: %s | ReplyToken: %s | Body: %s",
            body.sender_email, invoice_id, reply_token, body.body[:80],
        )

    await db.commit()
    await db.refresh(msg)
    return MessageOut.model_validate(msg)


@router.get(
    "/{invoice_id}/messages",
    response_model=list[MessageOut],
    summary="List all messages for an invoice (internal + vendor-facing)",
)
async def list_vendor_messages(
    invoice_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("AP_CLERK", "AP_ANALYST", "AP_MANAGER", "ADMIN", "AUDITOR"))],
):
    stmt = select(Invoice).where(Invoice.id == invoice_id, Invoice.deleted_at.is_(None))
    invoice = (await db.execute(stmt)).scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")

    msgs_stmt = (
        select(VendorMessage)
        .where(VendorMessage.invoice_id == invoice_id)
        .order_by(VendorMessage.created_at.asc())
    )
    msgs = (await db.execute(msgs_stmt)).scalars().all()
    return [MessageOut.model_validate(m) for m in msgs]
