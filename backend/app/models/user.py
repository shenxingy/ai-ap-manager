from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin

ROLES = ("AP_CLERK", "AP_ANALYST", "APPROVER", "ADMIN", "AUDITOR")


class User(Base, UUIDMixin, TimestampMixin):
    """
    User account entity representing a person with access to the AP system.

    Inherits from UUIDMixin (provides `id: UUID`), TimestampMixin (provides `created_at` and `updated_at`),
    and Base (SQLAlchemy declarative base).

    A user has an email, name, hashed password, and a role that determines permissions.
    Users support soft deletion via `deleted_at` timestamp and can be deactivated with `is_active` flag.
    """
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)  # One of: AP_CLERK, AP_ANALYST, APPROVER, ADMIN, AUDITOR
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # Deactivation flag (user can still be queried, but blocked from login)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # Soft delete: set when user is deleted but records retained for audit
    notification_prefs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # User's notification settings (email, Slack, digest frequency, etc.)
