# TODO — AI AP Operations Manager

## P0 — MVP (Weeks 1-4)

### Infrastructure & Scaffolding
- [x] Initialize monorepo: `frontend/`, `backend/`, `docs/`, `scripts/`
- [x] `docker-compose.yml`: Postgres, Redis, MinIO, backend, frontend, Celery worker
- [x] `.env.example` with all required vars documented
- [x] Backend: FastAPI app skeleton with health check, CORS, exception handlers
- [x] Backend: SQLAlchemy async engine + Alembic setup
- [ ] Frontend: Next.js 14 + Tailwind + shadcn/ui scaffold
- [ ] Frontend: API client (axios/fetch wrapper with auth headers)
- [ ] Seed data script: vendors, POs, GRNs, sample invoices

### Data Models (MVP subset)
- [x] `vendors`, `vendor_alias` tables
- [x] `purchase_orders`, `po_line_items` tables
- [x] `goods_receipts`, `grn_line_items` tables
- [x] `invoices`, `invoice_line_items` tables
- [x] `match_results` table
- [x] `exceptions` table
- [x] `approval_tasks`, `approval_matrix` tables
- [x] `audit_logs` table
- [x] `users`, `roles` tables (RBAC foundation)
- [x] Run initial Alembic migration

### Invoice Ingestion & Extraction (MVP)
- [ ] POST `/api/v1/invoices/upload` — PDF/image upload to MinIO
- [ ] Celery task: OCR with Tesseract → raw text
- [ ] **Dual-pass LLM extraction**: Pass A (structured prompt) + Pass B (document understanding prompt) → field-level comparator
- [ ] Store extracted fields in `invoices` + `invoice_line_items`; flag mismatched fields
- [ ] Manual field correction UI: mismatched fields highlighted in amber, AP Analyst confirms correct value
- [ ] Invoice status state machine: `received → extracting → extracted → matching → ...`

### 2-Way Match Engine (MVP)
- [ ] Match service: link invoice to PO by PO number
- [ ] Check quantity tolerance per line item (configurable %)
- [ ] Check amount tolerance (configurable % + absolute cap)
- [ ] Output match result: `MATCHED` / `PARTIAL_MATCH` / `MISMATCH` / `PO_NOT_FOUND`
- [ ] Auto-approve MATCHED invoices below threshold (rule-based, audited)
- [ ] Create exception for all non-MATCHED results

### Exception Queue (MVP)
- [ ] GET `/api/v1/exceptions` — list with filters (status, type, vendor, date)
- [ ] GET `/api/v1/exceptions/{id}` — detail with full match analysis
- [ ] PATCH `/api/v1/exceptions/{id}` — update status, assign owner, add comment
- [ ] Exception types: `PRICE_MISMATCH`, `QTY_MISMATCH`, `PO_NOT_FOUND`, `DUPLICATE`, `MISSING_GRN`
- [ ] Exception comments/thread (audit-logged)

### Approval Workflow (MVP - single level)
- [ ] Approval matrix: amount threshold → approver role
- [ ] Auto-create approval task when invoice passes match or exception is resolved
- [ ] POST `/api/v1/approvals/{id}/approve` and `/reject` (in-app)
- [ ] **Email-based approval**: generate signed token URL (48h expiry), embed in notification email, GET `/approvals/email?token=xxx` handler (no auth required)
- [ ] Approval task status: `pending → approved / rejected`, record method (in_app / email_token)
- [ ] Email notification with Approve/Reject button links (MVP: console log the email body)

### Auth & Users (MVP)
- [x] JWT auth: login, refresh token
- [x] User creation with roles: `AP_CLERK`, `AP_ANALYST`, `APPROVER`, `ADMIN`, `AUDITOR`
- [ ] Route-level permission guards (backend + frontend)

### KPI Dashboard (MVP)
- [ ] GET `/api/v1/kpi/summary` — touchless rate, exception rate, avg cycle time
- [ ] GET `/api/v1/kpi/trends` — daily/weekly time series
- [ ] Frontend: KPI cards + simple trend chart (recharts)

### Audit Trail (MVP)
- [ ] Middleware: log every state transition with actor, timestamp, snapshot
- [ ] GET `/api/v1/invoices/{id}/audit` — full history replay
- [ ] Audit log immutability (append-only, no updates)

---

### GL Smart Coding (MVP)
- [ ] GL coding suggestion service: frequency-based lookup (vendor history)
- [ ] API: GET `/api/v1/invoices/{id}/gl-suggestions` → per-line GL + cost center with confidence %
- [ ] Frontend: GL/cost center fields in invoice line editor show pre-filled grey suggestions with confidence badge
- [ ] "Confirm All Coding" button → bulk confirm, log to audit as "gl_coding_confirmed"
- [ ] Log every user override as "gl_coding_overridden" (feeds V1 ML retraining)

### Fraud Scoring (MVP - basic rule-based)
- [ ] Fraud scoring service: evaluate checklist signals on every invoice
- [ ] Store fraud_score + triggered_signals in `invoices` table (add column)
- [ ] Fraud badge in invoice header (🟢/🟡/🔴)
- [ ] HIGH fraud score → auto-create FRAUD_RISK exception, alert AP Manager
- [ ] CRITICAL fraud score → dual-authorization required (block until 2 ADMINs confirm)

---

## P1 — V1 (Weeks 5-8)

### 3-Way Match Engine
- [ ] Link GRNs to PO lines
- [ ] 3-way match: invoice qty ≤ GRN qty (with partial receipt support)
- [ ] Multiple GRNs per PO line aggregation
- [ ] Partial invoice matching (invoice covers subset of PO lines)
- [ ] Tolerance by vendor/category/currency configurable

### Multi-Level Approval
- [ ] Approval matrix config UI (amount bands × cost center × category → approver list)
- [ ] Sequential multi-level approval chains
- [ ] Delegation rules (approver out-of-office → delegate)
- [ ] Approval deadline + escalation

### Integration Layer
- [ ] CSV import: POs from ERP export
- [ ] CSV import: GRNs from WMS/ERP export
- [ ] CSV import: Vendor master data
- [ ] Vendor matching: fuzzy match on vendor name/tax ID/bank account
- [ ] Duplicate invoice detection (same vendor + amount + date ± 7 days + invoice number)

### Vendor Communication Hub (V1)
- [ ] `vendor_messages` table: invoice_id, sender_type (internal/vendor), sender_id, body, attachments, created_at
- [ ] POST `/api/v1/invoices/{id}/messages` — send internal or vendor-facing message
- [ ] Vendor-facing message → send email to vendor contact with reply link (portal)
- [ ] Vendor portal: minimal auth (magic link email), invoice status + message thread
- [ ] Vendor replies recorded back to `vendor_messages` via portal API
- [ ] "Communications" tab on invoice detail page (internal + vendor thread unified)
- [ ] Unread vendor message badge in invoice list and workbench feed
- [ ] All vendor messages included in audit trail export

### Vendor Compliance Doc Tracking (V1)
- [ ] `vendor_compliance_docs` table: vendor_id, doc_type (W9/W8BEN/VAT), file, status, expiry_date
- [ ] Vendor portal: upload W-9 / W-8BEN / VAT registration
- [ ] Alert AP Analyst when vendor compliance doc is missing or expired before approving payment
- [ ] Admin view: compliance doc status per vendor

### Recurring Invoice Detection (V1)
- [ ] `recurring_invoice_patterns` table: vendor_id, frequency, avg_amount, tolerance_pct, auto_fast_track
- [ ] Weekly Celery job: analyze last 6 months of approved invoices, detect patterns (same vendor, period, amount cluster)
- [ ] Tag matched invoices as `is_recurring=True` with pattern_id
- [ ] Fast-track workflow: recurring invoice within tolerance → bypass full exception queue → 1-click analyst confirmation
- [ ] Admin UI: view detected patterns, enable/disable fast-track per pattern

### Fraud Detection Upgrade (V1 — beyond MVP basic)
- [ ] Behavioral signals: bank account change detection (cross-reference vendor edit history)
- [ ] Ghost vendor detection: multiple vendors sharing same bank account
- [ ] Amount anomaly: 3x+ vendor historical average → elevated score
- [ ] Dual-authorization flow for CRITICAL fraud score (two ADMIN approval required)
- [ ] Fraud incident log: track all HIGH+ fraud flags and resolutions

### Policy/Contract Upload → Rule Extraction
- [ ] Upload PDF/Doc policy documents
- [ ] LLM pipeline: extract tolerance rules, approval thresholds, payment terms → JSON
- [ ] Human review UI: AI-suggested rules shown for review before publishing
- [ ] Rule version flow: `draft → in_review → published`
- [ ] Published rules auto-applied to match engine

### Role-Based Access Control
- [ ] RBAC middleware enforced on all endpoints
- [ ] Frontend route guards per role
- [ ] Admin UI: user management, role assignment

### Vendor Master Data UI
- [ ] Vendor list + detail page
- [ ] Bank account + tax ID validation fields
- [ ] Vendor alias management (multiple trade names)

---

### GL Smart Coding Upgrade (V1 — ML model)
- [ ] Train scikit-learn text classifier on confirmed GL coding history (vendor + description → GL + cost center)
- [ ] Weekly Celery beat: retrain model on new confirmed data
- [ ] A/B test: ML model vs frequency-based lookup (compare accuracy on holdout set)
- [ ] API: expose model version + accuracy stats in admin panel

### Exception Auto-Routing (V1)
- [ ] Routing rules: PRICE_MISMATCH → assign to procurement role; GRN_NOT_FOUND → warehouse role; TAX_DISCREPANCY → tax team role
- [ ] Configurable in admin: exception_type → default_role mapping
- [ ] Auto-assign on exception creation (before human even sees it)

---

## P2 — V2 (Weeks 9-12)

### AI Self-Optimization
- [ ] Log all human overrides (AP Analyst corrects AI extraction, changes exception outcome)
- [ ] Weekly summary: which rule changes would have reduced manual interventions?
- [ ] Rule recommendation UI: AI suggests new rules, human approves before publishing
- [ ] A/B tracking: old rule vs new rule performance comparison

### Root Cause Analysis
- [ ] Process mining: identify bottleneck steps (where do invoices spend most time?)
- [ ] Anomaly detection: exception rate spike → drill down to vendor/doc type/period
- [ ] LLM-generated narrative report: "Exception rate rose 40% this week because..."
- [ ] Scheduled weekly digest sent to AP Manager

### ERP Integration (Production)
- [ ] SAP connector: PO sync via BAPI/RFC or REST API
- [ ] Oracle connector: PO/GRN sync via Fusion REST API
- [ ] Voucher push: approved invoice → GL posting in ERP
- [ ] ERP sync status tracking + retry on failure

### Advanced Features
- [ ] Multi-currency support + FX rate tolerance
- [ ] SLA alerting: invoice approaching due date without approval
- [ ] Vendor self-service portal (read-only invoice status + dispute submission)
- [ ] Mobile-responsive approver view
- [ ] Bulk operations: bulk approve/reject/reassign in exception queue

---

### Conversational AI Query Interface (V2 — "Ask AI")
- [ ] Natural language input → structured query → results: "Show me all Acme invoices over $50k last month"
- [ ] Powered by Claude: NL → SQL/filter parameters, system executes query, shows results
- [ ] Suggested prompts for common queries
- [ ] No AI can mutate data through chat — read-only

### Predictive Cash Flow Forecasting (V2)
- [ ] Calculate expected outflows from pending approvals × payment terms
- [ ] Weekly/monthly cash flow forecast widget on KPI dashboard
- [ ] Export forecast as CSV for treasury team

### Industry Benchmarking (V2)
- [ ] Once multi-tenant: aggregate anonymized KPIs by industry segment
- [ ] Show "Your touchless rate is 63% — manufacturing industry median is 58%" on KPI dashboard

### 4-Way Matching (V2 — inspection-heavy industries)
- [ ] `inspection_reports` table: grn_id, inspector, result (pass/fail/partial), notes
- [ ] 4-way match: invoice vs PO vs GRN vs inspection report
- [ ] Exception: INSPECTION_FAILED — invoice cannot be approved until inspection pass

---

## Backlog / Nice-to-Have

- [ ] Slack/Teams notifications for approval requests (in addition to email)
- [ ] Vendor invoice templating in portal (vendor drafts from pre-approved template)
- [ ] Automated bill batching: multiple invoices to same vendor → one payment run
- [ ] Payment scheduling: optimize payment dates for cash flow vs early-pay discounts
- [ ] Vendor risk score based on historical accuracy (OCR error rate, exception rate)
- [ ] GDPR/data retention automation (archive invoices after 7 years)
- [ ] Multi-entity support: separate legal entities with consolidated reporting
