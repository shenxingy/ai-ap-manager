# Goal: P1/P2 Feature Review & Fix Pass

## Context

The AI AP Manager has had 19 new commits implementing P1/P2 features (approval matrix,
CSV import, duplicate detection, vendor comms/compliance, recurring patterns, fraud incidents,
analytics, backend tests). This review pass audits those new features for correctness,
security, and production-readiness — fixing real bugs only (no new features).

**Current baselines (verified before loop start):**
- `from app.main import app` → OK (no import errors)
- `pytest tests/ -x -q` → 21 passed
- `npm run build` → exits 0, 2 ESLint warnings (useEffect deps)
- 62 API routes registered

**Known issues to fix (P0 — fix immediately):**

1. **ESLint warnings in exception-routing admin page** — `useEffect` missing deps
   (`rule` at line 174, `editRule` at line 185 in `frontend/src/app/(app)/admin/exception-routing/page.tsx`)
   Fix: add deps to the dependency array or use `useCallback` pattern.

2. **Auth coverage audit on new endpoints** — Verify every new router in:
   `fraud_incidents.py`, `recurring_patterns.py`, `analytics.py`, `import_routes.py`,
   `portal.py`, `approval_matrix.py`
   has `get_current_user` or `require_role` on mutating endpoints.
   Read each file; fix missing guards.

3. **Missing frontend pages for new features** — Verify these pages exist and render (npm run build):
   - `/admin/fraud` (fraud incidents list)
   - `/admin/recurring-patterns` (recurring patterns)
   - `/admin/approval-matrix` (approval matrix rules)
   - `/admin/import` (CSV bulk import)
   - `/admin/vendors/[id]` (vendor compliance docs)
   - `/approvals` (approval queue)
   Fix missing pages by reading existing similar pages and building minimal but functional UIs.

4. **Duplicate detection endpoint coverage** — Ensure `POST /invoices/upload` (or extraction worker)
   calls `duplicate_detection.py` and sets `Invoice.is_duplicate = True` when detected.
   Verify the duplicate check result is surfaced on the invoice detail page.

## Review Dimensions

### 1. Security
- All mutating endpoints (`POST`, `PATCH`, `DELETE`) have auth guard
- `portal.py` vendor endpoints: vendor can only access their own invoices (check vendor_id filter)
- `import_routes.py`: uploaded CSV is validated row-by-row; bad rows are rejected with 422, not 500
- HMAC approval tokens: verify `hmac.compare_digest` is used (not `==`)
- No raw f-string SQL anywhere in new files

### 2. API Correctness
- `GET /fraud-incidents` returns proper paginated schema
- `GET /recurring-patterns` returns patterns with `invoice_count`, `avg_amount`
- `GET /analytics/process-mining` returns valid JSON (not 500 on empty data)
- `GET /analytics/anomalies` handles empty invoice set gracefully
- `POST /import/csv` validates required columns; returns row-level errors array
- `GET /approval-matrix` returns matrix rules ordered by priority
- `PATCH /approval-matrix/{id}` updates threshold/approver_ids correctly
- Vendor portal: `GET /vendors/portal/invoices` filtered by vendor_id from token

### 3. Frontend Correctness
- Fix the 2 `useEffect` ESLint warnings in exception-routing page
- Analytics page: check that empty state (no data) shows a message, not a broken chart
- Approvals page: only shows tasks assigned to current user
- Fraud page: shows open/closed incidents, allows outcome update
- Import page: CSV file picker, shows row-level errors inline
- Approval-matrix admin: CRUD for rules (add/edit/delete rows)

### 4. Type Safety
- No `@ts-ignore` or `any` without justification in new frontend files
- `npm run build` must still exit 0 after all fixes

### 5. Error Handling
- Analytics endpoints return 200 with empty arrays (not 500) when DB is empty
- Import endpoint returns structured `{imported: N, errors: [{row, reason}]}` response
- Duplicate detection service: if external check fails, logs warning but does NOT block invoice

### 6. Database Integrity
- All new models have FKs with appropriate `ondelete` cascade or RESTRICT
- `alembic upgrade head` runs cleanly inside Docker
- No migration defines a column as NOT NULL without a server_default (breaks existing rows)

### 7. Code Quality
- No unused imports in new Python files (run `python -c "from app.X import Y"` spot checks)
- No `console.log` in new frontend pages (only `console.error`)
- Files stay under 1500 lines each

## Success Criteria

All of the following must be true when CONVERGED:

1. `docker exec ai-ap-manager-backend-1 python -c "from app.main import app; print('OK')"` → OK
2. `cd frontend && npm run build` exits 0 with **zero** warnings (ESLint warnings fixed)
3. `docker exec ai-ap-manager-backend-1 python -m pytest tests/ -x -q` → all pass
4. Every mutating endpoint in the 6 new routers has auth protection (grep-verifiable)
5. `git status` clean — no uncommitted changes

## Worker Instructions

- Work in `/home/alexshen/projects/ai-ap-manager`
- Backend container: `docker exec ai-ap-manager-backend-1`
- Use `committer "fix/refactor/chore: message" file1 file2` — NEVER `git add .`
- Read files before editing
- After each fix, re-run the relevant success criterion
- Fix bugs only — do NOT add new features or refactor working code
- If a page is completely missing from frontend, build a minimal but working one
