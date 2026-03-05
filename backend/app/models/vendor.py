import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, text
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
    """
    Vendor master data.

    Represents a supplier/vendor in the AP system. Stores core contact, payment, and compliance
    information. Vendors may be linked to an entity (org/subsidiary) via entity_id, enabling
    multi-entity AP operations with vendor-specific terms per entity.

    Relationships:
        aliases: Alternative names used to identify this vendor in invoices (e.g., DBA names)
        compliance_docs: Regulatory documents (W9, VAT certs, insurance) with expiry tracking
    """
    __tablename__ = "vendors"

    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id"), nullable=True, index=True
    )  # Optional link to entity (org/subsidiary); NULL = vendor usable by all entities
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    tax_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)  # EIN/VAT ID
    bank_account: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bank_routing: Mapped[str | None] = mapped_column(String(100), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")  # ISO 4217 code (e.g., "USD", "EUR")
    payment_terms: Mapped[int] = mapped_column(Integer, nullable=False, default=30)  # Payment due date in days from invoice date
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # Soft delete timestamp; NULL = not deleted

    aliases: Mapped[list["VendorAlias"]] = relationship("VendorAlias", back_populates="vendor")
    compliance_docs: Mapped[list["VendorComplianceDoc"]] = relationship(
        "VendorComplianceDoc", back_populates="vendor"
    )


class VendorAlias(Base, UUIDMixin):
    """
    Vendor name aliases.

    Stores alternative names used to identify a vendor in invoices. Examples: DBA names,
    subsidiary names, common misspellings. Used by the matching engine to recognize vendor
    names in invoice data that may not exactly match the canonical vendor.name.
    """
    __tablename__ = "vendor_aliases"

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False, index=True
    )
    alias: Mapped[str] = mapped_column(String(255), nullable=False)  # Alternative vendor name
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    vendor: Mapped["Vendor"] = relationship("Vendor", back_populates="aliases")


class VendorComplianceDoc(Base, UUIDMixin, TimestampMixin):
    """
    Vendor compliance documents.

    Tracks regulatory documents required for vendor compliance: tax forms (W9, W8BEN), VAT
    certificates, insurance documents, etc. Includes upload, review workflow, and expiry tracking.
    Status transitions: pending_review → approved → active (or rejected/expired if compliance fails).

    Used by approval workflow to enforce compliance checks before payment authorization.
    """
    __tablename__ = "vendor_compliance_docs"

    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False, index=True
    )
    doc_type: Mapped[str] = mapped_column(String(50), nullable=False)  # W9, W8BEN, VAT, insurance, other
    file_key: Mapped[str | None] = mapped_column(String(500), nullable=True)  # MinIO object key for document file
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False, server_default="''")  # Legacy path reference (may be deprecated)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending_review"
    )  # pending_review, approved, expired, rejected, active, missing
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # Compliance deadline; NULL = no expiry
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )  # User who uploaded the document
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )  # Compliance officer who approved/rejected
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # When review was completed
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # Review feedback or rejection reason

    vendor: Mapped["Vendor"] = relationship("Vendor", back_populates="compliance_docs")
