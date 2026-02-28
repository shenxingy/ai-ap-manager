"""KPI Dashboard API endpoints."""
import csv
import io
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select, not_, exists
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_role
from app.db.session import get_session
from app.models.invoice import Invoice
from app.models.exception_record import ExceptionRecord
from app.models.approval import ApprovalTask
from app.schemas.kpi import KPISummary, KPITrendPoint, KPITrends

logger = logging.getLogger(__name__)
router = APIRouter()

PENDING_STATUSES = {"ingested", "extracting", "extracted", "matching", "matched"}
FORECAST_STATUSES = {"ingested", "extracting", "extracted", "matching", "matched", "exception"}


@router.get("/summary", response_model=KPISummary, summary="KPI summary for the last N days")
async def get_kpi_summary(
    days: int = Query(default=30, ge=1, le=365, description="Lookback window in days"),
    db: Annotated[AsyncSession, Depends(get_session)] = ...,
    current_user=Depends(require_role("AP_ANALYST", "AP_MANAGER", "APPROVER", "ADMIN", "AUDITOR")),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    base = select(Invoice).where(
        Invoice.deleted_at.is_(None),
        Invoice.created_at >= since,
    )

    # Total received
    total_received = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    # Total approved
    approved_q = base.where(Invoice.status == "approved")
    total_approved = (await db.execute(select(func.count()).select_from(approved_q.subquery()))).scalar_one()

    # Total pending
    pending_q = base.where(Invoice.status.in_(PENDING_STATUSES))
    total_pending = (await db.execute(select(func.count()).select_from(pending_q.subquery()))).scalar_one()

    # Invoices with at least one open exception
    inv_with_exc = (
        select(func.count(Invoice.id.distinct()))
        .select_from(Invoice)
        .join(ExceptionRecord, ExceptionRecord.invoice_id == Invoice.id)
        .where(
            Invoice.deleted_at.is_(None),
            Invoice.created_at >= since,
            ExceptionRecord.status == "open",
        )
    )
    total_exceptions = (await db.execute(inv_with_exc)).scalar_one()

    # Auto-approved = approved invoices with NO approval task
    auto_approved_q = (
        select(func.count(Invoice.id))
        .select_from(Invoice)
        .where(
            Invoice.deleted_at.is_(None),
            Invoice.created_at >= since,
            Invoice.status == "approved",
            not_(exists(select(ApprovalTask.id).where(ApprovalTask.invoice_id == Invoice.id))),
        )
    )
    auto_approved = (await db.execute(auto_approved_q)).scalar_one()

    touchless_rate = (auto_approved / total_approved) if total_approved > 0 else 0.0
    exception_rate = (total_exceptions / total_received) if total_received > 0 else 0.0

    # Avg cycle time: (updated_at - created_at) in hours for approved invoices
    cycle_time_q = (
        select(func.avg(
            func.extract("epoch", Invoice.updated_at - Invoice.created_at) / 3600
        ))
        .where(
            Invoice.deleted_at.is_(None),
            Invoice.created_at >= since,
            Invoice.status == "approved",
        )
    )
    avg_cycle = (await db.execute(cycle_time_q)).scalar_one()

    return KPISummary(
        total_received=total_received,
        total_approved=total_approved,
        total_pending=total_pending,
        total_exceptions=total_exceptions,
        touchless_rate=round(touchless_rate, 4),
        exception_rate=round(exception_rate, 4),
        avg_cycle_time_hours=round(float(avg_cycle), 2) if avg_cycle else None,
        period_days=days,
    )


@router.get("/sla-summary", summary="SLA overdue and approaching-due invoice counts")
async def get_sla_summary(
    db: Annotated[AsyncSession, Depends(get_session)] = ...,
    current_user=Depends(require_role("AP_CLERK", "AP_ANALYST", "AP_MANAGER", "APPROVER", "ADMIN", "AUDITOR")),
):
    now = datetime.now(timezone.utc)
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    approaching_cutoff = start_of_today + timedelta(days=3)

    # Approaching: due_date between now and today+3 days, not yet approved/paid
    approaching_q = select(func.count(Invoice.id)).where(
        Invoice.deleted_at.is_(None),
        Invoice.due_date >= now,
        Invoice.due_date <= approaching_cutoff,
        Invoice.status.not_in(["approved", "paid"]),
    )
    approaching_count = (await db.execute(approaching_q)).scalar_one()

    # Overdue: due_date < now, not yet approved/paid
    overdue_q = select(func.count(Invoice.id)).where(
        Invoice.deleted_at.is_(None),
        Invoice.due_date < now,
        Invoice.status.not_in(["approved", "paid"]),
    )
    overdue_count = (await db.execute(overdue_q)).scalar_one()

    return {"approaching_count": approaching_count, "overdue_count": overdue_count}


@router.get("/trends", response_model=KPITrends, summary="KPI time-series trends")
async def get_kpi_trends(
    period: str = Query(default="daily", pattern="^(daily|weekly)$"),
    days: int = Query(default=30, ge=7, le=365),
    db: Annotated[AsyncSession, Depends(get_session)] = ...,
    current_user=Depends(require_role("AP_ANALYST", "AP_MANAGER", "APPROVER", "ADMIN", "AUDITOR")),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)

    if period == "weekly":
        trunc_fn = func.date_trunc("week", Invoice.created_at)
    else:
        trunc_fn = func.date_trunc("day", Invoice.created_at)

    # Count by period bucket
    trend_q = (
        select(
            trunc_fn.label("period_start"),
            func.count(Invoice.id).label("received"),
            func.sum(func.cast(Invoice.status == "approved", type_=None)).label("approved"),
            func.avg(Invoice.total_amount).label("avg_amount"),
        )
        .where(Invoice.deleted_at.is_(None), Invoice.created_at >= since)
        .group_by("period_start")
        .order_by("period_start")
    )
    rows = (await db.execute(trend_q)).all()

    # Exception count per period (separate query, then merge)
    exc_q = (
        select(
            trunc_fn.label("period_start"),
            func.count(Invoice.id.distinct()).label("exc_count"),
        )
        .select_from(Invoice)
        .join(ExceptionRecord, ExceptionRecord.invoice_id == Invoice.id)
        .where(
            Invoice.deleted_at.is_(None),
            Invoice.created_at >= since,
            ExceptionRecord.status == "open",
        )
        .group_by("period_start")
    )
    exc_rows = {row.period_start: row.exc_count for row in (await db.execute(exc_q)).all()}

    points = []
    for row in rows:
        ps = row.period_start.date() if hasattr(row.period_start, "date") else row.period_start
        points.append(KPITrendPoint(
            period_start=ps,
            invoices_received=row.received or 0,
            invoices_approved=int(row.approved or 0),
            invoices_exceptions=exc_rows.get(row.period_start, 0),
            avg_amount=Decimal(str(row.avg_amount)).quantize(Decimal("0.01")) if row.avg_amount else None,
        ))

    return KPITrends(period=period, points=points)


@router.get("/cash-flow-forecast", summary="12-week cash flow forecast from pending invoices")
async def get_cash_flow_forecast(
    db: Annotated[AsyncSession, Depends(get_session)] = ...,
    current_user=Depends(require_role("AP_ANALYST", "ADMIN", "AUDITOR")),
):
    """Return 12 weeks of expected outflows bucketed by payment week.

    Payment date = due_date (confirmed, confidence=0.9) or invoice_date+30 days
    (estimated, confidence=0.5). Invoices with no date fall in the current week
    (confidence=0.3).
    """
    now = datetime.now(timezone.utc)
    # Monday of current week (as date for simple arithmetic)
    today = now.date()
    week_start_0 = today - timedelta(days=today.weekday())

    invoices = (await db.execute(
        select(Invoice).where(
            Invoice.deleted_at.is_(None),
            Invoice.status.in_(FORECAST_STATUSES),
            Invoice.total_amount.isnot(None),
        )
    )).scalars().all()

    # Initialise 12 weekly buckets
    buckets = {}
    for i in range(12):
        ws = week_start_0 + timedelta(weeks=i)
        buckets[ws] = {"expected_outflow": 0.0, "invoice_count": 0, "conf_sum": 0.0}

    for inv in invoices:
        if inv.due_date is not None:
            raw = inv.due_date
            pay_date = raw.date() if hasattr(raw, "date") else raw
            confidence = 0.9
        elif inv.invoice_date is not None:
            raw = inv.invoice_date
            base = raw.date() if hasattr(raw, "date") else raw
            pay_date = base + timedelta(days=30)
            confidence = 0.5
        else:
            pay_date = today
            confidence = 0.3

        # Week start (Monday) for this payment date
        ws = pay_date - timedelta(days=pay_date.weekday())

        if ws in buckets:
            buckets[ws]["expected_outflow"] += float(inv.total_amount)
            buckets[ws]["invoice_count"] += 1
            buckets[ws]["conf_sum"] += confidence

    result = []
    for i in range(12):
        ws = week_start_0 + timedelta(weeks=i)
        b = buckets[ws]
        avg_conf = b["conf_sum"] / b["invoice_count"] if b["invoice_count"] > 0 else 0.0
        result.append({
            "week_start": ws.isoformat(),
            "expected_outflow": round(b["expected_outflow"], 2),
            "invoice_count": b["invoice_count"],
            "confidence": round(avg_conf, 2),
        })

    return result


@router.get("/cash-flow-export", summary="Cash flow forecast exported as CSV")
async def get_cash_flow_export(
    db: Annotated[AsyncSession, Depends(get_session)] = ...,
    current_user=Depends(require_role("AP_ANALYST", "ADMIN", "AUDITOR")),
):
    """Stream pending invoices as CSV for treasury/cash-flow planning."""
    invoices = (await db.execute(
        select(Invoice).where(
            Invoice.deleted_at.is_(None),
            Invoice.status.in_(FORECAST_STATUSES),
        )
    )).scalars().all()

    def _generate():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "invoice_number", "vendor", "amount", "currency",
            "status", "due_date", "invoice_date",
        ])
        for inv in invoices:
            writer.writerow([
                inv.invoice_number or "",
                inv.vendor_name_raw or "",
                str(inv.total_amount) if inv.total_amount is not None else "",
                inv.currency or "",
                inv.status or "",
                inv.due_date.date().isoformat() if inv.due_date else "",
                inv.invoice_date.date().isoformat() if inv.invoice_date else "",
            ])
        yield buf.getvalue()

    return StreamingResponse(
        _generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=cash-flow-forecast.csv"},
    )
