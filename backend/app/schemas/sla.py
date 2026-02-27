"""Pydantic schemas for SLA alerts."""
import uuid
from datetime import datetime

from pydantic import BaseModel


class SlaAlertOut(BaseModel):
    id: uuid.UUID
    invoice_id: uuid.UUID
    alert_type: str
    due_date: datetime | None
    days_until_due: int | None
    invoice_status: str | None
    alert_date: datetime
    resolved: bool
    resolved_at: datetime | None
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SlaAlertListResponse(BaseModel):
    items: list[SlaAlertOut]
    total: int
