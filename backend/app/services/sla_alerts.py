"""SLA alerts service for overdue and approaching invoice deadlines.

Checks invoices for SLA violations and creates alert records.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ─── SLA Configuration ───
OVERDUE_ALERT_TYPE = "overdue"
APPROACHING_ALERT_TYPE = "approaching"


def check_sla_alerts(db: Session, invoice_id: str) -> list[dict]:
    """Check for SLA violations (overdue or approaching deadline).

    Args:
        db: Synchronous SQLAlchemy session.
        invoice_id: UUID string of the invoice to check.

    Returns:
        List of alert dicts: [{alert_type, alert_id}]
    """
    from app.models.invoice import Invoice
    from app.models.sla_alert import SLAAlert

    inv_uuid = uuid.UUID(invoice_id)

    invoice = db.execute(
        select(Invoice).where(Invoice.id == inv_uuid, Invoice.deleted_at.is_(None))
    ).scalars().first()

    if invoice is None:
        logger.warning("check_sla_alerts: invoice %s not found", invoice_id)
        return []

    if invoice.due_date is None:
        logger.debug("check_sla_alerts: invoice %s has no due_date", invoice_id)
        return []

    alerts: list[dict] = []
    now = datetime.now(timezone.utc)
    one_day_from_now = now + timedelta(days=1)

    # Check if overdue: due_date < now and status is PENDING/MATCHING
    if invoice.due_date < now and invoice.status in ("pending", "matching"):
        alert = _ensure_alert(
            db,
            invoice_id=inv_uuid,
            alert_type=OVERDUE_ALERT_TYPE,
            description=f"Invoice {invoice.invoice_number} is overdue. Due date was {invoice.due_date.date()}.",
        )
        if alert:
            alerts.append({"alert_type": OVERDUE_ALERT_TYPE, "alert_id": str(alert.id)})
            logger.info("check_sla_alerts: OVERDUE alert created for invoice %s", invoice_id)

    # Check if approaching: due_date <= now + 1 day and status is PENDING/MATCHING and NOT already overdue
    elif invoice.due_date <= one_day_from_now and invoice.status in ("pending", "matching"):
        alert = _ensure_alert(
            db,
            invoice_id=inv_uuid,
            alert_type=APPROACHING_ALERT_TYPE,
            description=f"Invoice {invoice.invoice_number} is approaching due date. Due date is {invoice.due_date.date()}.",
        )
        if alert:
            alerts.append({"alert_type": APPROACHING_ALERT_TYPE, "alert_id": str(alert.id)})
            logger.info("check_sla_alerts: APPROACHING alert created for invoice %s", invoice_id)

    return alerts


def _ensure_alert(
    db: Session,
    invoice_id: uuid.UUID,
    alert_type: str,
    description: str,
) -> "SLAAlert | None":
    """Create an SLA alert if one doesn't already exist (open).

    Returns:
        The created alert, or None if one already existed.
    """
    from app.models.sla_alert import SLAAlert

    existing = db.execute(
        select(SLAAlert).where(
            SLAAlert.invoice_id == invoice_id,
            SLAAlert.alert_type == alert_type,
            SLAAlert.status == "open",
        )
    ).scalars().first()

    if existing:
        return None

    alert = SLAAlert(
        invoice_id=invoice_id,
        alert_type=alert_type,
        description=description,
        status="open",
    )
    db.add(alert)
    db.flush()
    return alert
