"""Analytics report model for LLM-generated root cause narratives."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class AnalyticsReport(Base, UUIDMixin, TimestampMixin):
    """Stores AI-generated root cause narrative reports."""

    __tablename__ = "analytics_reports"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    report_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="root_cause"
    )  # root_cause, weekly_digest
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", index=True
    )  # pending, generating, complete, failed
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Rate limiting: track when last report was generated per user
    requester_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    # Token usage tracking for cost monitoring
    prompt_tokens: Mapped[int | None] = mapped_column(nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
