import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin


class InspectionResult(str, enum.Enum):
    """Allowed values for InspectionReport.result."""
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"


class InspectionReport(Base, UUIDMixin):
    """Quality inspection report linked to a Goods Receipt (and optionally an Invoice).

    result values: "pass", "fail", "partial"
    """

    __tablename__ = "inspection_reports"

    gr_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("goods_receipts.id"), nullable=False, index=True
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True, index=True
    )
    inspector_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    result: Mapped[str] = mapped_column(String(10), nullable=False)  # pass, fail, partial
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    inspected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="now()", nullable=False
    )
