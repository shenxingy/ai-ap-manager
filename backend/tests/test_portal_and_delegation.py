"""Tests for vendor portal endpoints and approval delegation.

Tests:
  1. test_portal_invite_requires_admin     — 403 for non-ADMIN callers
  2. test_portal_invite_success            — 201 + {token, vendor_id} for ADMIN
  3. test_portal_invoice_list             — 200 + {items, total} via vendor portal JWT
  4. test_portal_dispute_submission       — 201 + {status, exception_id, message_id}
  5. test_delegation_check               — create_approval_task re-routes to delegate
"""
import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.deps import get_current_user, get_current_vendor_id
from app.db.session import get_session
from app.services.approval import create_approval_task


# ─── Shared fixtures ──────────────────────────────────────────────────────────

VENDOR_ID = uuid.UUID("c1b2c3d4-e5f6-7890-abcd-ef1234567890")


class FakeAdminUser:
    id = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
    email = "admin@example.com"
    name = "Admin"
    role = "ADMIN"
    is_active = True
    deleted_at = None


class FakeApproverUser:
    id = uuid.UUID("b1b2c3d4-e5f6-7890-abcd-ef1234567890")
    email = "approver@example.com"
    name = "Approver"
    role = "APPROVER"
    is_active = True
    deleted_at = None


async def override_admin():
    return FakeAdminUser()


async def override_approver():
    return FakeApproverUser()


async def override_vendor_id():
    return VENDOR_ID


def make_session_override(mock_session):
    async def _override():
        yield mock_session
    return _override


# ─── Test 1: invite requires ADMIN ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_portal_invite_requires_admin():
    """POST /portal/auth/invite with non-ADMIN role must return 403."""
    app.dependency_overrides[get_current_user] = override_approver
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/portal/auth/invite",
                json={"vendor_id": str(uuid.uuid4())},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


# ─── Test 2: invite success ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_portal_invite_success():
    """POST /portal/auth/invite with ADMIN + valid vendor_id returns 201 + {token, vendor_id}."""
    mock_vendor = MagicMock()
    mock_vendor.id = VENDOR_ID

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_vendor

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    app.dependency_overrides[get_current_user] = override_admin
    app.dependency_overrides[get_session] = make_session_override(mock_session)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/portal/auth/invite",
                json={"vendor_id": str(VENDOR_ID)},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    data = response.json()
    assert "token" in data
    assert data["vendor_id"] == str(VENDOR_ID)


# ─── Test 3: portal invoice list ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_portal_invoice_list():
    """GET /portal/invoices with vendor JWT returns 200 + {items, total}."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.scalar = AsyncMock(return_value=0)

    app.dependency_overrides[get_current_vendor_id] = override_vendor_id
    app.dependency_overrides[get_session] = make_session_override(mock_session)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/portal/invoices")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["items"] == []


# ─── Test 4: portal dispute submission ────────────────────────────────────────

@pytest.mark.asyncio
async def test_portal_dispute_submission():
    """POST /portal/invoices/{id}/dispute returns 201 + {status, exception_id, message_id}.

    Also verifies that an ExceptionRecord with exception_code='VENDOR_DISPUTE' was added.
    """
    invoice_id = uuid.uuid4()

    mock_invoice = MagicMock()
    mock_invoice.id = invoice_id
    mock_invoice.vendor_id = VENDOR_ID

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_invoice

    added_objects = []
    exc_id = uuid.uuid4()
    msg_id = uuid.uuid4()
    refresh_ids = [exc_id, msg_id]
    refresh_count = [0]

    async def refresh_side_effect(obj):
        obj.id = refresh_ids[refresh_count[0]]
        refresh_count[0] += 1

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock(side_effect=added_objects.append)
    mock_session.refresh = AsyncMock(side_effect=refresh_side_effect)

    app.dependency_overrides[get_current_vendor_id] = override_vendor_id
    app.dependency_overrides[get_session] = make_session_override(mock_session)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/portal/invoices/{invoice_id}/dispute",
                json={"reason": "incorrect_amount", "description": "Amount does not match PO"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "dispute_submitted"
    assert "exception_id" in data
    assert "message_id" in data

    # Verify ExceptionRecord with VENDOR_DISPUTE code was added to the session
    from app.models.exception_record import ExceptionRecord
    exception_records = [o for o in added_objects if isinstance(o, ExceptionRecord)]
    assert len(exception_records) == 1, "Expected one ExceptionRecord to be added"
    assert exception_records[0].exception_code == "VENDOR_DISPUTE"


# ─── Test 5: delegation check ─────────────────────────────────────────────────

def test_delegation_check():
    """create_approval_task re-routes to the delegate when an active delegation exists.

    Setup: userA (APPROVER) has delegated to userB for the current date range.
    Expected: returned task.approver_id == userB.id, task.delegated_to == userA.id
    """
    userA_id = uuid.uuid4()
    userB_id = uuid.uuid4()
    invoice_id = uuid.uuid4()
    today = date.today()

    # Mock delegation: A → B, is_active=True, valid today through tomorrow
    mock_delegation = MagicMock()
    mock_delegation.delegate_id = userB_id
    mock_delegation.valid_until = today + timedelta(days=1)

    # Mock invoice with vendor_id=None to skip the compliance doc check branch
    mock_invoice = MagicMock()
    mock_invoice.vendor_id = None

    def make_scalar_result(first_value):
        r = MagicMock()
        r.scalars.return_value.first.return_value = first_value
        r.scalars.return_value.all.return_value = []
        return r

    db = MagicMock()
    # execute call order:
    # 1 — Invoice query for compliance check (vendor_id=None → branch skipped)
    # 2 — UserDelegation query → active delegation A → B
    # 3 — Invoice query for email notification
    db.execute.side_effect = [
        make_scalar_result(mock_invoice),    # compliance invoice check
        make_scalar_result(mock_delegation), # delegation lookup
        make_scalar_result(mock_invoice),    # email invoice lookup
    ]

    with patch("app.services.email.send_approval_request_email"):
        task = create_approval_task(
            db=db,
            invoice_id=invoice_id,
            approver_id=userA_id,
        )

    assert task.approver_id == userB_id, (
        f"Expected approver_id={userB_id} (delegate), got {task.approver_id}"
    )
    assert task.delegated_to == userA_id, (
        f"Expected delegated_to={userA_id} (original), got {task.delegated_to}"
    )
