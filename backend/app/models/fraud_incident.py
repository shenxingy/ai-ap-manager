"""Fraud detection models: VendorBankHistory and FraudIncident."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin


class VendorBankHistory(Base, UUIDMixin):
    """Tracks changes to vendor bank account numbers (hashed for security)."""

    __tablename__ = "vendor_bank_histories"

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False, index=True
    )
    bank_account_number: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )  # SHA-256 hex digest of the raw bank account number
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class FraudIncident(Base, UUIDMixin):
    """Records a fraud flag raised by the scoring engine."""

    __tablename__ = "fraud_incidents"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True
    )
    score_at_flag: Mapped[int] = mapped_column(Integer, nullable=False)
    triggered_signals: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    outcome: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending"
    )  # pending, genuine, false_positive
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
