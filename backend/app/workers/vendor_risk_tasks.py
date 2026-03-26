"""Vendor risk scoring Celery task.

Computes risk scores for all vendors weekly based on:
- exception_rate: fraction of invoices that hit exception status
- ocr_error_rate: derived from average ocr_confidence (1 - avg_confidence)
- score: exception_rate*0.6 + ocr_error_rate*0.4

Creates VENDOR_RISK exception records for HIGH/CRITICAL vendors.
"""
import logging
import uuid
from datetime import datetime

from sqlalchemy import text

from app.db.sync_session import get_sync_session as _get_sync_session
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="vendor_risk.compute_vendor_risk_scores")
def compute_vendor_risk_scores():
    """Compute risk scores for all vendors weekly.

    Returns dict with status and vendors_scored count.
    """
    db = _get_sync_session()
    try:
        vendors = db.execute(text(
            "SELECT DISTINCT vendor_id FROM invoices WHERE vendor_id IS NOT NULL AND deleted_at IS NULL"
        )).fetchall()

        updated = 0
        for row in vendors:
            vendor_id = row[0]

            stats = db.execute(text("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'exception' THEN 1 ELSE 0 END) as exceptions,
                    AVG(COALESCE(ocr_confidence, 0.8)) as avg_confidence
                FROM invoices
                WHERE vendor_id = :vid AND deleted_at IS NULL
            """), {"vid": str(vendor_id)}).fetchone()

            if not stats or stats.total == 0:
                continue

            exception_rate = float(stats.exceptions or 0) / float(stats.total)
            avg_confidence = float(stats.avg_confidence or 0.8)
            ocr_error_rate = 1.0 - avg_confidence
            score = min(1.0, exception_rate * 0.6 + ocr_error_rate * 0.4)

            if score >= 0.8:
                risk_level = "CRITICAL"
            elif score >= 0.6:
                risk_level = "HIGH"
            elif score >= 0.4:
                risk_level = "MEDIUM"
            else:
                risk_level = "LOW"

            # Upsert risk score (UNIQUE on vendor_id)
            db.execute(text("""
                INSERT INTO vendor_risk_scores
                    (id, vendor_id, ocr_error_rate, exception_rate, avg_extraction_confidence, score, risk_level, computed_at)
                VALUES
                    (:id, :vid, :ocr, :exc, :conf, :score, :level, :now)
                ON CONFLICT (vendor_id) DO UPDATE SET
                    ocr_error_rate = EXCLUDED.ocr_error_rate,
                    exception_rate = EXCLUDED.exception_rate,
                    avg_extraction_confidence = EXCLUDED.avg_extraction_confidence,
                    score = EXCLUDED.score,
                    risk_level = EXCLUDED.risk_level,
                    computed_at = EXCLUDED.computed_at
            """), {
                "id": str(uuid.uuid4()),
                "vid": str(vendor_id),
                "ocr": ocr_error_rate,
                "exc": exception_rate,
                "conf": avg_confidence,
                "score": score,
                "level": risk_level,
                "now": datetime.utcnow(),
            })

            # Create VENDOR_RISK exception for HIGH/CRITICAL vendors
            if risk_level in ("HIGH", "CRITICAL"):
                latest_invoice = db.execute(text("""
                    SELECT id FROM invoices
                    WHERE vendor_id = :vid AND status = 'pending' AND deleted_at IS NULL
                    ORDER BY created_at DESC LIMIT 1
                """), {"vid": str(vendor_id)}).fetchone()

                if latest_invoice:
                    inv_id = str(latest_invoice[0])
                    existing = db.execute(text("""
                        SELECT id FROM exception_records
                        WHERE invoice_id = :inv_id AND exception_code = 'VENDOR_RISK' AND status = 'open'
                    """), {"inv_id": inv_id}).fetchone()

                    if not existing:
                        severity = "high" if risk_level == "HIGH" else "critical"
                        db.execute(text("""
                            INSERT INTO exception_records
                                (id, invoice_id, exception_code, severity, status, description, created_at, updated_at)
                            VALUES
                                (:id, :inv_id, 'VENDOR_RISK', :sev, 'open', :desc, :now, :now)
                        """), {
                            "id": str(uuid.uuid4()),
                            "inv_id": inv_id,
                            "sev": severity,
                            "desc": f"Vendor risk level is {risk_level} (score={score:.2f}, exception_rate={exception_rate:.0%})",
                            "now": datetime.utcnow(),
                        })

            updated += 1

        db.commit()
        logger.info("Vendor risk scoring complete: %d vendors scored", updated)
        return {"status": "ok", "vendors_scored": updated}

    except Exception as e:
        db.rollback()
        logger.error("Vendor risk scoring failed: %s", e)
        return {"status": "error", "error": str(e)}
    finally:
        db.close()
