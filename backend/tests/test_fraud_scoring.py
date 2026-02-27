"""Unit tests for the fraud scoring service.

DB queries are replaced with MagicMock. No real database required.
"""
import uuid
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.fraud_scoring import score_invoice, SIGNAL_WEIGHTS
from app.core.config import settings


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_invoice(total_amount: float, vendor_id=None, invoice_date=None) -> MagicMock:
    inv = MagicMock()
    inv.id = uuid.uuid4()
    inv.total_amount = Decimal(str(total_amount))
    inv.vendor_id = vendor_id
    inv.invoice_date = invoice_date
    inv.deleted_at = None
    inv.fraud_score = 0
    inv.fraud_triggered_signals = []
    return inv


def _db_for_score(invoice, hist_invoices=None, dup_invoice=None,
                   approved_invoices=None, bank_change=None,
                   vendor_row=None) -> MagicMock:
    """Build a DB mock with appropriate side_effects for score_invoice.

    Call order inside score_invoice:
      1. Invoice load → scalars().first()
      [only if vendor_id is set:]
      2. hist_invoices (amount_spike) → scalars().all()
      3. dup query (potential_duplicate) → scalars().first()
      4. approved_count (new_vendor) → scalars().all()
      5. bank_change (bank_account_changed) → scalars().first()
      6. vendor_row (ghost_vendor) → scalars().first()
         [only if vendor_row has bank_account:]
      7. ghost_match → scalars().first()
    """
    db = MagicMock()

    r_inv = MagicMock()
    r_inv.scalars.return_value.first.return_value = invoice

    if invoice.vendor_id is None:
        db.execute.side_effect = [r_inv]
        return db

    r_hist = MagicMock()
    r_hist.scalars.return_value.all.return_value = hist_invoices or []

    r_dup = MagicMock()
    r_dup.scalars.return_value.first.return_value = dup_invoice  # None or mock

    r_approved = MagicMock()
    r_approved.scalars.return_value.all.return_value = approved_invoices or []

    # Signal 6: bank_account_changed — default None (not triggered)
    r_bank = MagicMock()
    r_bank.scalars.return_value.first.return_value = bank_change

    # Signal 7: ghost_vendor — default None vendor_row (not triggered; avoids 7th query)
    r_vendor = MagicMock()
    r_vendor.scalars.return_value.first.return_value = vendor_row

    side_effects = [r_inv, r_hist, r_dup, r_approved, r_bank, r_vendor]

    # If vendor_row has a bank_account, score_invoice fires one more query
    if vendor_row is not None and getattr(vendor_row, "bank_account", None):
        r_ghost = MagicMock()
        r_ghost.scalars.return_value.first.return_value = None
        side_effects.append(r_ghost)

    db.execute.side_effect = side_effects
    return db


# ─── Tests ────────────────────────────────────────────────────────────────────

@patch("app.services.audit.log")
def test_round_amount_signal(mock_audit_log):
    """Invoice with amount=5000.00 triggers round_amount signal (+10 points)."""
    # vendor_id=None → only round_amount and stale_invoice_date signals evaluated
    invoice = _make_invoice(total_amount=5000.00, vendor_id=None, invoice_date=None)
    db = _db_for_score(invoice)

    result = score_invoice(db, invoice.id)

    assert "round_amount" in result["triggered_signals"]
    assert result["fraud_score"] >= SIGNAL_WEIGHTS["round_amount"]
    # Verify invoice object was updated
    assert invoice.fraud_score == result["fraud_score"]
    mock_audit_log.assert_called_once()


@patch("app.services.audit.log")
def test_potential_duplicate_signal(mock_audit_log):
    """Duplicate invoice (same vendor, same amount, within 7 days) adds +30 points."""
    vendor_id = uuid.uuid4()
    # Use non-round amount to avoid round_amount signal (1234.56 != round(1234.56))
    invoice = _make_invoice(total_amount=1234.56, vendor_id=vendor_id, invoice_date=None)

    # Mock a duplicate invoice returned by the dup query
    mock_dup = MagicMock()
    mock_dup.id = uuid.uuid4()
    mock_dup.total_amount = Decimal("1234.56")

    db = _db_for_score(
        invoice,
        hist_invoices=[],      # < 3 → amount_spike not triggered
        dup_invoice=mock_dup,  # potential duplicate found
        approved_invoices=[],  # < 3 approved → new_vendor triggered
    )

    result = score_invoice(db, invoice.id)

    assert "potential_duplicate" in result["triggered_signals"]
    # potential_duplicate=30 + new_vendor=5 = 35
    assert result["fraud_score"] == SIGNAL_WEIGHTS["potential_duplicate"] + SIGNAL_WEIGHTS["new_vendor"]


def test_score_thresholds():
    """Verify score → risk_level mapping matches configured thresholds.

    Thresholds from config:
      LOW    < MEDIUM (20)
      MEDIUM >= 20 and < HIGH (40)
      HIGH   >= 40 and < CRITICAL (60)
      CRITICAL >= 60
    """

    def get_risk_level(score: int) -> str:
        if score >= settings.FRAUD_SCORE_CRITICAL_THRESHOLD:
            return "CRITICAL"
        elif score >= settings.FRAUD_SCORE_HIGH_THRESHOLD:
            return "HIGH"
        elif score >= settings.FRAUD_SCORE_MEDIUM_THRESHOLD:
            return "MEDIUM"
        else:
            return "LOW"

    assert get_risk_level(10) == "LOW"
    assert get_risk_level(25) == "MEDIUM"
    assert get_risk_level(45) == "HIGH"
    assert get_risk_level(65) == "CRITICAL"

    # Verify the thresholds themselves match expected business values
    assert settings.FRAUD_SCORE_MEDIUM_THRESHOLD == 20
    assert settings.FRAUD_SCORE_HIGH_THRESHOLD == 40
    assert settings.FRAUD_SCORE_CRITICAL_THRESHOLD == 60
