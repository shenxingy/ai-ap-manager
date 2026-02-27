"""Pydantic schemas for approval matrix rules and user delegations."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


# ─── Approval Matrix Rule schemas ───

class ApprovalMatrixRuleIn(BaseModel):
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    department: str | None = None
    category: str | None = None
    approver_role: str
    step_order: int = 1
    is_active: bool = True


class ApprovalMatrixRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    amount_min: Decimal | None
    amount_max: Decimal | None
    department: str | None
    category: str | None
    approver_role: str
    step_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ApprovalMatrixRuleUpdate(BaseModel):
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    department: str | None = None
    category: str | None = None
    approver_role: str | None = None
    step_order: int | None = None
    is_active: bool | None = None


# ─── User Delegation schemas ───

class UserDelegationIn(BaseModel):
    delegate_id: uuid.UUID
    valid_from: date
    valid_until: date | None = None


class UserDelegationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    delegator_id: uuid.UUID
    delegate_id: uuid.UUID
    valid_from: date
    valid_until: date | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
