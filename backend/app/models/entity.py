import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    tax_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD", server_default="'USD'")
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="UTC", server_default="'UTC'")
    contact_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("now()"),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
