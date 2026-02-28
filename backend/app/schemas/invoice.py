"""Pydantic schemas for invoice API endpoints."""
import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


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
    due_date: datetime | None = None
    fraud_score: int = 0
    is_recurring: bool = False
    source: str | None = None
    unread_vendor_messages: int = 0


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
    extracted_fields: dict[str, Any] = {}   # parsed from raw_json
    discrepancy_fields: list[str] = []       # parsed from JSON string

    @model_validator(mode="before")
    @classmethod
    def _parse_json_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            raw = data.get("raw_json") or "{}"
            disc = data.get("discrepancy_fields") or "[]"
        else:
            raw = getattr(data, "raw_json", None) or "{}"
            disc = getattr(data, "discrepancy_fields", None) or "[]"
        try:
            extracted = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except Exception:
            extracted = {}
        try:
            discrepancies = json.loads(disc) if isinstance(disc, str) else (disc or [])
            if not isinstance(discrepancies, list):
                discrepancies = []
        except Exception:
            discrepancies = []
        if isinstance(data, dict):
            return {**data, "extracted_fields": extracted, "discrepancy_fields": discrepancies}
        return {
            "id": getattr(data, "id", None),
            "pass_number": getattr(data, "pass_number", None),
            "model_used": getattr(data, "model_used", None),
            "tokens_used": getattr(data, "tokens_used", None),
            "latency_ms": getattr(data, "latency_ms", None),
            "extracted_fields": extracted,
            "discrepancy_fields": discrepancies,
        }


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
    fraud_triggered_signals: list = []
    is_recurring: bool
    is_duplicate: bool = False
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


# ─── Status override ───

class StatusOverrideRequest(BaseModel):
    status: str


class StatusOverrideResponse(BaseModel):
    invoice_id: uuid.UUID
    old_status: str
    new_status: str
    message: str


# ─── GL bulk update ───

class GLBulkLineUpdate(BaseModel):
    line_id: uuid.UUID
    gl_account: str
    cost_center: str | None = None


class GLBulkUpdate(BaseModel):
    lines: list[GLBulkLineUpdate]


class GLBulkUpdateResponse(BaseModel):
    updated: int
    errors: int


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
