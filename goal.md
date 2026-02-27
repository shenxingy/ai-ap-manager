# Goal: AI AP Manager — V1 Feature Completion (P1 Remaining)

## Context

All P0 features and the first wave of P1/P2 features are complete. The system now has:
9-feature set (approval matrix, CSV import, duplicate detection, vendor comms, compliance docs,
recurring patterns, fraud incidents, analytics, backend tests), all passing build + tests.

This goal drives the **remaining P1 features** needed for V1 (production-ready):
email ingestion, policy-to-rule LLM pipeline, RBAC enforcement, vendor CRUD, SLA alerts,
bulk operations, vendor portal auth, override logging + rule recommendations.

Working directory: `/home/alexshen/projects/ai-ap-manager`
Backend container: `docker exec ai-ap-manager-backend-1`
Frontend build check: `cd frontend && npm run build`
Tests: `docker exec ai-ap-manager-backend-1 python -m pytest tests/ -x -q`

---

## Feature 1: Email Ingestion Pipeline

### Backend
- Mock IMAP poller Celery task `backend/app/workers/email_ingestion.py`:
  - Function `poll_ap_mailbox()` — reads `EMAIL_HOST`, `EMAIL_USER`, `EMAIL_PASSWORD` from env (mock: just log "polling mailbox" if not configured)
  - Simulated: process any `.eml` files placed in `backend/data/inbox/` directory
  - Extract PDF/PNG/JPG attachments from email body
  - For each attachment: create Invoice record with `source="email"`, `source_email=from_address`, then enqueue `process_invoice` Celery task
  - Write audit log: `action="invoice_ingested_from_email"`, `details={filename, from_address}`
- Add `source` column to `invoices` table: enum `upload|email`, default `upload`
- Add `source_email` column (varchar, nullable)
- Alembic migration
- Celery beat: run `poll_ap_mailbox` every 5 minutes
- `GET /api/v1/admin/email-ingestion/status` — returns `{last_polled_at, total_ingested, configured: bool}` (ADMIN)

### Frontend
- Invoice list: show `source` badge — grey "Upload" or blue "Email" pill next to invoice number
- Admin → Settings page (`/admin/settings`):
  - Email ingestion status card: last poll time, total ingested, configured indicator
  - "Trigger Poll" button → `POST /api/v1/admin/email-ingestion/trigger`

---

## Feature 2: Policy PDF → LLM Rule Extraction

### Backend
- `POST /api/v1/rules/upload-policy` — ADMIN only, multipart file upload (PDF, DOC, TXT)
  - Store file in MinIO: `policies/{rule_id}/{filename}`
  - Create `Rule` record with `status=draft`, `source=policy_upload`
  - Enqueue Celery task `extract_rules_from_policy(rule_id, file_key)`
- Celery task `extract_rules_from_policy`:
  - Load file from MinIO; if PDF extract text with `pdfminer.six` (or fallback: read raw bytes as text)
  - Call Claude claude-sonnet-4-6 via Anthropic SDK:
    ```
    system: "You are an AP policy parser. Extract matching tolerance rules as JSON."
    user: "<policy text>"
    ```
  - Expected JSON response: `{tolerance_pct: float, max_line_variance: float, auto_approve_threshold: float, notes: str}`
  - Log to `ai_call_logs`: prompt, response, token_count, latency_ms
  - Update `Rule` record: `config=<extracted JSON>`, `status=in_review`, `ai_extracted=True`
  - Write audit log: `action="policy_parsed_by_ai"`, `details={rule_id, token_count}`
- Human review endpoints (ADMIN only):
  - `GET /api/v1/rules` — list all rules with status
  - `GET /api/v1/rules/{id}` — rule detail with `config` JSON
  - `PATCH /api/v1/rules/{id}` — update config fields (human edits AI suggestion)
  - `POST /api/v1/rules/{id}/publish` — set `status=published`; previous published rule → `status=superseded`
  - `POST /api/v1/rules/{id}/reject` — set `status=rejected`
- Shadow mode flag on Rule: `is_shadow_mode (bool default False)` — when True, rule runs alongside active rule but doesn't affect decisions; results logged for comparison

### Frontend
- Admin → Rules page (`/admin/rules`):
  - Upload zone: drag-and-drop PDF/DOC → triggers upload
  - Rule table: version · status badge · source (manual/policy_upload) · created_at · actions
  - Click rule → detail side-panel showing extracted `config` JSON as editable form fields
  - "Approve & Publish" button → `POST /rules/{id}/publish`
  - "Reject" button → `POST /rules/{id}/reject`
  - Processing indicator: spinner on rules with `status=draft` (AI extraction in progress)

---

## Feature 3: Full RBAC Enforcement

### Backend
- Audit every router file for missing `require_role()` or `get_current_user` on mutating endpoints
- Specifically verify and fix:
  - `vendors.py`: all write endpoints have `require_role(["ADMIN", "AP_ANALYST"])`
  - `import_routes.py`: all endpoints have auth
  - `analytics.py`: `require_role(["AP_ANALYST", "ADMIN"])`
  - `portal.py`: vendor reply endpoint has `validate_vendor_token` (not user auth)
  - `approval_matrix.py`: all write endpoints are ADMIN-only
  - `fraud_incidents.py`: PATCH outcome requires ADMIN or AP_ANALYST
  - `recurring_patterns.py`: PATCH requires ADMIN or AP_ANALYST
- `DELETE /api/v1/admin/users/{id}` — soft delete (set `deleted_at`), ADMIN only
- Add `deleted_at` to User model if not present; filter deleted users from all queries
- Per-role route guards in frontend (see Frontend section)

### Frontend
- Unauthorized page: `frontend/src/app/(app)/unauthorized/page.tsx` — simple 403 message with "Go to Dashboard" link
- Per-role navigation: hide menu items based on `user.role` from auth store:
  - Admin menu items (Users, Approval Matrix, Rules, Import, Email Settings) → only ADMIN
  - Analytics → only AP_ANALYST+
  - Exceptions → AP_CLERK+
  - Fraud → ADMIN, AP_ANALYST
- Redirect unauthorized page access to `/unauthorized` (check role in page component)

---

## Feature 4: Vendor CRUD Completion

### Backend
- Complete `vendors.py` router:
  - `GET /api/v1/vendors` — paginated list, filters: `name` (partial match), `is_active` (bool)
    Returns: `{items: [{id, vendor_name, tax_id, payment_terms, currency, is_active, invoice_count, compliance_status}], total, page, page_size}`
  - `GET /api/v1/vendors/{id}` — detail with: vendor fields + aliases list + compliance docs list + recent invoice count
  - `POST /api/v1/vendors` — create (ADMIN, AP_ANALYST); validate: `tax_id` EIN format if currency=USD (`^\d{2}-\d{7}$`)
  - `PATCH /api/v1/vendors/{id}` — update fields (ADMIN, AP_ANALYST); if `bank_account` changes → insert `vendor_bank_history` row
  - `POST /api/v1/vendors/{id}/aliases` — add alias (ADMIN, AP_ANALYST)
  - `DELETE /api/v1/vendors/{id}/aliases/{alias_id}` — remove alias (ADMIN, AP_ANALYST)
- Pydantic schemas: `VendorCreate`, `VendorUpdate`, `VendorListItem`, `VendorDetail`

### Frontend
- Vendor list page `frontend/src/app/(app)/admin/vendors/page.tsx` — if not already complete:
  - Table: name · tax_id · currency · payment_terms · is_active badge · invoice_count
  - Search bar (filter by name)
  - "Add Vendor" button → inline dialog with form
  - Row click → `/admin/vendors/{id}`
- Ensure vendor detail page (`/admin/vendors/[id]`) shows:
  - Edit form for vendor fields
  - Aliases section (add/remove)
  - Compliance docs section (already built — verify it renders)

---

## Feature 5: SLA Alerts & Due Date Tracking

### Backend
- Add `due_date` column to `invoices` table (date, nullable) — Alembic migration
- When invoice is extracted, set `due_date = invoice_date + vendor.payment_terms days`
- `sla_alerts` table: `id, invoice_id FK, alert_type (enum: approaching/overdue), sent_at, created_at`
- Celery beat task `check_sla_alerts` (daily at 9 AM UTC):
  - Find invoices where `due_date <= today + 3 days` AND `status NOT IN (APPROVED, PAID)` AND no `approaching` alert sent
  - Create `sla_alerts` row, write audit log: `action="sla_alert_sent"`, mock email to AP_ANALYST
  - Find invoices where `due_date < today` AND `status NOT IN (APPROVED, PAID)` AND no `overdue` alert sent
  - Create `sla_alerts` row with `alert_type=overdue`, audit log
- `GET /api/v1/invoices?overdue=true` — filter invoices past due_date
- `GET /api/v1/kpi/sla-summary` — `{approaching_count: int, overdue_count: int}`

### Frontend
- Invoice list: "Overdue" red badge on rows where `due_date < today`
- Dashboard: add "⚠️ Overdue" card (count from kpi/sla-summary) next to other KPI cards
  - Red accent if count > 0; click links to `/invoices?overdue=true`

---

## Feature 6: Bulk Operations

### Backend
- `POST /api/v1/exceptions/bulk-update` — body: `{ids: [uuid], action: str, comment: str}` (AP_ANALYST+)
  - Actions: `assign` (requires `assigned_to: uuid`), `resolve` (requires `resolution: str`)
  - Update each exception record; write audit log per invoice
  - Return: `{updated: N, errors: [{id, reason}]}`
- `POST /api/v1/approvals/bulk-approve` — body: `{task_ids: [uuid], comment: str}` (APPROVER+)
  - Approve all tasks in list (same logic as single approve)
  - Return: `{approved: N, errors: [{id, reason}]}`

### Frontend
- Exception queue page: add checkbox column; "Select All" checkbox in header
  - Bulk action toolbar (appears when ≥1 selected): "Assign" dropdown + "Resolve" button
  - Calls `POST /exceptions/bulk-update`
- Approvals page: add checkbox column + "Approve Selected" button
  - Calls `POST /approvals/bulk-approve`

---

## Feature 7: Override Logging & Rule Recommendations

### Backend
- `override_logs` table: `id, invoice_id FK, rule_id FK nullable, field_name (str), old_value (JSON), new_value (JSON), overridden_by FK users, reason (text), created_at`
- When AP user manually overrides a match result or exception → insert `override_log` row
- Log override when: exception manually resolved, approval forced-through, match result manually changed
- Weekly Celery job `analyze_overrides` (Sunday midnight):
  - Find rules where `override_count_last_30d > 5`
  - For numeric tolerances: compute median override delta → recommend new threshold
  - Create `rule_recommendations` table row: `{rule_id, current_value, suggested_value, override_count, reasoning, status: pending}`
- `GET /api/v1/admin/rule-recommendations` — list pending recommendations (ADMIN)
- `POST /api/v1/admin/rule-recommendations/{id}/accept` — apply as new rule draft (ADMIN)
- `POST /api/v1/admin/rule-recommendations/{id}/reject` — dismiss (ADMIN)

### Frontend
- Admin → AI Insights page (`/admin/ai-insights`):
  - "Rule Recommendations" section: table of suggested tolerance changes
  - Each row: current value → suggested value, override count, "Accept" / "Reject" buttons
  - "Override History" section: last 30 overrides with reason + who did it

---

## Feature 8: Additional Tests

### Backend tests (add to `backend/tests/`):
- `tests/test_duplicate_detection.py`:
  - `test_exact_duplicate`: same vendor_id + invoice_number → returns DUPLICATE_INVOICE candidate
  - `test_fuzzy_duplicate`: same vendor, amount within 2%, date within 7 days → POTENTIAL_DUPLICATE
  - `test_no_duplicate`: different vendor → empty list
- `tests/test_sla_alerts.py` (if Feature 5 implemented):
  - `test_overdue_invoice_flagged`: invoice with due_date=yesterday → alert created
  - `test_upcoming_invoice_flagged`: due_date=tomorrow → approaching alert created
- `tests/test_vendor_crud.py`:
  - `test_create_vendor`: POST /vendors → 201 with vendor_id
  - `test_duplicate_tax_id`: POST with existing tax_id → 409
  - `test_patch_vendor`: PATCH /vendors/{id} → fields updated

---

## Success Criteria — ALL VERIFIED ✓ (2026-02-27)

All 7 criteria confirmed passing:

1. ✅ Route count: 83 routes (≥ 70 required)
2. ✅ Frontend build: exits 0, zero type errors (22 pages generated)
3. ✅ Tests: 34 passed (≥ 25 required)
4. ✅ Email ingestion import: `poll_ap_mailbox` OK
5. ✅ Rules router import: OK (policy upload route exists)
6. ✅ All frontend pages exist: `/admin/settings`, `/admin/rules`, `/admin/ai-insights`, `/admin/vendors`
7. ✅ Git status checked; uncommitted files are in-progress P2 work (separate worker handling)

## Worker Notes

- Work from `/home/alexshen/projects/ai-ap-manager`
- Backend in Docker: `docker exec ai-ap-manager-backend-1 <cmd>`
- Alembic migrations: `docker exec ai-ap-manager-backend-1 alembic revision --autogenerate -m "..."` then `docker exec ai-ap-manager-backend-1 alembic upgrade head`
- Commits: `committer "feat/fix/test/chore: message" file1 file2` — NEVER `git add .`
- After each new API module: verify with `docker exec ai-ap-manager-backend-1 python -c "from app.api.v1.X import router; print('OK')"`
- Frontend after changes: `cd frontend && npm run build` to catch type errors
- Install Python deps inside container if needed: `docker exec ai-ap-manager-backend-1 pip install <pkg>`
