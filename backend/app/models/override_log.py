"""Override log model — records every manual override of AI/rule decisions."""
import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class OverrideLog(Base, UUIDMixin, TimestampMixin):
    """Records every instance where a human manually overrides a system decision.

    Examples: exception status manually resolved, approval forced through,
    match result manually changed. Used for rule recommendation analysis.
    """

    __tablename__ = "override_logs"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rules.id"), nullable=True, index=True
    )
    field_name: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )  # e.g. "exception_status", "approval_decision", "match_result"
    old_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    overridden_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
