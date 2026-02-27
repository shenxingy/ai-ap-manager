"""Recurring invoice pattern detection model."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin, TimestampMixin


class RecurringInvoicePattern(Base, UUIDMixin, TimestampMixin):
    """Auto-detected recurring invoice pattern per vendor.

    One row per vendor (unique constraint). Upserted by the detection Celery task.
    """

    __tablename__ = "recurring_invoice_patterns"

    __table_args__ = (UniqueConstraint("vendor_id", name="uq_recurring_pattern_vendor"),)

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False, index=True
    )
    frequency_days: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    tolerance_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.10)
    auto_fast_track: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
