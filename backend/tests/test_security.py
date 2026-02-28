"""Security and edge case tests — OWASP A01/A05, payment authorization."""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import app
from app.core.security import create_access_token
from app.db.session import get_session
from app.core.deps import get_current_user


# ─── Fixtures ─────────────────────────────────────────────────────────────────

class FakeUser:
    """Minimal user stub for dependency overrides."""

    def __init__(self, role: str = "ADMIN", email: str = "admin@example.com", name: str = "Admin User"):
        self.id = uuid.UUID("f96955d0-752f-4e0c-b1dc-d26d8dd1460e")
        self.email = email
        self.name = name
        self.role = role
        self.is_active = True
        self.deleted_at = None


class FakeInvoice:
    """Minimal invoice stub for dependency overrides."""

    def __init__(self, invoice_id: str, status: str = "ingested"):
        self.id = uuid.UUID(invoice_id)
        self.invoice_number = "INV-001"
        self.vendor_name_raw = "Test Vendor"
        self.total_amount = 1000.0
        self.status = status
        self.fraud_score = None
        self.payment_status = None
        self.payment_date = None
        self.payment_method = None
        self.payment_reference = None
        self.created_at = "2025-01-01T00:00:00Z"


def make_mock_session():
    """Return an AsyncMock session with a default empty-result execute."""
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 0
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    return mock_session


async def make_override_get_current_user(role: str = "ADMIN", email: str = "admin@example.com"):
    """Dependency override factory: returns user with specified role."""
    async def _override():
        return FakeUser(role=role, email=email)
    return _override


def make_session_override(mock_session):
    async def _override():
        yield mock_session
    return _override


# ─── Test: /me endpoint must not return password hash ──────────────────────────

@pytest.mark.asyncio
async def test_me_endpoint_excludes_password_hash():
    """GET /api/v1/auth/me must never return password_hash or password."""
    user_id = str(uuid.uuid4())
    token = create_access_token(subject=user_id, role="ADMIN")

    fake_user = FakeUser(role="ADMIN")
    fake_user.id = uuid.UUID(user_id)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_user

    async def mock_execute(*args, **kwargs):
        return mock_result

    mock_session = AsyncMock()
    mock_session.execute = mock_execute

    async def override_get_session():
        yield mock_session

    from app.db.session import get_session
    app.dependency_overrides[get_session] = override_get_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert "password" not in body, "password field must not be returned"
    assert "password_hash" not in body, "password_hash field must not be returned"
    assert "hashed_password" not in body, "hashed_password field must not be returned"
    assert body["role"] == "ADMIN"


# ─── Test: Ask AI must reject DML keywords ─────────────────────────────────────

@pytest.mark.asyncio
async def test_ask_ai_rejects_dml_keywords():
    """POST /api/v1/ask-ai must reject queries with DML keywords."""
    user_id = str(uuid.uuid4())
    token = create_access_token(subject=user_id, role="AP_ANALYST")

    mock_session = make_mock_session()
    app.dependency_overrides[get_session] = make_session_override(mock_session)
    app.dependency_overrides[get_current_user] = await make_override_get_current_user(role="AP_ANALYST")

    dml_keywords = [
        "DROP TABLE invoices",
        "DELETE FROM invoices WHERE id = 1",
        "INSERT INTO invoices VALUES (...)",
        "UPDATE invoices SET status='paid'",
        "ALTER TABLE invoices ADD COLUMN test",
        "TRUNCATE TABLE invoices",
    ]

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for keyword in dml_keywords:
                response = await client.post(
                    "/api/v1/ask-ai",
                    json={"question": keyword},
                    headers={"Authorization": f"Bearer {token}"},
                )
                # Should be 400 or 503 (depending on API key), but NOT 200
                assert response.status_code != 200, f"DML query should be rejected: {keyword}"
    finally:
        app.dependency_overrides.clear()


# ─── Test: Ask AI requires authentication ──────────────────────────────────────

@pytest.mark.asyncio
async def test_ask_ai_requires_auth():
    """POST /api/v1/ask-ai without Bearer token must return 401."""
    mock_session = make_mock_session()
    app.dependency_overrides[get_session] = make_session_override(mock_session)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/ask-ai", json={"question": "show invoices"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401, "Unauthenticated request should return 401"


# ─── Test: Payment endpoint requires ADMIN role ────────────────────────────────

@pytest.mark.asyncio
async def test_payment_requires_admin_role():
    """POST /api/v1/invoices/{id}/payment with AP_ANALYST role must return 403."""
    invoice_id = str(uuid.uuid4())
    token = create_access_token(subject=str(uuid.uuid4()), role="AP_ANALYST")

    mock_session = make_mock_session()
    app.dependency_overrides[get_session] = make_session_override(mock_session)
    app.dependency_overrides[get_current_user] = await make_override_get_current_user(role="AP_ANALYST")

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/invoices/{invoice_id}/payment",
                json={"payment_method": "ACH"},
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403, "Non-ADMIN role should get 403 Forbidden"


# ─── Test: Payment requires approved status ────────────────────────────────────

@pytest.mark.asyncio
async def test_payment_requires_approved_status():
    """POST /api/v1/invoices/{id}/payment on ingested invoice must return 400."""
    invoice_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    token = create_access_token(subject=user_id, role="ADMIN")

    # Mock invoice in 'ingested' status (not approved)
    fake_invoice = FakeInvoice(invoice_id, status="ingested")

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_invoice

    async def mock_execute(*args, **kwargs):
        return mock_result

    mock_session = AsyncMock()
    mock_session.execute = mock_execute
    mock_session.commit = AsyncMock()

    app.dependency_overrides[get_session] = make_session_override(mock_session)
    app.dependency_overrides[get_current_user] = await make_override_get_current_user(role="ADMIN")

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/invoices/{invoice_id}/payment",
                json={"payment_method": "ACH"},
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400, "Non-approved invoice should return 400"
    detail = response.json().get("detail", "").lower()
    assert "approved" in detail, "Error message should mention 'approved' status requirement"


# ─── Test: Payment succeeds for approved invoice with ADMIN ────────────────────

@pytest.mark.asyncio
async def test_payment_records_successfully_for_approved_invoice():
    """POST /api/v1/invoices/{id}/payment with ADMIN on approved invoice should return 200."""
    invoice_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    token = create_access_token(subject=user_id, role="ADMIN")

    # Mock invoice in 'approved' status
    fake_invoice = FakeInvoice(invoice_id, status="approved")

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_invoice

    async def mock_execute(*args, **kwargs):
        return mock_result

    mock_session = AsyncMock()
    mock_session.execute = mock_execute
    mock_session.commit = AsyncMock()

    app.dependency_overrides[get_session] = make_session_override(mock_session)
    app.dependency_overrides[get_current_user] = await make_override_get_current_user(role="ADMIN")

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/invoices/{invoice_id}/payment",
                json={"payment_method": "ACH", "payment_reference": "ACH123456"},
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200, f"Payment should succeed for approved invoice, got {response.status_code}"
    data = response.json()
    assert data["payment_status"] == "completed"
