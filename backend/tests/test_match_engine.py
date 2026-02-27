"""Unit tests for the 2-way and 3-way match engine.

All DB access is replaced with MagicMock. Internal persistence and
rule-loading helpers are patched to isolate the core matching logic.
"""
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.rules.match_engine import run_2way_match, run_3way_match


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_invoice(total_amount: float, status: str = "matching") -> MagicMock:
    inv = MagicMock()
    inv.id = uuid.uuid4()
    inv.total_amount = Decimal(str(total_amount))
    inv.status = status
    inv.deleted_at = None
    inv.po_id = None
    inv.notes = None
    inv.invoice_number = "INV-0001"
    inv.fraud_score = 0
    return inv


def _make_po(total_amount: float, po_lines: list | None = None) -> MagicMock:
    po = MagicMock()
    po.id = uuid.uuid4()
    po.total_amount = Decimal(str(total_amount))
    po.line_items = po_lines or []
    return po


def _make_inv_line(line_number: int, qty: float, unit_price: float,
                   invoice_id: uuid.UUID | None = None,
                   description: str = "Widget") -> MagicMock:
    line = MagicMock()
    line.id = uuid.uuid4()
    line.invoice_id = invoice_id or uuid.uuid4()
    line.line_number = line_number
    line.quantity = Decimal(str(qty))
    line.unit_price = Decimal(str(unit_price))
    line.description = description
    return line


def _make_po_line(line_number: int, qty: float, unit_price: float,
                  description: str = "Widget") -> MagicMock:
    line = MagicMock()
    line.id = uuid.uuid4()
    line.line_number = line_number
    line.quantity = Decimal(str(qty))
    line.unit_price = Decimal(str(unit_price))
    line.description = description
    return line


def _db_for_2way(invoice: MagicMock, inv_lines: list) -> MagicMock:
    """Build a DB mock for run_2way_match: invoice query then line-items query."""
    db = MagicMock()

    inv_result = MagicMock()
    inv_result.scalars.return_value.first.return_value = invoice

    lines_result = MagicMock()
    lines_result.scalars.return_value.all.return_value = inv_lines

    db.execute.side_effect = [inv_result, lines_result]
    return db


def _db_for_3way(invoice: MagicMock, inv_lines: list,
                 grns: list, gr_lines: list) -> MagicMock:
    """Build a DB mock for run_3way_match with GRN/GR-lines queries."""
    db = MagicMock()

    inv_result = MagicMock()
    inv_result.scalars.return_value.first.return_value = invoice

    lines_result = MagicMock()
    lines_result.scalars.return_value.all.return_value = inv_lines

    grn_result = MagicMock()
    grn_result.scalars.return_value.all.return_value = grns

    side_effects = [inv_result, lines_result, grn_result]

    if grns:
        gr_lines_result = MagicMock()
        gr_lines_result.scalars.return_value.all.return_value = gr_lines
        side_effects.append(gr_lines_result)

    db.execute.side_effect = side_effects
    return db


# Tolerance config: 5% relative, $5 absolute, threshold=$50
TIGHT_TOLERANCE = {
    "amount_tolerance_pct": 0.05,
    "amount_tolerance_abs": 5.00,
    "qty_tolerance_pct": 0.00,
    "auto_approve_threshold": 50.00,
    "auto_approve_requires_match": True,
}


# ─── 2-Way Match Tests ────────────────────────────────────────────────────────

@patch("app.rules.match_engine._persist_match_result")
@patch("app.rules.match_engine._find_po_for_invoice")
@patch("app.rules.match_engine.get_active_match_rules")
def test_2way_price_variance(mock_rules, mock_find_po, mock_persist):
    """Invoice $110 vs PO $100 at 5% tolerance → PRICE_VARIANCE exception.

    Variance = 10% > 5% tolerance AND $10 > $5 abs → header fails.
    """
    mock_rules.return_value = (TIGHT_TOLERANCE.copy(), None)

    invoice = _make_invoice(110.0)
    po = _make_po(100.0)
    mock_find_po.return_value = po

    db = _db_for_2way(invoice, [])  # no line items → header-only

    result = run_2way_match(db, invoice.id)

    assert result.match_status == "exception"
    assert "PRICE_VARIANCE" in result.exception_codes
    mock_persist.assert_called_once()


@patch("app.services.audit.log")
@patch("app.services.approval.auto_create_approval_task")
@patch("app.rules.match_engine._find_po_for_invoice")
@patch("app.rules.match_engine.get_active_match_rules")
def test_2way_auto_approve(mock_rules, mock_find_po, mock_auto_task, mock_audit_log):
    """Invoice $102 vs PO $100 at 5% tolerance, threshold=$50 → status=matched, task created.

    2% variance < 5% → header OK → overall matched. Invoice $102 > $50 threshold
    so can't auto-approve; instead status is set to 'matched' and ApprovalTask
    is created (via lazy import of auto_create_approval_task inside _persist_match_result).
    """
    mock_rules.return_value = (TIGHT_TOLERANCE.copy(), None)
    mock_auto_task.return_value = MagicMock()

    invoice = _make_invoice(102.0)
    po = _make_po(100.0)
    mock_find_po.return_value = po

    # DB: invoice query + line items + _persist_match_result's existing-MR check
    db = MagicMock()
    inv_result = MagicMock()
    inv_result.scalars.return_value.first.return_value = invoice
    lines_result = MagicMock()
    lines_result.scalars.return_value.all.return_value = []
    no_existing = MagicMock()
    no_existing.scalars.return_value.first.return_value = None  # no prior match result
    db.execute.side_effect = [inv_result, lines_result, no_existing]

    result = run_2way_match(db, invoice.id)

    assert result.match_status == "matched"
    assert result.exception_codes == []
    # invoice.status is set by _persist_match_result since 102 > threshold(50) → not auto-approved
    assert invoice.status == "matched"
    # auto_create_approval_task is called with (db, invoice.id) inside _persist_match_result
    mock_auto_task.assert_called_once_with(db, invoice.id)


# ─── 3-Way Match Tests ────────────────────────────────────────────────────────

@patch("app.rules.match_engine._persist_match_result")
@patch("app.rules.match_engine._find_po_for_invoice")
@patch("app.rules.match_engine.get_active_match_rules")
def test_3way_grn_not_found(mock_rules, mock_find_po, mock_persist):
    """No GoodsReceipt rows for PO → GRN_NOT_FOUND exception."""
    mock_rules.return_value = (TIGHT_TOLERANCE.copy(), None)

    invoice = _make_invoice(100.0)
    po = _make_po(100.0)
    mock_find_po.return_value = po

    db = _db_for_3way(invoice, [], grns=[], gr_lines=[])

    result = run_3way_match(db, invoice.id)

    assert result.match_status == "exception"
    assert "GRN_NOT_FOUND" in result.exception_codes
    mock_persist.assert_called_once()


@patch("app.rules.match_engine._persist_match_result")
@patch("app.rules.match_engine._find_po_for_invoice")
@patch("app.rules.match_engine.get_active_match_rules")
def test_3way_qty_over_receipt(mock_rules, mock_find_po, mock_persist):
    """Invoice qty=10 > GRN received qty=8 → QTY_OVER_RECEIPT exception."""
    mock_rules.return_value = (TIGHT_TOLERANCE.copy(), None)

    invoice = _make_invoice(100.0)
    po_line = _make_po_line(line_number=1, qty=10.0, unit_price=10.0)
    po = _make_po(100.0, po_lines=[po_line])
    mock_find_po.return_value = po

    inv_line = _make_inv_line(line_number=1, qty=10.0, unit_price=10.0,
                               invoice_id=invoice.id)

    # GRN with one GR line: received qty=8 against po_line
    mock_grn = MagicMock()
    mock_grn.id = uuid.uuid4()

    mock_grl = MagicMock()
    mock_grl.po_line_item_id = po_line.id
    mock_grl.quantity = Decimal("8.0")

    db = _db_for_3way(invoice, [inv_line], grns=[mock_grn], gr_lines=[mock_grl])

    result = run_3way_match(db, invoice.id)

    assert result.match_status == "exception"
    assert "QTY_OVER_RECEIPT" in result.exception_codes
    mock_persist.assert_called_once()
