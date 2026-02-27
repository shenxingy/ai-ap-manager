"""Pydantic schemas for invoice API endpoints."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


# ─── Upload response ───

class InvoiceUploadResponse(BaseModel):
    invoice_id: uuid.UUID
    status: str
    message: str


# ─── List item ───

class InvoiceListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str | None
    vendor_name_raw: str | None
    status: str
    total_amount: Decimal | None
    currency: str | None
    file_name: str
    created_at: datetime


# ─── Line item detail ───

class InvoiceLineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_number: int
    description: str
    quantity: Decimal | None
    unit_price: Decimal | None
    unit: str | None
    line_total: Decimal | None
    gl_account: str | None
    gl_account_suggested: str | None
    cost_center: str | None


# ─── Extraction result summary ───

class ExtractionResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    pass_number: int
    model_used: str
    tokens_used: int | None
    latency_ms: int | None
    discrepancy_fields: str | None  # stored as JSON string


# ─── Full invoice detail ───

class InvoiceDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str | None
    vendor_id: uuid.UUID | None
    vendor_name_raw: str | None
    vendor_address_raw: str | None
    po_id: uuid.UUID | None
    status: str
    storage_path: str
    file_name: str
    file_size_bytes: int | None
    mime_type: str | None
    currency: str | None
    subtotal: Decimal | None
    tax_amount: Decimal | None
    total_amount: Decimal | None
    invoice_date: datetime | None
    due_date: datetime | None
    payment_terms: str | None
    ocr_confidence: Decimal | None
    extraction_model: str | None
    fraud_score: int
    is_recurring: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime

    line_items: list[InvoiceLineItemOut] = []
    extraction_results: list[ExtractionResultOut] = []


# ─── Paginated list response ───

class InvoiceListResponse(BaseModel):
    items: list[InvoiceListItem]
    total: int
    page: int
    page_size: int


# ─── Audit log ───

class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action: str
    actor_id: uuid.UUID | None
    actor_email: str | None
    entity_type: str
    entity_id: uuid.UUID | None
    before_state: str | None   # raw JSON string
    after_state: str | None    # raw JSON string
    notes: str | None
    created_at: datetime
