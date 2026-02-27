# Goal: Complete the AI AP Operations Manager — Full MVP + V1 Core

## Project Context

Working dir: `/home/alexshen/projects/ai-ap-manager`

**Tech stack**:
- Backend: FastAPI (Python 3.11) + SQLAlchemy 2.0 async + Celery + PostgreSQL 16 + Redis
- Frontend: Next.js 14 (App Router) + TypeScript + Tailwind CSS + shadcn/ui + TanStack React Query + Zustand
- Infrastructure: Docker Compose (all services running on host)
- Backend runs at `http://localhost:8002` (container port 8000, host port 8002)
- Frontend will run at `http://localhost:3000`

**Running containers** (already up, do NOT restart):
- `ai-ap-manager-backend-1` (backend, FastAPI on 8002)
- `ai-ap-manager-worker-1` (Celery worker)
- `ai-ap-manager-db-1` (PostgreSQL on 5433)
- `ai-ap-manager-redis-1` (Redis on 6380)

**Backend API base**: `http://localhost:8002/api/v1`
**Swagger docs**: `http://localhost:8002/api/docs`

**Commit rule**: always use `committer "type: message" file1 file2 ...` — never `git add .`

---

## What the System Should Do (End State)

### 1. Working Frontend Application (Next.js 14)

`frontend/` directory must be a fully runnable Next.js 14 app:
- `package.json` with all dependencies
- TypeScript + Tailwind CSS configured
- App Router structure under `frontend/src/app/`
- `npm run dev` starts on port 3000 without errors
- `npm run build` compiles without TypeScript errors

#### Pages Required:

**Login** (`/login`):
- Email + password form
- POST to `http://localhost:8002/api/v1/auth/token`
- Store JWT in Zustand auth store
- Redirect to `/dashboard` on success

**Dashboard** (`/dashboard`):
- 4 KPI cards: Touchless Rate, Exception Rate, Avg Cycle Time, Total Received
- Line chart (recharts): daily/weekly invoices received vs approved vs exceptions
- Period selector (7/30/90 days)
- Auto-refresh every 5 minutes
- Data from GET `/api/v1/kpi/summary` and `/api/v1/kpi/trends`

**Invoice List** (`/invoices`):
- Paginated table: invoice_number, vendor_name_raw, total_amount, status, fraud badge, created_at
- Filter bar: status multi-select, date range
- Upload button → drag-and-drop modal → POST `/api/v1/invoices/upload`
- Status color badges
- Fraud score badge (🟢/🟡/🔴/🔴🔴 by threshold)

**Invoice Detail** (`/invoices/[id]`):
- Header: invoice#, vendor, amount, status badge, fraud badge
- 6 tabs: Details | Line Items | Match | Exceptions | Approvals | Audit Log
- **Details tab**: extracted fields, confidence indicators, amber mismatched field highlights
- **Line Items tab**: table with GL suggestion column (grey suggestion + confidence %)
- **Match tab**: match status, header variance, line-by-line match table with color coding
- **Exceptions tab**: list of exceptions for this invoice
- **Approvals tab**: approval task status + history
- **Audit Log tab**: chronological timeline from GET `/api/v1/invoices/{id}/audit`

**Exception Queue** (`/exceptions`):
- Filterable table: code, severity, status, assigned_to, invoice link
- Slide-out detail panel with comment thread + status update form
- PATCH `/api/v1/exceptions/{id}` on save

**Approvals** (`/approvals`):
- List of pending approval tasks for logged-in user
- Approve/Reject with notes modal
- POST `/api/v1/approvals/{task_id}/approve` and `/reject`

**App Shell**:
- Sidebar: Dashboard · Invoices · Exceptions · Approvals
- Top header: user info, logout
- Role-aware nav (APPROVER only sees Approvals + Invoices)
- Protected routes (redirect to /login if not authenticated)

---

### 2. Backend P0 Gaps (remaining endpoints)

**Field Correction**:
- `PATCH /api/v1/invoices/{id}/fields` — AP_ANALYST+
  - Body: `{field_name: str, corrected_value: any}`
  - Update Invoice or InvoiceLineItem field
  - Audit log: action="field_corrected"

**Exception Comments**:
- DB: `exception_comments` table (id UUID, exception_id FK, author_id FK, body TEXT, created_at)
- Alembic migration
- `ExceptionComment` SQLAlchemy model in `app/models/exception_record.py`
- `POST /api/v1/exceptions/{id}/comments` — AP_ANALYST+ (audit-logged)
- `GET /api/v1/exceptions/{id}/comments` — AP_CLERK+

**GL Coding Confirmation**:
- `PUT /api/v1/invoices/{id}/lines/{line_id}/gl`
  - Body: `{gl_account: str, cost_center?: str}`
  - Update InvoiceLineItem.gl_account
  - Audit log: "gl_coding_confirmed" if matches suggestion, "gl_coding_overridden" if different

**Current User**:
- `GET /api/v1/users/me` — return current user (id, email, name, role)

---

### 3. Backend P1 High-Value Features

**3-Way Match Engine**:
- `run_3way_match(db, invoice_id)` in `app/rules/match_engine.py`
  - Load all GRNs for invoice's PO
  - Aggregate received qty per po_line_item across all GRNs
  - Check: invoice_qty ≤ total_grn_qty (with tolerance)
  - Exception codes: GRN_NOT_FOUND, QTY_OVER_RECEIPT
  - Auto-select: if GRN exists for PO → use 3way, else fallback to 2way
- Update POST `/api/v1/invoices/{id}/match` to accept `?match_type=3way`

**Exception Auto-Routing**:
- `exception_routing_rules` table: id, exception_code, target_role, is_active
- Alembic migration + SQLAlchemy model
- Auto-assign when exception created: look up routing rule → find user with that role → set assigned_to
- Default rules seeded: PRICE_VARIANCE→AP_ANALYST, MISSING_PO→AP_ANALYST, FRAUD_FLAG→ADMIN
- `GET /api/v1/admin/exception-routing` (ADMIN)
- `POST /api/v1/admin/exception-routing` (ADMIN)

**Admin User Management**:
- `GET /api/v1/admin/users` — paginated list (ADMIN)
- `POST /api/v1/admin/users` — create user (ADMIN)
- `PATCH /api/v1/admin/users/{id}` — update role/is_active (ADMIN)

---

## Success Criteria

1. `cd frontend && npm run build` exits 0 (no TypeScript errors)
2. `docker exec ai-ap-manager-backend-1 python -c "from app.api.v1 import approvals, kpi, exceptions, match; print('OK')"` → OK
3. `docker exec ai-ap-manager-backend-1 python -c "from app.rules.match_engine import run_2way_match, run_3way_match; print('OK')"` → OK
4. All P0 backend items in TODO.md checked off
5. All P0 frontend items in TODO.md checked off
6. At least P1 3-Way Match and Exception Auto-Routing checked off in TODO.md
7. `git log --oneline -20` shows logical, incremental commits for each feature

## Notes for Workers

- **Never run `git add .`** — always `committer "type: msg" file1 file2`
- Backend runs inside Docker container; verify imports with `docker exec ai-ap-manager-backend-1 python -c "..."`
- Frontend: Node 22 + npm 10 available on host; run `npm` commands from `frontend/` dir
- Frontend API calls to backend use `http://localhost:8002/api/v1`
- For Alembic migrations: `docker exec ai-ap-manager-backend-1 alembic -c alembic.ini revision --autogenerate -m "description"` then `alembic upgrade head`
- Pydantic schemas live in `backend/app/schemas/`; API routes in `backend/app/api/v1/`
- Follow existing patterns: async SQLAlchemy session via `get_session` dep for API routes; sync session for Celery tasks
- Check PROGRESS.md for past lessons before starting — avoid known pitfalls
