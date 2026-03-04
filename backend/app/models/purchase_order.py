import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class PurchaseOrder(Base, UUIDMixin, TimestampMixin):
    """
    Purchase Order (PO) — authoritative source of goods/services commitment.

    The PO is matched against receipts (GRN) and invoices in the 3-way match engine.
    Status lifecycle: open → partial (part received/invoiced) → closed (fully received/invoiced) or cancelled.
    Soft-deleted via deleted_at for audit compliance.

    Relationships:
        - vendor: vendor record (1:N, PO → vendor)
        - entity: legal entity that issued the PO (1:N, optional)
        - buyer: user who created the PO (1:N, optional)
        - line_items: ordered line items (1:N, cascade delete)
    """
    __tablename__ = "purchase_orders"

    po_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="open"
    )  # Enum: open, partial, closed, cancelled
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    total_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    # Internal cost allocation code (for AP routing and cost tracking)
    cost_center: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # General Ledger account for top-level expense account coding (can be overridden at line level)
    gl_account: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Legal entity that issued this PO (for multi-entity organizations); null for single-entity
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id"), nullable=True, index=True
    )
    # User who created/owns this PO (for audit trail); null if system-generated
    buyer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Soft delete timestamp (for compliance audit trail; records never physically deleted)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    line_items: Mapped[list["POLineItem"]] = relationship("POLineItem", back_populates="po")


class POLineItem(Base, UUIDMixin, TimestampMixin):
    """
    Purchase Order Line Item — individual line within a PO.

    Tracks ordered, received, and invoiced quantities for 3-way match validation.
    Received and invoiced quantities are updated as GRNs and invoices are processed.

    Relationships:
        - po: parent PO (N:1, required, cascade delete)
    """
    __tablename__ = "po_line_items"

    po_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    line_number: Mapped[int] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # GL account for this line (overrides PO-level gl_account if set); null defaults to PO-level account
    gl_account: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Quantity received per GRN/receipt; updated by goods receipt matching process
    received_qty: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    # Quantity invoiced per invoice line items; updated during 3-way match validation
    invoiced_qty: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0)

    po: Mapped["PurchaseOrder"] = relationship("PurchaseOrder", back_populates="line_items")
