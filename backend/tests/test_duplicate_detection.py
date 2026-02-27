"""Tests for duplicate detection service.

Tests exact and fuzzy duplicate detection logic. Uses mocked database
sessions following the existing test patterns.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.invoice import Invoice
from app.models.exception_record import ExceptionRecord


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_invoice(
    invoice_id: uuid.UUID | None = None,
    vendor_id: uuid.UUID | None = ...,
    invoice_number: str | None = None,
    total_amount: float | None = None,
    normalized_amount_usd: float | None = None,
    invoice_date: datetime | None = None,
    status: str = "pending",
) -> MagicMock:
    """Create a mock Invoice object for testing."""
    inv = MagicMock(spec=Invoice)
    inv.id = invoice_id or uuid.uuid4()
    # Allow explicit None for vendor_id (use ... as sentinel for default)
    inv.vendor_id = vendor_id if vendor_id is not ... else uuid.uuid4()
    inv.invoice_number = invoice_number
    inv.total_amount = Decimal(str(total_amount)) if total_amount else None
    inv.normalized_amount_usd = Decimal(str(normalized_amount_usd)) if normalized_amount_usd else None
    inv.invoice_date = invoice_date
    inv.created_at = invoice_date or datetime.now(timezone.utc)
    inv.status = status
    inv.deleted_at = None
    inv.is_duplicate = False
    return inv


def _mock_db_for_exact_match(
    invoice: MagicMock,
    exact_match: MagicMock | None = None,
) -> MagicMock:
    """Build a DB mock for exact duplicate detection.

    Returns:
        - First execute: scalar result with the invoice
        - Second execute: scalar result with exact match (or None)
    """
    db = MagicMock()

    # First query: get the invoice
    inv_result = MagicMock()
    inv_result.scalars.return_value.first.return_value = invoice

    # Second query: check for exact duplicate
    exact_result = MagicMock()
    exact_result.scalars.return_value.first.return_value = exact_match

    db.execute.side_effect = [inv_result, exact_result]
    db.commit = MagicMock()

    return db


def _mock_db_for_fuzzy_match(
    invoice: MagicMock,
    fuzzy_candidates: list[MagicMock] | None = None,
) -> MagicMock:
    """Build a DB mock for fuzzy duplicate detection.

    Returns:
        - First execute: scalar result with the invoice
        - Second execute: scalar result with exact match (None)
        - Third execute: scalars result with fuzzy candidates
    """
    db = MagicMock()

    # First query: get the invoice
    inv_result = MagicMock()
    inv_result.scalars.return_value.first.return_value = invoice

    # Second query: check for exact duplicate (None = no exact match)
    exact_result = MagicMock()
    exact_result.scalars.return_value.first.return_value = None

    # Third query: fuzzy candidates
    fuzzy_result = MagicMock()
    fuzzy_result.scalars.return_value.all.return_value = fuzzy_candidates or []

    db.execute.side_effect = [inv_result, exact_result, fuzzy_result]
    db.commit = MagicMock()

    return db


# ─── Tests ────────────────────────────────────────────────────────────────────

@patch("app.services.duplicate_detection._ensure_exception")
def test_exact_duplicate(mock_ensure_exc):
    """Exact duplicate: same vendor_id + invoice_number → DUPLICATE_INVOICE exception.

    Two invoices with same vendor and invoice number should be detected as
    exact duplicates. The duplicate detection service should create an exception
    record with code='DUPLICATE_INVOICE' and severity='high'.
    """
    from app.services.duplicate_detection import check_duplicate

    vendor_id = uuid.uuid4()
    inv_id = uuid.uuid4()
    dup_id = uuid.uuid4()

    # Create invoice and its exact duplicate
    invoice = _make_invoice(
        invoice_id=inv_id,
        vendor_id=vendor_id,
        invoice_number="INV-001",
        total_amount=1000.0,
    )

    duplicate = _make_invoice(
        invoice_id=dup_id,
        vendor_id=vendor_id,
        invoice_number="INV-001",
        total_amount=1000.0,
    )

    db = _mock_db_for_exact_match(invoice, exact_match=duplicate)

    # Run duplicate check
    result = check_duplicate(db, str(inv_id))

    # Verify exception was recorded
    assert len(result) == 1
    assert result[0]["match_type"] == "exact"
    assert result[0]["matched_invoice_id"] == str(dup_id)

    # Verify _ensure_exception was called
    mock_ensure_exc.assert_called_once()
    call_kwargs = mock_ensure_exc.call_args[1]
    assert call_kwargs["code"] == "DUPLICATE_INVOICE"
    assert call_kwargs["severity"] == "high"

    # Verify is_duplicate was set
    assert invoice.is_duplicate is True
    db.commit.assert_called_once()


@patch("app.services.duplicate_detection._ensure_exception")
def test_fuzzy_duplicate(mock_ensure_exc):
    """Fuzzy duplicate: same vendor, amount within 2%, date within 7 days.

    Two invoices from the same vendor with amounts within 2% tolerance
    and dates within 7 days should be detected as potential duplicates.
    """
    from app.services.duplicate_detection import check_duplicate

    vendor_id = uuid.uuid4()
    inv_id = uuid.uuid4()
    dup_id = uuid.uuid4()

    # Create invoice with amount $1000 and date today
    invoice_date = datetime.now(timezone.utc)
    invoice = _make_invoice(
        invoice_id=inv_id,
        vendor_id=vendor_id,
        invoice_number="INV-001",
        total_amount=1000.0,
        normalized_amount_usd=1000.0,
        invoice_date=invoice_date,
    )

    # Create fuzzy duplicate: amount within 2% ($1010), date within 7 days
    dup_date = invoice_date + timedelta(days=3)
    duplicate = _make_invoice(
        invoice_id=dup_id,
        vendor_id=vendor_id,
        invoice_number="INV-002",
        total_amount=1010.0,
        normalized_amount_usd=1010.0,
        invoice_date=dup_date,
    )

    db = _mock_db_for_fuzzy_match(invoice, fuzzy_candidates=[duplicate])

    # Run duplicate check
    result = check_duplicate(db, str(inv_id))

    # Verify fuzzy match was detected
    assert len(result) == 1
    assert result[0]["match_type"] == "fuzzy"
    assert result[0]["matched_invoice_id"] == str(dup_id)

    # Verify exception was recorded
    mock_ensure_exc.assert_called_once()
    call_kwargs = mock_ensure_exc.call_args[1]
    assert call_kwargs["code"] == "DUPLICATE_INVOICE"
    assert call_kwargs["severity"] == "medium"


def test_no_duplicate_different_vendor():
    """No duplicate: different vendor → empty candidate list.

    Invoices from different vendors should not be flagged as duplicates,
    even if they have the same invoice number.
    """
    from app.services.duplicate_detection import check_duplicate

    vendor1 = uuid.uuid4()
    vendor2 = uuid.uuid4()
    inv_id = uuid.uuid4()

    # Create invoice from vendor1
    invoice = _make_invoice(
        invoice_id=inv_id,
        vendor_id=vendor1,
        invoice_number="INV-001",
        total_amount=1000.0,
        normalized_amount_usd=1000.0,
    )

    # Mock DB: no exact or fuzzy matches found
    db = MagicMock()

    inv_result = MagicMock()
    inv_result.scalars.return_value.first.return_value = invoice

    exact_result = MagicMock()
    exact_result.scalars.return_value.first.return_value = None

    fuzzy_result = MagicMock()
    fuzzy_result.scalars.return_value.all.return_value = []

    db.execute.side_effect = [inv_result, exact_result, fuzzy_result]

    # Run duplicate check
    result = check_duplicate(db, str(inv_id))

    # Verify no matches found
    assert result == []


def test_no_duplicate_missing_vendor_or_invoice_number():
    """No duplicate check: missing vendor_id or invoice_number → no exact match.

    Exact duplicate detection requires both vendor_id and invoice_number.
    If either is missing, the check should be skipped.
    """
    from app.services.duplicate_detection import check_duplicate

    inv_id = uuid.uuid4()

    # Create invoice with no vendor_id
    invoice = _make_invoice(
        invoice_id=inv_id,
        vendor_id=None,
        invoice_number="INV-001",
        total_amount=1000.0,
        normalized_amount_usd=1000.0,
    )

    # Mock DB: just return the invoice
    db = MagicMock()
    inv_result = MagicMock()
    inv_result.scalars.return_value.first.return_value = invoice

    # No additional queries should be made since vendor_id is None
    db.execute.side_effect = [inv_result]

    # Run duplicate check
    result = check_duplicate(db, str(inv_id))

    # Verify no matches
    assert result == []
