"""SQLAlchemy model for exception routing rules."""
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class ExceptionRoutingRule(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "exception_routing_rules"

    exception_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_role: Mapped[str] = mapped_column(String(50), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
