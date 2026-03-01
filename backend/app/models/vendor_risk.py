"""Vendor risk scoring model."""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class VendorRiskScore(Base):
    __tablename__ = "vendor_risk_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id"), nullable=False, index=True, unique=True)
    ocr_error_rate = Column(Float, default=0.0)
    exception_rate = Column(Float, default=0.0)
    avg_extraction_confidence = Column(Float, default=0.0)
    score = Column(Float, default=0.0)
    risk_level = Column(String(10), default="LOW")  # LOW/MEDIUM/HIGH/CRITICAL
    computed_at = Column(DateTime(timezone=True), default=datetime.utcnow)
