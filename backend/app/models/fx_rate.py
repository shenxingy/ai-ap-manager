"""FX exchange rate model."""
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Float, Integer, String, UniqueConstraint

from app.db.base import Base


class FxRate(Base):
    __tablename__ = "fx_rates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    base_currency = Column(String(3), nullable=False)
    quote_currency = Column(String(3), nullable=False)
    rate = Column(Float, nullable=False)
    valid_date = Column(Date, nullable=False)
    source = Column(String(20), nullable=False, default="ecb")
    fetched_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("base_currency", "quote_currency", "valid_date", name="uq_fx_rate_pair_date"),
    )
