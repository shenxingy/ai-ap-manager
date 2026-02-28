"""Celery task for daily SLA alert checks."""
import logging
from datetime import date, datetime, timezone

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Statuses that count as "pending approval" for SLA purposes
PENDING_STATUSES = {"ingested", "extracting", "extracted", "matching", "matched", "exception"}


@celery_app.task(name="app.workers.sla_tasks.check_sla_alerts")
def check_sla_alerts():
    """Check all pending invoices for SLA breaches and log alerts.

    Runs daily at 8 AM UTC. For each pending invoice with a due_date:
    - If due_date < today → critical alert (overdue)
    - If due_date within SLA_WARNING_DAYS_BEFORE → warning alert

    Deduplicates: one alert per invoice+type per day.
    """
    logger.info("check_sla_alerts: starting daily SLA check")
    try:
        from sqlalchemy import create_engine, func, select
        from sqlalchemy.orm import sessionmaker
        from app.core.config import settings
        from app.models.invoice import Invoice
        from app.models.sla_alert import SlaAlert

        engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
        Session = sessionmaker(bind=engine, expire_on_commit=False)

        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        warning_days = settings.SLA_WARNING_DAYS_BEFORE

        stats = {"warnings": 0, "critical": 0, "skipped_dedup": 0}

        with Session() as db:
            # Load pending invoices with a due_date
            invoices = db.execute(
                select(Invoice).where(
                    Invoice.deleted_at.is_(None),
                    Invoice.status.in_(list(PENDING_STATUSES)),
                    Invoice.due_date.isnot(None),
                )
            ).scalars().all()

            for inv in invoices:
                due = inv.due_date
                # Make tz-aware if naive
                if due.tzinfo is None:
                    due = due.replace(tzinfo=timezone.utc)

                days_until = int((due - now).total_seconds() / 86400)

                if days_until < 0:
                    alert_type = "critical"
                elif days_until <= warning_days:
                    alert_type = "warning"
                else:
                    continue  # Not yet in alert window

                # Deduplication check: one alert per invoice+type per day
                existing = db.execute(
                    select(func.count(SlaAlert.id)).where(
                        SlaAlert.invoice_id == inv.id,
                        SlaAlert.alert_type == alert_type,
                        SlaAlert.alert_date >= today_start,
                    )
                ).scalar()

                if existing and existing > 0:
                    stats["skipped_dedup"] += 1
                    continue

                alert = SlaAlert(
                    invoice_id=inv.id,
                    alert_type=alert_type,
                    due_date=due,
                    days_until_due=days_until,
                    invoice_status=inv.status,
                    alert_date=now,
                )
                db.add(alert)

                if alert_type == "critical":
                    stats["critical"] += 1
                    logger.warning(
                        "SLA CRITICAL: Invoice %s (status=%s) overdue by %d days",
                        inv.id, inv.status, abs(days_until),
                    )
                else:
                    stats["warnings"] += 1
                    logger.info(
                        "SLA WARNING: Invoice %s (status=%s) due in %d days",
                        inv.id, inv.status, days_until,
                    )

            db.commit()

        logger.info(
            "check_sla_alerts: complete — warnings=%d, critical=%d, dedup_skipped=%d",
            stats["warnings"], stats["critical"], stats["skipped_dedup"],
        )
        return stats

    except Exception as exc:
        logger.exception("check_sla_alerts failed: %s", exc)
        return {"status": "error", "error": str(exc)}


@celery_app.task(name="app.workers.sla_tasks.expire_compliance_docs")
def expire_compliance_docs():
    """Expire vendor compliance documents past their expiry_date.

    Runs weekly on Monday at 1 AM UTC. For each vendor compliance doc with:
    - expiry_date < today AND
    - status IN ("approved", "active")

    Set status = "expired" and commit.
    """
    logger.info("expire_compliance_docs: starting weekly compliance doc expiry check")
    try:
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import sessionmaker
        from app.core.config import settings
        from app.models.vendor import VendorComplianceDoc

        engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
        Session = sessionmaker(bind=engine, expire_on_commit=False)

        today = date.today()
        stats = {"expired": 0}

        with Session() as db:
            # Load docs that are past expiry and in active/approved status
            docs = db.execute(
                select(VendorComplianceDoc).where(
                    VendorComplianceDoc.expiry_date < today,
                    VendorComplianceDoc.status.in_(["approved", "active"]),
                )
            ).scalars().all()

            for doc in docs:
                doc.status = "expired"
                stats["expired"] += 1
                logger.info(
                    "Expired compliance doc %s for vendor %s (was %s)",
                    doc.id, doc.vendor_id, "approved" if doc.status == "approved" else "active",
                )

            db.commit()

        logger.info(
            "expire_compliance_docs: complete — expired=%d docs",
            stats["expired"],
        )
        return stats

    except Exception as exc:
        logger.exception("expire_compliance_docs failed: %s", exc)
        return {"status": "error", "error": str(exc)}
