# Proposed Tasks — P2 V2 Intelligence Layer

> Generated: 2026-02-27
> Plan: `docs/plans/2026-02-27-p2-v2-intelligence-layer.md`
> Parallelization: Wave 1 (Tasks A/B/C in parallel) → Wave 2 (Tasks D/E in parallel)

---

## Wave 1 — Backend Tasks (run in parallel)

---

### Task A: AI Self-Optimization Backend

**Goal**: Build the feedback logging layer and rule recommendation engine so the system can learn from human corrections.

**Context**:
- Work in `/home/alexshen/projects/ai-ap-manager`
- Backend runs in Docker: `docker exec ai-ap-manager-backend-1 <cmd>`
- Sync SQLAlchemy session pattern (use `_get_sync_session()` from `backend/app/workers/tasks.py`)
- Async FastAPI session: `Depends(get_session)` from `backend/app/core/deps.py`
- Commits: `committer "feat: message" file1 file2` — NEVER `git add .`

**Acceptance Criteria**:
1. `docker exec ai-ap-manager-backend-1 python -c "from app.api.v1.rule_recommendations import router; print('OK')"` → OK
2. PATCH /invoices/{id}/fields creates an `ai_feedback` row
3. `GET /api/v1/admin/rule-recommendations` returns 200 (empty list OK)

---

#### Step 1: DB Models

Create `backend/app/models/feedback.py`:

```python
# Two models: AiFeedback + RuleRecommendation

class AiFeedback(Base):
    __tablename__ = "ai_feedback"
    id: UUID PK
    feedback_type: str  # "field_correction" | "gl_correction" | "exception_resolution"
    invoice_id: UUID FK invoices.id (CASCADE DELETE)
    field_name: str | None  # e.g. "total_amount", "vendor_name_raw"
    ai_value: str | None    # original extracted value (as string)
    human_value: str | None # corrected value (as string)
    actor_id: UUID FK users.id (RESTRICT, nullable)
    created_at: datetime

class RuleRecommendation(Base):
    __tablename__ = "rule_recommendations"
    id: UUID PK
    rule_type: str  # "match_tolerance" | "gl_category" | "extraction_confidence"
    current_config: dict (JSON)
    suggested_config: dict (JSON)
    rationale: str  # AI-generated explanation
    expected_impact: str  # "Reduce PRICE_VARIANCE exceptions by ~15%"
    confidence: float  # 0.0–1.0
    status: str default "pending"  # "pending" | "accepted" | "rejected"
    reviewed_by: UUID | None FK users.id
    reviewed_at: datetime | None
    created_at: datetime
```

- Alembic migration: `docker exec ai-ap-manager-backend-1 alembic revision --autogenerate -m "add_ai_feedback_and_rule_recommendations"` then `upgrade head`
- Add to `backend/app/models/__init__.py`

#### Step 2: Pydantic Schemas

Create `backend/app/schemas/feedback.py`:
- `AiFeedbackOut`: id, feedback_type, invoice_id, field_name, ai_value, human_value, actor_id, created_at
- `RuleRecommendationOut`: all fields
- `RuleRecommendationUpdate`: status (accepted/rejected), review note
- `RuleRecommendationListResponse`: items[], total, page, page_size

#### Step 3: Feedback Service

Create `backend/app/services/feedback.py` (async, uses `AsyncSession`):

```python
async def log_field_correction(db, invoice_id, field_name, ai_value, human_value, actor_id): ...
async def log_gl_correction(db, invoice_id, field_name, ai_value, human_value, actor_id): ...
async def log_exception_correction(db, invoice_id, old_status, new_status, actor_id): ...
```

Each function creates an `AiFeedback` row and flushes (caller commits).

#### Step 4: Hook into Existing Endpoints

**`backend/app/api/v1/invoices.py`** — PATCH /invoices/{id}/fields (around line 380 where old_value/new_value are known):
```python
from app.services import feedback as feedback_svc
await feedback_svc.log_field_correction(db, invoice_id, field_name, old_value, new_value, current_user.id)
```

**`backend/app/api/v1/invoices.py`** — PUT /invoices/{id}/lines/{line_id}/gl:
```python
await feedback_svc.log_gl_correction(db, invoice_id, f"line_{line_id}_gl", old_gl, new_gl, current_user.id)
```

**`backend/app/api/v1/exceptions.py`** — PATCH /exceptions/{id} (when status changes):
```python
if old_status != new_status:
    await feedback_svc.log_exception_correction(db, exception.invoice_id, old_status, new_status, current_user.id)
```

#### Step 5: Weekly Analysis Celery Task

Create `backend/app/workers/feedback_tasks.py`:

```python
@celery_app.task(name="tasks.analyze_ai_feedback")
def analyze_ai_feedback():
    """
    Weekly job: analyze ai_feedback table, identify patterns, create RuleRecommendation rows.

    Analysis steps:
    1. Count field_corrections by field_name over last 90 days
    2. Fields with correction_rate > 30% (corrections / total invoices) → candidate for recommendation
    3. Count exception_corrections by old_status → new_status patterns
    4. For field_name=total_amount with high correction rate → suggest lowering AUTO_APPROVE_THRESHOLD
    5. Create RuleRecommendation rows for each identified pattern
    6. Deduplicate: skip if a pending recommendation for same rule_type already exists
    """
```

Use sync `_get_sync_session()` pattern. No LLM calls needed — rule generation is deterministic based on statistics.

#### Step 6: Rule Recommendations API

Create `backend/app/api/v1/rule_recommendations.py`:

- `GET /admin/rule-recommendations` — list (ADMIN only), filter by `?status=pending|accepted|rejected`
  - Pagination: `page`, `page_size`
  - Returns `RuleRecommendationListResponse`
- `POST /admin/rule-recommendations/{id}/accept` — set status=accepted, reviewed_by=current_user.id
  - Does NOT auto-apply the rule — human must still go to rule editor (separate flow)
  - Returns `RuleRecommendationOut`
- `POST /admin/rule-recommendations/{id}/reject` — set status=rejected
  - Returns `RuleRecommendationOut`

Register in `backend/app/api/v1/router.py` with prefix `/admin/rule-recommendations`.

#### Step 7: Beat Schedule

Add to `backend/app/workers/celery_app.py` at bottom (AFTER existing `celery_app.conf.update`):

```python
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    "analyze-ai-feedback-weekly": {
        "task": "tasks.analyze_ai_feedback",
        "schedule": crontab(hour=0, minute=0, day_of_week="sunday"),
    },
}
```

**NOTE**: If beat_schedule already exists, ADD to it; do NOT overwrite.

---

**OWN_FILES** (create these from scratch):
- `backend/app/models/feedback.py`
- `backend/app/schemas/feedback.py`
- `backend/app/services/feedback.py`
- `backend/app/workers/feedback_tasks.py`
- `backend/app/api/v1/rule_recommendations.py`

**SHARED_FILES** (modify, tell other workers what lines you changed):
- `backend/app/models/__init__.py` — append AiFeedback, RuleRecommendation imports
- `backend/app/api/v1/router.py` — append rule_recommendations router line
- `backend/app/api/v1/invoices.py` — add feedback hook in PATCH /fields and PUT /gl
- `backend/app/api/v1/exceptions.py` — add feedback hook in PATCH
- `backend/app/workers/celery_app.py` — add beat_schedule dict (create if not exists, append if exists)

**FORBIDDEN_FILES** (do not touch):
- `backend/app/api/v1/analytics.py`
- `backend/app/workers/analytics_tasks.py`
- `backend/app/workers/sla_tasks.py`
- `backend/app/api/v1/ask_ai.py`

---

### Task B: Analytics Intelligence Backend

**Goal**: Build the LLM-powered root cause narrative report + Ask AI conversational interface.

**Context**: Same as Task A. Anthropic SDK: `from anthropic import Anthropic` — API key in `settings.ANTHROPIC_API_KEY`.

**Acceptance Criteria**:
1. `docker exec ai-ap-manager-backend-1 python -c "from app.api.v1.ask_ai import router; print('OK')"` → OK
2. `POST /api/v1/analytics/root-cause-report` returns 202 with `{report_id, status: "pending"}`
3. `GET /api/v1/ask-ai` with `{question: "How many invoices were processed this month?"}` returns 200

---

#### Step 1: DB Model

Create `backend/app/models/analytics_report.py`:

```python
class AnalyticsReport(Base):
    __tablename__ = "analytics_reports"
    id: UUID PK
    report_type: str  # "root_cause" | "weekly_digest"
    status: str default "pending"  # "pending" | "complete" | "failed"
    narrative: str | None  # generated text (populated when complete)
    input_snapshot: dict (JSON)  # process mining + anomaly data used as input
    generated_by: UUID | None FK users.id
    created_at: datetime
    completed_at: datetime | None
```

- Alembic migration: `docker exec ai-ap-manager-backend-1 alembic revision --autogenerate -m "add_analytics_reports"` then `upgrade head`
- Add to `backend/app/models/__init__.py`

#### Step 2: LLM Root Cause Service

Create `backend/app/ai/root_cause.py`:

```python
from anthropic import Anthropic
from app.core.config import settings

SYSTEM_PROMPT = """You are an AP Operations analyst. Given process mining data (median hours per
invoice processing step) and anomaly data (vendors with abnormal exception rates), write a concise
3-5 paragraph executive summary. Focus on: (1) the top processing bottleneck, (2) the highest-risk
vendor anomaly, (3) one actionable recommendation. Be specific with numbers. Do not pad."""

def generate_root_cause_narrative(process_mining: list[dict], anomalies: list[dict]) -> str:
    """Call Claude to generate narrative. Returns text or raises on failure."""
    client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    # ...
    # Log to ai_call_logs table (use sync session)
```

Handle `ANTHROPIC_API_KEY` empty string → return "AI narrative unavailable (API key not configured)."

#### Step 3: Analytics Report Endpoints

Add to `backend/app/api/v1/analytics.py` (2 new routes at bottom):

- `POST /analytics/root-cause-report` (AP_ANALYST+):
  - Check if a "complete" report exists from last 60 minutes → if yes, return it (rate limit)
  - Create `AnalyticsReport(status="pending")` row, commit, return `{report_id, status}`
  - Dispatch Celery task `generate_root_cause_report.apply_async(args=[report_id])`

- `GET /analytics/reports` (AP_ANALYST+):
  - Return list of AnalyticsReport rows (newest first, limit 20)
  - Schema: `AnalyticsReportOut` (id, report_type, status, narrative, created_at, completed_at)

- `GET /analytics/reports/{id}` (AP_ANALYST+):
  - Return single report (for polling)

#### Step 4: Celery Task for Report Generation

Create `backend/app/workers/analytics_tasks.py`:

```python
@celery_app.task(name="tasks.generate_root_cause_report")
def generate_root_cause_report(report_id: str):
    """Fetch process mining + anomaly data, call LLM, update report."""
    db = _get_sync_session()
    try:
        report = db.get(AnalyticsReport, uuid.UUID(report_id))
        # Fetch data inline (call same query logic as analytics endpoints but sync)
        # Call root_cause.generate_root_cause_narrative(process_mining, anomalies)
        report.narrative = narrative
        report.status = "complete"
        report.completed_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        report.status = "failed"
        db.commit()
        raise
    finally:
        db.close()

@celery_app.task(name="tasks.generate_weekly_digest")
def generate_weekly_digest():
    """Weekly job: auto-generate root cause report + print mock email."""
    # Same logic, but generated_by=None (system-generated)
    # Print digest to console (MAIL_ENABLED=False pattern)
```

#### Step 5: Ask AI Endpoint

Create `backend/app/api/v1/ask_ai.py`:

```python
ALLOWED_TABLES = {"invoices", "exceptions", "vendors", "approval_tasks", "audit_logs"}
MAX_ROWS = 100

class AskAiRequest(BaseModel):
    question: str = Field(..., max_length=500)

class AskAiResponse(BaseModel):
    question: str
    sql_generated: str
    results: list[dict]
    row_count: int

@router.post("/ask-ai")
async def ask_ai(
    body: AskAiRequest,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role("AP_ANALYST", "ADMIN")),
):
    """Natural language → SQL query with safety guardrails."""
    # 1. Call Claude to generate SQL
    # System prompt: schema summary + "Return only the SELECT statement, no explanation"
    # 2. Validate generated SQL:
    #    - Must be SELECT only (no INSERT/UPDATE/DELETE/DROP)
    #    - Only references tables in ALLOWED_TABLES
    #    - If validation fails, return 422 with "unsafe query"
    # 3. Execute via db.execute(text(sql)) with LIMIT MAX_ROWS
    # 4. Log to ai_call_logs
    # 5. Return AskAiResponse
```

Register ask_ai router in `backend/app/api/v1/router.py` with prefix `/ask-ai` (no version prefix needed since it goes through the main router).

#### Step 6: Beat Schedule

**NOTE**: Add to `backend/app/workers/celery_app.py`. If Task A already created `beat_schedule`, ADD to it:

```python
celery_app.conf.beat_schedule["generate-weekly-digest"] = {
    "task": "tasks.generate_weekly_digest",
    "schedule": crontab(hour=8, minute=0, day_of_week="monday"),
}
```

---

**OWN_FILES** (create these from scratch):
- `backend/app/ai/root_cause.py`
- `backend/app/models/analytics_report.py`
- `backend/app/schemas/analytics_report.py`
- `backend/app/workers/analytics_tasks.py`
- `backend/app/api/v1/ask_ai.py`

**SHARED_FILES** (modify):
- `backend/app/models/__init__.py` — append AnalyticsReport import
- `backend/app/api/v1/analytics.py` — add 3 new routes at bottom
- `backend/app/api/v1/router.py` — add ask_ai router registration
- `backend/app/workers/celery_app.py` — add/append beat_schedule entry for weekly digest

**FORBIDDEN_FILES** (do not touch):
- `backend/app/models/feedback.py`
- `backend/app/workers/feedback_tasks.py`
- `backend/app/api/v1/rule_recommendations.py`
- `backend/app/workers/sla_tasks.py`

---

### Task C: Operations Backend — SLA Alerting + Bulk Operations

**Goal**: Add SLA alerting (Celery beat + API filter) and bulk exception/approval operations.

**Context**: Same as Task A.

**Acceptance Criteria**:
1. `docker exec ai-ap-manager-backend-1 python -c "from app.workers.sla_tasks import check_sla_alerts; print('OK')"` → OK
2. `GET /api/v1/invoices?overdue=true` returns 200
3. `POST /api/v1/exceptions/bulk-update` with `{ids: [...], status: "resolved"}` returns 200 with count

---

#### Step 1: DB Model

Create `backend/app/models/sla_alert.py`:

```python
class SlaAlert(Base):
    __tablename__ = "sla_alerts"
    id: UUID PK
    invoice_id: UUID FK invoices.id (CASCADE DELETE)
    alert_type: str  # "approaching" | "overdue"
    sent_at: datetime
    notified_users: list (JSON)  # list of user_ids notified

    # Unique constraint: (invoice_id, alert_type) — prevent duplicate alerts
    __table_args__ = (UniqueConstraint("invoice_id", "alert_type"),)
```

- Alembic migration: `docker exec ai-ap-manager-backend-1 alembic revision --autogenerate -m "add_sla_alerts"` then `upgrade head`
- Add to `backend/app/models/__init__.py`

#### Step 2: SLA Celery Task

Create `backend/app/workers/sla_tasks.py`:

```python
@celery_app.task(name="tasks.check_sla_alerts")
def check_sla_alerts():
    """
    Daily job (8 AM UTC): find invoices approaching or past due_date.

    Logic:
    1. Query invoices where due_date IS NOT NULL AND status NOT IN ('approved', 'rejected', 'cancelled')
    2. "approaching": due_date BETWEEN now() AND now() + SLA_WARNING_DAYS_BEFORE days
       AND no existing SlaAlert(alert_type="approaching") for this invoice
    3. "overdue": due_date < now()
       AND no existing SlaAlert(alert_type="overdue") for this invoice
    4. For each match: create SlaAlert row, print mock console notification
    """
    from app.core.config import settings
    warning_days = settings.SLA_WARNING_DAYS_BEFORE  # default 3
```

#### Step 3: Config Addition

Add to `backend/app/core/config.py` (in the Business Rules section):
```python
SLA_WARNING_DAYS_BEFORE: int = 3
```

#### Step 4: Overdue Filter in Invoice API

Add to `backend/app/api/v1/invoices.py` in GET /invoices list endpoint:

```python
overdue: bool = Query(default=False)
# If overdue=True: filter where due_date < now() AND status NOT IN ('approved', 'rejected')
```

#### Step 5: Bulk Exception Update

Add to `backend/app/api/v1/exceptions.py`:

```python
class BulkExceptionUpdate(BaseModel):
    ids: list[uuid.UUID] = Field(..., min_length=1, max_length=100)
    status: str | None = None
    assigned_to: uuid.UUID | None = None

class BulkUpdateResponse(BaseModel):
    updated: int
    skipped: int  # items not found or already in target state
    errors: list[str]

@router.post("/bulk-update")
async def bulk_update_exceptions(
    body: BulkExceptionUpdate,
    db: AsyncSession = Depends(get_session),
    current_user = Depends(require_role("AP_ANALYST", "ADMIN")),
):
    """Batch update up to 100 exceptions. Audit logs each updated item."""
    # For each id: fetch, validate transition, update, audit log
    # Return count of updated + skipped
```

#### Step 6: Bulk Approval

Add to `backend/app/api/v1/approvals.py`:

```python
class BulkApproveRequest(BaseModel):
    ids: list[uuid.UUID] = Field(..., min_length=1, max_length=50)
    notes: str | None = None

class BulkApproveResponse(BaseModel):
    approved: int
    skipped: int  # non-pending tasks
    errors: list[str]

@router.post("/bulk-approve")
async def bulk_approve(
    body: BulkApproveRequest,
    db: AsyncSession = Depends(get_session),
    current_user = Depends(require_role("ADMIN")),
):
    """ADMIN-only batch approval. Checks each task is PENDING before approving."""
    # For each id: fetch ApprovalTask, verify status=pending, call approval_svc.process_approval_decision()
    # Skip (not error) if task not found or not pending
    # Audit log each individually
```

#### Step 7: Beat Schedule

Add to `backend/app/workers/celery_app.py`:

```python
# Add daily SLA check to beat_schedule
celery_app.conf.beat_schedule["check-sla-alerts-daily"] = {
    "task": "tasks.check_sla_alerts",
    "schedule": crontab(hour=8, minute=0),
}
```

If beat_schedule dict doesn't exist yet (Task A created it), use dict update syntax:
```python
celery_app.conf.beat_schedule.update({
    "check-sla-alerts-daily": {...}
})
```

---

**OWN_FILES** (create from scratch):
- `backend/app/models/sla_alert.py`
- `backend/app/schemas/sla.py`
- `backend/app/workers/sla_tasks.py`

**SHARED_FILES** (modify):
- `backend/app/models/__init__.py` — append SlaAlert import
- `backend/app/api/v1/invoices.py` — add overdue filter
- `backend/app/api/v1/exceptions.py` — add POST /bulk-update
- `backend/app/api/v1/approvals.py` — add POST /bulk-approve
- `backend/app/workers/celery_app.py` — add/append daily SLA beat task
- `backend/app/core/config.py` — add SLA_WARNING_DAYS_BEFORE

**FORBIDDEN_FILES** (do not touch):
- `backend/app/models/feedback.py`
- `backend/app/models/analytics_report.py`
- `backend/app/api/v1/analytics.py`
- `backend/app/workers/feedback_tasks.py`

---

## Wave 2 — Frontend Tasks (run in parallel after Wave 1)

**Prerequisite**: All Wave 1 tasks merged to main. Run `git pull` before starting Wave 2.

---

### Task D: Intelligence Frontend

**Goal**: Build the AI Insights admin page and extend the Analytics page with root cause report UI.

**Context**:
- Frontend runs on Next.js 14 (App Router) in `frontend/`
- Build check: `cd frontend && npm run build` must exit 0 with zero warnings
- Pattern: `useQuery` + `useMutation` from @tanstack/react-query
- API client: `import api from "@/lib/api"`
- UI: shadcn/ui components (Badge, Button, Card, Dialog, Sheet, Table, Tabs)
- Custom toast hook pattern: copy from `fraud/page.tsx`
- After implementing, add sidebar link if needed

**Acceptance Criteria**:
1. `cd frontend && npm run build` exits 0 with zero warnings
2. `/admin/ai-insights` page renders (even with empty data from API)
3. Analytics page has "Generate Report" button that calls `POST /analytics/root-cause-report`

---

#### Sub-task D1: AI Insights Page

Create `frontend/src/app/(app)/admin/ai-insights/page.tsx`:

Sections:
1. **Correction Stats Card** — calls `GET /admin/rule-recommendations?status=pending` and displays count
   - Summary: "X pending rule recommendations · Y field corrections logged this week"
2. **Rule Recommendations Table** — columns: rule_type · current config (truncated) · suggested config · expected impact · confidence badge · actions
   - "Accept" button → `POST /admin/rule-recommendations/{id}/accept`
   - "Reject" button → `POST /admin/rule-recommendations/{id}/reject`
   - Both invalidate query on success
3. **Empty state**: "No recommendations yet. Corrections are analyzed weekly." if list is empty.

Add "AI Insights" link to sidebar in `frontend/src/app/(app)/layout.tsx` under Admin section (ADMIN role only).

#### Sub-task D2: Analytics Page Extension

Modify `frontend/src/app/(app)/analytics/page.tsx`:

Add a new "Root Cause Report" section below the anomalies list:
- "Generate Root Cause Report" button (AP_ANALYST+ visible)
  - On click: `POST /analytics/root-cause-report` → get `report_id`
  - Poll `GET /analytics/reports/{report_id}` every 3 seconds until `status !== "pending"`
  - Show loading spinner during polling
  - On complete: display narrative in a Card with formatted text
- "Past Reports" accordion/list: `GET /analytics/reports` (newest first, show last 5)
  - Each report: timestamp + first 100 chars of narrative + "View" button (expands full text)
- If ANTHROPIC_API_KEY is not configured: show an info card "AI narrative requires ANTHROPIC_API_KEY to be set" instead of the button

---

**OWN_FILES** (create from scratch):
- `frontend/src/app/(app)/admin/ai-insights/page.tsx`

**SHARED_FILES** (modify):
- `frontend/src/app/(app)/analytics/page.tsx` — add root cause report section
- `frontend/src/app/(app)/layout.tsx` — add AI Insights sidebar link

**FORBIDDEN_FILES** (do not touch):
- `frontend/src/app/(app)/invoices/` (Task E)
- `frontend/src/app/(app)/exceptions/page.tsx` (Task E)
- `frontend/src/app/(app)/approvals/page.tsx` (Task E)
- `frontend/src/app/(app)/dashboard/page.tsx` (Task E)

---

### Task E: Operations Frontend

**Goal**: Add overdue badges, bulk select UI, and SLA dashboard warnings.

**Context**: Same as Task D. Note: Checkbox is not yet installed in shadcn/ui — install it first.

**Acceptance Criteria**:
1. `cd frontend && npm run build` exits 0 with zero warnings
2. Exceptions page shows checkbox column and "Bulk Update" toolbar when items are selected
3. Invoice list shows a red "Overdue" badge for past-due invoices
4. Dashboard shows SLA warning card if overdue invoices exist

---

#### Step 1: Install Checkbox Component

```bash
cd frontend && npx shadcn-ui@latest add checkbox
```

This creates `frontend/src/components/ui/checkbox.tsx`.

#### Sub-task E1: Invoice List — Overdue Badge

Modify `frontend/src/app/(app)/invoices/page.tsx`:
- Add `overdue` to filter options (optional toggle)
- In invoice rows: check if `due_date` is in the past AND status not in `['approved', 'rejected']` → show red `<Badge className="bg-red-100 text-red-700">Overdue</Badge>` next to invoice number

#### Sub-task E2: Exceptions — Bulk Select

Modify `frontend/src/app/(app)/exceptions/page.tsx`:
- Add state: `const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())`
- Add checkbox column (first column) using `<Checkbox>` from shadcn/ui
- Add "Select All" checkbox in `<TableHead>`
- When `selectedIds.size > 0`, show a sticky bulk action toolbar above the table:
  - `{selectedIds.size} selected`
  - Status dropdown: select target status → "Update" button → `POST /exceptions/bulk-update`
  - "Clear selection" link
- On bulk update success: clear `selectedIds`, invalidate exceptions query, show toast

#### Sub-task E3: Approvals — Bulk Approve (Admin Only)

Modify `frontend/src/app/(app)/approvals/page.tsx`:
- Add checkbox column (if user is ADMIN role)
- When items selected + user is ADMIN: show "Bulk Approve" button
- On click: confirm dialog → `POST /approvals/bulk-approve`
- Show toast with count of approved

#### Sub-task E4: Dashboard — SLA Warning Card

Modify `frontend/src/app/(app)/dashboard/page.tsx`:
- Add a query: `useQuery({ queryKey: ["invoices-overdue"], queryFn: () => api.get("/invoices?overdue=true&page_size=1").then(r => r.data.total) })`
- If `overdueCount > 0`: render a warning card:
  ```
  ⚠️ {overdueCount} invoices past due date — review needed
  ```
  with a "View Overdue" link to `/invoices?overdue=true`

---

**OWN_FILES** (create from scratch):
- `frontend/src/components/ui/checkbox.tsx` (auto-generated by shadcn install)

**SHARED_FILES** (modify):
- `frontend/src/app/(app)/invoices/page.tsx`
- `frontend/src/app/(app)/exceptions/page.tsx`
- `frontend/src/app/(app)/approvals/page.tsx`
- `frontend/src/app/(app)/dashboard/page.tsx`

**FORBIDDEN_FILES** (do not touch):
- `frontend/src/app/(app)/admin/ai-insights/page.tsx` (Task D)
- `frontend/src/app/(app)/analytics/page.tsx` (Task D)
- `frontend/src/app/(app)/layout.tsx` (Task D)

---

## Success Criteria (All Tasks Complete)

1. `docker exec ai-ap-manager-backend-1 python -c "from app.main import app; print(len(app.routes))"` → ≥ 80
2. `cd frontend && npm run build` exits 0 with **zero** warnings
3. `docker exec ai-ap-manager-backend-1 python -m pytest tests/ -x -q` → all pass (≥ 21)
4. `docker exec ai-ap-manager-backend-1 alembic current` → shows head
5. `GET /api/v1/admin/rule-recommendations` → 200
6. `POST /api/v1/analytics/root-cause-report` → 202
7. `GET /api/v1/ask-ai` → 200 (or 422 on bad input)
8. `GET /api/v1/invoices?overdue=true` → 200
9. `POST /api/v1/exceptions/bulk-update` → 200
10. Frontend pages `/admin/ai-insights` and `/analytics` compile and render
