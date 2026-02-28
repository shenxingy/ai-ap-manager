"""Seed script — creates initial users, vendors, POs, GRNs, invoices, and related data.

Idempotent: checks for existing records before inserting.
Run: docker exec ai-ap-manager-backend-1 python scripts/seed.py
"""
import asyncio
import json
import sys
import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal

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
from app.models.invoice import Invoice, InvoiceLineItem
from app.models.exception_record import ExceptionRecord
from app.models.approval import ApprovalTask
from app.models.fraud_incident import FraudIncident

NOW = datetime.now(timezone.utc)


# ─── Upsert helpers ───────────────────────────────────────────────────────────

async def _upsert_user(db: AsyncSession, email: str, name: str, role: str) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    if user:
        print(f"  [skip] User {email}")
        return user
    user = User(
        email=email, name=name,
        password_hash=get_password_hash("changeme123"),
        role=role, is_active=True,
    )
    db.add(user)
    await db.flush()
    print(f"  [new]  User {email} ({role})")
    return user


async def _upsert_vendor(db: AsyncSession, name: str, tax_id: str,
                          currency: str = "USD", payment_terms: int = 30,
                          email: str = "") -> Vendor:
    result = await db.execute(select(Vendor).where(Vendor.name == name))
    vendor = result.scalars().first()
    if vendor:
        print(f"  [skip] Vendor {name}")
        return vendor
    vendor = Vendor(
        name=name, tax_id=tax_id, currency=currency,
        payment_terms=payment_terms, email=email, is_active=True,
    )
    db.add(vendor)
    await db.flush()
    print(f"  [new]  Vendor {name}")
    return vendor


async def _upsert_po(db: AsyncSession, po_number: str, vendor_id,
                      total_amount: float, lines: list[dict],
                      issued_days_ago: int = 14) -> PurchaseOrder:
    result = await db.execute(select(PurchaseOrder).where(PurchaseOrder.po_number == po_number))
    po = result.scalars().first()
    if po:
        print(f"  [skip] PO {po_number}")
        return po
    po = PurchaseOrder(
        po_number=po_number, vendor_id=vendor_id, status="open", currency="USD",
        total_amount=total_amount,
        issued_at=NOW - timedelta(days=issued_days_ago),
        expires_at=NOW + timedelta(days=180),
    )
    db.add(po)
    await db.flush()
    for line in lines:
        db.add(POLineItem(
            po_id=po.id, line_number=line["line_number"],
            description=line["description"], quantity=line["quantity"],
            unit_price=line["unit_price"], unit=line.get("unit", "ea"),
            category=line.get("category", ""),
        ))
    await db.flush()
    print(f"  [new]  PO {po_number} (${total_amount:,.2f})")
    return po


async def _upsert_gr(db: AsyncSession, gr_number: str, po_id, vendor_id,
                      lines: list[dict], received_days_ago: int = 7) -> GoodsReceipt:
    result = await db.execute(select(GoodsReceipt).where(GoodsReceipt.gr_number == gr_number))
    gr = result.scalars().first()
    if gr:
        print(f"  [skip] GR {gr_number}")
        return gr
    gr = GoodsReceipt(
        gr_number=gr_number, po_id=po_id, vendor_id=vendor_id,
        received_at=NOW - timedelta(days=received_days_ago),
    )
    db.add(gr)
    await db.flush()
    for line in lines:
        db.add(GRLineItem(
            gr_id=gr.id, line_number=line["line_number"],
            description=line["description"], quantity=line["quantity"],
        ))
    await db.flush()
    print(f"  [new]  GR {gr_number}")
    return gr


async def _upsert_matching_rule(db: AsyncSession, created_by_id) -> RuleVersion:
    result = await db.execute(select(Rule).where(Rule.name == "default_matching_tolerance"))
    rule = result.scalars().first()
    if not rule:
        rule = Rule(
            name="default_matching_tolerance",
            description="Default 2-way match tolerance configuration",
            rule_type="matching_tolerance", is_active=True,
        )
        db.add(rule)
        await db.flush()
    rv_result = await db.execute(
        select(RuleVersion).where(
            RuleVersion.rule_id == rule.id,
            RuleVersion.status == "published",
        )
    )
    existing_rv = rv_result.scalars().first()
    if existing_rv:
        print(f"  [skip] Published matching rule")
        return existing_rv
    config = {
        "amount_tolerance_pct": 0.02, "amount_tolerance_abs": 50.00,
        "qty_tolerance_pct": 0.00, "auto_approve_threshold": 5000.00,
        "auto_approve_requires_match": True,
    }
    rv = RuleVersion(
        rule_id=rule.id, version_number=1, status="published",
        config_json=json.dumps(config),
        change_summary="Initial default matching tolerance rule",
        created_by=created_by_id, published_at=NOW,
    )
    db.add(rv)
    await db.flush()
    print(f"  [new]  Matching tolerance rule (published)")
    return rv


async def _upsert_invoice(
    db: AsyncSession, *, invoice_number: str, vendor: Vendor,
    po: PurchaseOrder | None = None, status: str,
    subtotal: float, tax_rate: float = 0.08,
    invoice_days_ago: int = 15, payment_terms: int = 30,
    fraud_score: int = 0, fraud_signals: list | None = None,
    line_items: list[dict] | None = None,
) -> Invoice | None:
    result = await db.execute(select(Invoice).where(Invoice.invoice_number == invoice_number))
    inv = result.scalars().first()
    if inv:
        print(f"  [skip] Invoice {invoice_number}")
        return inv
    tax_amount = round(subtotal * tax_rate, 2)
    total_amount = round(subtotal + tax_amount, 2)
    invoice_date = NOW - timedelta(days=invoice_days_ago)
    due_date = invoice_date + timedelta(days=payment_terms)
    inv = Invoice(
        invoice_number=invoice_number,
        vendor_id=vendor.id,
        po_id=po.id if po else None,
        status=status,
        storage_path=f"seed/{invoice_number}.pdf",
        file_name=f"{invoice_number}.pdf",
        mime_type="application/pdf",
        source="upload",
        currency="USD",
        subtotal=subtotal,
        tax_amount=tax_amount,
        total_amount=total_amount,
        invoice_date=invoice_date,
        due_date=due_date,
        vendor_name_raw=vendor.name,
        fraud_score=fraud_score,
        fraud_triggered_signals=fraud_signals or [],
        ocr_confidence=0.94,
        extraction_model="claude-sonnet-4-6",
        normalized_amount_usd=total_amount,
    )
    db.add(inv)
    await db.flush()
    if line_items:
        for li in line_items:
            db.add(InvoiceLineItem(
                invoice_id=inv.id,
                line_number=li["line_number"],
                description=li["description"],
                quantity=li.get("quantity", 1),
                unit_price=li.get("unit_price", li.get("line_total", 0)),
                unit=li.get("unit", "ea"),
                line_total=li.get("line_total", li.get("quantity", 1) * li.get("unit_price", 0)),
            ))
        await db.flush()
    print(f"  [new]  Invoice {invoice_number} ({status}, ${total_amount:,.2f})")
    return inv


async def _upsert_exception(
    db: AsyncSession, invoice: Invoice, exception_code: str,
    severity: str, description: str, status: str = "open",
) -> ExceptionRecord | None:
    result = await db.execute(
        select(ExceptionRecord).where(
            ExceptionRecord.invoice_id == invoice.id,
            ExceptionRecord.exception_code == exception_code,
        )
    )
    if result.scalars().first():
        return None
    exc = ExceptionRecord(
        invoice_id=invoice.id, exception_code=exception_code,
        severity=severity.lower(), description=description, status=status,
    )
    db.add(exc)
    await db.flush()
    print(f"  [new]  Exception {exception_code} for {invoice.invoice_number}")
    return exc


async def _upsert_approval_task(
    db: AsyncSession, invoice: Invoice, approver: User,
    status: str = "pending", notes: str | None = None,
) -> ApprovalTask | None:
    result = await db.execute(
        select(ApprovalTask).where(ApprovalTask.invoice_id == invoice.id)
    )
    if result.scalars().first():
        return None
    task = ApprovalTask(
        invoice_id=invoice.id, approver_id=approver.id,
        step_order=1, status=status, approval_required_count=1,
        notes=notes,
        decided_at=NOW - timedelta(days=1) if status in ("approved", "rejected") else None,
    )
    db.add(task)
    await db.flush()
    print(f"  [new]  ApprovalTask ({status}) for {invoice.invoice_number}")
    return task


async def _upsert_fraud_incident(
    db: AsyncSession, invoice: Invoice, score: int, signals: list,
) -> None:
    result = await db.execute(
        select(FraudIncident).where(FraudIncident.invoice_id == invoice.id)
    )
    if result.scalars().first():
        return
    db.add(FraudIncident(
        invoice_id=invoice.id, score_at_flag=score,
        triggered_signals=signals, outcome="pending",
    ))
    await db.flush()
    print(f"  [new]  FraudIncident (score={score}) for {invoice.invoice_number}")


# ─── Main ─────────────────────────────────────────────────────────────────────

async def seed():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async with SessionLocal() as db:
        print("\n── Users ──")
        admin    = await _upsert_user(db, "admin@example.com",    "Admin User",       "ADMIN")
        clerk    = await _upsert_user(db, "clerk@example.com",    "AP Clerk",         "AP_CLERK")
        analyst  = await _upsert_user(db, "analyst@example.com",  "AP Analyst",       "AP_ANALYST")
        approver = await _upsert_user(db, "approver@example.com", "Finance Approver", "APPROVER")
        auditor  = await _upsert_user(db, "auditor@example.com",  "Internal Auditor", "AUDITOR")
        await db.commit()

        print("\n── Vendors ──")
        acme      = await _upsert_vendor(db, "Acme Corp",        "12-3456789", payment_terms=30,
                                          email="ap@acmecorp.example.com")
        techflow  = await _upsert_vendor(db, "TechFlow Systems", "98-7654321", payment_terms=45,
                                          email="billing@techflow.example.com")
        metalwrks = await _upsert_vendor(db, "MetalWorks Ltd",   "55-1234567", payment_terms=60,
                                          email="invoices@metalworks.example.com")
        await db.commit()

        print("\n── Purchase Orders ──")
        po1 = await _upsert_po(db, "PO-2026-001", acme.id, 4800.00, [
            {"line_number": 1, "description": "Industrial Widgets A-100", "quantity": 100, "unit_price": 30.00, "unit": "pcs", "category": "parts"},
            {"line_number": 2, "description": "Steel Bolts Grade 8",      "quantity": 500, "unit_price":  6.00, "unit": "pcs", "category": "fasteners"},
        ])
        po2 = await _upsert_po(db, "PO-2026-002", acme.id, 12500.00, [
            {"line_number": 1, "description": "Hydraulic Pump HP-5000",      "quantity": 5, "unit_price": 2000.00, "unit": "ea", "category": "equipment"},
            {"line_number": 2, "description": "Maintenance Service Contract","quantity": 1, "unit_price": 2500.00, "unit": "ea", "category": "services"},
        ])
        po3 = await _upsert_po(db, "PO-2026-003", techflow.id, 8500.00, [
            {"line_number": 1, "description": "Business Laptops Dell XPS 15", "quantity": 5, "unit_price": 1200.00, "unit": "ea", "category": "IT"},
            {"line_number": 2, "description": "4K Monitors UltraSharp 27\"",  "quantity": 5, "unit_price":  500.00, "unit": "ea", "category": "IT"},
        ])
        po4 = await _upsert_po(db, "PO-2026-004", techflow.id, 3200.00, [
            {"line_number": 1, "description": "Adobe Creative Cloud Licenses", "quantity": 8, "unit_price": 400.00, "unit": "ea", "category": "software"},
        ])
        po5 = await _upsert_po(db, "PO-2026-005", metalwrks.id, 6750.00, [
            {"line_number": 1, "description": "Hot-Rolled Steel Sheets 4x8ft", "quantity": 50, "unit_price": 85.00, "unit": "sheet", "category": "raw_material"},
            {"line_number": 2, "description": "Hex Bolts M12x50mm (box 200)", "quantity": 25, "unit_price": 70.00, "unit": "box",   "category": "fasteners"},
        ])
        po6 = await _upsert_po(db, "PO-2026-006", metalwrks.id, 15000.00, [
            {"line_number": 1, "description": "CNC Machined Aluminum Parts Batch #4", "quantity": 200, "unit_price": 75.00, "unit": "pcs", "category": "parts"},
        ])
        await db.commit()

        print("\n── Goods Receipts ──")
        gr1 = await _upsert_gr(db, "GR-2026-001", po1.id, acme.id, [
            {"line_number": 1, "description": "Industrial Widgets A-100", "quantity": 100.0},
            {"line_number": 2, "description": "Steel Bolts Grade 8",      "quantity": 500.0},
        ])
        gr2 = await _upsert_gr(db, "GR-2026-002", po3.id, techflow.id, [
            {"line_number": 1, "description": "Business Laptops Dell XPS 15", "quantity": 4.0},   # partial (80%)
            {"line_number": 2, "description": "4K Monitors UltraSharp 27\"",  "quantity": 5.0},
        ], received_days_ago=5)
        gr3 = await _upsert_gr(db, "GR-2026-003", po5.id, metalwrks.id, [
            {"line_number": 1, "description": "Hot-Rolled Steel Sheets 4x8ft", "quantity": 50.0},
            {"line_number": 2, "description": "Hex Bolts M12x50mm",            "quantity": 25.0},
        ], received_days_ago=3)
        gr4 = await _upsert_gr(db, "GR-2026-004", po6.id, metalwrks.id, [
            {"line_number": 1, "description": "CNC Machined Aluminum Parts", "quantity": 200.0},
        ], received_days_ago=2)
        await db.commit()

        print("\n── Matching Rule ──")
        await _upsert_matching_rule(db, admin.id)
        await db.commit()

        print("\n── Invoices ──")
        # INV-001: clean 2-way match, approved
        inv1 = await _upsert_invoice(
            db, invoice_number="INV-2026-001", vendor=acme, po=po1, status="approved",
            subtotal=4444.44, invoice_days_ago=20,
            line_items=[
                {"line_number": 1, "description": "Industrial Widgets A-100", "quantity": 100, "unit_price": 30.00, "line_total": 3000.00},
                {"line_number": 2, "description": "Steel Bolts Grade 8",      "quantity": 500, "unit_price":  6.00, "line_total": 3000.00},
            ],
        )

        # INV-002: amount over PO by $300 → PRICE_VARIANCE exception
        inv2 = await _upsert_invoice(
            db, invoice_number="INV-2026-002", vendor=acme, po=po2, status="exception",
            subtotal=11851.85, invoice_days_ago=18,
            line_items=[
                {"line_number": 1, "description": "Hydraulic Pump HP-5000",       "quantity": 5, "unit_price": 2060.00, "line_total": 10300.00},
                {"line_number": 2, "description": "Maintenance Service Contract",  "quantity": 1, "unit_price": 2500.00, "line_total":  2500.00},
            ],
        )

        # INV-003: TechFlow PO-003, 3-way match, pending approval
        inv3 = await _upsert_invoice(
            db, invoice_number="INV-2026-003", vendor=techflow, po=po3, status="matched",
            subtotal=7870.37, invoice_days_ago=12, payment_terms=45,
            line_items=[
                {"line_number": 1, "description": "Business Laptops Dell XPS 15", "quantity": 5, "unit_price": 1200.00, "line_total": 6000.00},
                {"line_number": 2, "description": "4K Monitors UltraSharp 27\"",  "quantity": 5, "unit_price":  500.00, "line_total": 2500.00},
            ],
        )

        # INV-004: Duplicate of INV-003 → DUPLICATE_INVOICE exception
        inv4 = await _upsert_invoice(
            db, invoice_number="INV-2026-004", vendor=techflow, po=po3, status="exception",
            subtotal=7870.37, invoice_days_ago=10, payment_terms=45,
            line_items=[
                {"line_number": 1, "description": "Business Laptops Dell XPS 15", "quantity": 5, "unit_price": 1200.00, "line_total": 6000.00},
                {"line_number": 2, "description": "4K Monitors UltraSharp 27\"",  "quantity": 5, "unit_price":  500.00, "line_total": 2500.00},
            ],
        )

        # INV-005: MetalWorks clean match, approved
        inv5 = await _upsert_invoice(
            db, invoice_number="INV-2026-005", vendor=metalwrks, po=po5, status="approved",
            subtotal=6250.00, invoice_days_ago=25, payment_terms=60,
            line_items=[
                {"line_number": 1, "description": "Hot-Rolled Steel Sheets", "quantity": 50, "unit_price": 85.00, "line_total": 4250.00},
                {"line_number": 2, "description": "Hex Bolts M12x50mm",      "quantity": 25, "unit_price": 80.00, "line_total": 2000.00},
            ],
        )

        # INV-006: pending approval, due in 2 days (SLA approaching)
        inv6 = await _upsert_invoice(
            db, invoice_number="INV-2026-006", vendor=metalwrks, po=po6, status="matched",
            subtotal=13888.89, invoice_days_ago=58, payment_terms=60,
            line_items=[
                {"line_number": 1, "description": "CNC Machined Aluminum Parts", "quantity": 200, "unit_price": 75.00, "line_total": 15000.00},
            ],
        )

        # INV-007: no PO, extracted, low fraud
        inv7 = await _upsert_invoice(
            db, invoice_number="INV-2026-007", vendor=acme, po=None, status="extracted",
            subtotal=1944.44, invoice_days_ago=3, fraud_score=25,
            fraud_signals=["no_po_reference"],
            line_items=[
                {"line_number": 1, "description": "Miscellaneous Parts Order", "quantity": 1, "unit_price": 1944.44, "line_total": 1944.44},
            ],
        )

        # INV-008: high fraud score — bank account mismatch + amount spike
        inv8 = await _upsert_invoice(
            db, invoice_number="INV-2026-008", vendor=techflow, po=None, status="extracted",
            subtotal=41666.67, invoice_days_ago=2, payment_terms=45,
            fraud_score=75, fraud_signals=["bank_account_mismatch", "amount_spike"],
            line_items=[
                {"line_number": 1, "description": "Enterprise Server Rack", "quantity": 2, "unit_price": 20833.33, "line_total": 41666.66},
            ],
        )

        # INV-009: MetalWorks, amount $150 over tolerance → PRICE_VARIANCE
        inv9 = await _upsert_invoice(
            db, invoice_number="INV-2026-009", vendor=metalwrks, po=po5, status="exception",
            subtotal=6388.89, invoice_days_ago=8, payment_terms=60,
            line_items=[
                {"line_number": 1, "description": "Hot-Rolled Steel Sheets", "quantity": 50, "unit_price": 87.00, "line_total": 4350.00},
                {"line_number": 2, "description": "Hex Bolts M12x50mm",      "quantity": 25, "unit_price": 82.00, "line_total": 2050.00},
            ],
        )

        # INV-010: Acme, extracted, OVERDUE (due 5 days ago)
        inv10 = await _upsert_invoice(
            db, invoice_number="INV-2026-010", vendor=acme, po=po2, status="extracted",
            subtotal=11574.07, invoice_days_ago=35, payment_terms=30,
            line_items=[
                {"line_number": 1, "description": "Hydraulic Pump HP-5000",      "quantity": 5, "unit_price": 2000.00, "line_total": 10000.00},
                {"line_number": 2, "description": "Maintenance Service Contract", "quantity": 1, "unit_price": 2500.00, "line_total":  2500.00},
            ],
        )
        await db.commit()

        print("\n── Exceptions ──")
        if inv2:
            await _upsert_exception(db, inv2, "PRICE_VARIANCE", "HIGH",
                "Invoice amount $12,800 exceeds PO-2026-002 approved amount $12,500 by $300 (2.4% — over 2% tolerance).")
        if inv4:
            await _upsert_exception(db, inv4, "DUPLICATE_INVOICE", "HIGH",
                "Invoice matches INV-2026-003 (same vendor, same amount, same PO within 7 days). Possible duplicate submission.")
        if inv9:
            await _upsert_exception(db, inv9, "PRICE_VARIANCE", "MEDIUM",
                "Invoice amount $6,900 exceeds PO-2026-005 approved amount $6,750 by $150 (2.2% — over 2% tolerance).")
        await db.commit()

        print("\n── Approval Tasks ──")
        if inv1:
            await _upsert_approval_task(db, inv1, approver, status="approved",
                notes="Clean match, standard approval.")
        if inv3:
            await _upsert_approval_task(db, inv3, approver, status="pending")
        if inv5:
            await _upsert_approval_task(db, inv5, approver, status="approved",
                notes="Matched GR-2026-003, approved.")
        if inv6:
            await _upsert_approval_task(db, inv6, approver, status="pending")
        await db.commit()

        print("\n── Fraud Incidents ──")
        if inv8:
            await _upsert_fraud_incident(db, inv8, score=75,
                signals=["bank_account_mismatch", "amount_spike"])
        await db.commit()

    await engine.dispose()
    print("\n✓ Seed complete.")
    print("  admin@example.com     / changeme123  (ADMIN)")
    print("  clerk@example.com     / changeme123  (AP_CLERK)")
    print("  analyst@example.com   / changeme123  (AP_ANALYST)")
    print("  approver@example.com  / changeme123  (APPROVER)")
    print("  auditor@example.com   / changeme123  (AUDITOR)")
    print("  Vendors: Acme Corp · TechFlow Systems · MetalWorks Ltd")
    print("  POs: PO-2026-001 through PO-2026-006")
    print("  GRs: GR-2026-001 through GR-2026-004")
    print("  Invoices: INV-2026-001 through INV-2026-010 (various states)")


if __name__ == "__main__":
    asyncio.run(seed())
