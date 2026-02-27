"""Approval matrix and user delegation models."""
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class ApprovalMatrixRule(Base, UUIDMixin, TimestampMixin):
    """Defines who must approve invoices matching amount/department/category criteria."""

    __tablename__ = "approval_matrix_rules"

    amount_min: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    amount_max: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approver_role: Mapped[str] = mapped_column(String(50), nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class UserDelegation(Base, UUIDMixin, TimestampMixin):
    """Temporarily delegates approval authority from one user to another."""

    __tablename__ = "user_delegations"

    delegator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    delegate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
