"""Payment recording endpoint — POST /api/v1/invoices/{invoice_id}/payment
                              POST /api/v1/payments/batch"""
import logging
import uuid
from datetime import UTC, date, datetime, time
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/invoices", tags=["payments"])
batch_router = APIRouter(prefix="/payments", tags=["payments"])


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


# ─── Batch payment schemas ───

class BatchPaymentRequest(BaseModel):
    invoice_ids: list[uuid.UUID]
    payment_method: str  # ACH, WIRE, CHECK, etc.
    payment_date: date
    notes: str | None = None


class BatchPaymentResult(BaseModel):
    invoice_id: uuid.UUID
    status: str  # "paid" or "skipped"
    error: str | None = None


class BatchPaymentResponse(BaseModel):
    processed: int
    succeeded: int
    failed: int
    results: list[BatchPaymentResult]


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
    payment_date = body.payment_date or datetime.now(UTC)
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


# ─── Batch payment endpoint ───

@batch_router.post(
    "/batch",
    response_model=BatchPaymentResponse,
    status_code=status.HTTP_200_OK,
    summary="Batch record payments for multiple approved invoices (ADMIN only)",
)
async def batch_payment(
    body: BatchPaymentRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("ADMIN"))],
):
    results: list[BatchPaymentResult] = []
    payment_dt = datetime.combine(body.payment_date, time(0, 0, 0)).replace(tzinfo=UTC)

    for invoice_id in body.invoice_ids:
        # Fetch invoice (read-only, no savepoint needed)
        row = await db.execute(
            select(Invoice).where(Invoice.id == invoice_id, Invoice.deleted_at.is_(None))
        )
        invoice = row.scalar_one_or_none()

        if invoice is None:
            results.append(BatchPaymentResult(invoice_id=invoice_id, status="skipped", error="Invoice not found"))
            continue

        if invoice.status != "approved":
            results.append(
                BatchPaymentResult(
                    invoice_id=invoice_id,
                    status="skipped",
                    error=f"Invoice not in approved status (current: {invoice.status})",
                )
            )
            continue

        # Mutate inside a savepoint so one failure doesn't block the others
        try:
            async with db.begin_nested():
                before = {"status": invoice.status, "payment_status": invoice.payment_status}
                invoice.payment_status = "completed"
                invoice.payment_date = payment_dt
                invoice.payment_method = body.payment_method
                invoice.payment_reference = None
                invoice.status = "paid"
                if body.notes:
                    invoice.notes = body.notes
                await db.flush()
                audit_svc.log(
                    db=db,
                    action="payment_recorded",
                    entity_type="invoice",
                    entity_id=invoice.id,
                    actor_id=current_user.id,
                    before=before,
                    after={"status": "paid", "payment_method": body.payment_method},
                    notes="Batch payment: " + body.payment_method + (" — " + body.notes if body.notes else ""),
                )
            results.append(BatchPaymentResult(invoice_id=invoice_id, status="paid", error=None))
        except Exception:
            logger.warning("batch_payment: savepoint failed for invoice %s", invoice_id, exc_info=True)
            results.append(
                BatchPaymentResult(invoice_id=invoice_id, status="skipped", error="Internal error processing invoice")
            )

    await db.commit()

    succeeded = sum(1 for r in results if r.status == "paid")
    return BatchPaymentResponse(
        processed=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
        results=results,
    )
