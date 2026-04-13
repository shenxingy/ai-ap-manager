"""Unit tests for GL coding service.

Tests the deterministic components:
  - _word_similarity: pure function, no DB
  - CATEGORY_GL_MAP: key coverage
  - Vendor history Counter logic: most-frequent GL selection and confidence
  - suggest_gl_codes: category_default fallback path (async with mocked DB)
"""
import uuid
from collections import Counter
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.services.gl_classifier  # ensure module is loaded for patching
from app.services.gl_coding import (
    CATEGORY_GL_MAP,
    _word_similarity,
    suggest_gl_codes,
)

# ─── _word_similarity ─────────────────────────────────────────────────────────

def test_word_similarity_identical():
    assert _word_similarity("bolt M6 steel", "bolt M6 steel") == 1.0


def test_word_similarity_partial_overlap():
    # 2 shared words ("steel", "bolt") out of max(3, 3) = 3
    score = _word_similarity("steel bolt M6", "steel bolt hex")
    assert abs(score - 2 / 3) < 0.001


def test_word_similarity_no_overlap():
    assert _word_similarity("steel bolt", "rubber gasket") == 0.0


def test_word_similarity_none_inputs():
    assert _word_similarity(None, "bolt") == 0.0
    assert _word_similarity("bolt", None) == 0.0
    assert _word_similarity(None, None) == 0.0


def test_word_similarity_empty_string():
    assert _word_similarity("", "bolt") == 0.0
    assert _word_similarity("bolt", "") == 0.0


# ─── CATEGORY_GL_MAP ──────────────────────────────────────────────────────────

def test_category_gl_map_parts():
    assert CATEGORY_GL_MAP["parts"] == "6010-PARTS"


def test_category_gl_map_equipment():
    assert CATEGORY_GL_MAP["equipment"] == "1500-EQUIPMENT"


def test_category_gl_map_services():
    assert CATEGORY_GL_MAP["services"] == "6100-SERVICES"


def test_category_gl_map_missing_key():
    assert CATEGORY_GL_MAP.get("unknown_category") is None


# ─── Vendor history Counter logic ─────────────────────────────────────────────

def test_vendor_history_most_frequent_wins():
    """Counter selects the GL account that appears most often."""
    gl_accounts = ["6010-PARTS", "6010-PARTS", "6100-SERVICES"]
    counter: Counter = Counter(gl_accounts)
    top_gl, _ = counter.most_common(1)[0]
    assert top_gl == "6010-PARTS"


def test_vendor_history_tie_any_winner():
    """With a tie, any of the tied accounts may win (just verify it's one of them)."""
    gl_accounts = ["6010-PARTS", "6100-SERVICES"]
    counter: Counter = Counter(gl_accounts)
    top_gl, _ = counter.most_common(1)[0]
    assert top_gl in {"6010-PARTS", "6100-SERVICES"}


def test_vendor_history_confidence_ratio():
    """Confidence = top_count / len(similar_lines)."""
    similar_lines = ["6010-PARTS", "6010-PARTS", "6100-SERVICES"]
    counter: Counter = Counter(similar_lines)
    _, top_count = counter.most_common(1)[0]
    confidence = top_count / len(similar_lines)
    assert abs(confidence - 2 / 3) < 0.001


# ─── suggest_gl_codes: category_default path ─────────────────────────────────
# predict_gl_account is imported lazily inside suggest_gl_codes; patch source module.

@pytest.mark.asyncio
async def test_suggest_gl_codes_category_default():
    """When no vendor history and no PO line, falls back to CATEGORY_GL_MAP."""
    invoice_id = uuid.uuid4()
    vendor_id = uuid.uuid4()
    line_id = uuid.uuid4()

    mock_invoice = MagicMock()
    mock_invoice.id = invoice_id
    mock_invoice.vendor_id = vendor_id
    mock_invoice.deleted_at = None

    mock_line = MagicMock()
    mock_line.id = line_id
    mock_line.invoice_id = invoice_id
    mock_line.line_number = 1
    mock_line.description = "equipment rental"
    mock_line.category = "equipment"
    mock_line.po_line_item_id = None
    mock_line.gl_account = None

    mock_vendor = MagicMock()
    mock_vendor.name = "Acme Corp"

    call_count = 0

    async def patched_execute(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            # Invoice load
            result.scalars.return_value.first.return_value = mock_invoice
        elif call_count == 2:
            # Line items
            result.scalars.return_value.all.return_value = [mock_line]
        elif call_count == 3:
            # Vendor history (none)
            result.scalars.return_value.all.return_value = []
        elif call_count == 4:
            # Vendor name lookup
            result.scalars.return_value.first.return_value = mock_vendor
        return result

    db = AsyncMock()
    db.execute.side_effect = patched_execute

    # predict_gl_account is lazily imported from app.services.gl_classifier
    with patch("app.services.gl_classifier.predict_gl_account", side_effect=Exception("no model")):
        results = await suggest_gl_codes(db, invoice_id)

    assert len(results) == 1
    assert results[0]["gl_account"] == "1500-EQUIPMENT"
    assert results[0]["source"] == "category_default"
    assert results[0]["confidence_pct"] == 0.3
