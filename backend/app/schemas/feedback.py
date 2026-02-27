"""Pydantic schemas for AI feedback and rule recommendations."""
import uuid
from datetime import datetime

from pydantic import BaseModel


# ─── AiFeedback schemas ───

class AiFeedbackOut(BaseModel):
    id: uuid.UUID
    feedback_type: str
    entity_type: str
    entity_id: uuid.UUID
    field_name: str | None
    old_value: str | None
    new_value: str | None
    actor_email: str | None
    invoice_id: uuid.UUID | None
    vendor_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── RuleRecommendation schemas ───

class RuleRecommendationOut(BaseModel):
    id: uuid.UUID
    rule_type: str
    title: str
    description: str
    evidence_summary: str | None
    suggested_config: str | None
    confidence_score: float | None
    status: str
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    review_notes: str | None
    analysis_period_start: datetime | None
    analysis_period_end: datetime | None
    correction_count: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RuleRecommendationListResponse(BaseModel):
    items: list[RuleRecommendationOut]
    total: int


class ReviewRequest(BaseModel):
    notes: str | None = None


# ─── Correction stats ───

class CorrectionStats(BaseModel):
    total_corrections: int
    by_type: dict[str, int]
    by_field: dict[str, int]
    period_days: int
