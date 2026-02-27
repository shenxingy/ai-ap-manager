import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class PurchaseOrder(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "purchase_orders"

    po_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="open"
    )  # open, partial, closed, cancelled
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    total_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    cost_center: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gl_account: Mapped[str | None] = mapped_column(String(100), nullable=True)
    buyer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    line_items: Mapped[list["POLineItem"]] = relationship("POLineItem", back_populates="po")


class POLineItem(Base, UUIDMixin, TimestampMixin):
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
    gl_account: Mapped[str | None] = mapped_column(String(100), nullable=True)
    received_qty: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    invoiced_qty: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0)

    po: Mapped["PurchaseOrder"] = relationship("PurchaseOrder", back_populates="line_items")
