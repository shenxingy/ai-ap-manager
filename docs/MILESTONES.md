# Milestones & Development Plan

> **Updated 2026-02-26 after competitive analysis.**
> New MVP additions (dual-pass extraction, email approval, GL coding, fraud scoring) are integrated below.
> Realistic team size assumed: 1-2 engineers.

---

## Pre-Sprint: Technical Spike (Day 1 — 2 hours)

**Before writing any application code**, validate the core extraction pipeline.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
pip install pytesseract anthropic pdf2image pillow
python scripts/extraction_spike.py path/to/sample_invoice.pdf
```

**Decision gate**:
- Tesseract produces readable text → keep `USE_CLAUDE_VISION=false`, proceed with dual-pass architecture
- Tesseract text is garbled (scanned invoice) → set `USE_CLAUDE_VISION=true`, use Claude Vision directly

**Do not skip this.** Building 40 tickets on a broken OCR assumption is the most expensive mistake possible.

---

## Week 1-2: Infrastructure + Core Extraction Pipeline

**Goal**: System boots, invoices can be uploaded and extracted, match engine works. No frontend yet.

### Data & Infra (Do First)

| ID | Task |
|----|------|
| DA-01 | `docker-compose.yml`: postgres, redis, minio, backend, celery worker |
| DA-02 | `.env` from `.env.example`, MinIO bucket creation script |
| DA-03 | Alembic initial migration: all MVP tables (invoices, vendors, PO, GRN, users, audit_logs, approval_tokens) |
| DA-04 | Seed script: 5 vendors, 10 POs, 8 GRNs, 3 users (admin, analyst, approver), rule_version v1 |

### Backend

| ID | Task |
|----|------|
| BE-01 | FastAPI app skeleton: main.py, CORS, health check, global exception handlers |
| BE-02 | SQLAlchemy 2.0 async engine + session dependency |
| BE-03 | JWT auth: login, refresh, `get_current_user` dependency |
| BE-04 | RBAC: `require_role()` decorator, enforce on all routes |
| BE-05 | MinIO client: `upload_file()`, `get_signed_url()` helpers |
| BE-06 | `POST /invoices/upload` → MinIO + DB, enqueue extraction task |
| BE-07 | Celery setup: worker, beat, Redis broker, task routing |
| BE-08 | OCR task: Tesseract OR Claude Vision (reads `USE_CLAUDE_VISION` env var) → raw text |
| BE-09 | **Dual-pass LLM extraction**: Pass A (structured) + Pass B (document understanding) → field comparator |
| BE-10 | Extraction validation: schema check + math check (line sum ≈ total) + mismatch flagging |
| BE-11 | Duplicate detection service |
| BE-12 | Master data validation (vendor fuzzy match, PO lookup) |
| BE-13 | Audit log: `write_audit_log()` helper, append-only, call on every state transition |
| BE-14 | 2-way match engine + tolerance loader from active rule_version |
| BE-15 | Exception creation service (from match results) |
| BE-16 | **Basic fraud scoring**: rule-based signals (bank change, amount spike, new vendor) → score + level |
| BE-17 | Auto-approve engine (MATCHED + amount < threshold → approved, audited) |
| BE-18 | Approval routing: matrix lookup → create `approval_task` records |
| BE-19 | **Email approval tokens**: HMAC-sign token, store in `approval_tokens`, `GET /approvals/email?token=` handler |
| BE-20 | Exception endpoints: list (with filters), detail, update (status/assign/note), comment, resolve |
| BE-21 | Approval endpoints: list (my tasks), approve, reject (in-app) |
| BE-22 | KPI: `/kpi/summary` + `/kpi/trends` |
| BE-23 | **GL coding suggestion**: frequency-based lookup, `GET /invoices/{id}/gl-suggestions` |

### Testing (Week 2)

| ID | Task |
|----|------|
| TE-01 | Unit: match engine — exact match, within tolerance, price mismatch, qty mismatch, PO not found |
| TE-02 | Unit: dual-pass comparator — agreement, numeric mismatch, date mismatch |
| TE-03 | Unit: fraud scoring — each signal fires correctly |
| TE-04 | Unit: email token — sign, validate, expired token rejected, already-used rejected |
| TE-05 | Integration: invoice upload → extraction pipeline → match → exception created |
| TE-06 | Integration: email approval token → task approved → invoice status updated |

**Week 2 Exit Criteria**: All unit tests pass. Can `curl` the API to upload a PDF, see extraction result, see match result, see exception created. No frontend needed yet.

---

## Week 3-4: Frontend + Full Exception/Approval UX

**Goal**: End-to-end demo-ready flow in the browser. E2E-01 and E2E-02 pass.

### Backend

| ID | Task |
|----|------|
| BE-24 | 3-way match engine (GRN aggregation, partial receipt) |
| BE-25 | SLA tracking: `sla_due_at` on exceptions, Celery beat → SLA breach exception |
| BE-26 | `GET /invoices/{id}/audit` — full timeline |
| BE-27 | `PATCH /invoices/{id}/fields` — field correction (manual override, logged) |
| BE-28 | `POST /invoices/{id}/trigger-match` — re-run match after correction |
| BE-29 | `POST /invoices/{id}/gl-coding/confirm` — bulk confirm GL suggestions |

### Frontend

| ID | Task |
|----|------|
| FE-01 | Next.js 14 + Tailwind + shadcn/ui + TanStack Query + Zustand scaffold |
| FE-02 | API client with auth header injection, 401 redirect, error toast |
| FE-03 | Login page + JWT cookie management via Next.js API route |
| FE-04 | App shell: sidebar nav, role-based route guards |
| FE-05 | Invoice upload page: drag-drop + progress indicator (polling status) |
| FE-06 | Invoice list: table + status/vendor/date/amount filters + pagination |
| FE-07 | **Invoice detail — 6 tabs**: Overview (with GL suggestion cells + Confirm All button), Match Results, Exceptions, Approvals, Communications (stub), Audit Trail |
| FE-08 | Invoice detail — dual-pass mismatch highlighting (amber fields) |
| FE-09 | Exception queue: table + SLA urgency colors + bulk assign |
| FE-10 | Exception detail: evidence panel (invoice vs PO side-by-side) + comment thread + resolve |
| FE-11 | Approval tasks list + inline quick approve/reject |
| FE-12 | Approval detail: invoice read-only + PDF viewer + approve/reject with note |
| FE-13 | **Email approval page** `/approvals/email?token=` — no auth, mobile-friendly, 4 states |
| FE-14 | KPI dashboard: 4 metric cards + touchless trend chart + exception type chart |
| FE-15 | AP Analyst workbench: summary cards + needs-action feed |
| FE-16 | **Fraud badge** in invoice header (🟢/🟡/🔴 with signal tooltip) |

### Testing (Week 4)

| ID | Task |
|----|------|
| TE-07 | E2E-01: Happy path — touchless auto-approved invoice |
| TE-08 | E2E-02: Price mismatch → exception → resolve → approve |
| TE-09 | E2E-18: Email approval token — approve from email link |
| TE-10 | E2E-22: Fraud flag — bank account change → HIGH risk → exception created |
| TE-11 | E2E-23: Dual-extraction mismatch → fields highlighted in UI |
| TE-12 | E2E-14: Low OCR confidence → manual review forced |

**Week 4 Exit Criteria**: Demo script runs end-to-end. All 6 E2E tests above pass.

---

## Week 5-6: Integration Layer, Vendor Hub, RBAC

**Goal**: CSV imports work, vendor communication hub live, full role enforcement.

### Backend

| ID | Task |
|----|------|
| BE-30 | CSV import: POs, GRNs, vendors |
| BE-31 | Full RBAC enforcement audit (every endpoint checked against role matrix) |
| BE-32 | `vendor_messages` table + `POST /invoices/{id}/messages` (internal + vendor-facing) |
| BE-33 | Vendor magic-link auth (email link → session token, no password) |
| BE-34 | Vendor portal API: invoice status, message thread, compliance doc upload |
| BE-35 | `vendor_compliance_docs` tracking + missing doc alert before payment |
| BE-36 | KPI trend endpoint with day/week granularity |
| BE-37 | Recurring invoice detection: Celery beat weekly job → `recurring_invoice_patterns` |
| BE-38 | Fast-track workflow for recurring invoices |
| BE-39 | Exception auto-routing by type (pricing → procurement role, GRN → warehouse role) |

### Frontend

| ID | Task |
|----|------|
| FE-17 | Admin: CSV import UI + progress + row-level error report |
| FE-18 | Admin: vendor master data page |
| FE-19 | Admin: approval matrix config UI (editable table) |
| FE-20 | Invoice detail: Communications tab — internal + vendor thread, attach files |
| FE-21 | Vendor portal: invoice status page + message reply + compliance doc upload |
| FE-22 | Admin: recurring invoice patterns page |
| FE-23 | Audit log explorer (AUDITOR role) |

**Week 6 Exit Criteria**: E2E-20 (vendor communication) and E2E-21 (recurring fast-track) pass.

---

## Week 7-8: Policy Parsing, Rule Versioning, Fraud Upgrade

**Goal**: Admin can extract rules from contracts, publish rule versions, full fraud behavioral detection.

### Backend

| ID | Task |
|----|------|
| BE-40 | Policy doc upload + pdfplumber text extraction |
| BE-41 | LLM policy parsing → `policy_rules` (extracted, unreviewed) |
| BE-42 | Rule version CRUD: draft → in_review → published (Redis cache, invalidate on publish) |
| BE-43 | Vendor-specific tolerance resolution from published rule version |
| BE-44 | Rule version diff (compare two versions) |
| BE-45 | Fraud upgrade: vendor bank account change detection, ghost vendor (shared bank), dual-auth flow |
| BE-46 | GL coding ML classifier: train on confirmed history, weekly retrain, A/B vs frequency baseline |

### Frontend

| ID | Task |
|----|------|
| FE-24 | Admin: policy doc upload + extraction status |
| FE-25 | Admin: extracted rule review (confirm / reject each AI-suggested rule) |
| FE-26 | Admin: rule version management + diff view |
| FE-27 | Invoice detail: match tab shows rule version badge + link |
| FE-28 | Admin: fraud incident log |

**Week 8 Exit Criteria**: E2E-07 (policy → rule → match) passes. V1 complete. Pilot-ready.

---

## Dependency Map

```
DA-01 (docker-compose) ──→ everything
DA-03 (migrations) ──→ BE-06, BE-14, BE-16, BE-18...
BE-07 (Celery) ──→ BE-08, BE-09
BE-09 (extraction) ──→ BE-14 (match)
BE-14 (match) ──→ BE-15 (exceptions)
BE-15 (exceptions) ──→ BE-18 (approval routing)
BE-18 + BE-19 (approval) ──→ FE-11, FE-12, FE-13
BE-40 (policy upload) ──→ BE-41 ──→ BE-42 (rule versions)
```

---

## Demo Script (Week 4 Milestone — Full Browser Demo)

```
1.  Login as AP Analyst (analyst@demo.com / demo123)
2.  Upload invoice_acme_001.pdf
3.  Watch status bar: received → extracting → matching → exception
4.  [If dual-pass mismatch] See amber highlighted field, correct it
5.  Notice fraud badge: 🟢 LOW
6.  Navigate to Exception Queue
7.  Open PRICE_MISMATCH exception — read evidence panel (invoice $74 vs PO $60)
8.  Add comment: "Vendor confirmed Q1 rate amendment"
9.  Resolve exception
10. Logout, login as Approver (approver@demo.com)
11. See approval task in My Approvals ($14,800 from Acme Corp)
12. Click into detail, view PDF, click Approve
13. Logout, check email inbox (or console log): approval notification shows "Approve" link
14. Click email Approve link in browser (no login required)
15. Login as AP Analyst
16. Navigate to KPI Dashboard
17. Confirm: touchless rate updated, cycle time calculated
```

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
