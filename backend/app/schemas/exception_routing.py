"""Pydantic schemas for exception routing rules."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ExceptionRoutingRuleIn(BaseModel):
    exception_code: str
    target_role: str
    priority: int = 0
    is_active: bool = True


class ExceptionRoutingRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    exception_code: str
    target_role: str
    priority: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ExceptionRoutingRuleUpdate(BaseModel):
    target_role: str | None = None
    priority: int | None = None
    is_active: bool | None = None
