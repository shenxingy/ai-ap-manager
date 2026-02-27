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

        # 7b. Normalize amount to USD (for cross-currency duplicate detection)
        try:
            from decimal import Decimal
            from app.services.fx import convert_to_usd
            if invoice.total_amount is not None and invoice.currency:
                invoice.normalized_amount_usd = float(
                    convert_to_usd(Decimal(str(invoice.total_amount)), invoice.currency)
                )
                db.flush()
                logger.info(
                    "FX normalized invoice %s: %s %s → $%.4f USD",
                    invoice_id, invoice.total_amount, invoice.currency, invoice.normalized_amount_usd,
                )
        except Exception as fx_exc:
            logger.warning("FX normalization failed for invoice %s: %s", invoice_id, fx_exc)

        # 7c. Duplicate detection (exact + fuzzy, creates DUPLICATE_INVOICE exceptions)
        try:
            from app.services.duplicate_detection import check_duplicate
            dup_matches = check_duplicate(db, str(inv_uuid))
            if dup_matches:
                logger.info(
                    "Duplicate detection: invoice=%s found %d match(es): %s",
                    invoice_id, len(dup_matches), dup_matches,
                )
        except Exception as dup_exc:
            logger.warning("Duplicate detection failed for invoice %s: %s", invoice_id, dup_exc)

        # 7d. Fraud scoring (run after extraction, before match)
        try:
            from app.services.fraud_scoring import score_invoice
            fraud_result = score_invoice(db, inv_uuid)
            logger.info("Fraud scored: invoice=%s score=%d", invoice_id, fraud_result["fraud_score"])
        except Exception as fraud_exc:
            logger.warning("Fraud scoring failed for invoice %s: %s", invoice_id, fraud_exc)

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


# ─── Recurring pattern detection ───

@celery_app.task(bind=True, name="tasks.detect_recurring_patterns", max_retries=2)
def detect_recurring_patterns(self) -> dict:
    """Detect recurring invoice patterns per vendor and upsert RecurringInvoicePattern rows.

    Algorithm:
    1. For each vendor with >= 3 approved invoices in the last 12 months
    2. Sort by invoice_date; compute day intervals between consecutive invoices
    3. If intervals cluster near {7, 14, 30, 60, 90} days (±20%), record as recurring
    4. Compute avg_amount; upsert RecurringInvoicePattern
    """
    from datetime import date, timedelta as td
    from decimal import Decimal
    from sqlalchemy import select, text, func
    from app.models.invoice import Invoice
    from app.models.vendor import Vendor
    from app.models.recurring_pattern import RecurringInvoicePattern

    logger.info("detect_recurring_patterns started")
    db = _get_sync_session()

    CANDIDATE_FREQUENCIES = [7, 14, 30, 60, 90]
    TOLERANCE = 0.20  # ±20%
    MIN_INVOICES = 3
    LOOKBACK_DAYS = 365

    updated = 0
    skipped = 0

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

        # Get all vendors with enough approved invoices in the window
        vendors_result = db.execute(
            select(Vendor.id).where(Vendor.deleted_at.is_(None))
        ).scalars().all()

        for vendor_id in vendors_result:
            invoices = db.execute(
                select(Invoice).where(
                    Invoice.vendor_id == vendor_id,
                    Invoice.status == "approved",
                    Invoice.deleted_at.is_(None),
                    Invoice.invoice_date.isnot(None),
                    Invoice.created_at >= cutoff,
                ).order_by(Invoice.invoice_date)
            ).scalars().all()

            if len(invoices) < MIN_INVOICES:
                skipped += 1
                continue

            # Compute day intervals between consecutive invoice dates
            dates = sorted([
                inv.invoice_date.date() if hasattr(inv.invoice_date, 'date') else inv.invoice_date
                for inv in invoices
            ])
            intervals = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
            if not intervals:
                skipped += 1
                continue

            avg_interval = sum(intervals) / len(intervals)

            # Find best matching canonical frequency
            best_freq = None
            for freq in CANDIDATE_FREQUENCIES:
                low, high = freq * (1 - TOLERANCE), freq * (1 + TOLERANCE)
                matching = sum(1 for iv in intervals if low <= iv <= high)
                if matching >= len(intervals) * 0.6:  # 60% of intervals must cluster
                    best_freq = freq
                    break

            if best_freq is None:
                skipped += 1
                continue

            amounts = [float(inv.total_amount) for inv in invoices if inv.total_amount]
            avg_amount = sum(amounts) / len(amounts) if amounts else 0.0

            # Upsert pattern
            existing = db.execute(
                select(RecurringInvoicePattern).where(
                    RecurringInvoicePattern.vendor_id == vendor_id
                )
            ).scalars().first()

            now_utc = datetime.now(timezone.utc)

            if existing:
                existing.frequency_days = best_freq
                existing.avg_amount = Decimal(str(round(avg_amount, 4)))
                existing.last_detected_at = now_utc
            else:
                pattern = RecurringInvoicePattern(
                    vendor_id=vendor_id,
                    frequency_days=best_freq,
                    avg_amount=Decimal(str(round(avg_amount, 4))),
                    tolerance_pct=0.10,
                    auto_fast_track=False,
                    last_detected_at=now_utc,
                )
                db.add(pattern)

            updated += 1

        db.commit()
        logger.info("detect_recurring_patterns done: updated=%d skipped=%d", updated, skipped)
        return {"updated": updated, "skipped": skipped}

    except Exception as exc:
        db.rollback()
        logger.exception("detect_recurring_patterns failed: %s", exc)
        raise self.retry(exc=exc, countdown=60)

    finally:
        db.close()
