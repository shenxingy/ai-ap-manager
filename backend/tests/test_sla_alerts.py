"""Tests for SLA alerts service.

Tests overdue and approaching invoice deadline detection. Uses mocked
database sessions following the existing test patterns.
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models.invoice import Invoice
from app.models.sla_alert import SLAAlert


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_invoice(
    invoice_id: uuid.UUID | None = None,
    invoice_number: str = "INV-001",
    due_date: datetime | None = None,
    status: str = "pending",
) -> MagicMock:
    """Create a mock Invoice object for testing."""
    inv = MagicMock(spec=Invoice)
    inv.id = invoice_id or uuid.uuid4()
    inv.invoice_number = invoice_number
    inv.due_date = due_date
    inv.status = status
    inv.deleted_at = None
    return inv


def _mock_db_for_sla_check(
    invoice: MagicMock,
    existing_alert: MagicMock | None = None,
) -> MagicMock:
    """Build a DB mock for SLA alert checking.

    Returns:
        - First execute: scalar result with the invoice
        - Second execute: scalar result with existing alert (or None)
    """
    db = MagicMock()

    # First query: get the invoice
    inv_result = MagicMock()
    inv_result.scalars.return_value.first.return_value = invoice

    # Second query: check for existing alert
    alert_result = MagicMock()
    alert_result.scalars.return_value.first.return_value = existing_alert

    db.execute.side_effect = [inv_result, alert_result]
    db.add = MagicMock()
    db.flush = MagicMock()

    return db


# ─── Tests ────────────────────────────────────────────────────────────────────

@patch("app.services.sla_alerts._ensure_alert")
def test_overdue_invoice_flagged(mock_ensure_alert):
    """Overdue invoice: due_date < now + status PENDING → alert created.

    An invoice with a due date in the past and status PENDING should be
    flagged as overdue. An alert record should be created with alert_type='overdue'.
    """
    from app.services.sla_alerts import check_sla_alerts

    inv_id = uuid.uuid4()
    alert_id = uuid.uuid4()

    # Create invoice with due_date = yesterday
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    invoice = _make_invoice(
        invoice_id=inv_id,
        invoice_number="INV-001",
        due_date=yesterday,
        status="pending",
    )

    # Mock alert creation
    mock_alert = MagicMock()
    mock_alert.id = alert_id
    mock_ensure_alert.return_value = mock_alert

    db = _mock_db_for_sla_check(invoice)

    # Run SLA check
    result = check_sla_alerts(db, str(inv_id))

    # Verify overdue alert was created
    assert len(result) == 1
    assert result[0]["alert_type"] == "overdue"
    assert result[0]["alert_id"] == str(alert_id)

    # Verify _ensure_alert was called with correct parameters
    mock_ensure_alert.assert_called_once()
    call_kwargs = mock_ensure_alert.call_args[1]
    assert call_kwargs["alert_type"] == "overdue"
    assert "overdue" in call_kwargs["description"].lower()


@patch("app.services.sla_alerts._ensure_alert")
def test_upcoming_invoice_flagged(mock_ensure_alert):
    """Approaching deadline: due_date = tomorrow + status PENDING → alert created.

    An invoice with a due date approaching (within 1 day) and status PENDING
    should be flagged as approaching. An alert record should be created
    with alert_type='approaching'.
    """
    from app.services.sla_alerts import check_sla_alerts

    inv_id = uuid.uuid4()
    alert_id = uuid.uuid4()

    # Create invoice with due_date = tomorrow
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    invoice = _make_invoice(
        invoice_id=inv_id,
        invoice_number="INV-002",
        due_date=tomorrow,
        status="pending",
    )

    # Mock alert creation
    mock_alert = MagicMock()
    mock_alert.id = alert_id
    mock_ensure_alert.return_value = mock_alert

    db = _mock_db_for_sla_check(invoice)

    # Run SLA check
    result = check_sla_alerts(db, str(inv_id))

    # Verify approaching alert was created
    assert len(result) == 1
    assert result[0]["alert_type"] == "approaching"
    assert result[0]["alert_id"] == str(alert_id)

    # Verify _ensure_alert was called with correct parameters
    mock_ensure_alert.assert_called_once()
    call_kwargs = mock_ensure_alert.call_args[1]
    assert call_kwargs["alert_type"] == "approaching"
    assert "approaching" in call_kwargs["description"].lower()


def test_no_alert_for_matched_invoice():
    """No alert: status MATCHED (not PENDING) → no alert created.

    Only invoices with status PENDING or MATCHING should be checked for
    SLA violations. Matched or approved invoices should not trigger alerts.
    """
    from app.services.sla_alerts import check_sla_alerts

    inv_id = uuid.uuid4()

    # Create invoice with due_date = yesterday but status MATCHED
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    invoice = _make_invoice(
        invoice_id=inv_id,
        invoice_number="INV-003",
        due_date=yesterday,
        status="matched",  # Not PENDING
    )

    # Mock DB
    db = MagicMock()
    inv_result = MagicMock()
    inv_result.scalars.return_value.first.return_value = invoice
    db.execute.side_effect = [inv_result]

    # Run SLA check
    result = check_sla_alerts(db, str(inv_id))

    # Verify no alerts were created
    assert result == []


def test_no_alert_without_due_date():
    """No alert: invoice has no due_date → no alert created.

    Invoices without a due date cannot be checked for SLA violations.
    The service should skip them gracefully.
    """
    from app.services.sla_alerts import check_sla_alerts

    inv_id = uuid.uuid4()

    # Create invoice with no due_date
    invoice = _make_invoice(
        invoice_id=inv_id,
        invoice_number="INV-004",
        due_date=None,  # No deadline
        status="pending",
    )

    # Mock DB
    db = MagicMock()
    inv_result = MagicMock()
    inv_result.scalars.return_value.first.return_value = invoice
    db.execute.side_effect = [inv_result]

    # Run SLA check
    result = check_sla_alerts(db, str(inv_id))

    # Verify no alerts were created
    assert result == []


def test_no_duplicate_alert_for_existing_open_alert():
    """No duplicate alert: existing open alert for same type → _ensure_alert returns None.

    If an open alert already exists for the invoice and alert type,
    _ensure_alert should return None, and check_sla_alerts should not
    add it to the result list.
    """
    from app.services.sla_alerts import check_sla_alerts

    inv_id = uuid.uuid4()

    # Create invoice with due_date = yesterday
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    invoice = _make_invoice(
        invoice_id=inv_id,
        invoice_number="INV-005",
        due_date=yesterday,
        status="pending",
    )

    # Mock _ensure_alert to return None (existing alert found)
    with patch("app.services.sla_alerts._ensure_alert", return_value=None):
        db = MagicMock()
        inv_result = MagicMock()
        inv_result.scalars.return_value.first.return_value = invoice
        db.execute.side_effect = [inv_result]

        # Run SLA check
        result = check_sla_alerts(db, str(inv_id))

        # Verify no alerts in result (since _ensure_alert returned None)
        assert result == []
