"""Tests for new feature modules.

Covers: ERP CSV parsers, KPI benchmarks endpoint, inspection report enum,
4-way match, GL classifier, entity model, entities endpoint, IMAP poll.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

# ─── Helpers ──────────────────────────────────────────────────────────────────

class FakeUser:
    """Minimal user stub for DB mock injection."""

    def __init__(self, role: str = "ADMIN"):
        self.id = uuid.uuid4()
        self.email = "testuser@example.com"
        self.name = "Test User"
        self.role = role
        self.is_active = True
        self.deleted_at = None


def _make_session_override(fake_user: FakeUser):
    """Return an async generator that yields a mock DB session returning fake_user."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_user

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    async def override():
        yield mock_session

    return override


# ─── ERP CSV Parser Tests ──────────────────────────────────────────────────────

def test_parse_sap_pos_missing_columns():
    """parse_sap_pos with missing required columns → errors non-empty, lines empty."""
    from app.integrations.sap_csv import parse_sap_pos

    csv_content = "INVOICE_NUMBER;AMOUNT\n001;100.00\n"
    lines, errors = parse_sap_pos(csv_content)

    assert lines == []
    assert len(errors) > 0


def test_parse_sap_pos_valid():
    """parse_sap_pos with valid semicolon CSV → lines parsed correctly."""
    from app.integrations.sap_csv import parse_sap_pos

    csv_content = (
        "PO_NUMBER;VENDOR_CODE;VENDOR_NAME;LINE_NUMBER;DESCRIPTION;QUANTITY;UNIT_PRICE;CURRENCY\n"
        "PO-001;V100;Acme Corp;1;Widget A;10;25.50;USD\n"
        "PO-001;V100;Acme Corp;2;Widget B;5;15.00;USD\n"
    )
    lines, errors = parse_sap_pos(csv_content)

    assert errors == []
    assert len(lines) == 2
    assert lines[0]["po_number"] == "PO-001"
    assert lines[0]["quantity"] == 10.0
    assert lines[0]["unit_price"] == 25.50
    assert lines[1]["line_number"] == "2"


def test_parse_oracle_grns_valid():
    """parse_oracle_grns with valid comma CSV → lines parsed correctly."""
    from app.integrations.oracle_csv import parse_oracle_grns

    csv_content = (
        "RECEIPT_NUMBER,PO_NUMBER,LINE_NUMBER,ITEM_DESCRIPTION,QUANTITY_RECEIVED,RECEIVED_DATE\n"
        "GRN-100,PO-001,1,Widget A,8,2024-01-15\n"
        "GRN-100,PO-001,2,Widget B,5,2024-01-15\n"
    )
    lines, errors = parse_oracle_grns(csv_content)

    assert errors == []
    assert len(lines) == 2
    assert lines[0]["receipt_number"] == "GRN-100"
    assert lines[0]["quantity_received"] == 8.0
    assert lines[0]["received_date"] == "2024-01-15"


# ─── KPI Benchmarks Auth ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_kpi_benchmarks_auth():
    """GET /api/v1/kpi/benchmarks with valid auth token → 200 with benchmark keys."""
    from app.core.security import create_access_token
    from app.db.session import get_session

    user_id = str(uuid.uuid4())
    token = create_access_token(subject=user_id, role="ADMIN")

    fake_user = FakeUser(role="ADMIN")
    fake_user.id = uuid.UUID(user_id)

    app.dependency_overrides[get_session] = _make_session_override(fake_user)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/kpi/benchmarks",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert "touchless_rate" in data
    assert "exception_rate" in data


# ─── ERP Sync 403 ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_erp_sync_sap_pos_analyst_forbidden():
    """POST /api/v1/admin/erp/sync/sap-pos with AP_ANALYST token → 403."""
    from app.core.security import create_access_token
    from app.db.session import get_session

    user_id = str(uuid.uuid4())
    token = create_access_token(subject=user_id, role="AP_ANALYST")

    fake_user = FakeUser(role="AP_ANALYST")
    fake_user.id = uuid.UUID(user_id)

    app.dependency_overrides[get_session] = _make_session_override(fake_user)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/admin/erp/sync/sap-pos",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": ("test.csv", b"PO_NUMBER;VENDOR_CODE\nPO-001;V100", "text/csv")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


# ─── InspectionResult Enum ────────────────────────────────────────────────────

def test_inspection_result_enum():
    """InspectionResult enum must have values 'pass', 'fail', 'partial'."""
    from app.models.inspection_report import InspectionResult

    values = {m.value for m in InspectionResult}
    assert "pass" in values
    assert "fail" in values
    assert "partial" in values


# ─── 4-Way Match Callable ─────────────────────────────────────────────────────

def test_run_4way_match_callable():
    """run_4way_match must be importable and callable."""
    from app.rules.match_engine import run_4way_match

    assert callable(run_4way_match)


# ─── GL Classifier No Model ───────────────────────────────────────────────────

def test_predict_gl_account_no_model():
    """predict_gl_account returns (None, 0.0) when no trained model is available."""
    import app.services.gl_classifier as gl_mod
    from app.services.gl_classifier import predict_gl_account

    with patch.object(gl_mod, "_cached_model", None), patch.object(gl_mod, "load_latest_model", return_value=(None, None)):
        result = predict_gl_account("Test Vendor", "supplies", 100)

    assert result == (None, 0.0)


# ─── Entity Model Tablename ───────────────────────────────────────────────────

def test_entity_model_tablename():
    """Entity.__tablename__ must equal 'entities'."""
    from app.models.entity import Entity

    assert Entity.__tablename__ == "entities"


# ─── Entities Unauthenticated ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_entities_unauthenticated():
    """GET /api/v1/entities without auth header → 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/entities")

    assert response.status_code == 401


# ─── IMAP Poll Skipped ────────────────────────────────────────────────────────

def test_imap_poll_skipped():
    """poll_ap_mailbox returns {'status': 'skipped'} when IMAP_HOST is not configured."""
    from app.core.config import settings
    from app.workers.email_ingestion import poll_ap_mailbox

    with patch.object(settings, "IMAP_HOST", ""):
        result = poll_ap_mailbox()

    assert result["status"] == "skipped"
