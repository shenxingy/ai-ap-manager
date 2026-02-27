"""Celery async tasks for invoice processing pipeline."""
import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tasks.process_invoice", max_retries=3)
def process_invoice(self, invoice_id: str) -> dict:
    """
    Full invoice processing pipeline:
    1. OCR extraction (dual-pass)
    2. Vendor lookup
    3. 2/3-way matching
    4. Exception detection
    5. Fraud scoring
    6. Auto-approve if eligible
    """
    logger.info(f"Processing invoice {invoice_id}")
    # TODO: implement full pipeline in sprint 1
    return {"invoice_id": invoice_id, "status": "queued"}


@celery_app.task(bind=True, name="tasks.run_ocr", max_retries=2)
def run_ocr(self, invoice_id: str, storage_path: str) -> dict:
    """Extract text from invoice file using Tesseract + Claude Vision fallback."""
    logger.info(f"Running OCR for invoice {invoice_id}")
    # TODO: implement in sprint 1
    return {"invoice_id": invoice_id, "status": "queued"}
