"""Pydantic schemas for vendor API endpoints."""
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


# ─── Alias schemas ───

class VendorAliasOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    alias: str
    created_at: datetime


class VendorAliasCreate(BaseModel):
    alias_name: str


# ─── Invoice stub for recent invoices ───

class InvoiceStub(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str | None
    status: str
    total_amount: Decimal | None
    currency: str | None
    created_at: datetime


# ─── List item ───

class VendorListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    tax_id: str | None
    payment_terms: int
    currency: str
    is_active: bool
    invoice_count: int = 0


# ─── Paginated list response ───

class VendorListResponse(BaseModel):
    items: list[VendorListItem]
    total: int
    page: int
    page_size: int


# ─── Detail ───

class VendorDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    tax_id: str | None
    bank_account: str | None
    bank_routing: str | None
    currency: str
    payment_terms: int
    email: str | None
    address: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    aliases: list[VendorAliasOut] = []
    recent_invoices: list[InvoiceStub] = []


# ─── Create ───

class VendorCreate(BaseModel):
    name: str
    tax_id: str | None = None
    payment_terms: int = 30
    currency: str = "USD"
    bank_account: str | None = None
    bank_routing: str | None = None
    email: str | None = None
    address: str | None = None
    is_active: bool = True


# ─── Update (partial) ───

class VendorUpdate(BaseModel):
    name: str | None = None
    tax_id: str | None = None
    payment_terms: int | None = None
    currency: str | None = None
    bank_account: str | None = None
    bank_routing: str | None = None
    email: str | None = None
    address: str | None = None
    is_active: bool | None = None
