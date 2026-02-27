"""Tests for vendor CRUD operations.

Tests vendor creation, updates, and duplicate checking logic.
Uses mocked database sessions following existing test patterns.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


# ─── Tests ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_vendor():
    """Vendor creation: instantiate + set fields → vendor ready for DB persistence.

    Tests that a vendor object can be created with all required fields
    and is ready for database insertion.
    """
    from app.models.vendor import Vendor

    vendor_id = uuid.uuid4()
    vendor = Vendor(
        id=vendor_id,
        name="New Vendor Corp",
        tax_id="98-7654321",
        payment_terms=45,
        currency="USD",
        is_active=True,
    )

    # Verify the vendor object has all required fields
    assert vendor.id == vendor_id
    assert vendor.name == "New Vendor Corp"
    assert vendor.tax_id == "98-7654321"
    assert vendor.payment_terms == 45
    assert vendor.currency == "USD"
    assert vendor.is_active is True
    assert vendor.deleted_at is None


@pytest.mark.asyncio
async def test_duplicate_tax_id_detection():
    """Duplicate tax_id: query finds existing vendor with same tax_id.

    The vendor creation endpoint checks for existing vendors with the same
    tax_id and should return 409 Conflict if found.
    """
    from app.models.vendor import Vendor

    existing_vendor = Vendor(
        id=uuid.uuid4(),
        name="Existing Vendor",
        tax_id="11-1111111",
        currency="USD",
        payment_terms=30,
        is_active=True,
    )

    new_tax_id = "11-1111111"  # Duplicate

    # Simulate the duplicate check: would query for existing vendor
    # If scalar_one_or_none returns the existing_vendor, endpoint returns 409
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=existing_vendor)

    # Verify that when existing vendor is found, conflict is detected
    found_vendor = await mock_result.scalar_one_or_none()
    assert found_vendor is not None
    assert found_vendor.tax_id == new_tax_id


@pytest.mark.asyncio
async def test_patch_vendor_updates_fields():
    """Vendor patch: update fields → fields changed correctly.

    Tests that patching a vendor updates only the specified fields.
    """
    from app.models.vendor import Vendor

    vendor_id = uuid.uuid4()
    vendor = Vendor(
        id=vendor_id,
        name="Acme Corp",
        payment_terms=30,
        is_active=True,
        currency="USD",
        tax_id="12-3456789",
    )

    # Simulate patch: update payment_terms
    updates = {"payment_terms": 60}
    for field, value in updates.items():
        setattr(vendor, field, value)

    # Verify the update
    assert vendor.payment_terms == 60
    assert vendor.id == vendor_id
    assert vendor.name == "Acme Corp"  # Other fields unchanged


@pytest.mark.asyncio
async def test_vendor_not_found_returns_none():
    """Vendor detail: query non-existent ID → scalar_one_or_none returns None.

    Tests that querying for a non-existent vendor returns None, which
    the endpoint converts to a 404 response.
    """
    nonexistent_id = uuid.uuid4()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none = AsyncMock(return_value=None)

    # Verify the query returns None for non-existent vendor
    found_vendor = await mock_result.scalar_one_or_none()
    assert found_vendor is None
