"""Tests for authentication endpoints."""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock

from app.main import app


# ─── Fixtures ─────────────────────────────────────────────────────────────────

class FakeUser:
    """Minimal user stub returned by DB mock."""

    id = "f96955d0-752f-4e0c-b1dc-d26d8dd1460e"
    email = "admin@example.com"
    name = "Admin User"
    role = "ADMIN"
    is_active = True
    deleted_at = None
    password_hash = "$2b$12$placeholder"  # will be mocked


# ─── Login Tests ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_valid_credentials_returns_jwt():
    """POST /api/v1/auth/login with valid credentials should return access_token."""
    fake_user = FakeUser()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_user

    async def mock_execute(*args, **kwargs):
        return mock_result

    mock_session = AsyncMock()
    mock_session.execute = mock_execute

    async def override_get_session():
        yield mock_session

    with patch("app.core.security.verify_password", return_value=True):
        from app.db.session import get_session
        app.dependency_overrides[get_session] = override_get_session
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/auth/login",
                    data={"username": "admin@example.com", "password": "changeme123"},
                )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid_credentials_returns_401():
    """POST /api/v1/auth/login with wrong password should return 401."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

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
            response = await client.post(
                "/api/v1/auth/login",
                data={"username": "wrong@example.com", "password": "badpass"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


# ─── /me Tests ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_me_with_valid_token_returns_user():
    """GET /api/v1/auth/me with valid Bearer token should return user data."""
    import uuid
    from app.core.security import create_access_token

    user_id = str(uuid.uuid4())
    token = create_access_token(subject=user_id, role="ADMIN")

    fake_user = FakeUser()
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
    data = response.json()
    assert data["email"] == "admin@example.com"
    assert data["role"] == "ADMIN"


@pytest.mark.asyncio
async def test_me_without_token_returns_401():
    """GET /api/v1/auth/me without Authorization header should return 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
