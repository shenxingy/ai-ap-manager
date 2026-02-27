# TODO — AI AP Operations Manager

## P0 — MVP (Weeks 1-4)

### Infrastructure & Scaffolding
- [ ] Initialize monorepo: `frontend/`, `backend/`, `docs/`, `scripts/`
- [ ] `docker-compose.yml`: Postgres, Redis, MinIO, backend, frontend, Celery worker
- [ ] `.env.example` with all required vars documented
- [ ] Backend: FastAPI app skeleton with health check, CORS, exception handlers
- [ ] Backend: SQLAlchemy async engine + Alembic setup
- [ ] Frontend: Next.js 14 + Tailwind + shadcn/ui scaffold
- [ ] Frontend: API client (axios/fetch wrapper with auth headers)
- [ ] Seed data script: vendors, POs, GRNs, sample invoices

### Data Models (MVP subset)
- [ ] `vendors`, `vendor_alias` tables
- [ ] `purchase_orders`, `po_line_items` tables
- [ ] `goods_receipts`, `grn_line_items` tables
- [ ] `invoices`, `invoice_line_items` tables
- [ ] `match_results` table
- [ ] `exceptions` table
- [ ] `approval_tasks`, `approval_matrix` tables
- [ ] `audit_logs` table
- [ ] `users`, `roles` tables (RBAC foundation)
- [ ] Run initial Alembic migration

### Invoice Ingestion & Extraction (MVP)
- [ ] POST `/api/v1/invoices/upload` — PDF/image upload to MinIO
- [ ] Celery task: OCR with Tesseract → raw text
- [ ] LLM extraction task: raw text → structured JSON fields (header + line items)
- [ ] Store extracted fields in `invoices` + `invoice_line_items`
- [ ] Manual field correction UI (AP Analyst can fix extraction errors)
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
- [ ] POST `/api/v1/approvals/{id}/approve` and `/reject`
- [ ] Approval task status: `pending → approved / rejected`
- [ ] Email notification (mock/console log for MVP)

### Auth & Users (MVP)
- [ ] JWT auth: login, refresh token
- [ ] User creation with roles: `AP_CLERK`, `AP_ANALYST`, `APPROVER`, `ADMIN`, `AUDITOR`
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

## Backlog / Nice-to-Have

- [ ] Slack/Teams notifications for approval requests
- [ ] Natural language search across invoices ("show me all Acme invoices over $50k last month")
- [ ] Predictive cash flow forecasting based on pending approvals
- [ ] Vendor risk scoring based on historical accuracy
- [ ] GDPR/data retention automation
