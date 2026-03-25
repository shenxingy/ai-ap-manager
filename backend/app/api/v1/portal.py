"""Vendor portal endpoints.

Endpoints:
  POST /portal/auth/invite              — ADMIN issues a vendor portal JWT
  GET  /portal/invoices                 — vendor lists their own invoices
  GET  /portal/invoices/{invoice_id}    — vendor views a single invoice (ownership-checked)
  POST /portal/invoices/{invoice_id}/reply — vendor replies to an inquiry (HMAC token)
"""
import hashlib
import hmac
import logging
import uuid
from datetime import datetime
from typing import Annotated

import pydantic
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_vendor_id, require_role
from app.core.limiter import limiter
from app.core.security import create_vendor_access_token
from app.db.session import get_session
from app.models.approval import VendorMessage
from app.models.invoice import Invoice
from app.models.invoice_template import InvoiceTemplate
from app.models.vendor import Vendor

logger = logging.getLogger(__name__)

# ─── Public Endpoint Documentation ───
# The following portal endpoints use vendor JWT tokens (not internal user JWT):
#   GET  /portal/invoices                        — vendor views their own invoices
#   GET  /portal/invoices/{invoice_id}           — vendor views a single invoice (ownership-checked)
#   POST /portal/invoices/{invoice_id}/dispute   — vendor submits a formal dispute
# These endpoints call get_current_vendor_id() instead of get_current_user().
# They are intentionally excluded from internal auth guards.
#
# The following portal endpoint uses HMAC token auth (not JWT):
#   POST /portal/invoices/{invoice_id}/reply     — vendor replies to an invoice inquiry
# This endpoint validates the `token` query parameter via verify_vendor_reply_token().
# It is intentionally excluded from both internal and vendor JWT auth guards.
#
# The following portal endpoint requires internal ADMIN JWT auth:
#   POST /portal/auth/invite                     — ADMIN issues a 30-day vendor portal JWT

router = APIRouter(prefix="/portal", tags=["portal"])


# ─── Schemas ───


class VendorReplyIn(BaseModel):
    """Vendor reply message body."""

    body: str = pydantic.Field(min_length=1, max_length=10000)


class VendorReplyResponse(BaseModel):
    """Response after vendor reply is recorded."""

    status: str
    message_id: uuid.UUID


class VendorInviteRequest(BaseModel):
    vendor_id: uuid.UUID


class VendorInviteResponse(BaseModel):
    token: str
    vendor_id: uuid.UUID


class VendorDisputeIn(BaseModel):
    reason: str = pydantic.Field(min_length=1, max_length=500)
    description: str = pydantic.Field(min_length=1, max_length=10000)


class VendorDisputeResponse(BaseModel):
    status: str
    exception_id: uuid.UUID
    message_id: uuid.UUID


class VendorInvoiceItem(BaseModel):
    """Minimal invoice view safe to expose to vendors."""

    id: uuid.UUID
    invoice_number: str | None
    status: str
    total_amount: float | None
    currency: str | None
    invoice_date: datetime | None
    due_date: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class VendorInvoiceListResponse(BaseModel):
    items: list[VendorInvoiceItem]
    total: int


class VendorTemplateItem(BaseModel):
    """Invoice template view safe to expose to vendors."""

    id: uuid.UUID
    name: str
    default_po_id: uuid.UUID | None
    line_items: list | None
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Token utilities ───


def create_vendor_reply_token(invoice_id: str) -> tuple[str, str]:
    """
    Create a self-verifying vendor reply token for an invoice.

    Token format: vendor_reply:{invoice_id}:{uuid}:{hmac_signature}
    The HMAC is computed over the prefix (vendor_reply:{invoice_id}:{uuid}).

    Returns (signed_token, signature).
    signed_token is sent to vendor in email URL.
    """
    prefix = f"vendor_reply:{invoice_id}:{uuid.uuid4()}"
    signature = hmac.new(
        settings.APPROVAL_TOKEN_SECRET.encode(),
        prefix.encode(),
        hashlib.sha256,
    ).hexdigest()
    signed_token = f"{prefix}:{signature}"
    return signed_token, signature


def verify_vendor_reply_token(raw_token: str) -> str | None:
    """
    Verify a vendor reply token HMAC signature and extract the invoice_id.

    Returns invoice_id if valid, None if HMAC verification fails.
    Token format: vendor_reply:{invoice_id}:{uuid}:{hmac_signature}
    """
    try:
        parts = raw_token.split(":")
        if len(parts) != 4 or parts[0] != "vendor_reply":
            return None

        invoice_id_str = parts[1]
        uuid.UUID(invoice_id_str)  # Validate UUID format

        # Recompute HMAC over prefix and compare with provided signature
        prefix = f"{parts[0]}:{parts[1]}:{parts[2]}"
        expected_sig = hmac.new(
            settings.APPROVAL_TOKEN_SECRET.encode(),
            prefix.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected_sig, parts[3]):
            return None

        return invoice_id_str

    except (ValueError, IndexError):
        return None


# ─── Endpoints ───


@router.post(
    "/auth/invite",
    response_model=VendorInviteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Issue a vendor portal JWT for a given vendor (ADMIN only)",
)
async def issue_vendor_invite(
    body: VendorInviteRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    _current_user: Annotated[object, Depends(require_role("ADMIN"))],
):
    """Generate a 30-day vendor portal JWT bound to the given vendor_id.

    The token is sent to the vendor (e.g. embedded in an email link).
    Only ADMIN can issue vendor portal tokens.
    """
    result = await db.execute(
        select(Vendor).where(Vendor.id == body.vendor_id, Vendor.deleted_at.is_(None))
    )
    vendor = result.scalar_one_or_none()
    if vendor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found.")

    token = create_vendor_access_token(str(body.vendor_id))
    return VendorInviteResponse(token=token, vendor_id=body.vendor_id)


@router.get(
    "/invoices",
    response_model=VendorInvoiceListResponse,
    summary="List invoices belonging to the authenticated vendor",
)
async def list_vendor_invoices(
    db: Annotated[AsyncSession, Depends(get_session)],
    vendor_id: Annotated[uuid.UUID, Depends(get_current_vendor_id)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Return only invoices where vendor_id matches the token claim."""
    base = (
        select(Invoice)
        .where(Invoice.vendor_id == vendor_id, Invoice.deleted_at.is_(None))
    )

    total = await db.scalar(
        select(func.count()).select_from(
            base.subquery()
        )
    ) or 0

    stmt = base.order_by(Invoice.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    items = [VendorInvoiceItem.model_validate(row) for row in result.scalars().all()]

    return VendorInvoiceListResponse(items=items, total=total)


@router.get(
    "/invoices/{invoice_id}",
    response_model=VendorInvoiceItem,
    summary="Get a single invoice (vendor must own it)",
)
async def get_vendor_invoice(
    invoice_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    vendor_id: Annotated[uuid.UUID, Depends(get_current_vendor_id)],
):
    """Return invoice detail only if it belongs to the authenticated vendor."""
    result = await db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.vendor_id == vendor_id,  # ownership check
            Invoice.deleted_at.is_(None),
        )
    )
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")
    return VendorInvoiceItem.model_validate(invoice)


@limiter.limit("20/minute")
@router.post(
    "/invoices/{invoice_id}/reply",
    response_model=VendorReplyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Vendor reply to an invoice inquiry",
)
async def vendor_reply(
    request: Request,
    invoice_id: uuid.UUID,
    body: VendorReplyIn,
    token: Annotated[str, Query(description="Vendor reply token")],
    db: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Accept a reply message from a vendor regarding an invoice.

    - invoice_id: UUID of the invoice
    - token: Public token authenticating the vendor (sent via email)
    - body: Message body from vendor
    """

    # Validate token
    verified_invoice_id = verify_vendor_reply_token(token)
    if verified_invoice_id is None or uuid.UUID(verified_invoice_id) != invoice_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired vendor token.",
        )

    # Verify invoice exists
    stmt = select(Invoice).where(Invoice.id == invoice_id, Invoice.deleted_at.is_(None))
    result = await db.execute(stmt)
    invoice = result.scalar_one_or_none()

    if invoice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found.",
        )

    # Create VendorMessage record
    message = VendorMessage(
        invoice_id=invoice_id,
        sender_id=None,  # External vendor
        sender_email=None,
        direction="inbound",
        body=body.body,
        is_internal=False,  # Vendor-visible
        attachments=[],
    )

    db.add(message)
    await db.commit()
    await db.refresh(message)

    logger.info("Vendor reply recorded for invoice %s (message_id=%s)", invoice_id, message.id)

    return VendorReplyResponse(
        status="reply_received",
        message_id=message.id,
    )


@limiter.limit("20/minute")
@router.post(
    "/invoices/{invoice_id}/dispute",
    response_model=VendorDisputeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Vendor submits a formal dispute for an invoice",
)
async def submit_vendor_dispute(
    request: Request,
    invoice_id: uuid.UUID,
    body: VendorDisputeIn,
    db: Annotated[AsyncSession, Depends(get_session)],
    vendor_id: Annotated[uuid.UUID, Depends(get_current_vendor_id)],
):
    """Create an ExceptionRecord (VENDOR_DISPUTE) and a VendorMessage for the dispute.

    Only the owning vendor may dispute their own invoice.
    """
    from app.models.exception_record import ExceptionRecord

    result = await db.execute(
        select(Invoice).where(
            Invoice.id == invoice_id,
            Invoice.vendor_id == vendor_id,
            Invoice.deleted_at.is_(None),
        )
    )
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")

    exc = ExceptionRecord(
        invoice_id=invoice_id,
        exception_code="VENDOR_DISPUTE",
        description=f"Vendor dispute: {body.reason} — {body.description}",
        severity="medium",
        status="open",
    )
    msg = VendorMessage(
        invoice_id=invoice_id,
        sender_id=None,
        sender_email=None,
        direction="inbound",
        body=f"[DISPUTE] {body.reason}: {body.description}",
        is_internal=False,
        attachments=[],
    )

    db.add(exc)
    db.add(msg)
    await db.commit()
    await db.refresh(exc)
    await db.refresh(msg)

    logger.info("Vendor dispute submitted for invoice %s (exception_id=%s)", invoice_id, exc.id)

    return VendorDisputeResponse(
        status="dispute_submitted",
        exception_id=exc.id,
        message_id=msg.id,
    )


@router.get(
    "/templates",
    response_model=list[VendorTemplateItem],
    summary="List invoice templates for the authenticated vendor",
)
async def list_vendor_templates(
    db: Annotated[AsyncSession, Depends(get_session)],
    vendor_id: Annotated[uuid.UUID, Depends(get_current_vendor_id)],
):
    """Return non-deleted templates where vendor_id matches the token claim."""
    result = await db.execute(
        select(InvoiceTemplate)
        .where(
            InvoiceTemplate.vendor_id == vendor_id,
            InvoiceTemplate.deleted_at.is_(None),
        )
        .order_by(InvoiceTemplate.created_at.desc())
    )
    return [VendorTemplateItem.model_validate(t) for t in result.scalars().all()]
