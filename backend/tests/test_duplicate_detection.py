"""Unit tests for duplicate detection service.

Tests exact duplicate (same vendor + invoice_number) and fuzzy duplicate
(same vendor, amount ±2%, date ±7 days) detection logic.
"""
import uuid
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.duplicate_detection import check_duplicate


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_invoice(
    vendor_id: str,
    invoice_number: str,
    total_amount: float,
    normalized_amount_usd: float | None = None,
    invoice_date: datetime | None = None,
) -> MagicMock:
    """Create a mock Invoice object for testing."""
    inv = MagicMock()
    inv.id = uuid.uuid4()
    inv.vendor_id = uuid.UUID(vendor_id) if vendor_id else None
    inv.invoice_number = invoice_number
    inv.total_amount = Decimal(str(total_amount))
    inv.normalized_amount_usd = normalized_amount_usd or total_amount
    inv.invoice_date = invoice_date
    inv.created_at = datetime.now(timezone.utc)
    inv.deleted_at = None
    inv.is_duplicate = False
    return inv


def _db_for_duplicate_check(
    current_invoice: MagicMock,
    exact_match: MagicMock | None = None,
    fuzzy_matches: list | None = None,
) -> MagicMock:
    """Build a DB mock for check_duplicate with appropriate execute() side effects.

    Call order in check_duplicate:
      1. Current invoice load (scalars().first())
      2. Exact duplicate query (scalars().first() - returns exact_match or None)
      3. Fuzzy candidates query (scalars().all() - returns fuzzy_matches or [])
    """
    db = MagicMock()

    # Query 1: Current invoice load
    inv_result = MagicMock()
    inv_result.scalars.return_value.first.return_value = current_invoice

    # Query 2: Exact duplicate check
    exact_result = MagicMock()
    exact_result.scalars.return_value.first.return_value = exact_match

    # Query 3: Fuzzy candidate check + _ensure_exception query(ies)
    side_effects = [inv_result, exact_result]

    if exact_match or fuzzy_matches:
        # If we found matches, we'll get fuzzy candidates query + potential exception checks
        fuzzy_result = MagicMock()
        fuzzy_result.scalars.return_value.all.return_value = fuzzy_matches or []
        side_effects.append(fuzzy_result)

        # For each match (exact or fuzzy), _ensure_exception runs queries
        # to check if exception already exists. Let's add those to side effects.
        for _ in (([exact_match] if exact_match else []) + (fuzzy_matches or [])):
            check_existing = MagicMock()
            check_existing.scalars.return_value.first.return_value = None
            side_effects.append(check_existing)
    else:
        # Just fuzzy candidates (will be empty)
        fuzzy_result = MagicMock()
        fuzzy_result.scalars.return_value.all.return_value = []
        side_effects.append(fuzzy_result)

    db.execute.side_effect = side_effects
    return db


# ─── Tests ────────────────────────────────────────────────────────────────────

@patch("app.services.duplicate_detection.logger")
def test_exact_duplicate(mock_logger):
    """Exact duplicate: same vendor_id + invoice_number → DUPLICATE_INVOICE exception created."""
    vendor_id = str(uuid.uuid4())

    # Current invoice
    current_inv = _make_invoice(
        vendor_id=vendor_id,
        invoice_number="INV-001",
        total_amount=1000.0,
    )

    # Matching exact duplicate
    exact_dup = _make_invoice(
        vendor_id=vendor_id,
        invoice_number="INV-001",
        total_amount=1000.0,
    )
    exact_dup.id = uuid.uuid4()  # Different id than current_inv

    db = _db_for_duplicate_check(current_inv, exact_match=exact_dup)

    result = check_duplicate(db, str(current_inv.id))

    # Should return list with one exact match
    assert len(result) == 1
    assert result[0]["match_type"] == "exact"
    assert result[0]["matched_invoice_id"] == str(exact_dup.id)

    # Verify invoice was marked as duplicate
    assert current_inv.is_duplicate is True

    # Verify log was called
    db.commit.assert_called_once()


@patch("app.services.duplicate_detection.logger")
def test_fuzzy_duplicate(mock_logger):
    """Fuzzy duplicate: same vendor, amount ±2%, date ±7 days → DUPLICATE_INVOICE exception."""
    vendor_id = str(uuid.uuid4())
    base_date = datetime(2026, 2, 27, 10, 0, 0, tzinfo=timezone.utc)

    # Current invoice: $1000 on 2026-02-27
    current_inv = _make_invoice(
        vendor_id=vendor_id,
        invoice_number="INV-001",
        total_amount=1000.0,
        normalized_amount_usd=1000.0,
        invoice_date=base_date,
    )

    # Fuzzy match: same vendor, $1010 (1% higher, within 2% tolerance),
    # invoice_date = 2026-02-25 (2 days earlier, within ±7 days)
    fuzzy_dup = _make_invoice(
        vendor_id=vendor_id,
        invoice_number="INV-002",  # Different invoice number
        total_amount=1010.0,
        normalized_amount_usd=1010.0,
        invoice_date=base_date - timedelta(days=2),
    )
    fuzzy_dup.id = uuid.uuid4()

    db = _db_for_duplicate_check(current_inv, exact_match=None, fuzzy_matches=[fuzzy_dup])

    result = check_duplicate(db, str(current_inv.id))

    # Should return list with one fuzzy match
    assert len(result) == 1
    assert result[0]["match_type"] == "fuzzy"
    assert result[0]["matched_invoice_id"] == str(fuzzy_dup.id)

    # Verify invoice was marked as duplicate
    assert current_inv.is_duplicate is True


@patch("app.services.duplicate_detection.logger")
def test_no_duplicate(mock_logger):
    """No duplicates: different vendor_ids → returns empty list."""
    vendor_id_1 = str(uuid.uuid4())
    vendor_id_2 = str(uuid.uuid4())

    # Current invoice from vendor_id_1
    current_inv = _make_invoice(
        vendor_id=vendor_id_1,
        invoice_number="INV-001",
        total_amount=1000.0,
        normalized_amount_usd=1000.0,
    )

    db = _db_for_duplicate_check(current_inv, exact_match=None, fuzzy_matches=[])

    result = check_duplicate(db, str(current_inv.id))

    # Should return empty list (no duplicates found)
    assert result == []

    # Invoice should NOT be marked as duplicate
    assert current_inv.is_duplicate is False
