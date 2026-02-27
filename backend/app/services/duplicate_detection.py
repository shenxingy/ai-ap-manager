"""Enhanced duplicate detection service.

Runs after extraction and sets normalized_amount_usd on the invoice.
Creates ExceptionRecord entries for exact and fuzzy duplicate matches.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ─── Fuzzy-match thresholds ───
AMOUNT_TOLERANCE_PCT = Decimal("0.02")   # ±2%
DATE_WINDOW_DAYS = 7                      # ±7 days


def check_duplicate(db: Session, invoice_id: str) -> list[dict]:
    """Check for duplicate invoices (exact and fuzzy) and create exceptions.

    Args:
        db: Synchronous SQLAlchemy session (Celery context).
        invoice_id: UUID string of the invoice to check.

    Returns:
        List of match dicts: [{match_type, matched_invoice_id}]
    """
    from app.models.invoice import Invoice
    from app.models.exception_record import ExceptionRecord

    inv_uuid = uuid.UUID(invoice_id)

    invoice = db.execute(
        select(Invoice).where(Invoice.id == inv_uuid, Invoice.deleted_at.is_(None))
    ).scalars().first()

    if invoice is None:
        logger.warning("check_duplicate: invoice %s not found", invoice_id)
        return []

    matches: list[dict] = []

    # ── Exact duplicate: same vendor + same invoice_number (excluding self) ──
    if invoice.vendor_id and invoice.invoice_number:
        exact_stmt = select(Invoice).where(
            Invoice.vendor_id == invoice.vendor_id,
            Invoice.invoice_number == invoice.invoice_number,
            Invoice.deleted_at.is_(None),
            Invoice.id != inv_uuid,
        )
        exact_match = db.execute(exact_stmt).scalars().first()
        if exact_match:
            _ensure_exception(
                db,
                invoice_id=inv_uuid,
                code="DUPLICATE_INVOICE",
                severity="high",
                description=(
                    f"Exact duplicate detected: same vendor ({invoice.vendor_id}) "
                    f"and invoice number '{invoice.invoice_number}'. "
                    f"Matched invoice: {exact_match.id}"
                ),
            )
            matches.append({"match_type": "exact", "matched_invoice_id": str(exact_match.id)})
            logger.info(
                "check_duplicate: EXACT duplicate found for invoice %s → %s",
                invoice_id, exact_match.id,
            )

    # ── Fuzzy duplicate: same vendor, amount ±2%, date ±7 days ──
    if invoice.vendor_id and invoice.normalized_amount_usd is not None:
        norm_amt = Decimal(str(invoice.normalized_amount_usd))
        low = norm_amt * (1 - AMOUNT_TOLERANCE_PCT)
        high = norm_amt * (1 + AMOUNT_TOLERANCE_PCT)

        date_center = invoice.invoice_date or invoice.created_at
        if date_center is not None:
            if hasattr(date_center, "tzinfo") and date_center.tzinfo is None:
                date_center = date_center.replace(tzinfo=timezone.utc)
            date_low = date_center - timedelta(days=DATE_WINDOW_DAYS)
            date_high = date_center + timedelta(days=DATE_WINDOW_DAYS)

            fuzzy_stmt = select(Invoice).where(
                Invoice.vendor_id == invoice.vendor_id,
                Invoice.normalized_amount_usd.isnot(None),
                Invoice.normalized_amount_usd >= float(low),
                Invoice.normalized_amount_usd <= float(high),
                Invoice.deleted_at.is_(None),
                Invoice.id != inv_uuid,
            )
            # Filter by date in Python (avoids timezone complexity in SQL)
            candidates = db.execute(fuzzy_stmt).scalars().all()
            for cand in candidates:
                cand_date = cand.invoice_date or cand.created_at
                if cand_date is None:
                    continue
                if hasattr(cand_date, "tzinfo") and cand_date.tzinfo is None:
                    cand_date = cand_date.replace(tzinfo=timezone.utc)
                if date_low <= cand_date <= date_high:
                    # Skip if already caught as exact duplicate
                    if any(m["matched_invoice_id"] == str(cand.id) for m in matches):
                        continue
                    _ensure_exception(
                        db,
                        invoice_id=inv_uuid,
                        code="DUPLICATE_INVOICE",
                        severity="medium",
                        description=(
                            f"Potential duplicate detected: same vendor ({invoice.vendor_id}), "
                            f"amount within 2% (normalized ${float(norm_amt):.2f}), "
                            f"date within ±7 days. Matched invoice: {cand.id}"
                        ),
                    )
                    matches.append({"match_type": "fuzzy", "matched_invoice_id": str(cand.id)})
                    logger.info(
                        "check_duplicate: FUZZY duplicate found for invoice %s → %s",
                        invoice_id, cand.id,
                    )
                    break  # one fuzzy exception is sufficient

    if matches:
        db.commit()

    return matches


def _ensure_exception(
    db: Session,
    invoice_id: uuid.UUID,
    code: str,
    severity: str,
    description: str,
) -> None:
    """Create a DUPLICATE_INVOICE exception if one doesn't already exist (open)."""
    from app.models.exception_record import ExceptionRecord

    existing = db.execute(
        select(ExceptionRecord).where(
            ExceptionRecord.invoice_id == invoice_id,
            ExceptionRecord.exception_code == code,
            ExceptionRecord.status == "open",
        )
    ).scalars().first()

    if existing:
        return

    exc = ExceptionRecord(
        invoice_id=invoice_id,
        exception_code=code,
        description=description,
        severity=severity,
        status="open",
    )
    db.add(exc)
    db.flush()
