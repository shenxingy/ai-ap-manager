# AI AP Manager — P2 V2 Feature Implementation Plan
**Date**: 2026-02-27
**Saved to**: `docs/plans/2026-02-27-p2-v2-intelligence-layer.md`

---

## Context

P0 (MVP) and P1 (V1) are complete. 68 API routes live, 21 tests passing, frontend build clean.
This plan delivers the P2 "V2 Intelligence Layer" — the features that make the system learn,
alert, and assist. We are NOT building ERP integration or the full Vendor Portal (those warrant
dedicated goals with external system access). We ARE building everything else in the V2 milestone.

---

## What's Being Built

### 1. AI Self-Optimization — Feedback Loop + Rule Recommendations
The system tracks every human correction (extracted field fix, GL override, exception resolution),
analyzes correction patterns weekly, and surfaces `rule_recommendations` for admin review.

**New DB tables**: `ai_feedback` · `rule_recommendations`
**New API**: `GET /admin/rule-recommendations` · `POST /admin/rule-recommendations/{id}/accept` · `POST /reject`
**Hook points**: `PATCH /invoices/{id}/fields` · `PUT /invoices/{id}/lines/{id}/gl` · `PATCH /exceptions/{id}`
**New Celery beat**: weekly `analyze_ai_feedback` task (Sunday midnight)
**New frontend page**: `/admin/ai-insights` — correction rate stats + recommendation cards

### 2. Root Cause LLM Narrative + Weekly Digest
Completes the Analytics page. A single Claude call generates a 3-5 paragraph narrative combining
process mining bottlenecks and anomaly alerts. Reports are stored and browsable.

**New DB table**: `analytics_reports`
**New API**: `POST /analytics/root-cause-report` (async, returns report_id) · `GET /analytics/reports` (list)
**New Celery beat**: weekly auto-digest (Monday 8 AM UTC) → mock-email + store report
**Frontend addition**: "Generate Report" button + polling + report history list on `/analytics`

### 3. SLA Alerting
Daily Celery job checks `invoices.due_date`. Invoices pending approval within 3 days get a warning;
overdue invoices get a critical alert. All alerts logged in `sla_alerts` table.

**New DB table**: `sla_alerts`
**New config keys**: `SLA_WARNING_DAYS_BEFORE: int = 3`
**New Celery beat**: daily `check_sla_alerts` (8 AM UTC)
**New API filter**: `GET /invoices?overdue=true`
**Frontend additions**: red "Overdue" badge on invoice list · dashboard warning card for approaching invoices

### 4. Bulk Operations
AP teams process many exceptions. Multi-select + bulk actions dramatically reduce repetitive work.

**New backend endpoints**:
- `POST /api/v1/exceptions/bulk-update` — batch status/assignment change (up to 100, audit-logged)
- `POST /api/v1/approvals/bulk-approve` — ADMIN-only batch approve (checks PENDING, creates individual audit entries)

**New frontend UI**: Checkbox column + bulk action toolbar in exceptions and approvals pages

---

## Architecture Decisions

### AI Feedback Logging
The `ai_feedback` table stores field-level corrections. The hook is placed **inside the async
FastAPI handler** (not in Celery) so it captures real-time corrections with the actor's user_id.
Pattern: sync DB session created inline (same as match engine endpoint pattern).

### Root Cause Report — Async Pattern
`POST /root-cause-report` triggers a Celery task, returns `{report_id, status: "pending"}`.
Frontend polls `GET /analytics/reports/{id}` until `status=complete`. This avoids HTTP timeouts
on slow LLM calls. Falls back to synchronous inline call if Celery unavailable.

### Beat Schedule — Centralized in celery_app.py
All new beat tasks go into one `celery_app.conf.beat_schedule` dict update at the bottom of
`backend/app/workers/celery_app.py`. Tasks must import lazily (inside the task function) to
avoid circular imports.

### Bulk Operations — Safety
`bulk-update` validates: list size ≤ 100, status is a valid transition, audit-logs each individual
item. `bulk-approve` verifies each task is `status=pending` before approving; skips non-pending
tasks with a log entry (no error thrown).

### shadcn/ui Checkbox
The Checkbox component is not yet installed. Task D (Operations Frontend) must run
`npx shadcn-ui@latest add checkbox` before building the bulk-select UI.

---

## File Ownership Map

### Task A — AI Self-Optimization Backend
**OWN (new files)**:
- `backend/app/models/feedback.py` — AiFeedback, RuleRecommendation models
- `backend/app/schemas/feedback.py` — Pydantic schemas
- `backend/app/services/feedback.py` — `log_field_correction()`, `log_gl_correction()`, `log_exception_correction()`
- `backend/app/workers/feedback_tasks.py` — `analyze_ai_feedback` Celery task
- `backend/app/api/v1/rule_recommendations.py` — CRUD endpoints

**MODIFY (shared files)**:
- `backend/app/models/__init__.py` — add AiFeedback, RuleRecommendation imports
- `backend/app/api/v1/router.py` — register rule_recommendations router
- `backend/app/api/v1/invoices.py` — hook feedback_svc in PATCH /fields and PUT /gl
- `backend/app/api/v1/exceptions.py` — hook feedback_svc in PATCH exception
- `backend/app/workers/celery_app.py` — add weekly analyze_ai_feedback beat task

**FORBIDDEN**: analytics.py, analytics_tasks.py, sla_tasks.py, fx_tasks.py

### Task B — Analytics Intelligence Backend
**OWN (new files)**:
- `backend/app/ai/root_cause.py` — LLM narrative generation
- `backend/app/models/analytics_report.py` — AnalyticsReport model
- `backend/app/schemas/analytics_report.py` — schemas
- `backend/app/workers/analytics_tasks.py` — weekly_digest Celery task
- `backend/app/api/v1/ask_ai.py` — POST /ask-ai with SQL whitelist safety

**MODIFY (shared files)**:
- `backend/app/models/__init__.py` — add AnalyticsReport import
- `backend/app/api/v1/analytics.py` — add POST /root-cause-report + GET /reports routes
- `backend/app/api/v1/router.py` — register ask_ai router
- `backend/app/workers/celery_app.py` — add weekly digest beat task

**FORBIDDEN**: feedback.py, feedback_tasks.py, sla_tasks.py, fx_tasks.py

### Task C — Operations Backend (SLA + Bulk)
**OWN (new files)**:
- `backend/app/models/sla_alert.py` — SlaAlert model
- `backend/app/schemas/sla.py` — SlaAlert schemas
- `backend/app/workers/sla_tasks.py` — check_sla_alerts daily Celery task

**MODIFY (shared files)**:
- `backend/app/models/__init__.py` — add SlaAlert import
- `backend/app/api/v1/invoices.py` — add `?overdue=true` filter param
- `backend/app/api/v1/exceptions.py` — add POST /bulk-update endpoint
- `backend/app/api/v1/approvals.py` — add POST /bulk-approve endpoint
- `backend/app/workers/celery_app.py` — add daily SLA beat task
- `backend/app/core/config.py` — add SLA_WARNING_DAYS_BEFORE setting

**FORBIDDEN**: feedback.py, analytics.py, ask_ai.py

### Task D — Intelligence Frontend
**OWN (new files)**:
- `frontend/src/app/(app)/admin/ai-insights/page.tsx`

**MODIFY**:
- `frontend/src/app/(app)/analytics/page.tsx` — add root cause report button + polling + history list

**FORBIDDEN**: exceptions page, approvals page, invoice pages (those belong to Task E)

### Task E — Operations Frontend
**MODIFY**:
- `frontend/src/app/(app)/invoices/page.tsx` — add overdue badge
- `frontend/src/app/(app)/exceptions/page.tsx` — add checkbox column + bulk action toolbar
- `frontend/src/app/(app)/approvals/page.tsx` — add bulk approve for ADMIN
- `frontend/src/app/(app)/dashboard/page.tsx` — add SLA warning card

**FORBIDDEN**: ai-insights page, analytics page, admin pages (those belong to Task D)

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Ask AI SQL injection | Whitelist of 5 tables only; use `text()` parameterized queries; NEVER allow DML |
| LLM cost on root-cause calls | Rate limit: max 1 report per 60 min per user; return cached report if < 1h old |
| Beat schedule merge conflicts | All 3 tasks modify celery_app.py — workers must be careful not to overwrite each other's entries; use dict-style additions |
| Checkbox component missing | Task E installs via `npx shadcn-ui@latest add checkbox` before building UI |
| models/__init__.py conflicts | Tasks A, B, C all add to this file; git auto-merge handles separate lines fine |
| SLA alerts duplicate firing | Deduplicate: check `sla_alerts` table for existing alert on same invoice + alert_type before inserting |

---

## Success Criteria

After this iteration, ALL of the following must be true:

1. `docker exec ai-ap-manager-backend-1 python -c "from app.main import app; print(len(app.routes))"` → ≥ 80
2. `cd frontend && npm run build` exits 0 with zero warnings
3. `docker exec ai-ap-manager-backend-1 python -m pytest tests/ -x -q` → all pass (≥ 21)
4. `docker exec ai-ap-manager-backend-1 alembic current` shows head (no pending migrations)
5. New pages compile and render: `/admin/ai-insights`
6. Analytics page has "Generate Root Cause Report" button
7. Invoice list shows overdue badge for past-due invoices
8. Exceptions page has checkbox multi-select + bulk update toolbar

---

## Parallelization

```
Wave 1 (parallel, no dependencies):
  Worker 1 → Task A (AI Self-Optimization Backend)
  Worker 2 → Task B (Analytics Intelligence Backend)
  Worker 3 → Task C (Operations Backend: SLA + Bulk)

Wave 2 (parallel, after Wave 1 merges to main):
  Worker 1 → Task D (Intelligence Frontend)
  Worker 2 → Task E (Operations Frontend)
```

Wave 2 frontend tasks should read the Wave 1 code to understand new API response shapes before building UIs.

---

## What's Deferred

- **ERP Integration** (SAP/Oracle) — needs real system credentials + pyrfc library
- **Vendor Portal** (separate layout, magic link auth) — dedicated goal
- **Multi-Currency Live Rates** (Open Exchange Rates API) — fx.py hardcoded rates are sufficient for now; the `fx_rates` DB table upgrade is low urgency
- **A/B Testing Framework** — P3 complexity
- **Email Ingestion (IMAP)** — P1 gap, separate focused goal
- **Communications Tab** — P1 gap, belongs in a P1 cleanup PR
