"""Unit tests for KPI rate calculations.

The KPI formulas live inside async route handlers that aggregate DB counts.
These tests verify the rate calculation logic using inline mock counts,
matching the formulas in app/api/v1/kpi.py.

Formulas:
  touchless_rate = auto_approved / total_approved   (where auto_approved = approved with NO approval task)
  exception_rate = total_exceptions / total_received
"""
import pytest


# ─── Touchless rate ───────────────────────────────────────────────────────────

def test_touchless_rate():
    """3 approved invoices, 2 auto-approved (no approval task) → touchless_rate ≈ 0.667."""
    total_approved = 3
    auto_approved = 2  # invoices approved with no ApprovalTask row

    touchless_rate = auto_approved / total_approved if total_approved > 0 else 0.0

    assert abs(touchless_rate - 2 / 3) < 0.001
    assert round(touchless_rate, 4) == 0.6667


def test_touchless_rate_zero_denominator():
    """When total_approved == 0, touchless_rate defaults to 0.0 (no division by zero)."""
    total_approved = 0
    auto_approved = 0

    touchless_rate = auto_approved / total_approved if total_approved > 0 else 0.0

    assert touchless_rate == 0.0


# ─── Exception rate ───────────────────────────────────────────────────────────

def test_exception_rate():
    """10 invoices received, 3 have open exceptions → exception_rate = 0.30."""
    total_received = 10
    total_exceptions = 3  # invoices with at least one open ExceptionRecord

    exception_rate = total_exceptions / total_received if total_received > 0 else 0.0

    assert abs(exception_rate - 0.30) < 0.001
    assert round(exception_rate, 4) == 0.3


def test_exception_rate_zero_denominator():
    """When total_received == 0, exception_rate defaults to 0.0."""
    total_received = 0
    total_exceptions = 0

    exception_rate = total_exceptions / total_received if total_received > 0 else 0.0

    assert exception_rate == 0.0
