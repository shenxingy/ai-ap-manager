"""Analytics endpoints — Process Mining and Anomaly Detection."""
import json
import logging
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_role
from app.db.session import get_session
from app.models.audit import AuditLog
from app.models.exception_record import ExceptionRecord
from app.models.invoice import Invoice
from app.models.user import User
from app.models.vendor import Vendor

logger = logging.getLogger(__name__)
router = APIRouter()

# ─── Step definitions ───

# Each tuple: (from_status, to_status, step_label)
STEPS = [
    ("ingested", "extracting", "pending_extraction→extracting"),
    ("extracting", "extracted", "extracting→extracted"),
    ("extracted", "matching", "extracted→matching"),
    ("matching", "matched", "matching→matched"),
    ("matched", "approved", "matched→approved"),
]


# ─── Helpers ───

def _percentile(data: list[float], pct: float) -> float:
    """Compute percentile via linear interpolation."""
    if not data:
        return 0.0
    sorted_d = sorted(data)
    n = len(sorted_d)
    if n == 1:
        return sorted_d[0]
    idx = (pct / 100.0) * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return sorted_d[lo] + frac * (sorted_d[hi] - sorted_d[lo])


def _safe_utc(dt: datetime) -> datetime:
    """Ensure datetime is tz-aware (UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ─── Process Mining ───

@router.get("/process-mining", summary="Invoice process mining — step durations")
async def get_process_mining(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("AP_ANALYST", "AP_MANAGER", "ADMIN", "AUDITOR"))],
) -> list[dict]:
    """Return median and p90 duration (hours) for each invoice processing step."""
    try:
        q = (
            select(AuditLog)
            .where(
                AuditLog.action.like("invoice%"),
                AuditLog.entity_type == "invoice",
                AuditLog.after_state.isnot(None),
                AuditLog.entity_id.isnot(None),
            )
            .order_by(AuditLog.entity_id, AuditLog.created_at)
        )
        rows = (await db.execute(q)).scalars().all()

        # Build per-invoice status → earliest_timestamp map
        timelines: dict[str, dict[str, datetime]] = defaultdict(dict)
        for row in rows:
            try:
                after = json.loads(row.after_state)
                status = after.get("status")
            except Exception:
                continue
            if not status:
                continue
            key = str(row.entity_id)
            # Keep only the FIRST occurrence of each status per invoice
            if status not in timelines[key]:
                timelines[key][status] = _safe_utc(row.created_at)

        # Collect durations per step
        step_hours: dict[str, list[float]] = {label: [] for _, _, label in STEPS}
        for timeline in timelines.values():
            for from_status, to_status, label in STEPS:
                if from_status in timeline and to_status in timeline:
                    t_from = timeline[from_status]
                    t_to = timeline[to_status]
                    if t_to > t_from:
                        hours = (t_to - t_from).total_seconds() / 3600.0
                        step_hours[label].append(hours)

        result = []
        for from_status, to_status, label in STEPS:
            hours = step_hours[label]
            if not hours:
                continue
            result.append({
                "step": label,
                "from_status": from_status,
                "to_status": to_status,
                "median_hours": round(statistics.median(hours), 2),
                "p90_hours": round(_percentile(hours, 90), 2),
                "invoice_count": len(hours),
            })

        return result
    except Exception as exc:
        logger.exception("Error in process mining: %s", exc)
        return []  # Return empty array on error for graceful degradation


# ─── Anomaly Detection ───

@router.get("/anomalies", summary="Vendor exception-rate anomaly detection")
async def get_anomalies(
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("AP_ANALYST", "AP_MANAGER", "ADMIN", "AUDITOR"))],
) -> list[dict]:
    """Return vendor-window combinations whose exception rate is > 2 std deviations from their mean."""
    try:
        since = datetime.now(timezone.utc) - timedelta(days=180)  # 6 months

        # Load invoices in the last 6 months with vendor name
        inv_q = (
            select(
                Invoice.id,
                Invoice.vendor_id,
                Vendor.name.label("vendor_name"),
                Invoice.created_at,
            )
            .join(Vendor, Invoice.vendor_id == Vendor.id)
            .where(
                Invoice.deleted_at.is_(None),
                Invoice.created_at >= since,
                Invoice.vendor_id.isnot(None),
            )
        )
        invoices = (await db.execute(inv_q)).all()

        if not invoices:
            return []

        # Get invoice IDs that have at least one exception record
        invoice_ids = [row.id for row in invoices]
        exc_q = select(ExceptionRecord.invoice_id).where(
            ExceptionRecord.invoice_id.in_(invoice_ids)
        )
        exc_invoice_ids = {str(r) for r in (await db.execute(exc_q)).scalars().all()}

        # Build per-vendor-window stats: window = 30-day bucket since `since`
        # window_data[vendor_id][window_idx] = {invoices, exceptions, vendor_name, period}
        window_data: dict[str, dict[int, dict]] = defaultdict(dict)
        for row in invoices:
            created = _safe_utc(row.created_at)
            window_idx = int((created - since).total_seconds() / (30 * 24 * 3600))
            vid = str(row.vendor_id)

            if window_idx not in window_data[vid]:
                period_start = since + timedelta(days=window_idx * 30)
                window_data[vid][window_idx] = {
                    "invoices": 0,
                    "exceptions": 0,
                    "vendor_name": row.vendor_name,
                    "period": period_start.strftime("%Y-%m-%d"),
                }

            w = window_data[vid][window_idx]
            w["invoices"] += 1
            if str(row.id) in exc_invoice_ids:
                w["exceptions"] += 1

        # Compute z-scores per vendor across its windows, flag |z| > 2.0
        result = []
        for vid, windows in window_data.items():
            rates = [
                w["exceptions"] / w["invoices"] if w["invoices"] > 0 else 0.0
                for w in windows.values()
            ]

            if len(rates) < 2:
                continue

            mean_rate = statistics.mean(rates)
            std_rate = statistics.stdev(rates)

            if std_rate == 0:
                continue  # No variance — nothing to flag

            for w in windows.values():
                rate = w["exceptions"] / w["invoices"] if w["invoices"] > 0 else 0.0
                z = (rate - mean_rate) / std_rate
                if abs(z) > 2.0:
                    result.append({
                        "vendor_id": vid,
                        "vendor_name": w["vendor_name"],
                        "period": w["period"],
                        "exception_rate": round(rate, 4),
                        "z_score": round(z, 2),
                        "direction": "spike" if z > 0 else "dip",
                    })

        # Sort by absolute z-score descending
        result.sort(key=lambda x: abs(x["z_score"]), reverse=True)
        return result
    except Exception as exc:
        logger.exception("Error in anomaly detection: %s", exc)
        return []  # Return empty array on error for graceful degradation
