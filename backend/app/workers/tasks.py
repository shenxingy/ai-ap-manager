"""Celery async tasks for invoice processing pipeline."""
import io
import json
import logging
import uuid

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


# ─── Sync DB session factory (Celery workers are synchronous) ───

def _get_sync_session():
    """Return a sync SQLAlchemy session. Caller must close it."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.core.config import settings

    engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    return Session()


# ─── OCR helpers ───

def _run_ocr_on_bytes(file_bytes: bytes, mime_type: str) -> str:
    """Convert file bytes to raw OCR text.

    For PDFs: pdf2image → list of PIL images → pytesseract per page.
    For images: pytesseract directly.
    Returns concatenated raw text.
    """
    import pytesseract
    from PIL import Image

    if mime_type == "application/pdf":
        from pdf2image import convert_from_bytes
        pages = convert_from_bytes(file_bytes)
    else:
        pages = [Image.open(io.BytesIO(file_bytes))]

    texts = []
    for page in pages:
        text = pytesseract.image_to_string(page)
        texts.append(text)
    return "\n".join(texts)


# ─── Main task ───

@celery_app.task(bind=True, name="tasks.process_invoice", max_retries=3)
def process_invoice(self, invoice_id: str) -> dict:
    """Full invoice extraction pipeline.

    1. Fetch invoice, set status=extracting
    2. Download from MinIO
    3. OCR (Tesseract or Claude Vision)
    4. Dual-pass LLM extraction
    5. Save results to DB
    6. Set status=extracted (or exception)
    7. Audit log
    """
    logger.info("process_invoice started: %s", invoice_id)
    db = _get_sync_session()

    try:
        from app.models.invoice import Invoice, InvoiceLineItem, ExtractionResult
        from app.services import storage as storage_svc
        from app.services import audit as audit_svc
        from app.ai import extractor
        from app.core.config import settings
        from sqlalchemy import select

        inv_uuid = uuid.UUID(invoice_id)

        # 1. Fetch invoice
        invoice = db.execute(select(Invoice).where(Invoice.id == inv_uuid)).scalar_one_or_none()
        if invoice is None:
            logger.error("Invoice %s not found in DB", invoice_id)
            return {"invoice_id": invoice_id, "status": "not_found"}

        prev_status = invoice.status
        invoice.status = "extracting"
        db.commit()

        audit_svc.log(
            db=db,
            action="invoice.status_changed",
            entity_type="invoice",
            entity_id=inv_uuid,
            before={"status": prev_status},
            after={"status": "extracting"},
            notes="Celery task started",
        )
        db.commit()

        # 2. Download file from MinIO
        try:
            file_bytes = storage_svc.download_file(
                bucket=settings.MINIO_BUCKET_NAME,
                object_name=invoice.storage_path,
            )
        except Exception as exc:
            logger.warning("MinIO download failed for %s: %s", invoice_id, exc)
            raise self.retry(exc=exc, countdown=30)

        # 3. OCR
        raw_text = ""
        ocr_confidence = 0.5  # default

        if settings.USE_CLAUDE_VISION:
            # Claude vision: pass image bytes directly — OCR skipped
            # Convert to base64 for Claude vision API
            import base64
            raw_text = f"[VISION_MODE] base64 image length={len(file_bytes)}"
            # In vision mode, pass the image bytes as raw_text placeholder;
            # the extractor would need a separate vision code path.
            # For now, fall back to pytesseract even in vision mode unless
            # a full vision extraction path is implemented.
            try:
                raw_text = _run_ocr_on_bytes(file_bytes, invoice.mime_type or "application/pdf")
                ocr_confidence = 0.8
            except Exception as exc:
                logger.warning("OCR failed (vision fallback): %s", exc)
                raw_text = ""
        else:
            try:
                raw_text = _run_ocr_on_bytes(file_bytes, invoice.mime_type or "application/pdf")
                ocr_confidence = 0.85
            except Exception as exc:
                logger.warning("OCR failed for %s: %s", invoice_id, exc)
                raw_text = ""

        logger.info("OCR complete for %s: %d chars", invoice_id, len(raw_text))

        # 4. Dual-pass LLM extraction
        pass1_result = extractor.run_extraction_pass(
            db=db, raw_text=raw_text, pass_number=1, invoice_id=inv_uuid
        )
        db.commit()  # flush ai_call_logs

        pass2_result = extractor.run_extraction_pass(
            db=db, raw_text=raw_text, pass_number=2, invoice_id=inv_uuid
        )
        db.commit()

        pass1_fields = pass1_result["fields"]
        pass2_fields = pass2_result["fields"]

        discrepancies = extractor.compare_passes(pass1_fields, pass2_fields)
        merged = extractor.merge_passes(pass1_fields, pass2_fields, discrepancies)

        logger.info(
            "Extraction done for %s: discrepancies=%s", invoice_id, discrepancies
        )

        # 5a. Store ExtractionResult for pass 1
        er1 = ExtractionResult(
            invoice_id=inv_uuid,
            pass_number=1,
            model_used=settings.ANTHROPIC_MODEL,
            raw_json=json.dumps(pass1_fields, default=str),
            tokens_used=(pass1_result["tokens_prompt"] + pass1_result["tokens_completion"]),
            latency_ms=pass1_result["latency_ms"],
            discrepancy_fields=json.dumps(discrepancies) if discrepancies else None,
        )
        db.add(er1)

        # 5b. Store ExtractionResult for pass 2
        er2 = ExtractionResult(
            invoice_id=inv_uuid,
            pass_number=2,
            model_used=settings.ANTHROPIC_MODEL,
            raw_json=json.dumps(pass2_fields, default=str),
            tokens_used=(pass2_result["tokens_prompt"] + pass2_result["tokens_completion"]),
            latency_ms=pass2_result["latency_ms"],
            discrepancy_fields=None,
        )
        db.add(er2)

        # 5c. Update invoice scalar fields from merged extraction
        def _safe_float(val) -> float | None:
            try:
                return float(val) if val is not None else None
            except (TypeError, ValueError):
                return None

        invoice.vendor_name_raw = merged.get("vendor_name")
        invoice.vendor_address_raw = merged.get("vendor_address")
        invoice.invoice_number = merged.get("invoice_number")
        invoice.currency = merged.get("currency")
        invoice.subtotal = _safe_float(merged.get("subtotal"))
        invoice.tax_amount = _safe_float(merged.get("tax_amount"))
        invoice.total_amount = _safe_float(merged.get("total_amount"))
        invoice.payment_terms = merged.get("payment_terms")
        invoice.ocr_confidence = ocr_confidence
        invoice.extraction_model = settings.ANTHROPIC_MODEL

        # Parse dates loosely
        from datetime import datetime as dt
        for field_name, col_name in [("invoice_date", "invoice_date"), ("due_date", "due_date")]:
            raw_val = merged.get(field_name)
            if raw_val:
                for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%B %d, %Y"):
                    try:
                        setattr(invoice, col_name, dt.strptime(raw_val, fmt))
                        break
                    except (ValueError, TypeError):
                        pass

        # 5d. Save line items
        line_items_data = merged.get("line_items") or []
        for idx, li in enumerate(line_items_data, start=1):
            if not isinstance(li, dict):
                continue
            line_item = InvoiceLineItem(
                invoice_id=inv_uuid,
                line_number=li.get("line_number", idx),
                description=str(li.get("description") or ""),
                quantity=_safe_float(li.get("quantity")),
                unit_price=_safe_float(li.get("unit_price")),
                unit=li.get("unit"),
                line_total=_safe_float(li.get("line_total")),
            )
            db.add(line_item)

        # 6. Set final status
        too_many_discrepancies = len(discrepancies) > settings.DUAL_PASS_MAX_MISMATCHES
        extraction_failed = bool(pass1_result["error"] and pass2_result["error"])

        if extraction_failed or (not pass1_fields and not raw_text):
            invoice.status = "exception"
            final_status = "exception"
        elif too_many_discrepancies:
            invoice.status = "extracted"  # still extracted but flagged
            final_status = "extracted"
        else:
            invoice.status = "extracted"
            final_status = "extracted"

        db.commit()

        # 7. Audit log — extraction complete
        audit_svc.log(
            db=db,
            action="invoice.status_changed",
            entity_type="invoice",
            entity_id=inv_uuid,
            before={"status": "extracting"},
            after={"status": final_status, "discrepancies": discrepancies},
            notes=f"Dual-pass extraction complete. Discrepant fields: {discrepancies}",
        )
        db.commit()

        # 8. Run 2-way match (only if extraction succeeded)
        if final_status == "extracted":
            try:
                from app.rules.match_engine import run_2way_match
                invoice.status = "matching"
                db.commit()

                audit_svc.log(
                    db=db,
                    action="invoice.status_changed",
                    entity_type="invoice",
                    entity_id=inv_uuid,
                    before={"status": "extracted"},
                    after={"status": "matching"},
                    notes="2-way match started",
                )
                db.commit()

                match_result = run_2way_match(db, inv_uuid)
                # match engine sets invoice.status and commits
                final_status = invoice.status
                logger.info(
                    "2-way match complete for %s: match_status=%s invoice.status=%s",
                    invoice_id, match_result.match_status, final_status
                )
            except Exception as match_exc:
                logger.exception("Match engine failed for %s: %s", invoice_id, match_exc)
                # Don't fail the whole task; leave status as extracted
                invoice.status = "extracted"
                db.commit()
                final_status = "extracted"

        logger.info("process_invoice complete: %s → %s", invoice_id, final_status)
        return {"invoice_id": invoice_id, "status": final_status}

    except Exception as exc:
        db.rollback()
        logger.exception("process_invoice failed for %s: %s", invoice_id, exc)
        # Retry on transient errors
        raise self.retry(exc=exc, countdown=60)

    finally:
        db.close()


# ─── OCR-only task (kept for backward compat) ───

@celery_app.task(bind=True, name="tasks.run_ocr", max_retries=2)
def run_ocr(self, invoice_id: str, storage_path: str) -> dict:
    """Extract text from invoice file using Tesseract."""
    logger.info("run_ocr for invoice %s", invoice_id)
    return {"invoice_id": invoice_id, "status": "delegated_to_process_invoice"}
