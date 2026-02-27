import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class Invoice(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "invoices"

    invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=True, index=True
    )
    po_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_orders.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="ingested"
    )  # ingested, extracting, extracted, matching, matched, exception, approved, paid, rejected, cancelled
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="upload")  # upload, email, api
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    subtotal: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    tax_amount: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    total_amount: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    invoice_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String(100), nullable=True)
    vendor_name_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)  # extracted text before vendor lookup
    vendor_address_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    remit_to: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    fraud_score: Mapped[int] = mapped_column(nullable=False, default=0)  # 0-100
    fraud_triggered_signals: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="'[]'")
    is_recurring: Mapped[bool] = mapped_column(nullable=False, default=False)
    is_duplicate: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    recurring_pattern_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recurring_invoice_patterns.id"), nullable=True
    )
    ocr_confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)  # 0.0-1.0
    extraction_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    normalized_amount_usd: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    line_items: Mapped[list["InvoiceLineItem"]] = relationship("InvoiceLineItem", back_populates="invoice")
    extraction_results: Mapped[list["ExtractionResult"]] = relationship(
        "ExtractionResult", back_populates="invoice"
    )


class InvoiceLineItem(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "invoice_line_items"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    line_number: Mapped[int] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    line_total: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gl_account: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gl_account_suggested: Mapped[str | None] = mapped_column(String(100), nullable=True)  # GL Smart Coding
    cost_center: Mapped[str | None] = mapped_column(String(100), nullable=True)
    po_line_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("po_line_items.id"), nullable=True
    )

    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="line_items")


class ExtractionResult(Base, UUIDMixin, TimestampMixin):
    """Dual-pass extraction results — stores both passes for field-level comparison."""

    __tablename__ = "extraction_results"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pass_number: Mapped[int] = mapped_column(nullable=False)  # 1 or 2
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_json: Mapped[str] = mapped_column(Text, nullable=False)  # full extracted JSON
    confidence_scores: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON field->score map
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discrepancy_fields: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of fields that differed between passes

    invoice: Mapped["Invoice"] = relationship("Invoice", back_populates="extraction_results")
