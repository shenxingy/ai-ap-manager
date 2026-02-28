# Goal: Product Completeness Sprint

## Context

All core features are implemented (88 routes, 22 frontend pages, 34 tests passing).
This sprint fills the remaining gaps to make the product demo-ready and functionally complete.

Working directory: `/home/alexshen/projects/ai-ap-manager`
Backend container: `docker exec ai-ap-manager-backend-1`
Frontend build check: `cd frontend && npm run build`
Tests: `docker exec ai-ap-manager-backend-1 python -m pytest tests/ -x -q`
Seed: `docker exec ai-ap-manager-backend-1 python scripts/seed.py`

---

## Gap 1: Comprehensive Seed Data (MOST IMPORTANT)

The DB currently has only 1 vendor + 2 POs + 1 GR and NO invoices.
Dashboard shows zeros. Nothing to demo.

### Target state after seed runs:

**Users** (5 roles):
- `admin@example.com` / `changeme123` — ADMIN
- `clerk@example.com` / `changeme123` — AP_CLERK
- `analyst@example.com` / `changeme123` — AP_ANALYST
- `approver@example.com` / `changeme123` — APPROVER
- `auditor@example.com` / `changeme123` — AUDITOR

**Vendors** (3):
- Acme Corp — industrial parts, NET30, USD, tax_id 12-3456789 (already exists)
- TechFlow Systems — IT equipment, NET45, USD, tax_id 98-7654321
- MetalWorks Ltd — steel/metals, NET60, USD, tax_id 55-1234567

**Purchase Orders** (6 total, 2 per vendor):
- PO-2026-001: Acme, $4,800 (already exists, 2 lines)
- PO-2026-002: Acme, $12,500 (already exists, 2 lines)
- PO-2026-003: TechFlow, $8,500 (2 lines: laptops + monitors)
- PO-2026-004: TechFlow, $3,200 (1 line: software licenses)
- PO-2026-005: MetalWorks, $6,750 (2 lines: steel sheets + bolts)
- PO-2026-006: MetalWorks, $15,000 (1 line: CNC machined parts)

**Goods Receipts** (4 total):
- GR-2026-001: for PO-2026-001, full receipt (already exists)
- GR-2026-002: for PO-2026-003, partial receipt (80% qty on line 1, 100% line 2)
- GR-2026-003: for PO-2026-005, full receipt
- GR-2026-004: for PO-2026-006, full receipt

**Invoices** (10, at various pipeline stages):

| # | Vendor | PO | Amount | Status | Notes |
|---|--------|----|---------|---------|----|
| INV-2026-001 | Acme | PO-001 | $4,800 | approved | Perfect 2-way match, approved |
| INV-2026-002 | Acme | PO-002 | $12,800 | exception | Amount over PO by $300 → PRICE_VARIANCE exception |
| INV-2026-003 | TechFlow | PO-003 | $8,500 | matched | 3-way match, pending approval |
| INV-2026-004 | TechFlow | PO-003 | $8,500 | exception | Duplicate of INV-003 → DUPLICATE_INVOICE exception |
| INV-2026-005 | MetalWorks | PO-005 | $6,750 | approved | Clean match, approved |
| INV-2026-006 | MetalWorks | PO-006 | $15,000 | matched | Pending approval, due in 2 days (approaching SLA) |
| INV-2026-007 | Acme | none | $2,100 | extracted | No PO, pending match, fraud_score=25 |
| INV-2026-008 | TechFlow | none | $45,000 | extracted | High fraud score (75), bank account mismatch signal |
| INV-2026-009 | MetalWorks | PO-005 | $6,900 | exception | Amount $150 over tolerance → PRICE_VARIANCE |
| INV-2026-010 | Acme | PO-002 | $12,500 | extracted | due_date = 5 days ago (OVERDUE) |

For each invoice:
- Set `storage_path = "seed/placeholder.pdf"`, `file_name = "invoice-{N}.pdf"`, `mime_type = "application/pdf"`
- Set `vendor_name_raw` to the vendor name
- Set `vendor_id` to the matched vendor
- Set `po_id` where matched
- Set realistic `invoice_date` (5-30 days ago), `due_date` (vendor.payment_terms days after invoice_date)
- Set `currency = "USD"`, `subtotal`, `tax_amount = subtotal*0.08`, `total_amount`
- Set `extraction_model = "claude-sonnet-4-6"`, `ocr_confidence = 0.94`
- INV-008: `fraud_score=75`, `fraud_triggered_signals=["bank_account_mismatch", "amount_spike"]`
- INV-002, INV-004, INV-009: create corresponding ExceptionRecord rows
- INV-001, INV-005: create ApprovalTask rows with status=approved + audit log entries
- INV-006: create ApprovalTask with status=pending
- INV-003: create ApprovalTask with status=pending

**Line items per invoice**: add 1-2 InvoiceLineItem rows matching PO lines where applicable.

**FraudIncident** (1):
- For INV-008: `score_at_flag=75`, `triggered_signals=["bank_account_mismatch","amount_spike"]`, `outcome="pending"`

**Important**: Seed must be **idempotent** — check by invoice_number before inserting, skip if exists.
Update `scripts/seed.py` in the local repo (not just the container). The container mounts the local `scripts/` folder.

---

## Gap 2: Recurring Invoice Detection — Add to Celery Beat

### Problem
The task `tasks.detect_recurring_patterns` exists in `backend/app/workers/tasks.py` but is NOT
in the beat schedule in `backend/app/workers/celery_app.py`. It never runs automatically.

### Fix
In `backend/app/workers/celery_app.py`, add to `celery_app.conf.beat_schedule`:

```python
"detect-recurring-patterns-weekly": {
    "task": "tasks.detect_recurring_patterns",
    "schedule": crontab(hour=2, minute=0, day_of_week="mon"),
},
```

---

## Gap 3: Compliance Expiry Check in Approval Flow

### Problem
`VendorComplianceDoc` has `expiry_date` and `status` fields, but the approval service
(`backend/app/services/approval.py`) never checks them. Expired docs don't affect approvals.

### Fix
In `backend/app/services/approval.py` → `create_approval_task()` function,
BEFORE creating the ApprovalTask, add:

```python
# Check vendor compliance docs
from app.models.vendor import VendorComplianceDoc
from app.models.exception_record import ExceptionRecord

expired_docs = db.execute(
    select(VendorComplianceDoc).where(
        VendorComplianceDoc.vendor_id == invoice.vendor_id,
        VendorComplianceDoc.status == "approved",
        VendorComplianceDoc.expiry_date < datetime.now(timezone.utc),
    )
).scalars().all()

if expired_docs:
    # Create a soft warning exception (don't block approval)
    exc = ExceptionRecord(
        invoice_id=invoice_id,
        exception_type="COMPLIANCE_DOC_EXPIRED",
        severity="HIGH",
        description=f"Vendor has {len(expired_docs)} expired compliance doc(s). Review before payment.",
        status="open",
    )
    db.add(exc)
    db.flush()
    audit_svc.log(db=db, action="exception.created", entity_type="exception",
                  entity_id=exc.id, after={"type": "COMPLIANCE_DOC_EXPIRED"})
```

---

## Success Criteria

1. `docker exec ai-ap-manager-backend-1 python scripts/seed.py` runs with no errors (idempotent)
2. After seed: `GET /api/v1/invoices` returns ≥ 10 invoices
3. After seed: `GET /api/v1/kpi/summary` returns non-zero numbers (total_invoices ≥ 10)
4. After seed: `GET /api/v1/exceptions` returns ≥ 3 exceptions
5. `backend/app/workers/celery_app.py` beat_schedule includes `detect-recurring-patterns-weekly`
6. `backend/app/services/approval.py` has compliance doc expiry check
7. `cd frontend && npm run build` exits 0
8. `docker exec ai-ap-manager-backend-1 python -m pytest tests/ -x -q` — all pass
9. `scripts/seed.py` in local repo matches container version (complete, 200+ lines)

## Worker Notes

- Work from `/home/alexshen/projects/ai-ap-manager`
- Backend in Docker: `docker exec ai-ap-manager-backend-1 <cmd>`
- Commits: `committer "feat/fix/chore: message" file1 file2` — NEVER `git add .`
- Seed script runs INSIDE container: `docker exec ai-ap-manager-backend-1 python scripts/seed.py`
- Verify seed ran: `docker exec ai-ap-manager-backend-1 python -c "from app.core.config import settings; from sqlalchemy import create_engine, text; e=create_engine(settings.DATABASE_URL_SYNC); print(e.connect().execute(text('SELECT COUNT(*) FROM invoices')).scalar())"`
- After modifying approval.py: test import with `docker exec ai-ap-manager-backend-1 python -c "from app.services.approval import create_approval_task; print('OK')"`
