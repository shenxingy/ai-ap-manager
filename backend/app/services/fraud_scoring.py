"""Rule-based Fraud Scoring service.

Evaluates deterministic signals on invoices. No LLM — all rules are explicit.
Auto-creates FRAUD_FLAG exception when score >= HIGH threshold.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)

# ─── Signal weights ───
SIGNAL_WEIGHTS = {
    "round_amount": 10,        # total_amount ends in .00 AND > $1000
    "amount_spike": 20,        # total > 2x vendor historical avg
    "potential_duplicate": 30, # same vendor + same amount within 7 days
    "stale_invoice_date": 10,  # invoice_date older than 90 days
    "new_vendor": 5,           # vendor has < 3 approved invoices ever
}


def score_invoice(db: Session, invoice_id: uuid.UUID) -> dict[str, Any]:
    """Score an invoice for fraud risk. Updates invoice.fraud_score in DB.

    Returns: {fraud_score: int, triggered_signals: list[str], created_exception: bool}
    """
    from app.models.invoice import Invoice
    from app.services import audit as audit_svc

    invoice = db.execute(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.deleted_at.is_(None))
    ).scalars().first()

    if invoice is None:
        logger.warning("score_invoice: invoice %s not found", invoice_id)
        return {"fraud_score": 0, "triggered_signals": [], "created_exception": False}

    triggered: list[str] = []
    total_score = 0

    inv_total = float(invoice.total_amount or 0)
    vendor_id = invoice.vendor_id

    # ── Signal 1: Round dollar amount ──
    if inv_total > 1000 and inv_total == round(inv_total):
        triggered.append("round_amount")
        total_score += SIGNAL_WEIGHTS["round_amount"]

    # ── Signal 2: Amount spike (> 2x vendor historical avg) ──
    if vendor_id and inv_total > 0:
        hist_stmt = select(Invoice).where(
            Invoice.vendor_id == vendor_id,
            Invoice.status == "approved",
            Invoice.deleted_at.is_(None),
            Invoice.id != invoice_id,
            Invoice.total_amount.isnot(None),
        )
        hist_invoices = db.execute(hist_stmt).scalars().all()
        if len(hist_invoices) >= 3:
            avg = sum(float(h.total_amount) for h in hist_invoices) / len(hist_invoices)
            if avg > 0 and inv_total > 2.0 * avg:
                triggered.append("amount_spike")
                total_score += SIGNAL_WEIGHTS["amount_spike"]

    # ── Signal 3: Potential duplicate ──
    if vendor_id and inv_total > 0:
        window_start = datetime.now(timezone.utc) - timedelta(days=settings.DUPLICATE_DETECTION_WINDOW_DAYS)
        dup_stmt = select(Invoice).where(
            Invoice.vendor_id == vendor_id,
            Invoice.total_amount == invoice.total_amount,
            Invoice.created_at >= window_start,
            Invoice.deleted_at.is_(None),
            Invoice.id != invoice_id,
        )
        potential_dup = db.execute(dup_stmt).scalars().first()
        if potential_dup:
            triggered.append("potential_duplicate")
            total_score += SIGNAL_WEIGHTS["potential_duplicate"]

    # ── Signal 4: Stale invoice date ──
    if invoice.invoice_date:
        ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)
        inv_date = invoice.invoice_date
        if inv_date.tzinfo is None:
            inv_date = inv_date.replace(tzinfo=timezone.utc)
        if inv_date < ninety_days_ago:
            triggered.append("stale_invoice_date")
            total_score += SIGNAL_WEIGHTS["stale_invoice_date"]

    # ── Signal 5: New vendor ──
    if vendor_id:
        approved_count = len(db.execute(
            select(Invoice).where(
                Invoice.vendor_id == vendor_id,
                Invoice.status == "approved",
                Invoice.deleted_at.is_(None),
            )
        ).scalars().all())
        if approved_count < 3:
            triggered.append("new_vendor")
            total_score += SIGNAL_WEIGHTS["new_vendor"]

    # ── Update invoice.fraud_score ──
    prev_score = invoice.fraud_score or 0
    invoice.fraud_score = total_score
    db.flush()

    # ── Auto-create FRAUD_FLAG exception if HIGH+ ──
    created_exception = False
    if total_score >= settings.FRAUD_SCORE_HIGH_THRESHOLD:
        _ensure_fraud_exception(db, invoice_id, total_score, triggered)
        created_exception = True

    # ── Audit log ──
    audit_svc.log(
        db=db,
        action="invoice.fraud_scored",
        entity_type="invoice",
        entity_id=invoice_id,
        before={"fraud_score": prev_score},
        after={"fraud_score": total_score, "triggered_signals": triggered},
        notes=f"Fraud scoring: {total_score} points. Signals: {', '.join(triggered) or 'none'}",
    )

    db.commit()

    logger.info(
        "Fraud score for invoice %s: %d (signals: %s)",
        invoice_id, total_score, triggered,
    )
    return {"fraud_score": total_score, "triggered_signals": triggered, "created_exception": created_exception}


def _ensure_fraud_exception(
    db: Session,
    invoice_id: uuid.UUID,
    score: int,
    signals: list[str],
) -> None:
    """Create FRAUD_FLAG exception if one doesn't already exist (open)."""
    from app.models.exception_record import ExceptionRecord

    existing = db.execute(
        select(ExceptionRecord).where(
            ExceptionRecord.invoice_id == invoice_id,
            ExceptionRecord.exception_code == "FRAUD_FLAG",
            ExceptionRecord.status == "open",
        )
    ).scalars().first()

    if existing:
        return

    exc = ExceptionRecord(
        invoice_id=invoice_id,
        exception_code="FRAUD_FLAG",
        description=f"Fraud score {score}/100. Signals: {', '.join(signals)}",
        severity="critical",
        status="open",
    )
    db.add(exc)
    db.flush()
