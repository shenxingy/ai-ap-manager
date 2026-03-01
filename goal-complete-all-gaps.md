# Goal: Complete All Remaining Gaps — AI AP Operations Manager

## Context

Working directory: `/home/alexshen/projects/ai-ap-manager`
Backend: FastAPI + SQLAlchemy async, runs in `docker exec ai-ap-manager-backend-1`
Frontend: Next.js 14 App Router in `frontend/`
Commits: `committer "type: msg" file1 file2` — NEVER `git add .`
Migrations: run inside container via `docker exec ai-ap-manager-backend-1 alembic upgrade head`
Always get the current alembic head before writing a migration: `docker exec ai-ap-manager-backend-1 alembic history | head -3`

Verify:
- Backend: `docker exec ai-ap-manager-backend-1 python -c "from app.main import app; print('OK')"`
- Tests: `docker exec ai-ap-manager-backend-1 python -m pytest tests/ -x -q`
- Frontend: `cd frontend && npm run build`

## Implementation Order (dependency-safe)

Dependencies must be implemented in order:
1. Phase 0 (drift fix) → independent, do first
2. Phase 1 (email IMAP) → needs new model columns + settings
3. Phase 2 (FX, vendor risk, GDPR) → models first, then celery tasks
4. Phase 3 (ERP, benchmarks, 4-way match, GL ML, Slack) → independent of each other
5. Phase 4 (entities → templates) → entities table must exist before templates FK
6. Phase 5 (PWA) → independent frontend change
7. Phase 6 (permission audit + tests) → after all features exist

---

## Gap 0: Fix TODO.md Drift

5 items in TODO.md are marked `[ ]` but the code is already done. Find and change them to `[x]`:
- Import page `/admin/import`
- Email ingestion status in settings UI
- Recurring pattern detection beat task sub-items
- Ask AI sidebar panel
- Cash flow forecast API + dashboard chart

Commit: `committer "chore: fix 5 TODO.md drift items" TODO.md`

---

## GAP-1: Real IMAP Email Ingestion

**What's needed:**
1. Add to `backend/app/core/config.py`: `IMAP_HOST`, `IMAP_PORT=993`, `IMAP_USER`, `IMAP_PASSWORD`, `IMAP_MAILBOX="INBOX"`
2. Alembic migration: add `email_from String(255)`, `email_subject String(500)`, `email_received_at DateTime(tz=True)` columns to `invoices` table
3. Add those 3 fields to `backend/app/models/invoice.py`
4. Replace file-drop polling in `backend/app/workers/email_ingestion.py` with `imaplib.IMAP4_SSL` — connect, fetch UNSEEN messages, extract PDF/image attachments, queue `process_invoice` Celery task, mark email as read (`\Seen`). If `IMAP_HOST` is empty, return `{"status": "skipped"}`
5. Add IMAP vars to `.env.example`

**Success:** `docker exec ai-ap-manager-backend-1 python -c "from app.workers.email_ingestion import poll_ap_mailbox; r=poll_ap_mailbox(); assert r['status'] in ('ok','skipped'); print('OK')"`

---

## GAP-3: Multi-Currency FX Support

**What's needed:**
1. Create `backend/app/models/fx_rate.py`: model `FxRate` with fields `id(int PK)`, `base_currency(str3)`, `quote_currency(str3)`, `rate(float)`, `valid_date(Date)`, `source(str20)`, `fetched_at(DateTime tz)`. Unique constraint on `(base_currency, quote_currency, valid_date)`. Register in `backend/app/db/base.py`
2. Alembic migration: create `fx_rates` table + add `normalized_amount_usd Float nullable` to `invoices`
3. Add `normalized_amount_usd` to `backend/app/models/invoice.py`
4. Add to config: `BASE_CURRENCY="USD"`, `FX_RATES_SOURCE="ecb"`
5. Create `backend/app/workers/fx_tasks.py`: Celery task `fetch_fx_rates` — fetch ECB XML from `https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml`, parse currency rates, upsert into `fx_rates` table as both EUR-based and USD-based rates using raw SQL `INSERT ... ON CONFLICT DO UPDATE`
6. Register beat task in `celery_app.py`: daily at 6 AM

**Success:** `docker exec ai-ap-manager-backend-1 python -c "from app.models.fx_rate import FxRate; from app.workers.fx_tasks import fetch_fx_rates; print('OK')"`

---

## GAP-11: Vendor Risk Scoring

**What's needed:**
1. Create `backend/app/models/vendor_risk.py`: model `VendorRiskScore` with fields `id(int PK)`, `vendor_id(UUID FK vendors)`, `ocr_error_rate(float)`, `exception_rate(float)`, `avg_extraction_confidence(float)`, `score(float 0-1)`, `risk_level(str10 LOW/MEDIUM/HIGH/CRITICAL)`, `computed_at(DateTime tz)`. Register in base.py
2. Alembic migration: create `vendor_risk_scores` table
3. Create `backend/app/workers/vendor_risk_tasks.py`: Celery task `compute_vendor_risk_scores` — for each vendor with invoices, compute exception_rate and avg_confidence from DB, derive risk score (exception_rate×0.6 + ocr_error_rate×0.4), assign risk_level, upsert into vendor_risk_scores. For HIGH/CRITICAL vendors, create a `VENDOR_RISK` exception on their latest open invoice if not already present
4. Register beat task: weekly Sunday 2 AM

**Success:** `docker exec ai-ap-manager-backend-1 python -c "from app.models.vendor_risk import VendorRiskScore; from app.workers.vendor_risk_tasks import compute_vendor_risk_scores; print('OK')"`

---

## GAP-10: GDPR Data Retention

**What's needed:**
1. Add to config: `RETENTION_DAYS_INVOICES=2555`, `RETENTION_DAYS_AUDIT_LOGS=365`, `RETENTION_ENABLED=False`
2. Create `backend/app/workers/retention_tasks.py`: Celery task `run_data_retention` — if `RETENTION_ENABLED=False` return skipped. Otherwise soft-delete invoices older than retention days (set `deleted_at=now`) with status in (approved/paid/rejected), hard-delete old audit logs. Write a system audit log entry recording what was deleted
3. Register beat task: monthly on 1st at 3 AM
4. Add vars to `.env.example`

**Success:** `docker exec ai-ap-manager-backend-1 python -c "from app.workers.retention_tasks import run_data_retention; r=run_data_retention(); assert r['status']=='skipped'; print('OK')"`

---

## GAP-2: ERP CSV Connectors

**What's needed:**
1. Create `backend/app/integrations/__init__.py` (empty)
2. Create `backend/app/integrations/sap_csv.py`: parse SAP PO export CSV (semicolon-delimited, required cols: PO_NUMBER, VENDOR_CODE, VENDOR_NAME, LINE_NUMBER, DESCRIPTION, QUANTITY, UNIT_PRICE, CURRENCY). Return `(list[SapPoLine], list[str errors])`. Function `upsert_sap_pos(lines, db)` upserts into `purchase_orders` + `po_line_items` using raw SQL
3. Create `backend/app/integrations/oracle_csv.py`: parse Oracle Fusion GRN CSV (comma-delimited, required cols: RECEIPT_NUMBER, PO_NUMBER, LINE_NUMBER, ITEM_DESCRIPTION, QUANTITY_RECEIVED, RECEIVED_DATE). Upsert into `goods_receipts` + `gr_line_items`
4. Create `backend/app/api/v1/erp.py`: `POST /admin/erp/sync/sap-pos` and `POST /admin/erp/sync/oracle-grns` — accept CSV file upload, parse, upsert, return `{created, updated, skipped, errors}`. Both require `ADMIN` role
5. Register erp router in `backend/app/api/v1/router.py`
6. Create `frontend/src/app/(app)/admin/erp/page.tsx`: two-tab upload UI (SAP POs tab, Oracle GRNs tab), each with a file input and upload button, results shown as JSON

**Success:** `docker exec ai-ap-manager-backend-1 python -c "from app.integrations.sap_csv import parse_sap_pos; from app.api.v1.erp import router; print('OK')"`

---

## GAP-5: KPI Benchmark Comparison

**What's needed:**
1. Add to `backend/app/api/v1/kpi.py`: `GET /kpi/benchmarks` endpoint — returns hardcoded industry benchmarks: touchless_rate (industry 75%, SMB 55%), exception_rate (industry 8%, SMB 15%), avg_cycle_time_days (industry 3, SMB 7), gl_coding_accuracy (industry 90%, SMB 75%). Requires `get_current_user` auth
2. Add benchmark comparison card to `frontend/src/app/(app)/dashboard/page.tsx`: useQuery for `/kpi/benchmarks`, display 4 metrics in a card below KPI cards showing industry avg and SMB avg

**Success:** `docker exec ai-ap-manager-backend-1 python -c "import ast; src=open('app/api/v1/kpi.py').read(); assert 'benchmarks' in src; print('OK')"`

---

## GAP-6: 4-Way Match (Quality Inspection)

**What's needed:**
1. Create `backend/app/models/inspection_report.py`: model `InspectionReport` with fields `id(UUID PK)`, `gr_id(UUID FK goods_receipts)`, `invoice_id(UUID FK invoices nullable)`, `inspector_id(UUID FK users nullable)`, `result(Enum pass/fail/partial)`, `notes(Text nullable)`, `inspected_at(DateTime tz)`, `created_at(DateTime tz)`. Register in base.py
2. Alembic migration: create `inspection_reports` table + `inspection_result_enum` PostgreSQL enum type
3. Add to `backend/app/api/v1/match.py`: `POST /gr/{gr_id}/inspection` endpoint — creates InspectionReport, if result=fail creates `INSPECTION_FAILED` exception record on related invoices. Requires ADMIN or AP_ANALYST role
4. Add `run_4way_match(db, invoice_id)` to `backend/app/rules/match_engine.py`: calls run_3way_match, then checks if GRN has inspection report — returns match_4way_status as "pending_inspection", "inspection_passed", or "inspection_failed"

**Success:** `docker exec ai-ap-manager-backend-1 python -c "from app.models.inspection_report import InspectionReport; from app.rules.match_engine import run_4way_match; print('OK')"`

---

## GAP-7: GL Coding ML Classifier

**What's needed:**
1. Add to `backend/requirements.txt`: `scikit-learn==1.4.2`, `joblib==1.3.2`. Install in container
2. Create `backend/app/services/gl_classifier.py` with:
   - `train_model(db)` → trains TF-IDF + LogisticRegression on confirmed GL assignments from `invoice_line_items` where `gl_account IS NOT NULL`. Returns `(pipeline, accuracy)`. Raises ValueError if < 20 training samples
   - `save_model_to_minio(model, version)` → serializes with joblib, uploads to MinIO as `models/gl-coding-v{N}.pkl`
   - `load_latest_model()` → downloads latest version from MinIO, caches in memory, returns `(model, version)` or `(None, None)`
   - `predict_gl_account(vendor_name, description, amount)` → returns `(account_code, confidence)` or `(None, 0.0)` if no model
3. Create `backend/app/workers/ml_tasks.py`: Celery task `retrain_gl_classifier` — calls train_model + save_model_to_minio, handles insufficient data gracefully
4. Register beat task: Saturday 4 AM
5. Update `backend/app/services/gl_coding.py`: call `predict_gl_account` first; if confidence >= 0.7, use ML result as primary suggestion (source="ml_classifier"), then append frequency-based suggestions as fallback

**Success:** `docker exec ai-ap-manager-backend-1 python -c "from app.services.gl_classifier import predict_gl_account; a,c = predict_gl_account('Test','supplies',100); print(f'GL: {a} conf={c}')"`

---

## GAP-8: Slack/Teams Webhook Notifications

**What's needed:**
1. Add to config: `SLACK_WEBHOOK_URL=""`, `TEAMS_WEBHOOK_URL=""` (empty = disabled)
2. Create `backend/app/services/notifications.py` with three functions:
   - `send_approval_request(invoice_number, vendor_name, amount, currency, approver_email, approve_url, reject_url)` — POST to Slack (text block) and Teams (MessageCard) if URLs configured
   - `send_approval_decision(invoice_number, decision, actor_email, notes)` — notify approval/rejection
   - `send_fraud_alert(invoice_number, vendor_name, fraud_score, risk_level, signals)` — only for HIGH/CRITICAL risk levels
   - All functions are no-ops if webhook URLs are empty. Use `urllib.request` (no extra deps)
3. Wire `send_approval_request` into `backend/app/services/approval.py` after creating approval task (wrap in try/except)
4. Wire `send_fraud_alert` into `backend/app/services/fraud_scoring.py` after creating FRAUD_FLAG exception (wrap in try/except)
5. Add to `.env.example`

**Success:** `docker exec ai-ap-manager-backend-1 python -c "from app.services.notifications import send_approval_request, send_fraud_alert; print('OK')"`

---

## GAP-9: Multi-Entity Support

**What's needed:**
1. Create `backend/app/models/entity.py`: model `Entity` with fields `id(UUID PK)`, `name(str200)`, `tax_id(str50 nullable)`, `base_currency(str3 default USD)`, `timezone(str50 default UTC)`, `contact_info(Text nullable)`, `created_at(DateTime tz)`, `deleted_at(DateTime tz nullable)`. Register in base.py
2. Alembic migration (non-destructive): create `entities` table + add nullable `entity_id UUID FK entities` to `invoices`, `purchase_orders`, `vendors`, `goods_receipts` tables
3. Add `entity_id` field to models: `invoice.py`, `vendor.py` (and optionally `purchase_order.py`, `goods_receipt.py`)
4. Create `backend/app/api/v1/entities.py`: `GET /entities` (all authenticated users) and `POST /entities` (ADMIN only) with Pydantic schemas EntityOut and EntityCreate
5. Register entities router in `router.py`

**Success:** `docker exec ai-ap-manager-backend-1 python -c "from app.models.entity import Entity; from app.api.v1.entities import router; print([r.path for r in router.routes])"`

---

## GAP-12: Invoice Template System

**What's needed:**
1. Create `backend/app/models/invoice_template.py`: model `InvoiceTemplate` with fields `id(UUID PK)`, `vendor_id(UUID FK vendors)`, `name(str200)`, `default_po_id(UUID FK purchase_orders nullable)`, `line_items(JSON nullable)`, `notes(Text nullable)`, `created_by(UUID FK users nullable)`, `created_at(DateTime tz)`, `deleted_at(DateTime tz nullable)`. Register in base.py
2. Alembic migration: create `invoice_templates` table (down_revision must be the entities migration above)
3. Create `backend/app/api/v1/invoice_templates.py`: CRUD endpoints under `/admin/invoice-templates` — `GET` list (ADMIN/AP_ANALYST), `POST` create (ADMIN/AP_ANALYST), `GET /{id}` detail, `DELETE /{id}` soft-delete (ADMIN)
4. Add `GET /portal/templates` to `backend/app/api/v1/portal.py` — returns templates for the authenticated vendor (using existing portal JWT auth)
5. Register templates router in `router.py`
6. Create `frontend/src/app/(app)/admin/invoice-templates/page.tsx`: simple table listing templates with name, vendor_id, created_at columns

**Success:** `docker exec ai-ap-manager-backend-1 python -c "from app.models.invoice_template import InvoiceTemplate; from app.api.v1.invoice_templates import router; print('OK')"`

---

## GAP-4: Mobile PWA Support

**What's needed:**
1. Create `frontend/public/manifest.json`: PWA manifest with `name="AI AP Manager"`, `short_name="AP Manager"`, `display="standalone"`, `theme_color="#1e40af"`, icons array (192px and 512px placeholder entries)
2. Add manifest link to `frontend/src/app/layout.tsx` metadata or head
3. Update `frontend/src/app/(app)/approvals/page.tsx`: wrap existing table in `<div className="hidden sm:block">`. Add mobile card view `<div className="block sm:hidden space-y-3">` where each pending approval is a card with invoice number, vendor, amount, due date, and Approve/Reject buttons

**Success:** `ls frontend/public/manifest.json && cd frontend && npm run build`

---

## NEAR-2: Permission Audit

Read every file in `backend/app/api/v1/`. For each endpoint (`@router.get/post/patch/delete`):
- Must have `Depends(get_current_user)` or `Depends(require_role(...))`, OR be explicitly public
- Intentionally public: `POST /auth/token`, `GET /approvals/email?token=...` (HMAC token), portal vendor endpoints (JWT token)
- Fix any missing auth guards
- Add a comment block at top of `portal.py` documenting which endpoints are intentionally public and why

---

## NEAR-4: Test Coverage

Create `backend/tests/test_new_features.py` with tests for:
- `parse_sap_pos` with missing columns → returns errors, no lines
- `parse_sap_pos` with valid CSV → parses correctly
- `parse_oracle_grns` with valid CSV → parses correctly
- `GET /kpi/benchmarks` with auth → 200 with benchmarks dict
- `POST /admin/erp/sync/sap-pos` with analyst token → 403
- `InspectionResult` enum values (pass/fail/partial)
- `run_4way_match` is callable
- `predict_gl_account` returns (None, 0.0) when no model trained
- `Entity` model has correct tablename
- `GET /entities` without auth → 401
- IMAP polling returns skipped when IMAP_HOST not configured

---

## Final Verification

```bash
docker exec ai-ap-manager-backend-1 python -c "
from app.main import app
from app.models.fx_rate import FxRate
from app.models.vendor_risk import VendorRiskScore
from app.models.inspection_report import InspectionReport
from app.models.entity import Entity
from app.models.invoice_template import InvoiceTemplate
from app.integrations.sap_csv import parse_sap_pos
from app.integrations.oracle_csv import parse_oracle_grns
from app.services.gl_classifier import predict_gl_account
from app.services.notifications import send_fraud_alert
from app.workers.fx_tasks import fetch_fx_rates
from app.workers.vendor_risk_tasks import compute_vendor_risk_scores
from app.workers.retention_tasks import run_data_retention
from app.workers.ml_tasks import retrain_gl_classifier
print('All imports OK')
"

docker exec ai-ap-manager-backend-1 python -c "
from app.workers.celery_app import celery_app
tasks = list(celery_app.conf.beat_schedule.keys())
assert any('fx-rates' in t for t in tasks), 'Missing FX task'
assert any('vendor-risk' in t for t in tasks), 'Missing vendor risk task'
assert any('retention' in t for t in tasks), 'Missing retention task'
assert any('gl-classifier' in t for t in tasks), 'Missing GL retrain task'
print('Beat tasks OK:', tasks)
"

docker exec ai-ap-manager-backend-1 python -m pytest tests/ -x -q 2>&1 | tail -10
cd frontend && npm run build
```

---

## STATUS

- [ ] Gap 0: Fix TODO.md drift (5 items)
- [x] GAP-1: Email IMAP ingestion
- [ ] GAP-3: Multi-currency FX support
- [x] GAP-11: Vendor risk scoring
- [x] GAP-10: GDPR data retention
- [ ] GAP-2: ERP CSV connectors (SAP + Oracle)
- [x] GAP-5: KPI benchmark comparison
- [ ] GAP-6: 4-way match (inspection reports)
- [x] GAP-7: GL coding ML classifier
- [x] GAP-8: Slack/Teams webhook notifications
- [ ] GAP-9: Multi-entity support
- [ ] GAP-12: Invoice template system
- [ ] GAP-4: Mobile PWA + responsive approvals
- [x] NEAR-2: Permission audit
- [ ] NEAR-4: Test coverage expansion

STATUS: NOT CONVERGED
