"""Pydantic schemas for match results."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GRLineOut(BaseModel):
    id: uuid.UUID
    line_number: int
    description: str
    qty_received: float
    unit: str | None


class GRNSummaryOut(BaseModel):
    id: uuid.UUID
    gr_number: str
    received_at: datetime
    lines: list[GRLineOut]


class LineItemMatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    match_result_id: uuid.UUID
    invoice_line_id: uuid.UUID
    po_line_id: uuid.UUID | None
    gr_line_id: uuid.UUID | None
    status: str  # matched, qty_variance, price_variance, unmatched
    qty_variance: float | None
    price_variance: float | None
    price_variance_pct: float | None
    created_at: datetime

    # Enriched fields (populated by endpoint)
    description: str | None = None
    invoice_amount: float | None = None
    po_amount: float | None = None
    qty_invoiced: float | None = None
    qty_on_po: float | None = None
    qty_received: float | None = None


class MatchResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_id: uuid.UUID
    po_id: uuid.UUID | None
    gr_id: uuid.UUID | None
    match_type: str  # 2way, 3way, non_po
    match_status: str  # matched, partial, exception, pending
    rule_version_id: uuid.UUID | None
    amount_variance: float | None
    amount_variance_pct: float | None
    matched_at: datetime | None
    notes: str | None
    created_at: datetime
    line_matches: list[LineItemMatchOut]

    # Enriched fields (populated by endpoint)
    po_number: str | None = None
    gr_number: str | None = None
    grn_data: GRNSummaryOut | None = None


class MatchTriggerResponse(BaseModel):
    message: str
    match_status: str
    invoice_status: str
