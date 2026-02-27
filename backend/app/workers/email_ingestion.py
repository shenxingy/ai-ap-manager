"""Email ingestion worker — polls /app/data/inbox/ for .eml files and creates Invoice records."""
import email
import logging
import os
import uuid
from pathlib import Path

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

INBOX_PATH = Path("/app/data/inbox")
ALLOWED_ATTACHMENT_TYPES = {".pdf", ".png", ".jpg", ".jpeg"}
MIME_MAP = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


# ─── Sync DB session ───

def _get_sync_session():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.core.config import settings

    engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    return Session()


# ─── Task ───

@celery_app.task(name="app.workers.email_ingestion.poll_ap_mailbox")
def poll_ap_mailbox() -> dict:
    """Scan inbox directory for .eml files and ingest each attachment as an Invoice.

    Reads EMAIL_HOST, EMAIL_USER, EMAIL_PASSWORD from settings to decide whether
    ingestion is configured. If not configured, skips silently.
    """
    from app.core.config import settings

    # Guard: if email credentials not configured, skip
    email_host = getattr(settings, "EMAIL_HOST", None)
    email_user = getattr(settings, "EMAIL_USER", None)
    email_password = getattr(settings, "EMAIL_PASSWORD", None)

    if not (email_host and email_user and email_password):
        logger.info("Email ingestion not configured — polling skipped")
        return {"status": "skipped", "reason": "not_configured"}

    # Ensure inbox exists
    INBOX_PATH.mkdir(parents=True, exist_ok=True)

    eml_files = list(INBOX_PATH.glob("*.eml"))
    if not eml_files:
        logger.info("poll_ap_mailbox: inbox empty, nothing to process")
        return {"status": "ok", "processed": 0}

    ingested = 0
    errors = 0

    for eml_path in eml_files:
        try:
            _process_eml(eml_path)
            ingested += 1
        except Exception as exc:
            logger.exception("poll_ap_mailbox: failed to process %s: %s", eml_path.name, exc)
            errors += 1

    logger.info("poll_ap_mailbox done: ingested=%d errors=%d", ingested, errors)
    return {"status": "ok", "processed": ingested, "errors": errors}


def _process_eml(eml_path: Path) -> None:
    """Parse a single .eml file and create Invoice records for each valid attachment."""
    from app.models.invoice import Invoice
    from app.services import storage as storage_svc
    from app.services import audit as audit_svc
    from app.core.config import settings

    with open(eml_path, "rb") as f:
        msg = email.message_from_bytes(f.read())

    from_address = email.utils.parseaddr(msg.get("From", ""))[1] or "unknown"

    db = _get_sync_session()
    try:
        for part in msg.walk():
            content_disposition = part.get("Content-Disposition", "")
            if "attachment" not in content_disposition:
                continue

            filename = part.get_filename()
            if not filename:
                continue

            suffix = Path(filename).suffix.lower()
            if suffix not in ALLOWED_ATTACHMENT_TYPES:
                logger.debug("Skipping non-invoice attachment: %s", filename)
                continue

            payload = part.get_payload(decode=True)
            if not payload:
                continue

            invoice_id = uuid.uuid4()
            object_name = f"invoices/{invoice_id}/{filename}"
            mime_type = MIME_MAP.get(suffix, "application/octet-stream")

            # Upload attachment to MinIO
            try:
                storage_svc.upload_file(
                    bucket=settings.MINIO_BUCKET_NAME,
                    object_name=object_name,
                    data=payload,
                    content_type=mime_type,
                )
            except Exception as exc:
                logger.warning("MinIO upload failed for %s: %s", filename, exc)
                continue

            # Create Invoice record
            invoice = Invoice(
                id=invoice_id,
                status="ingested",
                storage_path=object_name,
                file_name=filename,
                mime_type=mime_type,
                file_size_bytes=len(payload),
                source="email",
                source_email=from_address,
            )
            db.add(invoice)
            db.flush()

            # Write audit log
            audit_svc.log(
                db=db,
                action="invoice_ingested_from_email",
                entity_type="invoice",
                entity_id=invoice_id,
                after={"filename": filename, "from_address": from_address},
            )
            db.commit()

            # Enqueue extraction task
            try:
                from app.workers.tasks import process_invoice  # noqa: PLC0415
                process_invoice.delay(str(invoice_id))
            except Exception as exc:
                logger.warning("Failed to enqueue process_invoice for %s: %s", invoice_id, exc)

            logger.info(
                "Ingested email attachment: invoice_id=%s file=%s from=%s",
                invoice_id, filename, from_address,
            )

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
