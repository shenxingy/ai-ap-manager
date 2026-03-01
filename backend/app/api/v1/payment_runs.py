"""Payment Runs API — GET|POST /payment-runs, GET|POST|PATCH /payment-runs/{run_id}"""
import json
import uuid
from datetime import date, datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import require_role
from app.db.session import get_session
from app.models.audit import AuditLog
from app.models.invoice import Invoice
from app.models.payment_run import PaymentRun
from app.models.user import User
from app.models.vendor import Vendor

router = APIRouter()


# ─── Schemas ───

class GenerateRunRequest(BaseModel):
    frequency: str       # weekly, bi-weekly, monthly, etc.
    payment_method: str  # ACH, WIRE, CHECK, etc.
    scheduled_date: Optional[date] = None


class PaymentRunSummary(BaseModel):
    id: uuid.UUID
    name: str
    vendor_id: Optional[uuid.UUID]
    vendor_name: Optional[str] = None
    scheduled_date: date
    frequency: str
    status: str
    total_amount: float
    invoice_count: int
    payment_method: str
    executed_at: Optional[datetime]
    created_at: datetime
    model_config = {"from_attributes": True}


class PaymentRunListResponse(BaseModel):
    items: list[PaymentRunSummary]
    total: int


class GenerateRunResponse(BaseModel):
    runs_created: int
    invoices_assigned: int
    runs: list[PaymentRunSummary]


class InvoiceSummaryItem(BaseModel):
    id: uuid.UUID
    invoice_number: Optional[str]
    vendor_id: Optional[uuid.UUID]
    vendor_name: Optional[str] = None
    total_amount: Optional[float]
    currency: Optional[str]
    status: str
    payment_status: Optional[str]
    model_config = {"from_attributes": True}


class PaymentRunDetail(BaseModel):
    id: uuid.UUID
    name: str
    vendor_id: Optional[uuid.UUID]
    vendor_name: Optional[str] = None
    scheduled_date: date
    frequency: str
    status: str
    total_amount: float
    invoice_count: int
    payment_method: str
    executed_at: Optional[datetime]
    executed_by: Optional[uuid.UUID]
    notes: Optional[str]
    created_at: datetime
    invoices: list[InvoiceSummaryItem]


class ExecuteRunResponse(BaseModel):
    executed: int
    total_paid: float


# ─── GET / ───

@router.get(
    "",
    response_model=PaymentRunListResponse,
    summary="List payment runs with optional filters (ADMIN only)",
)
async def list_payment_runs(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("ADMIN"))],
    run_status: Optional[str] = Query(default=None, alias="status"),
    vendor_id: Optional[uuid.UUID] = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    # Count
    count_stmt = select(func.count(PaymentRun.id))
    if run_status:
        count_stmt = count_stmt.where(PaymentRun.status == run_status)
    if vendor_id:
        count_stmt = count_stmt.where(PaymentRun.vendor_id == vendor_id)
    total = (await db.execute(count_stmt)).scalar_one()

    # Fetch with vendor join
    stmt = (
        select(PaymentRun, Vendor.name.label("vendor_name"))
        .outerjoin(Vendor, PaymentRun.vendor_id == Vendor.id)
        .order_by(PaymentRun.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    if run_status:
        stmt = stmt.where(PaymentRun.status == run_status)
    if vendor_id:
        stmt = stmt.where(PaymentRun.vendor_id == vendor_id)

    rows = (await db.execute(stmt)).all()
    items = []
    for run, vendor_name in rows:
        item = PaymentRunSummary.model_validate(run)
        item.vendor_name = vendor_name
        items.append(item)

    return PaymentRunListResponse(items=items, total=total)


# ─── POST /generate ───

@router.post(
    "/generate",
    response_model=GenerateRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate payment runs from approved invoices grouped by vendor (ADMIN only)",
)
async def generate_payment_runs(
    body: GenerateRunRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("ADMIN"))],
):
    scheduled = body.scheduled_date or date.today()

    # All approved invoices not yet assigned to a run
    invoices_result = await db.execute(
        select(Invoice).where(
            Invoice.status == "approved",
            Invoice.payment_run_id.is_(None),
            Invoice.deleted_at.is_(None),
        )
    )
    invoices = invoices_result.scalars().all()

    if not invoices:
        return GenerateRunResponse(runs_created=0, invoices_assigned=0, runs=[])

    # Group by vendor_id
    groups: dict[Optional[uuid.UUID], list[Invoice]] = {}
    for inv in invoices:
        groups.setdefault(inv.vendor_id, []).append(inv)

    # Batch-load vendor names
    vendor_ids = [vid for vid in groups if vid is not None]
    vendor_map: dict[uuid.UUID, str] = {}
    if vendor_ids:
        vendor_rows = await db.execute(select(Vendor).where(Vendor.id.in_(vendor_ids)))
        for v in vendor_rows.scalars().all():
            vendor_map[v.id] = v.name

    created_runs: list[PaymentRun] = []
    total_assigned = 0

    for vendor_id_key, inv_group in groups.items():
        vendor_name = vendor_map.get(vendor_id_key, "Unknown") if vendor_id_key else "No Vendor"
        run_name = f"{body.frequency.upper()} {body.payment_method} - {scheduled} - {vendor_name}"
        total_amount = sum(float(inv.total_amount or 0) for inv in inv_group)

        run = PaymentRun(
            name=run_name,
            vendor_id=vendor_id_key,
            scheduled_date=scheduled,
            frequency=body.frequency,
            payment_method=body.payment_method,
            total_amount=total_amount,
            invoice_count=len(inv_group),
            status="pending",
        )
        db.add(run)
        await db.flush()  # get run.id before assigning to invoices

        for inv in inv_group:
            inv.payment_run_id = run.id

        total_assigned += len(inv_group)
        created_runs.append(run)

    await db.commit()

    run_summaries = []
    for run in created_runs:
        await db.refresh(run)
        s = PaymentRunSummary.model_validate(run)
        s.vendor_name = vendor_map.get(run.vendor_id) if run.vendor_id else None
        run_summaries.append(s)

    return GenerateRunResponse(
        runs_created=len(created_runs),
        invoices_assigned=total_assigned,
        runs=run_summaries,
    )


# ─── GET /{run_id} ───

@router.get(
    "/{run_id}",
    response_model=PaymentRunDetail,
    summary="Get payment run detail with its invoices (ADMIN only)",
)
async def get_payment_run(
    run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("ADMIN"))],
):
    result = await db.execute(
        select(PaymentRun)
        .where(PaymentRun.id == run_id)
        .options(selectinload(PaymentRun.invoices))
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Payment run not found.")

    vendor_name: Optional[str] = None
    if run.vendor_id:
        v_result = await db.execute(select(Vendor.name).where(Vendor.id == run.vendor_id))
        vendor_name = v_result.scalar_one_or_none()

    return PaymentRunDetail(
        id=run.id,
        name=run.name,
        vendor_id=run.vendor_id,
        vendor_name=vendor_name,
        scheduled_date=run.scheduled_date,
        frequency=run.frequency,
        status=run.status,
        total_amount=float(run.total_amount),
        invoice_count=run.invoice_count,
        payment_method=run.payment_method,
        executed_at=run.executed_at,
        executed_by=run.executed_by,
        notes=run.notes,
        created_at=run.created_at,
        invoices=[
            InvoiceSummaryItem(
                id=inv.id,
                invoice_number=inv.invoice_number,
                vendor_id=inv.vendor_id,
                vendor_name=inv.vendor_name_raw,
                total_amount=float(inv.total_amount) if inv.total_amount is not None else None,
                currency=inv.currency,
                status=inv.status,
                payment_status=inv.payment_status,
            )
            for inv in run.invoices
        ],
    )


# ─── POST /{run_id}/execute ───

@router.post(
    "/{run_id}/execute",
    response_model=ExecuteRunResponse,
    summary="Execute a pending payment run — marks invoices paid and closes the run (ADMIN only)",
)
async def execute_payment_run(
    run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("ADMIN"))],
):
    result = await db.execute(
        select(PaymentRun)
        .where(PaymentRun.id == run_id)
        .options(selectinload(PaymentRun.invoices))
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Payment run not found.")
    if run.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payment run must be 'pending' to execute (current: {run.status}).",
        )

    now = datetime.now(timezone.utc)
    executed_count = 0
    total_paid = 0.0

    for inv in run.invoices:
        before = {"status": inv.status, "payment_status": inv.payment_status}
        inv.status = "paid"
        inv.payment_status = "completed"
        inv.payment_date = now
        inv.payment_method = run.payment_method
        db.add(AuditLog(
            actor_id=current_user.id,
            actor_email=current_user.email,
            action="payment_run.executed",
            entity_type="invoice",
            entity_id=inv.id,
            before_state=json.dumps(before, default=str),
            after_state=json.dumps(
                {"status": "paid", "payment_status": "completed", "payment_method": run.payment_method},
                default=str,
            ),
            notes=f"Paid via payment run {run.id} by {current_user.email}",
        ))
        executed_count += 1
        total_paid += float(inv.total_amount or 0)

    run.status = "completed"
    run.executed_at = now
    run.executed_by = current_user.id

    await db.commit()

    return ExecuteRunResponse(executed=executed_count, total_paid=total_paid)


# ─── PATCH /{run_id}/cancel ───

@router.patch(
    "/{run_id}/cancel",
    response_model=PaymentRunSummary,
    summary="Cancel a payment run and release its assigned invoices (ADMIN only)",
)
async def cancel_payment_run(
    run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("ADMIN"))],
):
    result = await db.execute(
        select(PaymentRun)
        .where(PaymentRun.id == run_id)
        .options(selectinload(PaymentRun.invoices))
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Payment run not found.")
    if run.status in ("completed", "cancelled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel a run with status '{run.status}'.",
        )

    for inv in run.invoices:
        inv.payment_run_id = None

    run.status = "cancelled"
    await db.commit()
    await db.refresh(run)

    return PaymentRunSummary.model_validate(run)
