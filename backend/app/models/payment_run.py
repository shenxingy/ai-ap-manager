from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.invoice import Invoice


class PaymentRun(Base, UUIDMixin, TimestampMixin):
    """
    Payment run entity representing a scheduled batch of invoices for payment.

    A payment run groups invoices (linked via the invoices relationship) that are
    scheduled to be paid together on a specific date, potentially to a specific vendor.
    Each run has a payment method (ACH, wire, check, etc.) and tracks execution state
    for audit purposes.

    Relationships:
        - invoices: List of Invoice records associated with this payment run
        - vendor (implicit): Optional vendor if this run is vendor-specific
        - executed_by (implicit): User who executed the payment run
    """
    __tablename__ = "payment_runs"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # FK to vendors; nullable for multi-vendor or generic payment runs
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=True, index=True
    )
    # Date when this payment run is scheduled to be processed
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Recurrence pattern (e.g. "one-time", "weekly", "monthly")
    frequency: Mapped[str] = mapped_column(String(50), nullable=False)
    # Workflow state: pending, approved, in_progress, executed, failed, cancelled
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    # Aggregate amount of all invoices in this run (denormalized for reporting)
    total_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    # ISO 4217 currency code (e.g. "USD", "EUR")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    # Count of invoices in this run (denormalized for reporting)
    invoice_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Payment method (e.g. "ACH", "wire_transfer", "check", "card")
    payment_method: Mapped[str] = mapped_column(String(50), nullable=False)
    # Timestamp when the payment run was actually executed
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # User who executed the payment run (audit trail)
    executed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # Optional narrative notes for the payment run (context, instructions, etc.)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    invoices: Mapped[list[Invoice]] = relationship("Invoice", back_populates="payment_run")
