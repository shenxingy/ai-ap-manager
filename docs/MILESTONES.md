# Milestones & Development Plan

---

## Week 1-2: MVP Core Loop

**Goal**: Working end-to-end flow with mock data — upload → extract → match → queue → approve → KPI.

### Backend Tickets

| ID | Task | Owner |
|----|------|-------|
| BE-01 | FastAPI app scaffold: main.py, CORS, health check, exception handlers | Backend |
| BE-02 | SQLAlchemy async setup + Alembic + initial migration (all MVP tables) | Backend |
| BE-03 | User model + JWT auth (login, refresh, get_current_user) | Backend |
| BE-04 | Vendor, PO, GRN models + seed data script (10 vendors, 20 POs, 15 GRNs) | Backend |
| BE-05 | MinIO integration: upload helper, get_signed_url | Backend |
| BE-06 | Invoice upload endpoint (POST /invoices/upload) → MinIO + DB | Backend |
| BE-07 | Celery setup + Redis broker + beat scheduler skeleton | Backend |
| BE-08 | OCR worker task: Tesseract → raw_text | Backend |
| BE-09 | LLM extraction task: raw_text → structured JSON (Claude API, with prompt template) | Backend |
| BE-10 | Extraction validation: schema check + math check + confidence gating | Backend |
| BE-11 | Audit log middleware + write_audit_log() helper | Backend |
| BE-12 | Duplicate detection service | Backend |
| BE-13 | 2-way match engine (pseudocode → Python) | Backend |
| BE-14 | Tolerance configuration loader from active rule_version | Backend |
| BE-15 | Exception creation service (from match results) | Backend |
| BE-16 | Approval routing service + approval matrix lookup | Backend |
| BE-17 | Exception endpoints: list, detail, update, comment, resolve | Backend |
| BE-18 | Approval endpoints: list, approve, reject | Backend |
| BE-19 | KPI query service + /kpi/summary + /kpi/trends | Backend |
| BE-20 | Seed rule_version v1 (default tolerances, approval matrix) | Backend |

### Frontend Tickets

| ID | Task | Owner |
|----|------|-------|
| FE-01 | Next.js 14 scaffold + Tailwind + shadcn/ui + TanStack Query setup | Frontend |
| FE-02 | API client wrapper (base URL, auth header injection, error handling) | Frontend |
| FE-03 | Auth: login page + JWT token management (httpOnly cookies via API route) | Frontend |
| FE-04 | App shell: sidebar nav, route guards by role | Frontend |
| FE-05 | Invoice upload page: drag-drop zone + progress indicator | Frontend |
| FE-06 | Invoice list page: table with filters + pagination | Frontend |
| FE-07 | Invoice detail page: 5-tab layout (overview, match, exceptions, approvals, audit) | Frontend |
| FE-08 | Exception queue page: table with filters + bulk assign | Frontend |
| FE-09 | Exception detail page: evidence panel + comment thread + resolve action | Frontend |
| FE-10 | Approval tasks page: pending list + quick approve/reject | Frontend |
| FE-11 | Approval detail page: full invoice view + PDF viewer + decision | Frontend |
| FE-12 | KPI dashboard: metric cards + 3 charts (recharts) | Frontend |
| FE-13 | AP Analyst workbench / dashboard: summary cards + needs-action feed | Frontend |

### Data & Infra Tickets

| ID | Task | Owner |
|----|------|-------|
| DA-01 | docker-compose.yml: postgres, redis, minio, backend, worker, frontend | DevOps |
| DA-02 | .env.example with all required vars | DevOps |
| DA-03 | MinIO bucket creation script + CORS policy | DevOps |
| DA-04 | Seed script: create admin user, AP analyst, approver for demo | DevOps |

### Testing (Week 2)

| ID | Task |
|----|------|
| TE-01 | Unit tests: match engine (all 13 cases) |
| TE-02 | Unit tests: extraction validation |
| TE-03 | Integration test: invoice upload → extraction pipeline |
| TE-04 | E2E-01: Happy path touchless invoice |
| TE-05 | E2E-02: Price mismatch → exception → resolve → approve |

**Week 2 Exit Criteria**: E2E-01 and E2E-02 pass. Seed data demo can be run.

---

## Week 3-4: Exception Queue & Approval Flow

**Goal**: Full exception handling + multi-level approval + audit completeness.

### Backend Tickets

| ID | Task |
|----|------|
| BE-21 | 3-way match engine (GRN aggregation + partial receipt) |
| BE-22 | Auto-resolve engine for low-severity exceptions |
| BE-23 | Multi-level approval task creation (sequential levels) |
| BE-24 | Approval delegation rules (V1 prep) |
| BE-25 | SLA tracking: set sla_due_at on exceptions, Celery beat check for SLA breach |
| BE-26 | Invoice audit trail endpoint (GET /invoices/{id}/audit) |
| BE-27 | Invoice field correction endpoint (PATCH /invoices/{id}/fields) |
| BE-28 | Re-trigger match endpoint (POST /invoices/{id}/trigger-match) |

### Frontend Tickets

| ID | Task |
|----|------|
| FE-14 | Exception queue: SLA urgency indicators + "SLA at risk" filter |
| FE-15 | Invoice detail: manual field correction form with confidence highlighting |
| FE-16 | Audit trail tab: timeline view with event type icons |
| FE-17 | Approval detail: approval chain visualization (step diagram) |
| FE-18 | Admin panel skeleton + user management page |

### Testing (Week 4)

| ID | Task |
|----|------|
| TE-06 | E2E-03: Missing PO → manual link → proceed |
| TE-07 | E2E-04: Duplicate invoice rejected |
| TE-08 | E2E-05: 3-way match with partial GRN |
| TE-09 | E2E-06: Multi-level approval chain |
| TE-10 | E2E-08: Approver rejects → back to analyst → re-approve |

**Week 4 Exit Criteria**: All E2E tests 01-08 pass. Demo-ready for internal review.

---

## Week 5-6: Integration Layer & KPI

**Goal**: CSV import for POs/GRNs/vendors + complete KPI + RBAC enforcement.

### Backend Tickets

| ID | Task |
|----|------|
| BE-29 | CSV import service: POs (POST /import/purchase-orders) |
| BE-30 | CSV import service: GRNs (POST /import/goods-receipts) |
| BE-31 | CSV import service: Vendors (POST /import/vendors) |
| BE-32 | Vendor fuzzy matching (name + tax_id) |
| BE-33 | Full RBAC enforcement on all endpoints |
| BE-34 | KPI trend endpoint with granularity (day/week) |
| BE-35 | Vendor master data API (list, detail, update aliases) |

### Frontend Tickets

| ID | Task |
|----|------|
| FE-19 | Admin: CSV import UI (file upload + progress + error report) |
| FE-20 | Admin: Vendor master data management page |
| FE-21 | Admin: Approval matrix config UI (editable table) |
| FE-22 | KPI dashboard: remaining charts (exception by type, cycle time) |
| FE-23 | Frontend RBAC: role-based route guards + hidden actions per role |
| FE-24 | Audit log explorer page (AUDITOR role) |

### Testing

| ID | Task |
|----|------|
| TE-11 | E2E-09: Low OCR confidence → forced manual review |
| TE-12 | E2E-10: KPI dashboard reflects real data |
| TE-13 | Integration: CSV import PO → match in subsequent invoice |
| TE-14 | Role access matrix: verify each role can/cannot access each endpoint |

---

## Week 7-8: Policy Parsing & Rule Versioning

**Goal**: Admin can upload contract PDFs, AI extracts rules, admin reviews and publishes.

### Backend Tickets

| ID | Task |
|----|------|
| BE-36 | Policy document upload endpoint + PDF text extraction (pdfplumber) |
| BE-37 | LLM policy parsing task: extract rules → policy_rules table |
| BE-38 | Rule version CRUD: create draft, submit review, publish, archive |
| BE-39 | Active rule version loader (cache in Redis, invalidate on publish) |
| BE-40 | Verify match_results correctly reference rule_version_id |
| BE-41 | Rule version diff: compare two versions for admin review UI |

### Frontend Tickets

| ID | Task |
|----|------|
| FE-25 | Admin: policy document upload + extraction status |
| FE-26 | Admin: extracted rule review UI (confirm / reject each rule) |
| FE-27 | Admin: rule version management page (table + diff view) |
| FE-28 | Admin: publish rule version with confirmation dialog |
| FE-29 | Invoice detail: match results show rule version with link |

### Testing

| ID | Task |
|----|------|
| TE-15 | E2E-07: Policy upload → extract → publish → applied in match |
| TE-16 | Unit: rule version publish archives previous |
| TE-17 | Unit: tolerance resolution with vendor-specific rule from policy |
| TE-18 | Integration: policy rule published → match uses new tolerance |

**Week 8 Exit Criteria**: Full V1 feature complete. Customer pilot-ready.

---

## Dependency Map

```
DA-01 (docker-compose) → all other tickets depend on this
BE-02 (migrations) → BE-04, BE-06, BE-12, BE-13 ...
BE-07 (Celery) → BE-08, BE-09, BE-10
BE-13 (match engine) → BE-15 (exception creation)
BE-16 (approval routing) → FE-10, FE-11
BE-36 (policy upload) → BE-37 (LLM parse) → BE-38 (rule version)
```

---

## Demo Script (Week 2 Milestone)

```
1. Login as AP Analyst (analyst@demo.com)
2. Upload sample_invoice.pdf
3. Watch status: received → extracting → extracted → matching → exception
4. Navigate to Exception Queue
5. Open PRICE_MISMATCH exception
6. Read match evidence (invoice price vs PO price)
7. Add comment: "Vendor confirmed rate increase"
8. Resolve exception
9. Navigate to Approvals (as Approver role)
10. Approve invoice
11. Navigate to KPI Dashboard
12. Observe touchless rate updated
```
