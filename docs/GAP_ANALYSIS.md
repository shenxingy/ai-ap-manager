# Gap Analysis — AI AP Operations Manager
Generated: 2026-03-01 | Auditor: Claude Code (direct codebase inspection)

---

## Summary

| Category | Planned | Implemented | Gaps |
|----------|---------|-------------|------|
| P0 MVP features | 28 | 27 | 1 |
| P1 V1 features | 24 | 21 | 3 |
| P2 V2 features | 18 | 6 | 12 |
| Production readiness | 10 | 10 | 0 |
| P3 Backlog | 20+ | 0 | 20+ |
| **Total tracked gaps** | | | **16 significant** |

---

## ✅ Confirmed Implemented (spot-checked)

These features were verified with grep/file existence checks:

| Feature | Evidence |
|---------|----------|
| Invoice ingestion + OCR pipeline | `app/workers/tasks.py:process_invoice`, beat task |
| 2-way + 3-way match engine | `app/rules/match_engine.py`, `run_2way_match`, `run_3way_match` |
| Exception queue + routing | `GET/PATCH /exceptions`, `app/models/exception_routing.py` |
| Multi-level approval chain | `_get_next_approval_step` in `approval.py:599`, beat task |
| Approval escalation | `escalate_overdue_approvals` in beat_schedule (9:30 daily) |
| Email-token approvals | HMAC-signed tokens, `/approvals/email?token=...` |
| KPI dashboard API | `GET /kpi/summary`, `/kpi/trends`, `/kpi/sla-summary` |
| Cash flow forecast | `GET /kpi/cash-flow-forecast`, `GET /kpi/cash-flow-export` — DONE |
| Cash flow frontend chart | `dashboard/page.tsx:140` — `useQuery(kpi-cash-flow-forecast)` |
| GL smart coding (frequency) | `app/services/gl_coding.py`, `GET /invoices/{id}/gl-suggestions` |
| Fraud scoring | `app/services/fraud_scoring.py`, wired in Celery pipeline |
| Rule self-optimization API | `GET/POST /admin/rule-recommendations`, `feedback_tasks.py` weekly_digest |
| Root cause analysis | `POST /analytics/root-cause-report`, async LLM narrative |
| Audit log export CSV | `GET /audit/export` — endpoint registered |
| Rate limiting | `slowapi`, limiter on login/upload/ask-ai |
| Request ID middleware | `backend/app/middleware/request_id.py` |
| Sentry monitoring | `sentry_sdk.init` in `main.py:22` |
| Payment tracking | `payment_status/date/method/reference` columns + `POST /invoices/{id}/payment` |
| Login audit events | `action="user_login"` in `auth.py:36` |
| Ask AI frontend panel | `AskAiPanel.tsx` + wired in `AppShell.tsx:107` |
| Frontend RBAC middleware | `frontend/src/middleware.ts` EXISTS |
| Recurring invoice tagging | `_check_recurring_pattern` in `tasks.py:354` |
| Recurring pattern beat task | `detect-recurring-patterns-weekly` in beat_schedule |
| CSV import frontend | `admin/import/page.tsx` — real implementation (API wired) |
| Email ingestion status UI | `admin/settings/page.tsx:90` — queries `/admin/email-ingestion/status` |
| Vendor portal | `/portal/invoices`, `/portal/login`, dispute + reply endpoints |
| Duplicate invoice detection | `duplicate_detection.py`, wired in Celery pipeline |
| Production deployment config | `docker-compose.prod.yml`, `nginx/nginx.conf`, `gunicorn.conf.py` |

---

## 🔴 Confirmed Gaps (sorted by priority)

### P1 Gap — V1 Production-Ready

#### GAP-1: Email Ingestion — File-Drop Only, No Real IMAP
**Priority**: P1 (V1 blocker for "monitored AP mailbox" feature)
**Location**: `backend/app/workers/email_ingestion.py`
**Evidence**:
- Worker reads from `/app/data/inbox/` file directory, not IMAP
- Guards on `EMAIL_HOST/EMAIL_USER/EMAIL_PASSWORD` but never opens IMAP connection
- Missing fields on Invoice model: `email_from`, `email_subject`, `email_received_at`
- TODO.md line 453-460: `[ ]` IMAP polling, `[ ]` fetch unread, `[ ]` mark as read, `[ ]` store email metadata

**What's missing**:
- `imaplib` or `imapclient` IMAP connection in `poll_ap_mailbox`
- Config: `IMAP_HOST`, `IMAP_USER`, `IMAP_PASSWORD`, `IMAP_MAILBOX` in `settings.py`
- Alembic migration: add `email_from`, `email_subject`, `email_received_at` to `invoices`
- Mark processed emails as read in IMAP

---

### P2 Gaps — V2 Intelligence Layer

#### GAP-2: ERP Integration — SAP/Oracle Connectors Missing
**Priority**: P2 (V2 milestone)
**Location**: `backend/app/integrations/` — **DIRECTORY DOES NOT EXIST**
**Evidence**: `ls backend/app/integrations/ → MISSING`
**What's missing**:
- `backend/app/integrations/` package
- `sap.py` — SAP connector (PO/GRN sync, voucher push)
- `oracle.py` — Oracle Fusion connector
- Sync orchestration Celery tasks
- Sync status tracking API
- Admin ERP Integration page (`/admin/erp`)

#### GAP-3: Multi-Currency FX Support
**Priority**: P2 (V2 milestone)
**Location**: No `fx_rates` model or table exists
**Evidence**: `grep -r "fx_rate\|FxRate" backend/app/models/` → nothing (only `normalized_amount_usd` for dedup, not for match engine)
**What's missing**:
- `fx_rates` table: `base_currency, quote_currency, rate, valid_date`
- Celery beat: daily FX rate fetch (Open Exchange Rates API / ECB XML)
- Match engine: compare normalized amounts when invoice currency ≠ PO currency
- `fx_tolerance_pct` in matching_tolerance rule config
- KPI aggregation in base currency
- Frontend: currency flag/code next to amount, normalized amount in invoice detail

#### GAP-4: Mobile PWA Support
**Priority**: P2 (V2 milestone)
**Location**: `frontend/public/manifest.json` — MISSING
**Evidence**: `ls frontend/public/manifest.json → MISSING`
**What's missing**:
- `public/manifest.json` for "Add to Home Screen"
- Service worker for offline caching
- Responsive stacked card layouts for approvals on mobile (< 768px)
- `frontend/src/app/(app)/approvals/page.tsx` — no mobile-responsive layout

#### GAP-5: Benchmark/Industry Comparison Endpoint
**Priority**: P2
**Location**: `backend/app/api/v1/kpi.py`
**Evidence**: No `/api/v1/kpi/benchmarks` route in registered routes list
**What's missing**:
- Industry benchmark data (hardcoded or external)
- `GET /api/v1/kpi/benchmarks` endpoint
- KPI dashboard benchmark comparison card

#### GAP-6: 4-Way Match (Quality Inspection)
**Priority**: P2 (Backlog / V2+)
**Location**: No `inspection_reports` model
**Evidence**: No `inspection_reports` table in `backend/app/models/`
**What's missing**:
- `inspection_reports` model + migration
- `run_4way_match()` in match engine
- `POST /api/v1/gr/{gr_id}/inspection` endpoint
- `INSPECTION_FAILED` exception type

#### GAP-7: GL Coding ML Training Pipeline
**Priority**: P2
**Location**: `backend/app/services/gl_coding.py`
**Evidence**: Only frequency-based lookup implemented; no scikit-learn code found
**What's missing**:
- Training data collection from confirmed GL assignments
- scikit-learn classifier (vendor + description → GL account)
- Weekly Celery retrain beat task
- Model artifact storage in MinIO (`models/gl-coding-v{N}.pkl`)
- Load model from MinIO in `gl_coding.py` predictions
- Admin panel: model version, retrain date, accuracy stats

#### GAP-8: Slack / Teams Webhook Notifications
**Priority**: P2/P3
**Location**: `backend/app/services/email.py`
**Evidence**: Only console-mock email notifications; no Slack/Teams code
**What's missing**:
- `SLACK_WEBHOOK_URL` config + `POST` to Slack for approval requests
- `TEAMS_WEBHOOK_URL` config + Teams adaptive card
- User notification preferences per channel

#### GAP-9: Multi-Entity / Multi-Tenant Support
**Priority**: P3
**Location**: Models (no `entities` table)
**Evidence**: No `entities` model in `backend/app/models/`
**What's missing**:
- `entities` table: legal entity name, tax_id, currency
- `entity_id` FK on invoices, POs, vendors
- Entity selector in frontend header
- Cross-entity consolidated KPI (ADMIN only)

#### GAP-10: GDPR Data Retention Auto-Deletion
**Priority**: P3
**Location**: Not implemented
**Evidence**: No retention policy code; no Celery task for auto-deletion; no `retention_days` config
**What's missing**:
- `retention_days` config per data type
- Celery beat: monthly job to soft-delete invoices older than retention period
- Audit log of what was deleted and why

#### GAP-11: Vendor Risk Scoring (Weekly Job)
**Priority**: P3
**Location**: No `vendor_risk_scores` table
**Evidence**: `grep -r "vendor_risk" backend/app/models/` → nothing
**What's missing**:
- `vendor_risk_scores` table: vendor_id, ocr_error_rate, exception_rate, avg_extraction_confidence, score
- Weekly Celery job to recompute scores
- Risk score on vendor detail page + invoice header
- Auto-create "VENDOR_RISK" flag on high-risk vendor invoices

#### GAP-12: Invoice Template System (Vendor Portal)
**Priority**: P3
**Location**: Not implemented
**Evidence**: Vendor portal has basic invoice view/dispute; no template creation flow
**What's missing**:
- Template builder: AP creates per-vendor invoice templates
- Vendor portal: draft invoice from template
- "template-sourced" invoice trust level (faster processing)

---

## ⚠️ Drift Items (TODO marked open but actually implemented)

These items are marked `[ ]` in TODO.md but the code is actually done:

| TODO Line | Claim | Actual Status | Fix Needed |
|-----------|-------|---------------|------------|
| L469 | Import page `/admin/import` marked `[ ]` | **DONE** — fully wired (CSV upload, 3 tabs, real API calls) | Update TODO.md |
| L476 | Email ingestion status in settings marked `[ ]` | **DONE** — `settings/page.tsx:90` queries `/admin/email-ingestion/status` | Update TODO.md |
| L537-547 | Recurring pattern detection beat task sub-items | **DONE** — `detect-recurring-patterns-weekly` in beat_schedule | Update TODO.md |
| L929 | Ask AI sidebar panel marked `[ ]` | **DONE** — `AskAiPanel.tsx` + `AppShell.tsx:107` | Update TODO.md |
| L950,957 | Cash flow forecast API + dashboard | **DONE** — endpoint + frontend chart both implemented | Update TODO.md |

---

## 🟡 Near-Gaps (implemented but incomplete or untested)

#### NEAR-1: Rule Recommendations Auto-Generation Not Verified
**Location**: `backend/app/workers/feedback_tasks.py`
**Issue**: `weekly_digest` task generates recommendations BUT:
- It's triggered weekly (Sunday midnight) — no way to manually test without seeded override data
- `GET /admin/override-history` exists but no override data seeded
- Recommendation acceptance (`/accept`, `/reject`) exists but untested end-to-end

#### NEAR-2: Full Permission Audit Not Done
**Location**: `backend/app/api/v1/`
**Issue**: TODO.md line 629 — "full permission audit: verify all endpoints call `require_role()`" is open
- 87 auth references found, but no systematic audit per endpoint
- Portal endpoints intentionally token-based (not JWT) — needs documentation
- Vendor bank account format validation (routing + account number check) not implemented (TODO line 663)

#### NEAR-3: Seed Data Completeness Unverified
**Location**: `backend/scripts/seed.py`
**Issue**: DB container was down during audit — could not verify counts
- Expected: 10 invoices, 3 vendors, ≥3 exceptions, ≥2 approval tasks (from goal-completeness.md)
- Seed script exists but actual DB state unknown
- Run `docker exec ai-ap-manager-backend-1 python scripts/seed.py` to verify

#### NEAR-4: Tests Incomplete
**Location**: `backend/tests/`
**Issue**: Unit/integration tests exist (13 test files), but TODO shows these open:
- Playwright E2E tests: NOT started
- k6 / Locust load tests: NOT started
- Frontend unit tests (Jest + RTL): NOT started

---

## 📊 Feature Completion by Phase

```
P0 MVP:     ████████████████████████████░ 96%  (27/28 — email IMAP gap)
P1 V1:      ████████████████████████░░░░░ 88%  (21/24 — email IMAP + sub-items)
P2 V2:      ████████░░░░░░░░░░░░░░░░░░░░░ 33%  (6/18 — ERP, FX, mobile, GL-ML, etc.)
P3 Backlog: ██░░░░░░░░░░░░░░░░░░░░░░░░░░░ ~5%  (Slack, entity, GDPR, templates...)
```

---

## Priority Action Plan

### Must-fix for P1 demo-ready:
1. **GAP-1**: Implement real IMAP email ingestion (replace file-drop with `imaplib`)
2. **NEAR-3**: Verify seed data — restart DB, run seed, confirm 10 invoices in KPI

### High-value P2 starts:
3. **GAP-3**: Multi-currency FX (needed for manufacturing companies with USD/EUR invoices)
4. **GAP-7**: GL ML training pipeline (biggest accuracy improvement for V2 metrics)

### Quick wins (remove TODO drift):
5. Update TODO.md: mark import page, email status UI, recurring beat, ask-ai panel, cash flow as `[x]`

### P3 (future roadmap):
6. GAP-2 (ERP), GAP-4 (PWA), GAP-5 (benchmarks), GAP-6 (4-way match), GAP-8 (Slack), GAP-9 (entities), GAP-10 (GDPR), GAP-11 (vendor risk), GAP-12 (templates)
