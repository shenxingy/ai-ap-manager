"""Payment recording endpoint — POST /api/v1/invoices/{invoice_id}/payment"""
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role
from app.db.session import get_session
from app.models.invoice import Invoice
from app.models.user import User
from app.services import audit as audit_svc

router = APIRouter(prefix="/invoices", tags=["payments"])


class PaymentRecordIn(BaseModel):
    payment_method: str
    payment_reference: str | None = None
    payment_date: datetime | None = None


class PaymentRecordOut(BaseModel):
    invoice_id: uuid.UUID
    payment_status: str
    payment_date: datetime
    payment_method: str
    payment_reference: str | None
    model_config = {"from_attributes": True}


@router.post(
    "/{invoice_id}/payment",
    response_model=PaymentRecordOut,
    status_code=status.HTTP_200_OK,
    summary="Record payment for an approved invoice (ADMIN only)",
)
async def record_payment(
    invoice_id: uuid.UUID,
    body: PaymentRecordIn,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("ADMIN"))],
):
    result = await db.execute(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.deleted_at.is_(None))
    )
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    if invoice.status != "approved":
        raise HTTPException(
            status_code=400,
            detail=f"Invoice must be in 'approved' state to record payment (current: {invoice.status}).",
        )
    before = {"status": invoice.status, "payment_status": invoice.payment_status}
    payment_date = body.payment_date or datetime.now(timezone.utc)
    invoice.payment_status = "completed"
    invoice.payment_date = payment_date
    invoice.payment_method = body.payment_method
    invoice.payment_reference = body.payment_reference
    invoice.status = "paid"
    await db.flush()
    audit_svc.log(
        db=db,
        action="payment_recorded",
        entity_type="invoice",
        entity_id=invoice.id,
        actor_id=current_user.id,
        before=before,
        after={
            "status": "paid",
            "payment_method": body.payment_method,
            "payment_reference": body.payment_reference,
        },
        notes=f"Payment recorded: {body.payment_method} ref={body.payment_reference}",
    )
    await db.commit()
    await db.refresh(invoice)
    return PaymentRecordOut(
        invoice_id=invoice.id,
        payment_status=invoice.payment_status,
        payment_date=invoice.payment_date,
        payment_method=invoice.payment_method,
        payment_reference=invoice.payment_reference,
    )
