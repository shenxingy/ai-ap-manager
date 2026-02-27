"""Seed script — creates initial admin user and sample data for dev.

Idempotent: checks for existing records before inserting (ON CONFLICT DO NOTHING pattern).
"""
import asyncio
import json
import sys
import os
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import hash_password as get_password_hash
from app.models.user import User
from app.models.vendor import Vendor
from app.models.purchase_order import PurchaseOrder, POLineItem
from app.models.goods_receipt import GoodsReceipt, GRLineItem
from app.models.rule import Rule, RuleVersion


async def seed():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async with SessionLocal() as db:
        # ── Users ──
        admin = await _upsert_user(db, "admin@example.com", "Admin User", "ADMIN")
        await _upsert_user(db, "clerk@example.com", "AP Clerk", "AP_CLERK")
        await _upsert_user(db, "analyst@example.com", "AP Analyst", "AP_ANALYST")
        await _upsert_user(db, "approver@example.com", "Finance Approver", "APPROVER")
        await db.commit()

        # ── Vendor ──
        vendor = await _upsert_vendor(db, "Acme Corp", "12-3456789")
        await db.commit()

        # ── Purchase Orders ──
        po1 = await _upsert_po(
            db,
            po_number="PO-2026-001",
            vendor_id=vendor.id,
            total_amount=4800.00,
            lines=[
                {"line_number": 1, "description": "Industrial Widgets A-100", "quantity": 100, "unit_price": 30.00, "unit": "pcs", "category": "parts"},
                {"line_number": 2, "description": "Steel Bolts Grade 8", "quantity": 500, "unit_price": 6.00, "unit": "pcs", "category": "fasteners"},
            ],
        )

        po2 = await _upsert_po(
            db,
            po_number="PO-2026-002",
            vendor_id=vendor.id,
            total_amount=12500.00,
            lines=[
                {"line_number": 1, "description": "Hydraulic Pump Model HP-5000", "quantity": 5, "unit_price": 2000.00, "unit": "ea", "category": "equipment"},
                {"line_number": 2, "description": "Maintenance Service Contract", "quantity": 1, "unit_price": 2500.00, "unit": "ea", "category": "services"},
            ],
        )

        await db.commit()

        # ── Goods Receipt for PO1 ──
        await _upsert_gr(
            db,
            gr_number="GR-2026-001",
            po_id=po1.id,
            vendor_id=vendor.id,
            lines=[
                {"line_number": 1, "po_line_item_id": None, "description": "Industrial Widgets A-100", "quantity": 100.0},
                {"line_number": 2, "po_line_item_id": None, "description": "Steel Bolts Grade 8", "quantity": 500.0},
            ],
        )
        await db.commit()

        # ── Default Matching Tolerance Rule ──
        await _upsert_matching_rule(db, admin.id)
        await db.commit()

        print("Seed complete.")
        print("  admin@example.com / changeme123 (ADMIN)")
        print("  clerk@example.com / changeme123 (AP_CLERK)")
        print("  analyst@example.com / changeme123 (AP_ANALYST)")
        print("  approver@example.com / changeme123 (APPROVER)")
        print(f"  Vendor: Acme Corp (id={vendor.id})")
        print(f"  PO: {po1.po_number} (total=$4,800.00)")
        print(f"  PO: {po2.po_number} (total=$12,500.00)")
        print("  GR: GR-2026-001 (for PO-2026-001)")
        print("  Default matching tolerance rule: published")

    await engine.dispose()


# ─── Upsert helpers ───

async def _upsert_user(db: AsyncSession, email: str, name: str, role: str) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    if user:
        print(f"  [skip] User {email} already exists")
        return user
    user = User(
        email=email,
        name=name,
        password_hash=get_password_hash("changeme123"),
        role=role,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user


async def _upsert_vendor(db: AsyncSession, name: str, tax_id: str) -> Vendor:
    result = await db.execute(select(Vendor).where(Vendor.name == name))
    vendor = result.scalars().first()
    if vendor:
        print(f"  [skip] Vendor {name} already exists")
        return vendor
    vendor = Vendor(
        name=name,
        tax_id=tax_id,
        currency="USD",
        payment_terms=30,
        email="ap@acmecorp.example.com",
        is_active=True,
    )
    db.add(vendor)
    await db.flush()
    return vendor


async def _upsert_po(
    db: AsyncSession,
    po_number: str,
    vendor_id,
    total_amount: float,
    lines: list[dict],
) -> PurchaseOrder:
    result = await db.execute(select(PurchaseOrder).where(PurchaseOrder.po_number == po_number))
    po = result.scalars().first()
    if po:
        print(f"  [skip] PO {po_number} already exists")
        return po

    po = PurchaseOrder(
        po_number=po_number,
        vendor_id=vendor_id,
        status="open",
        currency="USD",
        total_amount=total_amount,
        issued_at=datetime.now(timezone.utc) - timedelta(days=14),
        expires_at=datetime.now(timezone.utc) + timedelta(days=180),
    )
    db.add(po)
    await db.flush()

    for line_data in lines:
        line = POLineItem(
            po_id=po.id,
            line_number=line_data["line_number"],
            description=line_data["description"],
            quantity=line_data["quantity"],
            unit_price=line_data["unit_price"],
            unit=line_data.get("unit"),
            category=line_data.get("category"),
        )
        db.add(line)

    await db.flush()
    return po


async def _upsert_gr(
    db: AsyncSession,
    gr_number: str,
    po_id,
    vendor_id,
    lines: list[dict],
) -> GoodsReceipt:
    result = await db.execute(
        select(GoodsReceipt).where(GoodsReceipt.gr_number == gr_number)
    )
    gr = result.scalars().first()
    if gr:
        print(f"  [skip] GR {gr_number} already exists")
        return gr

    gr = GoodsReceipt(
        gr_number=gr_number,
        po_id=po_id,
        vendor_id=vendor_id,
        received_at=datetime.now(timezone.utc) - timedelta(days=7),
    )
    db.add(gr)
    await db.flush()

    for line_data in lines:
        line = GRLineItem(
            gr_id=gr.id,
            po_line_item_id=line_data.get("po_line_item_id"),
            line_number=line_data["line_number"],
            description=line_data["description"],
            quantity=line_data["quantity"],
        )
        db.add(line)

    await db.flush()
    return gr


async def _upsert_matching_rule(db: AsyncSession, created_by_id) -> RuleVersion:
    """Insert default matching tolerance rule (idempotent)."""
    result = await db.execute(
        select(Rule).where(Rule.name == "default_matching_tolerance")
    )
    rule = result.scalars().first()

    if not rule:
        rule = Rule(
            name="default_matching_tolerance",
            description="Default 2-way match tolerance configuration",
            rule_type="matching_tolerance",
            is_active=True,
        )
        db.add(rule)
        await db.flush()

    # Check if a published version already exists
    rv_result = await db.execute(
        select(RuleVersion).where(
            RuleVersion.rule_id == rule.id,
            RuleVersion.status == "published",
        )
    )
    existing_rv = rv_result.scalars().first()
    if existing_rv:
        print(f"  [skip] Published matching rule version already exists")
        return existing_rv

    config = {
        "amount_tolerance_pct": 0.02,
        "amount_tolerance_abs": 50.00,
        "qty_tolerance_pct": 0.00,
        "auto_approve_threshold": 5000.00,
        "auto_approve_requires_match": True,
    }

    rv = RuleVersion(
        rule_id=rule.id,
        version_number=1,
        status="published",
        config_json=json.dumps(config),
        change_summary="Initial default matching tolerance rule",
        created_by=created_by_id,
        published_at=datetime.now(timezone.utc),
    )
    db.add(rv)
    await db.flush()
    return rv


if __name__ == "__main__":
    asyncio.run(seed())
