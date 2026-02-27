"""Pydantic schemas for analytics reports."""
import uuid
from datetime import datetime

from pydantic import BaseModel


class AnalyticsReportOut(BaseModel):
    id: uuid.UUID
    title: str
    report_type: str
    status: str
    narrative: str | None
    error_message: str | None
    requested_by: uuid.UUID | None
    completed_at: datetime | None
    requester_email: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    model_used: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AnalyticsReportListResponse(BaseModel):
    items: list[AnalyticsReportOut]
    total: int


class GenerateReportRequest(BaseModel):
    title: str | None = None  # If None, auto-generated based on date
