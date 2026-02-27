# Goal: AI AP Manager — P1 + P2 Feature Completion

## Context

All P0 features are complete and working. The system handles the full AP lifecycle:
invoice ingestion → OCR extraction → 2/3-way matching → exception handling →
single-approver workflow → KPI reporting → GL coding → fraud scoring.

This goal drives the next phase: multi-level approvals, bulk data imports, vendor
communications, compliance tracking, recurring invoice detection, enhanced fraud
signals, policy-driven rule extraction, and advanced analytics.

Working directory: `/home/alexshen/projects/ai-ap-manager`
Backend container: `docker exec ai-ap-manager-backend-1`
Frontend build check: `cd frontend && npm run build`

---

## Feature 1: Multi-Level Approval Matrix

### Backend
- `approval_matrix` table: `id, amount_min, amount_max, department, category, approver_role, step_order, is_active, created_at`
- Alembic migration: `docker exec ai-ap-manager-backend-1 alembic revision --autogenerate -m "add_approval_matrix"`
- SQLAlchemy model in `backend/app/models/approval_matrix.py`; export from `models/__init__.py`
- Approval chain engine in `backend/app/services/approval.py`:
  - `build_approval_chain(db, invoice) -> list[dict]` — query matrix rows matching invoice amount + department/category, sort by step_order, return ordered approver list
  - `auto_create_approval_task` updated: use `build_approval_chain` if matrix rows exist, else fall back to single APPROVER
  - Sequential chain: when Task N is approved → auto-create Task N+1 (if chain has N+1)
  - ApprovalTask needs `chain_step` and `chain_total` fields (add via migration if missing)
- `user_delegations` table: `id, delegator_id, delegate_id, valid_from, valid_until, is_active, created_at`
- Alembic migration for `user_delegations`
- When assigning any approval task: check for active delegation from assigned user → reassign to delegate
- `PUT /api/v1/users/{id}/delegation` — set/update delegation (APPROVER or ADMIN role required)
- `DELETE /api/v1/users/{id}/delegation` — remove delegation
- Approval escalation Celery beat task (daily at 8 AM UTC):
  - Find `approval_tasks` where `status=pending AND due_at < now()`
  - Reassign to first ADMIN user
  - Write audit log: `action="approval_escalated"`
  - Console mock email to new assignee
- CRUD endpoints for approval matrix (all ADMIN only):
  - `GET /api/v1/approval-matrix` — list all rules
  - `POST /api/v1/approval-matrix` — create rule
  - `PUT /api/v1/approval-matrix/{id}` — update rule
  - `DELETE /api/v1/approval-matrix/{id}` — soft delete (set is_active=False)
- Pydantic schemas: `ApprovalMatrixRuleIn`, `ApprovalMatrixRuleOut`, `ApprovalMatrixRuleUpdate`

### Frontend
- Admin Settings → Approval Matrix page (`/admin/approval-matrix`):
  - Table of rules: amount band (min–max) · department · category · approver_role · step_order · is_active
  - Add/edit row inline or via dialog
  - Delete (soft) with confirmation
  - Preview card: "Invoice of $8,000 in Procurement → Step 1: AP_ANALYST → Step 2: ADMIN"
- Invoice detail → Approvals tab: show full chain timeline (Step 1 ✓ → Step 2 pending → Step 3)
- Sidebar: add "Approval Matrix" under Admin section

---

## Feature 2: CSV Bulk Import

### Backend
- `POST /api/v1/import/pos` — upload CSV of Purchase Orders (ADMIN, AP_ANALYST)
  - Parse CSV with pandas or csv module; validate required columns: `po_number, vendor_name, total_amount, currency, issue_date`
  - Upsert by `po_number` (update if exists, create if not)
  - Return: `{created: N, updated: N, skipped: N, errors: [{row: N, field: str, message: str}]}`
  - If > 1000 rows → dispatch Celery task instead of inline processing
- `POST /api/v1/import/grns` — upload CSV of Goods Receipts (ADMIN, AP_ANALYST)
  - Required columns: `gr_number, po_number, received_date, total_received_value`
  - Link to existing PO by `po_number`; warn if PO not found (add to errors, don't fail)
  - Same upsert + return pattern
- `POST /api/v1/import/vendors` — upload CSV of vendor master data (ADMIN)
  - Required columns: `vendor_name, tax_id, payment_terms, currency`
  - Fuzzy dedup: if `tax_id` matches existing → update; if name similarity ≥ 90% → add to warnings
  - Use `difflib.SequenceMatcher` for name similarity
- Pydantic schemas for import results in `backend/app/schemas/imports.py`
- Register all import routes in router under prefix `/import`

### Frontend
- Import page (`/admin/import`):
  - Three tabs: POs · GRNs · Vendors
  - Each tab: drag-and-drop CSV upload zone
  - "Preview" button shows first 10 rows in a table
  - Column mapping dropdowns (auto-map by header name, allow manual override)
  - "Import" button → show spinner → results summary card (created/updated/skipped/errors)
  - "Download error report" button if errors > 0 (downloads CSV of errors)
- Sidebar: add "Import" under Admin section

---

## Feature 3: Enhanced Duplicate Invoice Detection

### Backend
- Add `normalized_amount_usd` column to `invoices` table (Decimal, nullable)
- Alembic migration
- FX conversion utility in `backend/app/services/fx.py`:
  - Simple hardcoded rates table (EUR=1.08, GBP=1.27, CAD=0.74, others=1.0)
  - `convert_to_usd(amount, currency) -> Decimal`
- Duplicate detection service `backend/app/services/duplicate_detection.py`:
  - `check_duplicate(db, invoice_id) -> list[DuplicateCandidate]`
  - Exact match: same `vendor_id` + `invoice_number` (excluding self) → `DUPLICATE_INVOICE` exception (HIGH severity)
  - Fuzzy match: same `vendor_id` + `normalized_amount_usd` within 2% + `invoice_date` within ±7 days → soft flag (MEDIUM severity, code `POTENTIAL_DUPLICATE`)
  - Return list of candidates with match_type and matched_invoice_id
- Wire into Celery pipeline in `backend/app/workers/tasks.py` AFTER extraction, BEFORE match:
  ```python
  from app.services.duplicate_detection import check_duplicate
  check_duplicate(db, invoice_id)
  ```
- Update fraud scoring to compute `normalized_amount_usd` when scoring

---

## Feature 4: Vendor Communications Hub

### Backend
- `vendor_messages` table: `id (UUID PK), invoice_id (FK), sender_id (UUID nullable FK users), sender_email (str), direction (enum: inbound/outbound), body (Text), is_internal (bool default True), attachments (JSON default []), created_at`
- Alembic migration
- SQLAlchemy model `VendorMessage` in `backend/app/models/vendor_message.py`
- `POST /api/v1/invoices/{id}/messages` — send message (AP_ANALYST+)
  - Body: `{body: str, is_internal: bool}`
  - If `is_internal=False`: mock email to vendor (print to console with reply token link)
  - Audit log: `action="vendor_message_sent"`, `details={direction, is_internal}`
- `GET /api/v1/invoices/{id}/messages` — list messages (AP_CLERK+), ordered by created_at
- `POST /api/v1/portal/invoices/{id}/reply` — vendor reply via magic link token (no auth required)
  - Query param: `?token=<vendor_reply_token>`
  - Validate token (HMAC, same pattern as approval tokens); if valid → create inbound VendorMessage
  - Body: `{body: str}`
- `unread_vendor_messages` count: add to `InvoiceListItem` schema in `schemas/invoice.py`
  - Compute as count of inbound messages after last outbound message from AP team
- Pydantic schemas: `VendorMessageCreate`, `VendorMessageOut`, `VendorReplyIn`

### Frontend
- Invoice detail: add **Communications** tab (7th tab, after Audit Log)
  - Message thread: chronological bubbles
  - Internal note = grey left bubble; vendor message = blue right bubble
  - Sender name/email + timestamp below each bubble
  - Compose box at bottom: textarea + "Internal" / "Vendor-facing" toggle + Send button
  - Send calls `POST /invoices/{id}/messages`
- Invoice list: orange dot badge on rows with `unread_vendor_messages > 0`
- Header: notification bell icon showing total unread vendor message count (query from `GET /invoices?has_unread=true`)

---

## Feature 5: Vendor Compliance Documents

### Backend
- `vendor_compliance_docs` table: `id (UUID PK), vendor_id (FK), doc_type (enum: W9/W8BEN/VAT/insurance/other), file_key (str — MinIO path), status (enum: active/expired/missing), expiry_date (date nullable), uploaded_by (UUID FK users), created_at, updated_at`
- Alembic migration
- SQLAlchemy model in `backend/app/models/vendor.py` (add to existing file or new file)
- `POST /api/v1/vendors/{id}/compliance-docs` — upload file (ADMIN, AP_ANALYST)
  - Accept multipart: `doc_type` field + file
  - Store in MinIO bucket `ap-documents` under key `compliance/{vendor_id}/{doc_type}/{filename}`
  - Create/update `VendorComplianceDoc` record
- `GET /api/v1/vendors/{id}/compliance-docs` — list docs with status
- Celery beat task (weekly, Monday 6 AM UTC): scan all compliance docs where `expiry_date < now()` → set `status=expired`
- Compliance check in approval service (`auto_create_approval_task`):
  - Query vendor's compliance docs for `doc_type IN (W9, W8BEN)`
  - If any are `missing` or `expired` → create `COMPLIANCE_MISSING` exception (MEDIUM severity)
  - Console mock email to AP_ANALYST

### Frontend
- Vendor detail page (`/admin/vendors/{id}`): Compliance Documents section
  - Cards per doc_type: W-9 · W-8BEN · VAT · Insurance
  - Status badge: green (active) · orange (expiring ≤30 days) · red (expired/missing)
  - Upload button per doc type → file picker → POST request
  - Expiry date displayed and editable
- Invoice detail header: yellow warning banner if vendor has any expired/missing compliance docs

---

## Feature 6: Recurring Invoice Detection

### Backend
- `recurring_invoice_patterns` table (check if already exists; if not, create):
  - `id, vendor_id, frequency_days (int), avg_amount (Decimal), tolerance_pct (float default 0.10), auto_fast_track (bool default False), last_detected_at, created_at, updated_at`
- Detection Celery task `detect_recurring_patterns(vendor_id=None)`:
  - For each vendor with ≥ 3 approved invoices in the last 12 months
  - Sort invoices by date; compute day intervals between consecutive invoices
  - Detect dominant interval: check if most intervals are within 20% of {7, 14, 30, 60, 90}
  - Compute avg_amount and std_dev from those invoices
  - Create or update `RecurringInvoicePattern` record
- Celery beat: run `detect_recurring_patterns` weekly (Sunday midnight)
- Tagging in Celery pipeline (after extraction, before match):
  - Check if vendor has active `RecurringInvoicePattern`
  - If invoice amount within `pattern.tolerance_pct` of `pattern.avg_amount` → set `invoice.is_recurring=True`, `invoice.recurring_pattern_id=...`
- Fast-track in approval service:
  - If `invoice.is_recurring=True` AND `pattern.auto_fast_track=True` → skip exception queue, immediately create ApprovalTask with `is_fast_track=True` flag
- `GET /api/v1/admin/recurring-patterns` — list all patterns (ADMIN, AP_ANALYST)
- `PATCH /api/v1/admin/recurring-patterns/{id}` — toggle `auto_fast_track`, update `tolerance_pct`
- `POST /api/v1/admin/recurring-patterns/detect` — manually trigger detection job

### Frontend
- Invoice list: "🔄 Recurring" badge on recurring invoices
- Invoice detail header: "🔄 Recurring invoice detected — 1-click approval available" banner if `is_recurring=True && auto_fast_track=True`
- Admin → Recurring Patterns page (`/admin/recurring-patterns`):
  - Table: vendor · frequency · avg amount · tolerance % · fast-track toggle · last detected
  - Toggle fast-track per pattern
  - "Run Detection" button

---

## Feature 7: Enhanced Fraud Signals

### Backend
- `vendor_bank_history` table: `id, vendor_id, bank_account_number (hashed), changed_at, changed_by`
- Alembic migration
- In `PATCH /api/v1/vendors/{id}` handler: if `bank_account` field changes → insert row to `vendor_bank_history`
- Fraud signal in `backend/app/services/fraud_scoring.py`:
  - **bank_account_changed** (+25): check `vendor_bank_history` for any change within last 30 days for this vendor
  - **ghost_vendor** (+30): check if any other active vendor shares the same `bank_account` hash
- `fraud_incidents` table: `id, invoice_id, score_at_flag, triggered_signals (JSON), reviewed_by (UUID nullable FK), outcome (enum: genuine/false_positive/pending default pending), notes (Text), created_at`
- Alembic migration
- Auto-create `FraudIncident` when fraud_score ≥ 40 (HIGH threshold) after scoring
- `GET /api/v1/fraud-incidents` — list incidents (ADMIN, AP_ANALYST); filter by outcome
- `PATCH /api/v1/fraud-incidents/{id}` — update outcome + notes (ADMIN, AP_ANALYST)
- Pydantic schemas: `FraudIncidentOut`, `FraudIncidentUpdate`

### Frontend
- Fraud Incidents page (`/admin/fraud`):
  - Table: invoice # · vendor · score · signals · status badge (open/reviewed) · outcome
  - Click row → slide-out with details: invoice link, all triggered signals with scores, notes textarea, outcome dropdown
  - "Mark Reviewed" button
- Dashboard KPI: add "Open Fraud Incidents" card (count of `outcome=pending`)

---

## Feature 8: Analytics — Process Mining & Anomaly Detection

### Backend
- `GET /api/v1/analytics/process-mining` — (AP_ANALYST+):
  - Query `audit_logs` for each invoice status transition (action LIKE 'invoice_%')
  - Compute median + p90 time in each status: pending_extraction → extracting → extracted → matching → matched/exception → approved
  - Return: `[{step: str, from_status: str, to_status: str, median_hours: float, p90_hours: float, invoice_count: int}]`
- `GET /api/v1/analytics/anomalies` — (AP_ANALYST+):
  - Compute exception_rate per vendor per 30-day window (last 6 months)
  - Z-score: `(window_rate - mean_rate) / std_rate` per vendor
  - Return anomalies where `abs(z_score) > 2.0`: `[{vendor_id, vendor_name, period, exception_rate, z_score, direction}]`
- Register under new router `backend/app/api/v1/analytics.py`, prefix `/analytics`

### Frontend
- Analytics page (`/analytics`):
  - Sidebar link (AP_ANALYST+)
  - Process mining funnel: horizontal bar chart (recharts) showing median hours per step; color = green (<24h), yellow (<72h), red (>72h)
  - Anomaly alerts section: list cards with vendor name, period, z-score badge, exception rate vs baseline
- Sidebar: add "Analytics" nav item (visible to AP_ANALYST+)

---

## Feature 9: Backend Unit Tests

Write pytest tests in `backend/tests/`. The test runner is: `docker exec ai-ap-manager-backend-1 python -m pytest tests/ -x -q`

- `tests/test_match_engine.py`:
  - `test_2way_price_variance`: invoice total 10% over PO total → PRICE_VARIANCE exception created
  - `test_2way_auto_approve`: invoice total within tolerance → status=matched, ApprovalTask created
  - `test_3way_grn_not_found`: no GoodsReceipt for PO → GRN_NOT_FOUND exception
  - `test_3way_qty_over_receipt`: invoice qty > GRN qty → QTY_OVER_RECEIPT exception
- `tests/test_fraud_scoring.py`:
  - `test_round_amount_signal`: amount 5000.00 → round_amount signal fires (+10)
  - `test_potential_duplicate_signal`: two invoices same vendor/amount/week → +30 on second
  - `test_score_thresholds`: score < 20 → LOW; 20–39 → MEDIUM; 40–59 → HIGH; ≥60 → CRITICAL
- `tests/test_approval_tokens.py`:
  - `test_create_and_verify_token`: create token, verify succeeds
  - `test_expired_token`: token with past expiry → verify returns False
  - `test_reuse_rejected`: token marked is_used=True → verify returns False
- `tests/test_kpi.py`:
  - `test_touchless_rate`: 3 approved invoices (2 without ApprovalTask, 1 with) → touchless_rate = 2/3
  - `test_exception_rate`: 10 invoices, 3 with exceptions → exception_rate = 0.30

Each test file must use a sqlite in-memory DB or mock the DB session. Use `pytest.fixture` for setup.

---

## Success Criteria

The loop declares CONVERGED only when ALL of the following are true:

1. `docker exec ai-ap-manager-backend-1 python -c "from app.main import app; print(len(app.routes))"` prints a number ≥ 55 (indicating all new routes registered)
2. `cd frontend && npm run build` exits 0 with no TypeScript errors
3. `docker exec ai-ap-manager-backend-1 alembic current` shows no pending migrations
4. `docker exec ai-ap-manager-backend-1 python -m pytest tests/ -x -q 2>&1 | tail -5` shows at least some tests passing (not "no tests ran")
5. All 9 features above have at least their backend models + API endpoints implemented and importable
6. Frontend has new pages: `/admin/approval-matrix`, `/admin/import`, `/admin/recurring-patterns`, `/admin/fraud`, `/analytics`

## Worker Notes

- Work from `/home/alexshen/projects/ai-ap-manager`
- Backend in Docker: `docker exec ai-ap-manager-backend-1 <cmd>`
- Alembic always run inside container: `docker exec ai-ap-manager-backend-1 alembic -c alembic.ini revision --autogenerate -m "..."` then `upgrade head`
- Commits: `committer "feat/fix/test: message" file1 file2` — NEVER `git add .`
- Each task must be independently committable
- After implementing backend, verify: `docker exec ai-ap-manager-backend-1 python -c "from app.api.v1.<module> import router; print('OK')"`
- Frontend TypeScript: run `cd frontend && npm run build` to catch type errors before committing

## Final Verification

Run on 2026-02-27:

```
$ docker exec ai-ap-manager-backend-1 python -c "from app.main import app; print('OK')"
OK

$ docker exec ai-ap-manager-backend-1 python -m pytest tests/ -x -q
.....................                                                    [100%]
=============================== warnings summary ===============================
../usr/local/lib/python3.11/site-packages/passlib/utils/__init__.py:854
  /usr/local/lib/python3.11/site-packages/passlib/utils/__init__.py:854: DeprecationWarning: 'crypt' is deprecated and slated for removal in Python 3.13
    from crypt import crypt as _crypt

-- Docs: https://docs.pytest.org/en/latest/how-to/capture-results.html
21 passed, 1 warning in 0.68s
```

✓ Backend imports cleanly
✓ All 21 tests pass
✓ System ready for review pass
