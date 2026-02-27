import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class Rule(Base, UUIDMixin, TimestampMixin):
    """Rule definition (metadata). Active config is in the latest published RuleVersion."""

    __tablename__ = "rules"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # matching_tolerance, auto_approve, fraud, gl_coding
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    versions: Mapped[list["RuleVersion"]] = relationship(
        "RuleVersion", back_populates="rule", order_by="RuleVersion.created_at.desc()"
    )


class RuleVersion(Base, UUIDMixin, TimestampMixin):
    """Versioned rule configuration. Lifecycle: draft → in_review → published → superseded/rejected."""

    __tablename__ = "rule_versions"

    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rules.id"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="draft"
    )  # draft, in_review, published, superseded, rejected, archived
    source: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # policy_upload, manual
    config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # JSON blob of rule parameters
    ai_extracted: Mapped[bool] = mapped_column(nullable=False, default=False)
    is_shadow_mode: Mapped[bool] = mapped_column(nullable=False, default=False)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    rule: Mapped["Rule"] = relationship("Rule", back_populates="versions")
