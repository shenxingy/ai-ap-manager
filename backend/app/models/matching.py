import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class MatchResult(Base, UUIDMixin, TimestampMixin):
    """Header-level match result for an invoice against PO and/or GR."""

    __tablename__ = "match_results"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True, unique=True
    )
    po_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_orders.id"), nullable=True, index=True
    )
    gr_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("goods_receipts.id"), nullable=True
    )
    match_type: Mapped[str] = mapped_column(String(20), nullable=False)  # 2way, 3way, non_po
    match_status: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # matched, partial, exception, pending
    rule_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rule_versions.id"), nullable=True
    )
    amount_variance: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    amount_variance_pct: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)
    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    line_matches: Mapped[list["LineItemMatch"]] = relationship("LineItemMatch", back_populates="match_result")


class LineItemMatch(Base, UUIDMixin, TimestampMixin):
    """Line-level match between invoice line and PO/GR line."""

    __tablename__ = "line_item_matches"

    match_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("match_results.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoice_line_items.id"), nullable=False
    )
    po_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("po_line_items.id"), nullable=True
    )
    gr_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("gr_line_items.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # matched, qty_variance, price_variance, unmatched
    qty_variance: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    price_variance: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    price_variance_pct: Mapped[float | None] = mapped_column(Numeric(7, 4), nullable=True)

    match_result: Mapped["MatchResult"] = relationship("MatchResult", back_populates="line_matches")
