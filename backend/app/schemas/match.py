"""Pydantic schemas for match results."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


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


class MatchTriggerResponse(BaseModel):
    message: str
    match_status: str
    invoice_status: str
