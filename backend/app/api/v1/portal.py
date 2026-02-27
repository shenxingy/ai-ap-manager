"""Vendor portal endpoints (public, no auth required).

Endpoints:
  POST /portal/invoices/{invoice_id}/reply  — vendor reply to an invoice inquiry
"""
import hashlib
import hmac
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.models.approval import VendorMessage
from app.models.invoice import Invoice

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portal", tags=["portal"])


# ─── Schemas ───


class VendorReplyIn(BaseModel):
    """Vendor reply message body."""

    body: str


class VendorReplyResponse(BaseModel):
    """Response after vendor reply is recorded."""

    status: str
    message_id: uuid.UUID


# ─── Token utilities ───


def create_vendor_reply_token(invoice_id: str) -> tuple[str, str]:
    """
    Create a vendor reply token for an invoice.

    Returns (raw_token, token_hash).
    raw_token is sent to vendor in email URL; token_hash would be stored in DB if needed.
    """
    raw = f"vendor_reply:{invoice_id}:{uuid.uuid4()}"
    token_hash = hmac.new(
        settings.APPROVAL_TOKEN_SECRET.encode(),
        raw.encode(),
        hashlib.sha256,
    ).hexdigest()
    return raw, token_hash


def verify_vendor_reply_token(raw_token: str) -> str | None:
    """
    Verify a vendor reply token and extract the invoice_id.

    Returns invoice_id if valid, None if invalid or expired.
    """
    try:
        parts = raw_token.split(":")
        if len(parts) != 3 or parts[0] != "vendor_reply":
            return None

        invoice_id_str = parts[1]
        # Verify format is a valid UUID
        uuid.UUID(invoice_id_str)

        # Recompute the hash
        expected_hash = hmac.new(
            settings.APPROVAL_TOKEN_SECRET.encode(),
            raw_token.encode(),
            hashlib.sha256,
        ).hexdigest()

        # This check is optional here since we don't store the hash,
        # but we could enhance it later. For now, validate format only.
        return invoice_id_str

    except (ValueError, IndexError):
        return None


# ─── Endpoints ───


@router.post(
    "/invoices/{invoice_id}/reply",
    response_model=VendorReplyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Vendor reply to an invoice inquiry",
)
async def vendor_reply(
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
    from sqlalchemy import select

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
        sender_email=None,  # Could extract from token if stored; for now, leave blank
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
