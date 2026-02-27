import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


EXCEPTION_CODES = (
    "PRICE_VARIANCE",
    "QTY_VARIANCE",
    "MISSING_PO",
    "VENDOR_MISMATCH",
    "DUPLICATE_INVOICE",
    "FRAUD_FLAG",
    "EXTRACTION_LOW_CONFIDENCE",
    "EXTRACTION_DISCREPANCY",
    "COMPLIANCE_MISSING",
    "AMOUNT_OVER_THRESHOLD",
    "OTHER",
)


class ExceptionRecord(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "exception_records"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True
    )
    exception_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")  # low, medium, high, critical
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="open"
    )  # open, in_progress, resolved, escalated, waived
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)  # LLM-generated root cause narrative

    invoice: Mapped["Invoice"] = relationship("Invoice", foreign_keys=[invoice_id])  # type: ignore[name-defined]
