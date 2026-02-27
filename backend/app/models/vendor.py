import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class ComplianceDocType(str, enum.Enum):
    W9 = "W9"
    W8BEN = "W8BEN"
    VAT = "VAT"
    insurance = "insurance"
    other = "other"


class ComplianceDocStatus(str, enum.Enum):
    active = "active"
    expired = "expired"
    missing = "missing"


class Vendor(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "vendors"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tax_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    bank_account: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bank_routing: Mapped[str | None] = mapped_column(String(100), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    payment_terms: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    aliases: Mapped[list["VendorAlias"]] = relationship("VendorAlias", back_populates="vendor")
    compliance_docs: Mapped[list["VendorComplianceDoc"]] = relationship(
        "VendorComplianceDoc", back_populates="vendor"
    )


class VendorAlias(Base, UUIDMixin):
    __tablename__ = "vendor_aliases"

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False, index=True
    )
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    vendor: Mapped["Vendor"] = relationship("Vendor", back_populates="aliases")


class VendorComplianceDoc(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "vendor_compliance_docs"

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False, index=True
    )
    doc_type: Mapped[str] = mapped_column(String(50), nullable=False)  # W9, W8BEN, VAT, insurance, other
    file_key: Mapped[str | None] = mapped_column(String(500), nullable=True)  # MinIO object key
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False, server_default="''")
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending_review"
    )  # pending_review, approved, expired, rejected, active, missing
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    vendor: Mapped["Vendor"] = relationship("Vendor", back_populates="compliance_docs")
