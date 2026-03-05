"""Tests for the health endpoint."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_returns_200():
    """GET /health/live should return HTTP 200 (no dependency checks)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/live")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_returns_ok_status():
    """GET /health/live should return JSON body with status == ok."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/live")
    data = response.json()
    assert data["status"] == "ok"
