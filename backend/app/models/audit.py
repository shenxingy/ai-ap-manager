import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class AuditLog(Base, UUIDMixin, TimestampMixin):
    """Immutable audit trail for all state transitions and decisions."""

    __tablename__ = "audit_logs"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)  # denormalized for deleted users
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    before_state: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON snapshot
    after_state: Mapped[str | None] = mapped_column(Text, nullable=True)   # JSON snapshot
    rule_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rule_versions.id"), nullable=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class AICallLog(Base, UUIDMixin, TimestampMixin):
    """Logs every LLM API call for cost tracking, debugging, and compliance."""

    __tablename__ = "ai_call_logs"

    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True, index=True
    )
    call_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # extraction_pass_1, extraction_pass_2, root_cause, gl_coding, policy_parse
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="success")  # success, error, timeout
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_json: Mapped[str | None] = mapped_column(Text, nullable=True)
