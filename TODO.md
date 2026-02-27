# TODO — AI AP Operations Manager

> Priority tiers: **P0** = MVP (Weeks 1-4) | **P1** = V1 (Weeks 5-8) | **P2** = V2 (Weeks 9-12) | **P3** = Backlog
> Status: `[x]` done · `[ ]` open · `[-]` in-progress

---

## P0 — MVP (Weeks 1-4)

### Infrastructure & Scaffolding

- [x] Initialize monorepo: `frontend/`, `backend/`, `docs/`, `scripts/`
- [x] `docker-compose.yml`: Postgres, Redis, MinIO, backend, frontend, Celery worker
- [x] `.env.example` with all required vars documented
- [x] Backend: FastAPI app skeleton with health check, CORS, exception handlers
- [x] Backend: SQLAlchemy async engine + Alembic setup
- [x] Seed data script: vendors, POs, GRNs, default matching rule (idempotent)
  - [x] Seed ADMIN, AP_CLERK, AP_ANALYST, APPROVER users (changeme123)
  - [x] Seed Acme Corp vendor + PO-2026-001 ($4,800) + PO-2026-002 ($12,500) + GR-2026-001
  - [x] Seed default published matching_tolerance rule

#### Frontend Scaffold (Next.js 14)
- [x] Initialize Next.js 14 (App Router) in `frontend/`
  - [x] `npx create-next-app@latest frontend --ts --tailwind --app --src-dir`
  - [x] Install and configure shadcn/ui (`npx shadcn-ui@latest init`)
  - [ ] Custom brand colors in `tailwind.config.ts`
  - [ ] Dark mode support via `class` strategy
- [x] Install dependencies:
  - [x] `@tanstack/react-query` — server state
  - [x] `zustand` — client state (auth, UI toggles)
  - [x] `axios` — HTTP client
  - [x] `recharts` — KPI charts
  - [x] `react-hook-form` + `zod` — forms + validation (included by create-next-app)
  - [x] `date-fns` — date formatting
  - [x] `lucide-react` — icons
- [x] App shell layout (`app/layout.tsx`)
  - [x] Sidebar navigation component
  - [x] Sidebar items by role: Dashboard · Invoices · Exceptions · Approvals · Vendors · Admin
  - [x] Top header: breadcrumb, user avatar, logout button
  - [ ] Mobile: collapsible sidebar (hamburger)
  - [x] Role-aware nav: APPROVER sees only Invoices + Approvals; AP_CLERK sees Invoices only
- [x] API client (`lib/api.ts`)
  - [x] Axios instance with `baseURL = process.env.NEXT_PUBLIC_API_URL`
  - [x] Request interceptor: attach `Authorization: Bearer <token>` from auth store
  - [x] Response interceptor: on 401, attempt token refresh; on refresh fail, redirect to /login
  - [ ] Global error handler: toast notification for 4xx/5xx
- [x] React Query setup (`lib/query-client.ts`)
  - [x] `QueryClientProvider` at root
  - [ ] Default staleTime 30s, retry 2
- [x] Auth store (`lib/stores/auth-store.ts`)
  - [x] Zustand slice: `user`, `accessToken`, `isAuthenticated`, `login()`, `logout()`, `refresh()`
  - [x] Persist token in `localStorage` (clear on logout)
- [x] Route guard HOC / middleware (`middleware.ts`)
  - [x] Redirect unauthenticated users to `/login`
  - [ ] Redirect authenticated users away from `/login`
- [ ] Docker: add frontend service to `docker-compose.yml` (port 3000, hot reload)

---

### Data Models (MVP subset)

- [x] `vendors`, `vendor_alias` tables
- [x] `purchase_orders`, `po_line_items` tables
- [x] `goods_receipts`, `grn_line_items` tables
- [x] `invoices`, `invoice_line_items` tables
  - [x] `fraud_score` Integer column on invoices
  - [x] `gl_account_suggested` String column on invoice_line_items
- [x] `match_results`, `line_item_matches` tables
- [x] `exceptions` table
- [x] `approval_tasks`, `approval_tokens` tables
- [x] `audit_logs`, `ai_call_logs` tables
- [x] `users`, `rules`, `rule_versions` tables
- [x] Run initial Alembic migration
- [x] DB: store `fraud_triggered_signals` JSON column on invoices
  - [x] Alembic migration: `ALTER TABLE invoices ADD COLUMN fraud_triggered_signals JSONB DEFAULT '[]'`
  - [x] Update `fraud_scoring.py` to persist signal list alongside score

---

### Invoice Ingestion & Extraction (MVP)

#### Backend
- [x] POST `/api/v1/invoices/upload` — PDF/image upload to MinIO (20MB limit, MIME validation)
- [x] GET `/api/v1/invoices` — paginated list with filters (status, vendor_id, date_from, date_to)
- [x] GET `/api/v1/invoices/{id}` — full detail with line_items + extraction_results
- [x] GET `/api/v1/invoices/{id}/audit` — full audit history (chronological)
- [x] MinIO storage service — upload, download, presigned URL, bucket auto-create
- [x] Audit service — `log()` helper writing to audit_logs (flush, not commit)
- [x] Celery task: OCR with Tesseract → raw text
- [x] Dual-pass LLM extraction: Pass A (structured) + Pass B (document understanding) → field-level diff
- [x] Store extracted fields in `invoices` + `invoice_line_items`; flag mismatched fields
- [x] PATCH `/api/v1/invoices/{id}/fields` — manual field correction (AP_ANALYST+)
  - [x] Accept body: `{field_name: str, corrected_value: Any, line_id?: UUID}`
  - [x] Validate field_name is one of the allowed correctable fields
  - [x] Update invoice / invoice_line_item fields
  - [x] Log to audit_logs: action="field_corrected", before/after snapshot
  - [ ] If invoice.status == "exception" (extraction failed), auto-trigger re-match
- [x] Invoice status state machine — validation + PATCH override
  - [x] Enforce valid transitions: ingested→extracting→extracted→matching→matched/exception→approved/rejected
  - [x] `PATCH /api/v1/invoices/{id}/status` — ADMIN-only forced status override (audited)
  - [x] Prevent invalid jumps (e.g., approved→extracting) with 422 response

#### Frontend — Invoice List Page (`/invoices`)
- [x] Paginated data table — scaffolded: invoice_number · vendor · total_amount · status · created_at · fraud badge
- [x] Status badge: color-coded chip (ingested=gray, extracting=blue, matched=green, exception=red, approved=emerald)
- [x] Fraud score badge: 🟢 <20 · 🟡 20-39 · 🔴 40-59 · 🔴🔴 60+
- [x] Filter bar: status multi-select · vendor search · date range picker
- [x] Upload button → drag-and-drop modal — scaffolded
  - [x] File picker (PDF, JPEG, PNG, max 20MB)
  - [ ] Upload progress indicator
  - [ ] Success: show new invoice ID, redirect to detail
  - [x] Error: file type / size validation before upload
- [x] Pagination controls (page, page_size)
- [x] Row click → navigate to `/invoices/{id}`

#### Frontend — Invoice Detail Page (`/invoices/{id}`)
- [x] Header section: invoice_number · vendor_name · total_amount · currency · status badge · fraud badge
- [ ] Action bar:
  - [ ] "Re-run Extraction" button (AP_ANALYST+)
  - [ ] "Trigger Re-match" button (AP_ANALYST+)
  - [ ] "Download Original" button (presigned URL)
- [x] Tab layout: **Details** | **Line Items** | **Match** | **Exceptions** | **Approvals** | **Audit Log**
- [x] **Details tab** — scaffolded (basic field display):
  - [x] Fields: invoice_number, vendor, invoice_date, due_date, subtotal, tax_amount, total_amount, payment_terms
  - [ ] Extraction confidence indicator per field (color dot: green/amber/red)
  - [ ] Amber highlight + edit icon for mismatched fields (discrepancy_fields from ExtractionResult)
  - [ ] Inline edit → save → calls PATCH /invoices/{id}/fields
  - [ ] Extraction pass comparison: Pass A vs Pass B values shown side-by-side for discrepant fields
- [x] **Line Items tab** — scaffolded:
  - [x] Table: line# · description · qty · unit_price · line_total · GL account · GL suggestion
  - [ ] GL account cell: grey suggestion text + confidence badge
  - [ ] Click suggestion → auto-fills field
  - [ ] "Confirm All Coding" button → PUT each line's gl_account (AP_ANALYST+)
- [x] **Match tab** — scaffolded:
  - [x] Match status card: matched/partial/exception, match_type, rule_version used
  - [x] Header variance: invoice total vs PO total, variance amount + %
  - [ ] Line match table: each invoice line vs matched PO line, qty variance, price variance
  - [ ] Color coding: matched=green, variance=amber, unmatched=red
- [x] **Exceptions tab** — scaffolded:
  - [x] List of open exceptions for this invoice (link to exception detail)
- [x] **Approvals tab** — scaffolded:
  - [x] Current approval task status (pending/approved/rejected)
  - [x] Approver name, due date, decision channel
  - [x] Decision history (all tasks for this invoice)
- [x] **Audit Log tab** — scaffolded:
  - [x] Timeline component: event · actor · timestamp · before/after diff
  - [x] Data from GET /invoices/{id}/audit

---

### 2-Way Match Engine (MVP)

- [x] Match service: PO lookup by FK, notes heuristic, invoice_number prefix
- [x] Quantity tolerance per line (configurable %)
- [x] Amount tolerance (configurable % + absolute cap)
- [x] Output: matched / partial / exception (MISSING_PO, PRICE_VARIANCE, QTY_VARIANCE)
- [x] Auto-approve MATCHED invoices below threshold (rule-based, audited)
- [x] Exception creation for non-MATCHED results (deduplicated)
- [x] GET `/api/v1/invoices/{id}/match` — MatchResult with LineItemMatches
- [x] POST `/api/v1/invoices/{id}/match` — manually trigger re-match (AP_ANALYST+)
- [x] Wired into Celery pipeline (extracted → matching → matched/exception/approved)
- [x] Seed: default published matching_tolerance rule

---

### Exception Queue (MVP)

#### Backend
- [x] GET `/api/v1/exceptions` — list with filters (status, exception_code, invoice_id, assigned_to, severity)
- [x] GET `/api/v1/exceptions/{id}` — detail with invoice summary
- [x] PATCH `/api/v1/exceptions/{id}` — update status, assigned_to, resolution_notes (AP_ANALYST+, audit-logged)
- [x] Exception comments/thread
  - [x] DB: `exception_comments` table (id, exception_id FK, author_id FK, body TEXT, created_at)
  - [x] Alembic migration for exception_comments
  - [x] SQLAlchemy model `ExceptionComment` in `app/models/exception_record.py`
  - [x] Schema: `ExceptionCommentIn(body: str)`, `ExceptionCommentOut(id, author_id, body, created_at)`
  - [x] POST `/api/v1/exceptions/{id}/comments` — add comment (AP_ANALYST+, audit-logged)
  - [x] GET `/api/v1/exceptions/{id}/comments` — list comments (AP_CLERK+)
  - [ ] Include comment_count in ExceptionListItem response

#### Frontend — Exception Queue Page (`/exceptions`)
- [x] Filterable table — scaffolded: code · severity badge · status · assigned_to · invoice link · created_at
- [x] Severity badge: critical=red, high=orange, medium=yellow, low=gray
- [x] Row click → slide-out detail panel
- [x] Detail panel — scaffolded:
  - [x] Exception info: code, description, AI root cause (if available)
  - [x] Invoice mini-card: invoice#, vendor, amount, current status
  - [x] Comment thread (chronological list)
  - [x] Add comment textarea + Submit button
  - [x] Status update dropdown (open/in_progress/resolved/waived)
  - [ ] Assign to selector (autocomplete users)
  - [ ] Resolution notes textarea
  - [ ] Save button → PATCH /exceptions/{id}
- [ ] Filter bar: status · exception_code · severity · assigned_to
- [ ] Pagination

---

### Approval Workflow (MVP - single level)

#### Backend
- [x] `ApprovalTask` + `ApprovalToken` models
- [x] `create_approval_task()` — creates task + HMAC tokens + email notification
- [x] `process_approval_decision()` — web (JWT) + email (token) channels
- [x] `auto_create_approval_task()` — called after match when total > threshold
- [x] GET `/api/v1/approvals` — list pending tasks for current user (APPROVER+)
- [x] GET `/api/v1/approvals/{task_id}` — task detail with invoice summary
- [x] POST `/api/v1/approvals/{task_id}/approve` — in-app (JWT)
- [x] POST `/api/v1/approvals/{task_id}/reject` — in-app (JWT)
- [x] GET `/api/v1/approvals/email?token=xxx` — email token (no auth), returns HTML confirmation

#### Frontend — Approvals Page (`/approvals`)
- [x] List of pending approval tasks for the logged-in APPROVER — scaffolded
- [x] Each item: invoice# · vendor · amount · due_at countdown · status
- [x] Click → Approval detail modal / page — scaffolded
  - [x] Invoice summary card (all key fields)
  - [ ] Match result summary: status, variances
  - [x] Notes textarea
  - [x] Approve button (green) + Reject button (red)
  - [x] Confirmation dialog before submitting
- [ ] Success: mark task as decided, remove from list, show toast
- [ ] Past decisions tab: history of approved/rejected invoices

---

### Auth & Users (MVP)

#### Backend
- [x] POST `/api/v1/auth/token` — login (email + password → JWT access + refresh)
- [x] POST `/api/v1/auth/refresh` — refresh access token
- [x] User creation with roles: AP_CLERK, AP_ANALYST, APPROVER, ADMIN, AUDITOR
- [x] `require_role()` dependency for route-level guards
- [ ] Verify ALL existing endpoints use `require_role()` dependency (audit pass)
  - [ ] POST /invoices/upload → AP_CLERK+
  - [ ] GET /invoices → AP_CLERK+
  - [ ] GET /invoices/{id} → AP_CLERK+
  - [ ] PATCH /invoices/{id}/fields → AP_ANALYST+
  - [ ] GET /exceptions → AP_CLERK+
  - [ ] PATCH /exceptions/{id} → AP_ANALYST+
  - [ ] GET /approvals → APPROVER+
  - [ ] POST /approvals/{id}/approve → APPROVER+
  - [ ] GET /kpi/summary → AP_ANALYST+
  - [ ] GET /invoices/{id}/audit → AP_CLERK+
- [x] GET `/api/v1/users/me` — return current user info (role, name, email)

#### Frontend — Login Page (`/login`)
- [x] Email + password form — scaffolded (react-hook-form + zod validation)
- [x] POST /api/v1/auth/token on submit
- [x] Store access token + user role in auth Zustand store
- [x] On success: redirect to `/dashboard`
- [x] On failure: show "Invalid credentials" toast
- [ ] "Remember me" checkbox (persist token in localStorage vs session)

---

### KPI Dashboard (MVP)

#### Backend
- [x] GET `/api/v1/kpi/summary` — touchless rate, exception rate, avg cycle time, period totals
- [x] GET `/api/v1/kpi/trends` — daily/weekly bucketed invoices_received, invoices_approved, invoices_exceptions

#### Frontend — KPI Dashboard Page (`/dashboard`)
- [x] Summary metric cards row — scaffolded:
  - [x] Touchless Rate (large %, color green if >70%)
  - [x] Exception Rate (large %, color red if >20%)
  - [x] Avg Cycle Time (hours → formatted as "2d 4h")
  - [x] Total Invoices Received (count, this period)
  - [ ] Total Approved / Pending / Exceptions (3 mini cards)
- [x] Period selector: "Last 7 days / 30 days / 90 days" (updates ?days= param)
- [x] Trend chart (recharts LineChart) — scaffolded:
  - [x] X-axis: date, Y-axis: invoice count
  - [x] Three lines: Received (blue) · Approved (green) · Exceptions (red)
  - [ ] Toggle: daily / weekly
  - [x] Tooltip on hover showing exact counts
- [x] Auto-refresh every 5 minutes (`refetchInterval: 300000`)
- [ ] Loading skeleton while fetching
- [ ] Empty state if no data in period

---

### Audit Trail (MVP)

#### Backend
- [x] GET `/api/v1/invoices/{id}/audit` — full history replay
- [ ] Audit log immutability enforcement
  - [ ] Alembic migration: create restricted DB role `ap_app` with no UPDATE/DELETE on audit_logs
  - [ ] `GRANT SELECT, INSERT ON audit_logs TO ap_app`
  - [ ] `REVOKE UPDATE, DELETE ON audit_logs FROM ap_app`
  - [ ] Document in CLAUDE.md
- [ ] Verify ALL state transitions are audit-logged:
  - [x] invoice_uploaded (in upload handler)
  - [x] invoice_extracted (in celery task)
  - [x] invoice.match_completed (in match engine)
  - [x] invoice_approved / invoice_rejected (in approval service)
  - [x] exception_updated (in exceptions PATCH)
  - [x] field_corrected (add when PATCH /invoices/{id}/fields is built)
  - [x] manual_status_override (add when PATCH /invoices/{id}/status is built)

---

### GL Smart Coding (MVP)

#### Backend
- [x] `app/services/gl_coding.py` — frequency-based GL lookup from vendor history
  - [x] Word-overlap similarity for description matching
  - [x] PO line fallback
  - [x] Category default fallback
- [x] GET `/api/v1/invoices/{id}/gl-suggestions` — per-line suggestions with confidence %
- [x] PUT `/api/v1/invoices/{id}/lines/{line_id}/gl` — confirm GL coding for a line (AP_ANALYST+)
  - [x] Body: `{gl_account: str, cost_center?: str}`
  - [x] Update `invoice_line_item.gl_account` (and `cost_center`)
  - [x] Log to audit: action="gl_coding_confirmed" (user accepted suggestion) OR "gl_coding_overridden" (user entered different value)
  - [x] Compare submitted gl_account vs gl_account_suggested to determine confirmed vs overridden
- [ ] PUT `/api/v1/invoices/{id}/lines/gl-bulk` — bulk confirm all GL suggestions (AP_ANALYST+)
  - [ ] Accept all suggestions for all lines in one call
  - [ ] Log each line as "gl_coding_confirmed"

#### Frontend — GL Coding UI (inside Invoice Detail → Line Items tab)
- [ ] GL account column in line items table
- [ ] Show `gl_account_suggested` in grey italic below the editable field
- [ ] Confidence badge next to suggestion (e.g., "87% — vendor history")
- [ ] Click suggestion → fills the field and marks as "to confirm"
- [ ] Manual override: type a different value (field turns amber)
- [ ] "Confirm All Coding" button → calls PUT /lines/gl-bulk
- [ ] Individual confirm: checkmark icon per line
- [ ] After confirmation: field turns solid, confidence badge disappears

---

### Fraud Scoring (MVP - basic rule-based)

#### Backend
- [x] `app/services/fraud_scoring.py` — 5 rule-based signals
  - [x] round_amount (+10): total ends in .00 AND > $1000
  - [x] amount_spike (+20): total > 2x vendor historical avg
  - [x] potential_duplicate (+30): same vendor + same amount within 7 days
  - [x] stale_invoice_date (+10): invoice_date older than 90 days
  - [x] new_vendor (+5): vendor has < 3 approved invoices
- [x] Auto-creates FRAUD_FLAG exception when score >= HIGH threshold (40)
- [x] Wired into Celery `process_invoice` pipeline (after extraction, before match)
- [x] GET `/api/v1/invoices/{id}/fraud-score` — returns score + risk_level
- [x] Persist `fraud_triggered_signals` to invoices table (see Data Models section)
- [ ] CRITICAL score (≥60) → dual-authorization enforcement
  - [ ] Backend: `approval_required_count` field on ApprovalTask (default 1, 2 for CRITICAL)
  - [ ] Approval service: only mark invoice approved when `approved_count >= required_count`
  - [ ] Block approval button in frontend until second ADMIN approves

#### Frontend — Fraud Badge
- [ ] Fraud risk badge on invoice list and detail header
  - [ ] 🟢 Low (<20) · 🟡 Medium (20-39) · 🔴 High (40-59) · 🔴🔴 Critical (60+)
  - [ ] Tooltip on hover: list triggered signals with their point values
- [ ] CRITICAL score → red warning banner on invoice detail page
  - [ ] "⚠️ Dual authorization required — this invoice requires 2 ADMIN approvals"
  - [ ] Approve button disabled until second admin approves

---

## P1 — V1 (Weeks 5-8)

### Vendor Management CRUD

#### Backend
- [x] `GET /api/v1/vendors` — paginated list (AP_CLERK+): `{id, name, tax_id, payment_terms, currency, is_active, invoice_count}`; filter params: `name`, `is_active`
- [x] `GET /api/v1/vendors/{id}` — detail (AP_CLERK+): vendor + aliases list + recent 10 invoice stubs
- [x] `POST /api/v1/vendors` — create vendor (AP_ANALYST+): audit log `vendor_created`
- [x] `PATCH /api/v1/vendors/{id}` — partial update (AP_ANALYST+): audit log `vendor_updated`; separate `bank_account_changed` audit event when bank_account changes
- [x] `POST /api/v1/vendors/{id}/aliases` — add alias (AP_ANALYST+)
- [x] `DELETE /api/v1/vendors/{id}/aliases/{alias_id}` — remove alias (AP_ANALYST+)
- [x] Pydantic schemas: `VendorListItem`, `VendorDetail`, `VendorCreate`, `VendorUpdate`, `VendorAliasCreate`

#### Frontend
- [x] Vendor management page (`/admin/vendors`) — list, create, edit, aliases UI

---

### 3-Way Match Engine

#### Backend
- [ ] DB migration: link `grn_line_items.po_line_item_id` (FK to po_line_items)
  - [ ] Alembic migration adding the column + index
  - [ ] Backfill in seed script (link GR-2026-001 lines to PO-2026-001 lines)
- [x] Extend match engine: `run_3way_match(db, invoice_id) -> MatchResult`
  - [x] Load all GRNs for the invoice's PO (via po_id)
  - [x] Aggregate received qty by PO line: `sum(gr_line_item.quantity)` across all GRNs
  - [x] Per invoice line: invoice_qty ≤ total_grn_qty (with tolerance)
  - [x] Exception codes: `GRN_NOT_FOUND` (no GRN for PO line), `QTY_OVER_RECEIPT` (invoice > GRN)
  - [x] Multiple GRNs per PO line: aggregate, handle partial receipts
  - [x] Partial invoice: invoice covers subset of PO lines → allowed (no MISSING_LINE exception)
- [ ] `run_3way_match` response: include `grn_lines_used` per invoice line
- [x] Auto-select match type: if GRN exists for this PO → use 3way, else 2way
- [ ] Update GET `/api/v1/invoices/{id}/match` response to include GRN data
- [ ] Tolerance configurable by vendor / category / currency (extend rule engine config format)
- [x] POST `/api/v1/invoices/{id}/match` — `?match_type=3way` param (supports match_type=auto/2way/3way)

#### Frontend
- [-] Match tab in invoice detail: show "2-Way Match" vs "3-Way Match" label — scaffolded, GRN data not yet wired
- [ ] For 3-way: show GRN line reference in line match table
- [ ] GRN_NOT_FOUND exception highlighted with "No GR found for this PO line" message

---

### Multi-Level Approval

#### Backend
- [ ] `approval_matrix` table: `id, amount_min, amount_max, department, category, approver_role, step_order, is_active`
  - [ ] Alembic migration
  - [ ] SQLAlchemy model in `app/models/approval.py`
- [ ] Approval workflow engine: `build_approval_chain(db, invoice) -> list[ApprovalTask]`
  - [ ] Look up applicable matrix rows by amount + department/category
  - [ ] Sort by step_order
  - [ ] Create task chain: Task 2 only created after Task 1 approved
- [ ] Sequential chain: when Task N approved → auto-create Task N+1
- [ ] Delegation:
  - [ ] `user_delegations` table: `delegator_id, delegate_id, valid_from, valid_to, created_at`
  - [ ] Alembic migration
  - [ ] When assigning approval task: check for active delegation, assign to delegate
  - [ ] PUT `/api/v1/users/{id}/delegation` — set delegation (APPROVER or ADMIN)
- [ ] Approval escalation:
  - [ ] Celery beat task (daily): check `approval_tasks.due_at < now` for pending tasks
  - [ ] Escalation: reassign to user's manager (or ADMIN role)
  - [ ] Audit log: action="approval_escalated"
  - [ ] Email notification to new assignee (console mock)
- [ ] CRUD for approval matrix:
  - [ ] GET `/api/v1/approval-matrix` — list all rules (ADMIN)
  - [ ] POST `/api/v1/approval-matrix` — create rule (ADMIN)
  - [ ] PUT `/api/v1/approval-matrix/{id}` — update rule (ADMIN)
  - [ ] DELETE `/api/v1/approval-matrix/{id}` — soft delete (ADMIN)

#### Frontend
- [ ] Approval matrix config UI (Admin Settings → Approval Matrix)
  - [ ] Table of rules: amount band · department · category → approver role · step
  - [ ] Add/edit/delete rows
  - [ ] Preview: "Invoice of $8,000 in Procurement → Step 1: AP_ANALYST → Step 2: ADMIN"
- [ ] Approval chain visible in invoice detail → Approvals tab
  - [ ] Timeline showing each step with status

---

### Integration Layer

#### Backend
- [ ] CSV import: Purchase Orders from ERP export
  - [ ] POST `/api/v1/import/pos` — multipart CSV file (ADMIN, AP_ANALYST)
  - [ ] Configurable column mapping (e.g., `po_number`, `vendor_tax_id`, `total_amount`)
  - [ ] Upsert by po_number; versioning via updated_at
  - [ ] Return: `{created: N, updated: N, skipped: N, errors: [{row: N, message: str}]}`
  - [ ] Celery task for large files (> 1000 rows)
- [ ] CSV import: Goods Receipts from WMS/ERP
  - [ ] POST `/api/v1/import/grns` — link by po_number
  - [ ] Same upsert + error return pattern
- [ ] CSV import: Vendor master data
  - [ ] POST `/api/v1/import/vendors`
  - [ ] Fuzzy dedup: if tax_id matches existing vendor → update; if name 90%+ similar → warn
- [ ] Email ingestion pipeline
  - [ ] IMAP polling Celery beat task (every 5 min)
  - [ ] Config: `IMAP_HOST`, `IMAP_USER`, `IMAP_PASSWORD`, `IMAP_MAILBOX` in settings
  - [ ] Fetch unread emails from AP mailbox
  - [ ] Extract PDF/image attachments → auto-create Invoice records + trigger processing
  - [ ] Store `email_from`, `email_subject`, `email_received_at` on invoice
  - [ ] Mark email as read after processing
  - [ ] Error: no attachment → log warning, skip
- [ ] Duplicate invoice detection (enhanced)
  - [ ] Detect: same vendor_id + invoice_number (exact) → block as `DUPLICATE_INVOICE`
  - [ ] Detect: same vendor_id + total_amount + invoice_date ± 7 days → soft flag
  - [ ] Cross-currency normalization: convert to base currency for amount comparison
    - [ ] [AI idea] Store `normalized_amount_usd` on invoices for FX-agnostic dup check
  - [ ] Run in Celery pipeline after extraction (before match)

#### Frontend
- [ ] Import page (`/admin/import`)
  - [ ] Three import tabs: POs · GRNs · Vendors
  - [ ] Drag-and-drop CSV upload per type
  - [ ] Preview table: first 10 rows + column mapping dropdowns
  - [ ] Submit → show progress + results (created/updated/skipped/errors)
  - [ ] Download error report CSV
- [ ] Invoice list: `source` badge ("email" vs "upload")
- [ ] Email ingestion status in settings: last poll time, total auto-ingested count

---

### Vendor Communication Hub (V1)

#### Backend
- [ ] `VendorMessage` model — already in `app/models/approval.py` (move to `app/models/vendor_message.py`)
  - [ ] Alembic migration for `vendor_messages` table
  - [ ] Fields: id, invoice_id, sender_id (nullable for external vendor), sender_email, direction (inbound/outbound), body, is_internal, attachments (JSON), created_at
- [ ] POST `/api/v1/invoices/{id}/messages` — send message (AP_ANALYST+)
  - [ ] Body: `{body: str, is_internal: bool, attachments?: list[file]}`
  - [ ] If `is_internal=False` → send vendor-facing email (console mock) with reply link
  - [ ] Audit log: action="vendor_message_sent"
- [ ] GET `/api/v1/invoices/{id}/messages` — list messages (AP_CLERK+)
- [ ] Vendor portal reply endpoint: POST `/api/v1/portal/invoices/{id}/reply`
  - [ ] Magic link auth: `?token=<vendor_token>` (similar pattern to approval tokens)
  - [ ] Creates inbound VendorMessage, notifies AP team
- [ ] Unread message count: include `unread_vendor_messages` in InvoiceListItem response
- [ ] All vendor messages included in `/invoices/{id}/audit` response (separate event type)

#### Frontend
- [ ] Invoice detail: **Communications tab** (new tab)
  - [ ] Unified thread: internal notes + vendor-facing messages (visually distinct)
  - [ ] Internal note = grey bubble, vendor message = blue bubble
  - [ ] Compose box: toggle "Internal" vs "Vendor-facing"
  - [ ] Attachment upload in compose box
  - [ ] Send button → POST /invoices/{id}/messages
- [ ] Invoice list: unread badge (orange dot) if vendor message awaiting response
- [ ] Notification bell in header: count of invoices with unread vendor messages

---

### Vendor Compliance Doc Tracking (V1)

#### Backend
- [ ] `vendor_compliance_docs` table: `id, vendor_id, doc_type (W9/W8BEN/VAT/insurance), file_path, status (active/expired/missing), expiry_date, uploaded_by, created_at`
  - [ ] Alembic migration
  - [ ] SQLAlchemy model in `app/models/vendor.py`
- [ ] POST `/api/v1/vendors/{id}/compliance-docs` — upload compliance doc (ADMIN, AP_ANALYST)
  - [ ] Store in MinIO under `compliance/` prefix
  - [ ] Validate doc_type is in allowed set
- [ ] GET `/api/v1/vendors/{id}/compliance-docs` — list compliance docs
- [ ] Celery beat (weekly): check expiry_dates → update status to "expired" if past expiry
- [ ] Compliance check in approval service:
  - [ ] Before creating approval task: check if vendor has missing/expired W-9 or W-8BEN
  - [ ] If missing → create `COMPLIANCE_MISSING` exception (no blocking, but flagged)
  - [ ] Alert AP Analyst via email notification (console mock)

#### Frontend
- [ ] Vendor detail page: Compliance Documents section
  - [ ] List of docs with type, status badge (active/expired/missing), expiry date
  - [ ] Upload button per doc type
  - [ ] Status: green (active) · orange (expiring in 30 days) · red (expired/missing)
- [ ] Invoice detail: compliance warning banner if vendor has expired docs

---

### Recurring Invoice Detection (V1)

#### Backend
- [ ] `RecurringInvoicePattern` model (already in `app/models/invoice.py`)
  - [ ] Verify migration exists for recurring_invoice_patterns table
  - [ ] Fields: vendor_id, frequency_days, avg_amount, tolerance_pct, auto_fast_track, last_detected_at
- [ ] Detection Celery beat task (weekly):
  - [ ] For each vendor with ≥ 3 approved invoices
  - [ ] Group by vendor, compute inter-invoice intervals (days between consecutive invoices)
  - [ ] Detect periodicity: dominant interval (7, 14, 30, 60, 90 days) with ±20% tolerance
  - [ ] Compute amount cluster: mean ± std dev
  - [ ] Create/update RecurringInvoicePattern records
  - [ ] Log to audit
- [ ] Tagging: when new invoice uploaded and vendor has active pattern
  - [ ] If invoice_amount within pattern.tolerance_pct of pattern.avg_amount → set is_recurring=True, recurring_pattern_id
  - [ ] Run in Celery pipeline step before match
- [ ] Fast-track workflow:
  - [ ] After tagging is_recurring=True: skip full exception queue
  - [ ] Create ApprovalTask immediately (bypass match wait)
  - [ ] Flag in ApprovalTask: `is_fast_track=True`
  - [ ] 1-click analyst confirmation UI

#### Frontend
- [ ] Recurring invoice badge: "🔄 Recurring" on invoice list and detail header
- [ ] Fast-track banner: "Recurring invoice detected — 1-click approval available"
- [ ] Admin → Recurring Patterns page:
  - [ ] Table: vendor · frequency · avg amount · tolerance · fast-track toggle · last detected
  - [ ] Enable/disable fast-track per pattern
  - [ ] Manual detect button (triggers detection job for that vendor)

---

### Fraud Detection Upgrade (V1)

#### Backend
- [ ] Behavioral signal: bank account change detection
  - [ ] `vendor_bank_history` table: vendor_id, bank_account, changed_at, changed_by
  - [ ] Alembic migration
  - [ ] When vendor bank account updated: log to vendor_bank_history
  - [ ] Fraud signal: bank account changed within 30 days before invoice → +25 score
- [ ] Ghost vendor detection
  - [ ] Cross-reference bank account across all vendors
  - [ ] Signal: invoice from vendor sharing bank account with another vendor → +30 score
- [ ] Fraud incident log:
  - [ ] `fraud_incidents` table: invoice_id, score_at_flag, triggered_signals, reviewed_by, outcome, created_at
  - [ ] All HIGH+ fraud flags auto-create a fraud_incident record
  - [ ] GET `/api/v1/fraud-incidents` — list for ADMIN/AUDITOR
- [ ] Dual-authorization flow for CRITICAL (≥60) — wire into approval service (see P0 TODO above)

#### Frontend
- [ ] Fraud Incidents page (`/admin/fraud`) — ADMIN only
  - [ ] Table: invoice · score · signals · status (open/reviewed) · outcome
  - [ ] Mark as reviewed with outcome notes

---

### Policy/Contract Upload → Rule Extraction (V1)

#### Backend
- [ ] POST `/api/v1/rules/upload-policy` — multipart PDF/Doc upload (ADMIN)
  - [ ] Store file in MinIO under `policies/` prefix
  - [ ] Trigger Celery task: `extract_rules_from_policy(policy_file_id)`
- [ ] LLM extraction task (Claude claude-sonnet-4-6):
  - [ ] Prompt: extract tolerance rules, approval thresholds, payment terms from policy text
  - [ ] Output schema: `[{rule_type, description, config_json, confidence}]`
  - [ ] Store in `rule_suggestions` table: rule_id, policy_file_id, suggested_config, status, created_at
  - [ ] Log to ai_call_logs: call_type="policy_parse"
- [ ] Human review flow:
  - [ ] GET `/api/v1/rules/suggestions` — list pending suggestions (ADMIN)
  - [ ] POST `/api/v1/rules/suggestions/{id}/accept` — creates draft RuleVersion from suggestion
  - [ ] POST `/api/v1/rules/suggestions/{id}/reject` — marks suggestion as rejected
- [ ] Rule version flow: draft → in_review → published
  - [ ] POST `/api/v1/rules/{id}/versions/{ver_id}/publish` — ADMIN only
  - [ ] Published hook: invalidate active rule cache, optionally re-run pending invoices
- [ ] Shadow mode (AI idea): new rule runs in parallel for 2 weeks, compare outcomes
  - [ ] `rule_shadow_runs` table: rule_version_id, invoice_id, shadow_result, active_result
  - [ ] Celery job: weekly comparison report

#### Frontend
- [ ] Rule Suggestions page (`/admin/rules`)
  - [ ] Upload policy document button
  - [ ] Processing status while LLM runs
  - [ ] List of extracted rule suggestions with:
    - [ ] Rule type, description, extracted config (formatted JSON diff from current)
    - [ ] Confidence % from LLM
    - [ ] Accept → creates draft rule version
    - [ ] Reject → dismiss
  - [ ] Draft rules list: edit config → submit for review → publish

---

### Role-Based Access Control (V1)

#### Backend
- [x] `require_role()` dependency exists
- [ ] Full permission audit: verify all endpoints call `require_role()`
- [x] GET `/api/v1/admin/users` — list all users (ADMIN)
- [x] POST `/api/v1/admin/users` — create user (ADMIN)
  - [x] Body: email, name, role, password
  - [x] Hash password, send welcome email (console mock)
- [x] PATCH `/api/v1/admin/users/{id}` — update name/role/is_active (ADMIN)
- [ ] DELETE `/api/v1/admin/users/{id}` — soft delete (ADMIN)

#### Frontend
- [x] Admin panel (`/admin/users`) — scaffolded with user table, create/edit forms, role badges
  - [x] User table: email · name · role · status (active/inactive)
  - [x] Create user form (modal)
  - [x] Edit user: role change dropdown, deactivate toggle
  - [x] Role badge: color-coded (ADMIN=red, ANALYST=blue, CLERK=gray, APPROVER=green)
- [ ] Per-role route guards:
  - [ ] `/admin/*` — ADMIN only
  - [ ] `/approvals` — APPROVER+ (AP_ANALYST, ADMIN can also view)
  - [ ] `/exceptions` — AP_CLERK+
  - [ ] `/kpi` — AP_ANALYST+
- [ ] Unauthorized page (403) component

---

### Vendor Master Data UI (V1)

#### Backend
- [ ] GET `/api/v1/vendors` — paginated list with filters (name, is_active)
- [ ] GET `/api/v1/vendors/{id}` — detail with aliases + compliance docs + invoice count
- [ ] POST `/api/v1/vendors` — create vendor (ADMIN, AP_ANALYST)
- [ ] PATCH `/api/v1/vendors/{id}` — update vendor fields (ADMIN, AP_ANALYST)
  - [ ] Bank account change → log to vendor_bank_history (fraud signal)
- [ ] POST `/api/v1/vendors/{id}/aliases` — add trade name alias
- [ ] DELETE `/api/v1/vendors/{id}/aliases/{alias_id}` — remove alias
- [ ] Validate tax_id format (EIN format for US vendors)
- [ ] Validate bank account format (basic routing + account validation)

#### Frontend
- [ ] Vendor list page (`/vendors`)
  - [ ] Table: name · tax_id · invoice count · compliance status · is_active
  - [ ] Search by name/tax_id
  - [ ] Create vendor button
- [ ] Vendor detail page (`/vendors/{id}`)
  - [ ] Header: name, tax_id, bank account, payment_terms, currency
  - [ ] Edit button → inline form
  - [ ] Bank account change warning: "⚠️ Changing bank account will trigger fraud signal"
  - [ ] Aliases section: list + add/remove
  - [ ] Compliance docs section (W-9, W-8BEN, VAT)
  - [ ] Recent invoices mini-list (last 10)

---

### GL Smart Coding Upgrade — ML Model (V1)

#### Backend
- [ ] Training data collection
  - [ ] Query: all InvoiceLineItems with confirmed gl_account (is_confirmed=True or from approved invoices)
  - [ ] Features: vendor_name + line_description + category → label: gl_account
- [ ] Train scikit-learn classifier
  - [ ] TF-IDF vectorizer on (vendor_name + description) text
  - [ ] Logistic Regression or Linear SVM
  - [ ] Evaluate on holdout set: accuracy, top-3 accuracy
- [ ] Celery beat: weekly retrain job using new confirmed data
- [ ] Model artifact storage: serialize with joblib → store in MinIO `models/gl-coding-v{N}.pkl`
- [ ] Serve prediction in `gl_coding.py`: load model from MinIO, add `ml_model` as suggestion source
- [ ] A/B test framework:
  - [ ] Split invoices by hash(invoice_id) % 2 → group A (frequency) vs group B (ML)
  - [ ] Log which method was used and whether user accepted/overrode
  - [ ] Report endpoint: GET `/api/v1/admin/gl-model-stats` → accuracy per group
- [ ] Admin panel: model version, last retrain date, accuracy stats

---

### Exception Auto-Routing (V1)

#### Backend
- [x] `exception_routing_rules` table: `id, exception_code, target_role, priority, is_active`
  - [x] Alembic migration
  - [x] SQLAlchemy model in `app/models/exception_routing.py`
  - [x] Defaults: PRICE_VARIANCE→AP_ANALYST, GRN_NOT_FOUND→AP_ANALYST, FRAUD_FLAG→ADMIN (+ QTY_VARIANCE, QTY_OVER_RECEIPT, MISSING_PO)
- [x] Auto-assign logic in match engine / fraud scoring:
  - [x] When exception created: look up routing rule by exception_code
  - [x] Find first active user with target_role → set assigned_to
  - [x] Log to audit: action="exception_auto_routed" (implemented in match_engine._resolve_assignee)
- [x] CRUD for routing rules:
  - [x] GET `/api/v1/admin/exception-routing` — list rules (ADMIN)
  - [x] POST `/api/v1/admin/exception-routing` — create rule (ADMIN)
  - [x] PATCH `/api/v1/admin/exception-routing/{id}` — update (ADMIN)

#### Frontend
- [ ] Admin → Exception Routing page (`/admin/exception-routing`) — CRUD UI for routing rules
  - [ ] Table: exception_code → assigned_role
  - [ ] Edit mapping dropdowns
  - [ ] Priority ordering (drag to reorder)

---

## P2 — V2 (Weeks 9-12)

### AI Self-Optimization

#### Backend
- [ ] Override logging
  - [ ] `ai_feedback` table: invoice_id, field_name, ai_value, human_value, actor_id, created_at
  - [ ] Alembic migration
  - [ ] Log when user corrects extracted field (from PATCH /invoices/{id}/fields)
  - [ ] Log when user overrides GL coding (from PUT /invoices/{id}/lines/{id}/gl)
  - [ ] Log when AP Analyst changes exception outcome (from PATCH /exceptions/{id})
- [ ] Weekly analysis Celery job:
  - [ ] Analyze ai_feedback: which fields have highest correction rate?
  - [ ] For extraction: are certain vendor types consistently wrong on specific fields?
  - [ ] For GL coding: compare ML model suggestion acceptance rate
  - [ ] For match rules: simulate alternative tolerance values, compute exception reduction
- [ ] Rule recommendation engine:
  - [ ] `rule_recommendations` table: rule_type, current_config, suggested_config, expected_impact, confidence, status, created_at
  - [ ] Auto-create recommendations weekly
  - [ ] Human review required before any rule change
- [ ] GET `/api/v1/admin/rule-recommendations` — list pending recommendations (ADMIN)
- [ ] POST `/api/v1/admin/rule-recommendations/{id}/accept` — apply recommendation as new rule draft
- [ ] POST `/api/v1/admin/rule-recommendations/{id}/reject` — dismiss
- [ ] A/B testing framework:
  - [ ] `rule_ab_tests` table: rule_id, test_group (A/B), period, metric_results
  - [ ] Split invoices A/B, run different rule versions, compare exception rates

#### Frontend
- [ ] Admin → AI Insights page (`/admin/ai-insights`)
  - [ ] Top extraction errors: which fields, which vendors, correction rate chart
  - [ ] Rule recommendations list: current vs suggested config, expected improvement
  - [ ] Accept / Reject / Ask AI to explain buttons
  - [ ] A/B test results chart

---

### Root Cause Analysis

#### Backend
- [ ] Process mining:
  - [ ] Query avg time in each status per invoice (using audit_log timestamps)
  - [ ] Identify bottleneck: which step has highest median dwell time?
  - [ ] GET `/api/v1/analytics/process-mining` → `{step, avg_hours, p90_hours, invoice_count}`
- [ ] Anomaly detection:
  - [ ] Z-score on exception_rate grouped by vendor/doc_type/period
  - [ ] Alert when Z-score > 2.5 (exceptional spike)
  - [ ] GET `/api/v1/analytics/anomalies` → `[{dimension, value, z_score, period}]`
- [ ] LLM narrative report:
  - [ ] POST `/api/v1/analytics/root-cause-report` → triggers async Claude narrative generation
  - [ ] System prompt: provide anomaly data + process mining results
  - [ ] Output: 3-5 paragraph natural language explanation
  - [ ] Log to ai_call_logs (call_type="root_cause")
  - [ ] Store report in `analytics_reports` table
- [ ] Weekly digest:
  - [ ] Celery beat: weekly job to generate and "send" digest (console mock)
  - [ ] Include: top anomalies, process bottlenecks, AI narrative

#### Frontend
- [ ] Analytics page (`/analytics`)
  - [ ] Process mining funnel chart: avg time per status step
  - [ ] Anomaly alerts list: spike events with Z-score
  - [ ] "Generate Root Cause Report" button → polling for completion → display narrative
  - [ ] Report history: list of past weekly digests

---

### ERP Integration (Production)

#### Backend
- [ ] Integration config:
  - [ ] `erp_integrations` table: id, erp_type (sap/oracle/generic), connection_params (JSON encrypted), sync_schedule, last_sync_at, status
  - [ ] Alembic migration
- [ ] SAP connector (`app/integrations/sap.py`):
  - [ ] Connect via BAPI RFC (pyrfc) or S/4HANA REST API
  - [ ] Inbound: sync POs (`MM_PO_GEN_REPORT` or `/sap/opu/odata/sap/API_PURCHASEORDER_PROCESS_SRV`)
  - [ ] Inbound: sync GRNs (MIGO transactions or GR API)
  - [ ] Outbound: post voucher on invoice approved (FB60 BAPI)
- [ ] Oracle Fusion connector (`app/integrations/oracle.py`):
  - [ ] REST API: `/fscmRestApi/resources/11.13.18.05/purchaseOrders`
  - [ ] Inbound: POs + GRNs
  - [ ] Outbound: AP invoice creation on approval
- [ ] Sync orchestration:
  - [ ] Celery beat: scheduled sync per configured ERP
  - [ ] Delta sync: only changed records since last_sync_at
  - [ ] Conflict resolution: ERP wins on master data (PO/GRN), AP system wins on extracted invoice data
- [ ] Sync status tracking:
  - [ ] `erp_sync_log` table: erp_id, entity_type, entity_id, status, error_message, synced_at
  - [ ] Dead letter queue: failed items → retry up to 3x with exponential backoff
  - [ ] GET `/api/v1/admin/erp-sync-log` — view recent sync events

#### Frontend
- [ ] Admin → ERP Integration page (`/admin/erp`)
  - [ ] Connection setup form per ERP type
  - [ ] Test connection button
  - [ ] Sync schedule config
  - [ ] Sync log table: entity, status, timestamp, error
  - [ ] Manual sync trigger button

---

### Multi-Currency Support + FX Rate Tolerance

#### Backend
- [ ] `fx_rates` table: `base_currency, quote_currency, rate, valid_date`
  - [ ] Alembic migration
- [ ] Celery beat: daily FX rate fetch from Open Exchange Rates API (or ECB XML)
  - [ ] Config: `OPEN_EXCHANGE_RATES_APP_ID` in settings
  - [ ] Store rates for all invoice currencies in DB
- [ ] Invoice normalization: `normalized_amount_usd` (base currency amount) on invoices
  - [ ] Compute on extraction: total_amount × fx_rate_to_usd
  - [ ] Update when fx rate refreshed
- [ ] Match engine: compare normalized amounts when currency mismatch between invoice and PO
- [ ] Tolerance: configurable `fx_tolerance_pct` in matching_tolerance rule config
- [ ] KPI: aggregate totals in base currency

#### Frontend
- [ ] Invoice list: show currency flag/code next to amount
- [ ] KPI dashboard: "All amounts shown in USD (base currency)" note
- [ ] Invoice detail: "Original: €5,200 — Normalized: $5,618 (rate: 1.0804 on 2026-02-26)"

---

### SLA Alerting

#### Backend
- [ ] Celery beat: daily job — check `invoices.due_date`
  - [ ] Alert 3 days before due_date if still pending/matched (not yet approved)
  - [ ] Alert on due_date if not yet approved (overdue)
  - [ ] Send email notification to assigned AP Analyst + APPROVER (console mock)
- [ ] `sla_alerts` table: invoice_id, alert_type (approaching/overdue), sent_at, actor_notified
- [ ] GET `/api/v1/invoices?overdue=true` — filter for overdue invoices

#### Frontend
- [ ] Invoice list: "Overdue" red badge on past-due invoices
- [ ] Dashboard: "⚠️ 3 invoices approaching due date" warning card
- [ ] Notification bell: SLA alerts as in-app notifications

---

### Vendor Portal (Read-Only + Disputes)

#### Backend
- [ ] Vendor portal auth: magic link email token (48h expiry, vendor_id scoped)
  - [ ] POST `/api/v1/portal/auth` — send magic link to vendor email (console mock)
  - [ ] GET `/api/v1/portal/auth?token=xxx` — validates token, returns short-lived session
- [ ] GET `/api/v1/portal/invoices` — vendor's invoices (limited fields, no internal data)
- [ ] GET `/api/v1/portal/invoices/{id}` — invoice status + payment_terms (no fraud score, no internal notes)
- [ ] POST `/api/v1/portal/invoices/{id}/dispute` — submit dispute
  - [ ] Creates ExceptionRecord with code="VENDOR_DISPUTE"
  - [ ] Creates VendorMessage (inbound, is_internal=False)
  - [ ] Notifies AP team

#### Frontend
- [ ] Vendor portal (separate Next.js layout at `/portal/*` or subdomain)
  - [ ] Login via magic link (no password)
  - [ ] Invoice list: invoice# · amount · status · due_date
  - [ ] Invoice detail: status timeline · payment_terms · contact AP button
  - [ ] Dispute form: reason + description + attachments
  - [ ] Mobile-responsive (vendors may use phones)

---

### Mobile-Responsive Approver View

- [ ] Approvals page: fully responsive (stacked cards on mobile < 768px)
- [ ] Invoice detail: horizontal scroll for tables on mobile
- [ ] PWA manifest (`manifest.json`) for "Add to Home Screen" on iOS/Android
- [ ] Service worker: cache API responses for offline viewing

---

### Bulk Operations

#### Backend
- [ ] POST `/api/v1/exceptions/bulk-update`
  - [ ] Body: `{ids: list[UUID], status: str, assigned_to?: UUID}`
  - [ ] Batch update up to 100 exceptions
  - [ ] Audit log each update
- [ ] POST `/api/v1/approvals/bulk-approve`
  - [ ] Batch approve multiple tasks (ADMIN only)
  - [ ] Each approval still creates individual audit log entries

#### Frontend
- [ ] Exception queue: checkbox column for multi-select
- [ ] Bulk action toolbar: appears when ≥1 checked
  - [ ] Bulk assign dropdown
  - [ ] Bulk status change
  - [ ] Bulk close (waive)
  - [ ] "N items selected" count

---

### Conversational AI Query Interface — "Ask AI" (V2)

#### Backend
- [ ] POST `/api/v1/ask-ai` — natural language query → structured results
  - [ ] Body: `{question: str}`
  - [ ] Claude prompt: system context with DB schema (invoices, exceptions, vendors, POs)
  - [ ] Safety: only allow SELECT on whitelist of tables (invoices, vendors, exceptions, approvals, audit_logs)
  - [ ] Execute generated SQL via read-only DB connection
  - [ ] Return: `{question, sql_generated, results: list[dict], row_count}`
  - [ ] Log to ai_call_logs (call_type="nl_query")
  - [ ] Hard limit: max 500 rows returned

#### Frontend
- [ ] "Ask AI" sidebar panel (all pages)
  - [ ] Input field: "Ask anything about your invoices..."
  - [ ] Suggested prompts (5 pre-built):
    - [ ] "Show all invoices over $50k this month"
    - [ ] "Which vendors have the most exceptions?"
    - [ ] "What's our approval backlog?"
    - [ ] "Show invoices pending > 7 days"
    - [ ] "Top 5 exception types last quarter"
  - [ ] Results as table with pagination
  - [ ] "Show SQL" toggle (expandable)
  - [ ] Query history (session-scoped)
  - [ ] Read-only disclaimer: "AI cannot modify data"

---

### Predictive Cash Flow Forecasting (V2)

#### Backend
- [ ] Algorithm: for each pending/matched invoice with due_date
  - [ ] expected_outflow_date = today + avg(payment_terms_days) if no due_date
  - [ ] Bucket by week: sum expected outflows per 7-day period
- [ ] GET `/api/v1/kpi/cash-flow-forecast`
  - [ ] Returns: `[{week_start: date, expected_outflow: Decimal, invoice_count: int, confidence: str}]`
  - [ ] Confidence: "high" (due_date set) vs "estimated" (payment_terms proxy)
- [ ] GET `/api/v1/kpi/cash-flow-export` — CSV download for treasury
  - [ ] Columns: invoice#, vendor, amount, currency, expected_date, status

#### Frontend
- [ ] KPI dashboard: "Cash Flow Forecast" section below trend chart
  - [ ] Bar chart: weekly expected outflows (next 12 weeks)
  - [ ] Color: confirmed (dark blue) vs estimated (light blue)
  - [ ] Total bar at top: "~$245K expected outflow this month"
- [ ] "Export CSV" button for treasury team

---

### Industry Benchmarking (V2)

> Requires multi-tenant architecture first

- [ ] Anonymize and aggregate KPI data by industry segment + company_size
- [ ] Benchmark endpoint: GET `/api/v1/kpi/benchmarks`
  - [ ] Returns: `{your_touchless_rate: 0.63, industry_median: 0.58, percentile: 72}`
- [ ] KPI dashboard: benchmark comparison card
  - [ ] "Your touchless rate is 63% — manufacturing median is 58% (72nd percentile)"

---

### 4-Way Matching (V2 — inspection-heavy industries)

#### Backend
- [ ] `inspection_reports` table: `id, gr_id FK, inspector_id FK, result (pass/fail/partial), notes, inspected_at`
  - [ ] Alembic migration
- [ ] Extend match engine: `run_4way_match(db, invoice_id)`
  - [ ] After 3-way: for each GRN line, check inspection_report.result = "pass"
  - [ ] Exception: `INSPECTION_FAILED` if any inspection report is fail/partial
  - [ ] Block invoice approval until inspection passes
- [ ] POST `/api/v1/gr/{gr_id}/inspection` — log inspection result (ADMIN, AP_ANALYST)

#### Frontend
- [ ] Invoice match tab: show inspection status per GRN line
- [ ] INSPECTION_FAILED exception: "Cannot approve until inspection report passes"

---

## P3 — Backlog / Nice-to-Have

### Notifications
- [ ] Slack notifications for approval requests (Slack webhook integration)
  - [ ] Config: `SLACK_WEBHOOK_URL` in settings
  - [ ] Message format: invoice# · vendor · amount · Approve/Reject links
- [ ] Microsoft Teams notifications (Teams webhook)
- [ ] In-app notification center (bell icon with unread count)
  - [ ] WebSocket or SSE push for real-time updates
  - [ ] Notification types: approval_request, exception_assigned, sla_alert, vendor_message
- [ ] User notification preferences: per-channel (email/Slack/in-app) opt-in per notification type

### Vendor Invoice Templating
- [ ] Template builder: AP team creates pre-approved invoice template per vendor
- [ ] Vendor portal: vendor drafts invoice from template (fields pre-filled)
- [ ] Template invoice submitted → enters pipeline as "template-sourced" (higher trust, faster processing)

### Payment Operations
- [ ] Automated bill batching
  - [ ] Group approved invoices to same vendor with similar due dates into one payment run
  - [ ] Payment run schedule: weekly, bi-weekly, monthly
  - [ ] GET `/api/v1/payment-runs` — list upcoming batched payments
- [ ] Payment scheduling optimizer
  - [ ] For each approved invoice: calculate early payment discount if paid before discount_cutoff
  - [ ] Suggest optimal payment date: balance cash flow vs discount capture
  - [ ] Report: "Paying 3 days early saves $1,200 on Acme Corp invoices this month"

### Vendor Risk Score
- [ ] `vendor_risk_scores` table: vendor_id, ocr_error_rate, exception_rate, avg_extraction_confidence, score, computed_at
- [ ] Weekly Celery job: recompute vendor risk scores from invoice history
- [ ] Risk score displayed on vendor detail page + invoice header
- [ ] High-risk vendor → auto-create "VENDOR_RISK" flag on future invoices

### Compliance & Retention
- [ ] GDPR/data retention:
  - [ ] Celery beat (monthly): find invoices created > 7 years ago
  - [ ] Archive to cold storage (MinIO `archive/` bucket)
  - [ ] Soft-delete from active DB (already supported via deleted_at)
  - [ ] Configurable retention period per data category
- [ ] Audit log export:
  - [ ] GET `/api/v1/audit/export` → downloads full audit log as CSV or JSON (AUDITOR role)
  - [ ] Date range filter
  - [ ] Signed URL for large exports

### Multi-Entity Support
- [ ] `entities` table: legal entity name, tax_id, currency, contact info
- [ ] All invoices, POs, vendors scoped by entity_id
- [ ] Cross-entity consolidated KPI reporting (ADMIN)
- [ ] Entity selector in frontend header

### Testing Infrastructure
- [ ] Backend unit tests (pytest):
  - [ ] Match engine: MISSING_PO, PRICE_VARIANCE, QTY_VARIANCE, auto-approve
  - [ ] Fraud scoring: each signal independently, score thresholds
  - [ ] Approval token: create, verify, expiry, reuse rejection
  - [ ] GL coding: vendor_history, po_line fallback, category_default
  - [ ] KPI queries: touchless_rate calculation edge cases (all approved, none approved)
- [ ] Backend integration tests:
  - [ ] Full invoice pipeline: upload → OCR → extraction → match → approval (mocked MinIO + Celery)
  - [ ] Auth: token creation, refresh, expiry, role enforcement
  - [ ] Concurrent uploads: verify no race conditions in invoice creation
- [ ] Frontend unit tests (Jest + React Testing Library):
  - [ ] Invoice list pagination and filter state
  - [ ] GL coding acceptance flow
  - [ ] Fraud badge rendering at each threshold
- [ ] E2E tests (Playwright):
  - [ ] Login → upload invoice → view extraction → trigger match → approve
  - [ ] Exception queue: assign → comment → resolve
  - [ ] KPI dashboard: verify chart renders with real data
- [ ] Load testing (k6 or Locust):
  - [ ] 100 concurrent invoice uploads
  - [ ] 1000 concurrent GET /invoices requests
  - [ ] Celery: 50 simultaneous processing tasks

### DevOps & Observability
- [ ] Production Dockerfile:
  - [ ] Multi-stage build (builder + runtime)
  - [ ] Non-root user (UID 1001)
  - [ ] Minimal image (python:3.11-slim)
- [ ] Structured logging:
  - [ ] JSON log format for all backend services
  - [ ] Log fields: timestamp, level, service, trace_id, invoice_id (when applicable)
  - [ ] Correlation ID: inject X-Trace-ID header, propagate to Celery tasks
- [ ] Prometheus metrics:
  - [ ] GET `/metrics` endpoint (Starlette Prometheus middleware)
  - [ ] Custom metrics: invoice_processing_duration_seconds, extraction_accuracy_gauge, exception_rate_gauge
  - [ ] Celery task metrics: task_duration, task_failure_rate
- [ ] Health checks:
  - [ ] GET `/health` → DB connection + Redis + MinIO reachability
  - [ ] GET `/health/ready` vs `/health/live` (Kubernetes probes)
- [ ] API documentation:
  - [ ] Swagger already auto-generated at `/api/docs`
  - [ ] Add detailed descriptions + examples to all schemas
  - [ ] OpenAPI spec export for client SDK generation
- [ ] README.md:
  - [ ] Quick-start: `docker-compose up -d && python scripts/seed.py`
  - [ ] Architecture diagram (text or Mermaid)
  - [ ] API overview table
  - [ ] Development workflow: migrations, adding models, writing tests

---

## North Star Metrics (Tracking)

| Metric | Now | MVP Target | V1 Target | V2 Target |
|--------|-----|------------|-----------|-----------|
| Touchless rate | N/A | 55% | 75% | 85% |
| Avg cycle time (days) | N/A | 7 | 4 | 3 |
| Extraction accuracy (field) | N/A | 92% | 96% | 98% |
| GL coding accuracy | N/A | 75% | 90% | 95% |
| Fraud catch rate | N/A | 70% | 85% | 92% |
| Audit completeness | N/A | 100% | 100% | 100% |
| Recurring invoice touchless | N/A | 0% | 90% | 95% |
