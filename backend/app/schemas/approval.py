"""Pydantic schemas for approval workflow API endpoints."""
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


# ─── Approval task output ───

class ApprovalTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_id: uuid.UUID
    approver_id: uuid.UUID
    step_order: int
    approval_required_count: int
    status: str
    due_at: datetime | None
    decided_at: datetime | None
    decision_channel: str | None
    notes: str | None
    created_at: datetime

    # Invoice summary fields (populated by the service layer)
    invoice_number: str | None = None
    vendor_name_raw: str | None = None
    total_amount: Decimal | None = None


# ─── Decision request body ───

class ApprovalDecisionRequest(BaseModel):
    notes: str | None = None


# ─── Paginated list response ───

class ApprovalListResponse(BaseModel):
    items: list[ApprovalTaskOut]
    total: int
