"""AI feedback logging service.

Records human corrections for AI-extracted fields, GL coding overrides,
and exception resolutions into the ai_feedback table.
"""
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def log_field_correction(
    db: AsyncSession,
    invoice_id: uuid.UUID,
    field_name: str,
    old_value: Any,
    new_value: Any,
    actor_id: uuid.UUID | None,
    actor_email: str | None,
    vendor_id: uuid.UUID | None = None,
) -> None:
    """Log a field correction event to ai_feedback."""
    try:
        from app.models.feedback import AiFeedback
        entry = AiFeedback(
            feedback_type="field_correction",
            entity_type="invoice",
            entity_id=invoice_id,
            field_name=field_name,
            old_value=str(old_value) if old_value is not None else None,
            new_value=str(new_value) if new_value is not None else None,
            actor_id=actor_id,
            actor_email=actor_email,
            invoice_id=invoice_id,
            vendor_id=vendor_id,
        )
        db.add(entry)
        # Do NOT commit here — caller commits
    except Exception as exc:
        logger.warning("log_field_correction failed (non-fatal): %s", exc)


async def log_gl_correction(
    db: AsyncSession,
    invoice_id: uuid.UUID,
    line_id: uuid.UUID,
    old_gl_account: str | None,
    new_gl_account: str,
    actor_id: uuid.UUID | None,
    actor_email: str | None,
    vendor_id: uuid.UUID | None = None,
) -> None:
    """Log a GL coding correction to ai_feedback."""
    try:
        from app.models.feedback import AiFeedback
        entry = AiFeedback(
            feedback_type="gl_correction",
            entity_type="invoice_line_item",
            entity_id=line_id,
            field_name="gl_account",
            old_value=old_gl_account,
            new_value=new_gl_account,
            actor_id=actor_id,
            actor_email=actor_email,
            invoice_id=invoice_id,
            vendor_id=vendor_id,
        )
        db.add(entry)
    except Exception as exc:
        logger.warning("log_gl_correction failed (non-fatal): %s", exc)


async def log_exception_correction(
    db: AsyncSession,
    exception_id: uuid.UUID,
    invoice_id: uuid.UUID | None,
    old_status: str | None,
    new_status: str | None,
    actor_id: uuid.UUID | None,
    actor_email: str | None,
) -> None:
    """Log an exception status change to ai_feedback."""
    try:
        from app.models.feedback import AiFeedback
        entry = AiFeedback(
            feedback_type="exception_correction",
            entity_type="exception",
            entity_id=exception_id,
            field_name="status",
            old_value=old_status,
            new_value=new_status,
            actor_id=actor_id,
            actor_email=actor_email,
            invoice_id=invoice_id,
        )
        db.add(entry)
    except Exception as exc:
        logger.warning("log_exception_correction failed (non-fatal): %s", exc)
