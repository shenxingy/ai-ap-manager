"""AI feedback and rule recommendation models."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class AiFeedback(Base, UUIDMixin, TimestampMixin):
    """Records every human correction made to AI-extracted data."""

    __tablename__ = "ai_feedback"

    feedback_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # field_correction, gl_correction, exception_correction
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)  # invoice, invoice_line_item, exception
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    field_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Link back to the invoice for aggregation
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True, index=True
    )
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=True, index=True
    )


class RuleRecommendation(Base, UUIDMixin, TimestampMixin):
    """AI-generated recommendations for rule changes based on correction patterns."""

    __tablename__ = "rule_recommendations"

    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)  # tolerance, routing, gl_mapping
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_config: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    confidence_score: Mapped[float | None] = mapped_column(nullable=True)  # 0.0-1.0
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", index=True
    )  # pending, accepted, rejected
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Period this recommendation covers
    analysis_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    analysis_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    correction_count: Mapped[int | None] = mapped_column(nullable=True)
