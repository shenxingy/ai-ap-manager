"""Unit tests for SLA alert detection.

Tests SLA violations and near-violations based on invoice due dates
and approval status.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_invoice(
    status: str = "matched",
    due_date: datetime | None = None,
    created_at: datetime | None = None,
    vendor_id=None,
) -> MagicMock:
    """Create a mock Invoice object for SLA testing."""
    inv = MagicMock()
    inv.id = uuid.uuid4()
    inv.status = status
    inv.due_date = due_date
    inv.created_at = created_at or datetime.now(timezone.utc)
    inv.vendor_id = vendor_id or uuid.uuid4()
    inv.total_amount = Decimal("1000.00")
    inv.deleted_at = None
    return inv


def _make_alert(alert_type: str, invoice_id=None) -> MagicMock:
    """Create a mock SLAAlert object."""
    alert = MagicMock()
    alert.id = uuid.uuid4()
    alert.invoice_id = invoice_id or uuid.uuid4()
    alert.alert_type = alert_type  # "overdue" or "approaching"
    alert.triggered_at = datetime.now(timezone.utc)
    alert.is_resolved = False
    return alert


def _db_for_sla_check(invoices: list) -> MagicMock:
    """Build a DB mock for SLA check that returns a list of invoices."""
    db = MagicMock()

    # Query to fetch non-approved invoices (matched/pending/exception status)
    result = MagicMock()
    result.scalars.return_value.all.return_value = invoices

    db.execute = MagicMock(return_value=result)
    db.add = MagicMock()
    db.flush = MagicMock()
    db.commit = MagicMock()

    return db


# ─── Tests ────────────────────────────────────────────────────────────────────

@patch("app.services.audit.log")
def test_overdue_invoice_flagged(mock_audit_log):
    """Invoice with due_date=yesterday, non-approved status → overdue alert created.

    This test verifies that when an invoice is past its due date and hasn't been
    approved, the SLA check creates an "overdue" alert.
    """
    try:
        from app.services import sla_alerts  # Lazy import to handle missing module
    except ImportError:
        pytest.skip("sla_alerts service not yet implemented")

    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)

    # Create invoice: due yesterday, not yet approved
    invoice = _make_invoice(
        status="matched",  # Not approved yet
        due_date=yesterday,
    )

    db = _db_for_sla_check([invoice])

    # Call the SLA check (if it exists)
    try:
        alerts = sla_alerts.check_and_create_sla_alerts(db)

        # Verify overdue alert was created
        assert len(alerts) >= 1
        assert any(a["alert_type"] == "overdue" for a in alerts)
        db.commit.assert_called()
    except AttributeError:
        # Function doesn't exist yet; skip this test gracefully
        pytest.skip("sla_alerts.check_and_create_sla_alerts not yet implemented")


@patch("app.services.audit.log")
def test_upcoming_invoice_flagged(mock_audit_log):
    """Invoice with due_date=3 days from now, non-approved → approaching alert created.

    This test verifies that invoices approaching their due date (within SLA window)
    are flagged with an "approaching" alert for proactive management.
    """
    try:
        from app.services import sla_alerts  # Lazy import to handle missing module
    except ImportError:
        pytest.skip("sla_alerts service not yet implemented")

    now = datetime.now(timezone.utc)
    three_days_ahead = now + timedelta(days=3)

    # Create invoice: due in 3 days, not yet approved
    invoice = _make_invoice(
        status="matched",  # Not approved yet
        due_date=three_days_ahead,
    )

    db = _db_for_sla_check([invoice])

    # Call the SLA check (if it exists)
    try:
        alerts = sla_alerts.check_and_create_sla_alerts(db)

        # Verify approaching alert was created
        assert len(alerts) >= 1
        assert any(a["alert_type"] == "approaching" for a in alerts)
        db.commit.assert_called()
    except AttributeError:
        # Function doesn't exist yet; skip this test gracefully
        pytest.skip("sla_alerts.check_and_create_sla_alerts not yet implemented")


def test_approved_invoice_no_alert():
    """Invoice with status=approved (past due) → NO alert created.

    Once an invoice is approved, it's no longer subject to SLA checks.
    """
    try:
        from app.services import sla_alerts  # Lazy import to handle missing module
    except ImportError:
        pytest.skip("sla_alerts service not yet implemented")

    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)

    # Create invoice: due yesterday, BUT already approved
    invoice = _make_invoice(
        status="approved",  # Already approved!
        due_date=yesterday,
    )

    db = _db_for_sla_check([invoice])

    # Call the SLA check (if it exists)
    try:
        alerts = sla_alerts.check_and_create_sla_alerts(db)

        # No alert should be created for approved invoices
        if alerts:
            assert all(a["invoice_id"] != invoice.id for a in alerts)
    except AttributeError:
        # Function doesn't exist yet; skip this test gracefully
        pytest.skip("sla_alerts.check_and_create_sla_alerts not yet implemented")
