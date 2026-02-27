"""Pydantic schemas for exception records."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class ExceptionListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_id: uuid.UUID
    exception_code: str
    description: str
    severity: str  # low, medium, high, critical
    status: str  # open, in_progress, resolved, escalated, waived
    assigned_to: uuid.UUID | None
    assigned_to_email: str | None = None
    resolved_at: datetime | None
    created_at: datetime
    comment_count: int = 0


class InvoiceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str | None
    vendor_name_raw: str | None
    total_amount: float | None
    status: str
    currency: str | None


class ExceptionDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_id: uuid.UUID
    exception_code: str
    description: str
    severity: str
    status: str
    assigned_to: uuid.UUID | None
    resolved_by: uuid.UUID | None
    resolved_at: datetime | None
    resolution_notes: str | None
    ai_root_cause: str | None
    created_at: datetime
    updated_at: datetime
    invoice: InvoiceSummary | None = None


class ExceptionPatch(BaseModel):
    """Fields that AP_ANALYST+ can update on an exception."""
    status: str | None = None
    assigned_to: uuid.UUID | None = None
    resolution_notes: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v is None:
            return v
        allowed = {"open", "in_progress", "resolved", "escalated", "waived"}
        if v not in allowed:
            raise ValueError(f"status must be one of: {', '.join(sorted(allowed))}")
        return v


class ExceptionListResponse(BaseModel):
    items: list[ExceptionListItem]
    total: int
    page: int
    page_size: int


class ExceptionCommentCreate(BaseModel):
    body: str


class ExceptionCommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    exception_id: uuid.UUID
    author_id: uuid.UUID
    body: str
    created_at: datetime
