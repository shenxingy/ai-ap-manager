import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class MessageDirection(str, enum.Enum):
    inbound = "inbound"
    outbound = "outbound"


class ApprovalTask(Base, UUIDMixin, TimestampMixin):
    """A single approval step in a workflow for an invoice."""

    __tablename__ = "approval_tasks"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True
    )
    approver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    step_order: Mapped[int] = mapped_column(nullable=False, default=1)
    approval_required_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending"
    )  # pending, partially_approved, approved, rejected, delegated, expired
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_channel: Mapped[str | None] = mapped_column(String(50), nullable=True)  # web, email
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    delegated_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    tokens: Mapped[list["ApprovalToken"]] = relationship(
        "ApprovalToken", back_populates="task", cascade="all, delete-orphan"
    )


class ApprovalToken(Base, UUIDMixin, TimestampMixin):
    """HMAC-signed one-time token for email-based approvals (Tipalti-style)."""

    __tablename__ = "approval_tokens"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("approval_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # approve, reject
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    task: Mapped["ApprovalTask"] = relationship("ApprovalTask", back_populates="tokens")


class VendorMessage(Base, UUIDMixin, TimestampMixin):
    """Vendor Communication Hub — AP↔vendor messages anchored to an invoice."""

    __tablename__ = "vendor_messages"

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True
    )
    sender_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True  # null = external vendor
    )
    sender_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # inbound, outbound
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # internal AP note vs vendor-visible
    attachments: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="'[]'")
