"""Email ingestion worker — polls an IMAP mailbox for unseen messages and creates Invoice records."""
import email
import email.utils
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from app.db.sync_session import get_sync_session as _get_sync_session
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
}
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tiff"}
MIME_BY_EXT = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tiff": "image/tiff",
}


# ─── Task ───

@celery_app.task(name="app.workers.email_ingestion.poll_ap_mailbox")
def poll_ap_mailbox() -> dict:
    """Poll IMAP mailbox for unseen messages and ingest invoice attachments.

    Reads IMAP_HOST, IMAP_PORT, IMAP_USER, IMAP_PASSWORD, IMAP_MAILBOX from settings.
    Returns immediately if IMAP_HOST is not configured.
    """
    import imaplib

    from app.core.config import settings

    if not settings.IMAP_HOST:
        logger.info("poll_ap_mailbox: IMAP_HOST not configured — skipping")
        return {"status": "skipped", "reason": "IMAP_HOST not configured"}

    processed = 0
    errors = 0

    try:
        mail = imaplib.IMAP4_SSL(settings.IMAP_HOST, settings.IMAP_PORT)
        mail.login(settings.IMAP_USER, settings.IMAP_PASSWORD)
        mail.select(settings.IMAP_MAILBOX)

        _, uid_data = mail.search(None, "UNSEEN")
        uids = uid_data[0].split()
        logger.info("poll_ap_mailbox: %d unseen message(s) found", len(uids))

        for uid in uids:
            try:
                _, msg_data = mail.fetch(uid, "(RFC822)")
                raw = cast(tuple[bytes, bytes], msg_data[0])[1]
                msg = email.message_from_bytes(cast(bytes, raw))
                count = _ingest_message(msg)
                processed += count
                # Mark as Seen regardless of attachment outcome
                mail.store(uid, "+FLAGS", "\\Seen")
            except Exception as exc:
                logger.exception("poll_ap_mailbox: failed processing uid %s: %s", uid, exc)
                errors += 1

        mail.logout()

    except Exception as exc:
        logger.exception("poll_ap_mailbox: IMAP connection error: %s", exc)
        return {"status": "error", "error": "IMAP connection error"}

    logger.info("poll_ap_mailbox done: processed=%d errors=%d", processed, errors)
    return {"status": "ok", "processed": processed, "errors": errors}


# ─── Helpers ───

def _ingest_message(msg: email.message.Message) -> int:
    """Parse a single email message and create Invoice records for each valid attachment.

    Returns the count of invoices created.
    """
    from app.core.config import settings
    from app.models.invoice import Invoice
    from app.services import audit as audit_svc
    from app.services import storage as storage_svc

    from_header = msg.get("From", "")
    from_address = email.utils.parseaddr(from_header)[1] or from_header or "unknown"
    subject = msg.get("Subject", "") or ""

    # Parse Date header → email_received_at
    date_str = msg.get("Date", "")
    received_at: datetime | None = None
    if date_str:
        try:
            ts = email.utils.parsedate_to_datetime(date_str)
            received_at = ts.astimezone(UTC)
        except Exception:
            received_at = None

    db = _get_sync_session()
    ingested = 0
    try:
        for part in msg.walk():
            ct = part.get_content_type()
            fname = part.get_filename() or ""
            suffix = Path(fname).suffix.lower() if fname else ""

            is_valid = (ct in ALLOWED_MIME_TYPES) or (suffix in ALLOWED_EXTENSIONS)
            if not is_valid:
                continue

            payload = cast(bytes, part.get_payload(decode=True))
            if not payload:
                continue

            # Derive safe filename and mime type
            if not fname:
                ext = ".pdf" if ct == "application/pdf" else ".jpg"
                fname = f"attachment{ext}"
                suffix = ext

            mime_type = MIME_BY_EXT.get(suffix, ct or "application/octet-stream")
            invoice_id = uuid.uuid4()
            object_name = f"invoices/{invoice_id}/{fname}"

            try:
                storage_svc.upload_file(
                    bucket=settings.MINIO_BUCKET_NAME,
                    object_name=object_name,
                    data=payload,
                    content_type=mime_type,
                )
            except Exception as exc:
                logger.warning("MinIO upload failed for %s: %s", fname, exc)
                continue

            invoice = Invoice(
                id=invoice_id,
                status="ingested",
                storage_path=object_name,
                file_name=fname,
                mime_type=mime_type,
                file_size_bytes=len(payload),
                source="email",
                source_email=from_address,
                email_from=from_address,
                email_subject=subject,
                email_received_at=received_at,
            )
            db.add(invoice)
            db.flush()

            audit_svc.log(
                db=db,
                action="invoice_ingested_from_email",
                entity_type="invoice",
                entity_id=invoice_id,
                after={
                    "filename": fname,
                    "from_address": from_address,
                    "subject": subject,
                },
            )
            db.commit()

            try:
                from app.workers.tasks import process_invoice  # noqa: PLC0415
                process_invoice.delay(str(invoice_id))
            except Exception as exc:
                logger.warning("Failed to enqueue process_invoice for %s: %s", invoice_id, exc)

            logger.info(
                "Ingested email attachment: invoice_id=%s file=%s from=%s",
                invoice_id, fname, from_address,
            )
            ingested += 1

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return ingested
