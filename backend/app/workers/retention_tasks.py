"""GDPR data retention task — soft-delete archived invoices, hard-delete old audit logs."""
import logging
from datetime import UTC, datetime, timedelta

from celery import shared_task
from sqlalchemy import create_engine, delete, update
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.audit import AuditLog
from app.models.invoice import Invoice

logger = logging.getLogger(__name__)


@shared_task(name="run_data_retention")
def run_data_retention() -> dict:
    """Run monthly GDPR data retention job.

    - Soft-deletes invoices older than RETENTION_DAYS_INVOICES with final status
    - Hard-deletes audit logs older than RETENTION_DAYS_AUDIT_LOGS
    - Logs the action to audit_logs table

    Returns:
        dict: {"status": "ok"|"skipped", "invoices_soft_deleted": N, "audit_logs_deleted": M, "error": str|None}
    """
    if not settings.RETENTION_ENABLED:
        return {"status": "skipped", "reason": "RETENTION_ENABLED=False"}

    # Create sync engine and session
    engine = create_engine(settings.DATABASE_URL_SYNC, echo=False)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        now = datetime.now(UTC)

        # ─── Soft-delete invoices ───
        cutoff_invoices = now - timedelta(days=settings.RETENTION_DAYS_INVOICES)
        invoices_stmt = (
            update(Invoice)
            .where(
                Invoice.deleted_at.is_(None),
                Invoice.created_at < cutoff_invoices,
                Invoice.status.in_(["approved", "paid", "rejected"]),
            )
            .values(deleted_at=now)
        )
        result_invoices = db.execute(invoices_stmt)
        invoices_count = result_invoices.rowcount
        db.commit()
        logger.info(f"Soft-deleted {invoices_count} invoices older than {cutoff_invoices}")

        # ─── Hard-delete audit logs ───
        cutoff_audit = now - timedelta(days=settings.RETENTION_DAYS_AUDIT_LOGS)
        audit_stmt = delete(AuditLog).where(AuditLog.created_at < cutoff_audit)
        result_audit = db.execute(audit_stmt)
        audit_logs_count = result_audit.rowcount
        db.commit()
        logger.info(f"Hard-deleted {audit_logs_count} audit logs older than {cutoff_audit}")

        # ─── Log retention action to audit_logs ───
        retention_log = AuditLog(
            actor_id=None,
            actor_email="system",
            action="DATA_RETENTION_RUN",
            entity_type="system",
            entity_id=None,
            notes=f"Soft-deleted {invoices_count} invoices; hard-deleted {audit_logs_count} audit logs",
        )
        db.add(retention_log)
        db.commit()
        logger.info("Logged retention job completion to audit_logs")

        return {
            "status": "ok",
            "invoices_soft_deleted": invoices_count,
            "audit_logs_deleted": audit_logs_count,
        }

    except Exception as e:
        db.rollback()
        logger.exception(f"Data retention job failed: {e}")
        return {
            "status": "error",
            "invoices_soft_deleted": 0,
            "audit_logs_deleted": 0,
            "error": str(e),
        }
    finally:
        db.close()
        engine.dispose()
