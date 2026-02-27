"""KPI dashboard Pydantic schemas."""
from datetime import date
from decimal import Decimal
from pydantic import BaseModel


class KPISummary(BaseModel):
    total_received: int
    total_approved: int
    total_pending: int        # status in (matched, extracted, extracting, ingested)
    total_exceptions: int     # invoices with at least one open exception
    touchless_rate: float     # auto-approved / total (0.0-1.0)
    exception_rate: float     # invoices with exception / total (0.0-1.0)
    avg_cycle_time_hours: float | None  # avg hours from created_at to approved
    period_days: int           # window used for stats (default 30)


class KPITrendPoint(BaseModel):
    period_start: date
    invoices_received: int
    invoices_approved: int
    invoices_exceptions: int
    avg_amount: Decimal | None


class KPITrends(BaseModel):
    period: str   # "daily" or "weekly"
    points: list[KPITrendPoint]
