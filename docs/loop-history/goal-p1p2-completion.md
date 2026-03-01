# Goal: P1/P2 Feature Completion

## Context

Working directory: `/home/alexshen/projects/ai-ap-manager`
Backend: FastAPI + SQLAlchemy async, runs in `docker exec ai-ap-manager-backend-1`
Frontend: Next.js 14 App Router in `frontend/`
Commits: `committer "type: msg" file1 file2` — NEVER `git add .`
DO NOT run alembic migrations (hook blocks it). All needed tables already exist.

Verify commands:
- Backend import: `docker exec ai-ap-manager-backend-1 python -c "from app.services.approval import process_approval_decision; print('OK')"`
- Tests: `docker exec ai-ap-manager-backend-1 python -m pytest tests/ -x -q`
- Build: `cd frontend && npm run build`

---

## Gap 1: Multi-Step Approval Chain Auto-Progression

### Problem
`build_approval_chain(db, invoice)` exists in `backend/app/services/approval.py:445` and returns
`[{step_order, approver_role}]` from the `approval_matrix_rules` table. But `process_approval_decision()`
never calls it. When a task is approved, the invoice jumps straight to "approved" even if
the matrix defines 2 or 3 steps. Only the FIRST step is created by `auto_create_approval_task()`.

### Fix: `backend/app/services/approval.py`

In `process_approval_decision()`, in the `else: # action == "approve"` branch,
AFTER `task.status = "approved"` and BEFORE `db.commit()`:

```python
# ── Multi-step chain: check for next step ──
next_step = _get_next_approval_step(db, invoice, task.step_order)
if next_step:
    # Don't mark invoice as approved yet — chain continues
    invoice.status = "matched"  # or keep current if not "approved"
    # Find first user with the required role
    from app.models.user import User
    next_approver = db.execute(
        select(User).where(
            User.role == next_step["approver_role"],
            User.is_active == True,
            User.deleted_at.is_(None),
        )
    ).scalars().first()
    if next_approver:
        create_approval_task(
            db=db,
            invoice_id=invoice.id,
            approver_id=next_approver.id,
            step_order=next_step["step_order"],
            due_hours=72,
            required_count=1,
        )
        # Re-set invoice status to pending-approval
        invoice.status = "matched"
        db.flush()
        audit_svc.log(
            db=db,
            action="approval_chain_advanced",
            entity_type="invoice",
            entity_id=invoice.id,
            actor_id=actor_id,
            after={"next_step": next_step["step_order"], "next_role": next_step["approver_role"]},
        )
else:
    # No next step → invoice fully approved
    invoice.status = "approved"
    db.flush()
```

Add helper function (sync, takes db Session):
```python
def _get_next_approval_step(db: Session, invoice, current_step_order: int) -> dict | None:
    """Return the next approval step from the matrix, or None if chain is complete."""
    chain = build_approval_chain(db, invoice)  # returns sorted list
    for step in chain:
        if step["step_order"] > current_step_order:
            return step
    return None
```

Also fix `auto_create_approval_task()`: use `build_approval_chain()` to determine step 1 approver role.
If chain is empty (no matching matrix rows), fall back to current behavior (find APPROVER role user).

### Fix: Approval Chain Timeline in Approvals Tab

Modify `frontend/src/app/(app)/approvals/page.tsx` to show step information:
- Add `step_order` column to the approvals table: "Step 1", "Step 2", etc.
- Add a "chain progress" indicator: "Step 1 of 2" if invoice has multiple tasks

Modify `frontend/src/app/(app)/invoices/[id]/page.tsx` Approvals tab:
- Group tasks by invoice, sort by step_order
- Show timeline: Step 1 → [status] → Step 2 → [status]
- Use color: approved=green, pending=yellow, rejected=red, not-yet-created=gray

---

## Gap 2: Approval Escalation Beat Task

### Problem
No automated escalation when approval tasks sit unactioned past their `due_at` deadline.

### Fix: `backend/app/workers/sla_tasks.py`

Add a new Celery task below `check_sla_alerts`:

```python
@celery_app.task(name="app.workers.sla_tasks.escalate_overdue_approvals")
def escalate_overdue_approvals():
    """Daily job: find approval tasks past due_at, reassign to ADMIN role."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.core.config import settings
    from app.models.approval import ApprovalTask
    from app.models.user import User
    from app.models.invoice import Invoice
    from datetime import datetime, timezone

    engine = create_engine(settings.DATABASE_URL_SYNC, pool_pre_ping=True)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)

    with Session() as db:
        # Find pending tasks past due
        overdue_tasks = db.execute(
            select(ApprovalTask).where(
                ApprovalTask.status == "pending",
                ApprovalTask.due_at.isnot(None),
                ApprovalTask.due_at < now,
            )
        ).scalars().all()

        admin_user = db.execute(
            select(User).where(User.role == "ADMIN", User.is_active == True)
        ).scalars().first()

        for task in overdue_tasks:
            old_approver = task.approver_id
            if admin_user and task.approver_id != admin_user.id:
                task.approver_id = admin_user.id
                db.flush()
                logger.warning(
                    "Escalated approval task %s (invoice %s) from %s to ADMIN %s",
                    task.id, task.invoice_id, old_approver, admin_user.id,
                )

        db.commit()
        logger.info("escalate_overdue_approvals: processed %d tasks", len(overdue_tasks))
```

Then add to `backend/app/workers/celery_app.py` beat_schedule (append, do NOT overwrite):
```python
"escalate-overdue-approvals-daily": {
    "task": "app.workers.sla_tasks.escalate_overdue_approvals",
    "schedule": crontab(hour=9, minute=30),
},
```

---

## Gap 3: Recurring Invoice Tagging in Processing Pipeline

### Problem
`detect_recurring_patterns` detects and stores `RecurringInvoicePattern` records weekly.
But when a new invoice is processed, the pipeline (`backend/app/workers/tasks.py`) never
checks if the vendor has an active pattern and never tags `invoice.is_recurring = True`.

### Fix: `backend/app/workers/tasks.py`

After the fraud scoring step (search for `score_invoice` or `run_fraud_scoring`) and before
the match engine step, add a recurring check:

```python
# ── Step: Recurring invoice detection ──
try:
    _check_recurring_pattern(db, invoice)
except Exception as exc:
    logger.warning("Recurring check failed for invoice %s: %s", invoice_id, exc)
```

Add helper function (sync):
```python
def _check_recurring_pattern(db, invoice):
    """Tag invoice as recurring if vendor has an active pattern matching this amount."""
    from app.models.recurring_pattern import RecurringInvoicePattern
    from sqlalchemy import select

    if not invoice.vendor_id or not invoice.total_amount:
        return

    pattern = db.execute(
        select(RecurringInvoicePattern).where(
            RecurringInvoicePattern.vendor_id == invoice.vendor_id,
        )
    ).scalars().first()

    if pattern is None:
        return

    avg = float(pattern.avg_amount or 0)
    tol = float(pattern.tolerance_pct or 0.1)
    inv_total = float(invoice.total_amount)

    if avg > 0 and abs(inv_total - avg) / avg <= tol:
        invoice.is_recurring = True
        invoice.recurring_pattern_id = pattern.id
        db.flush()
        logger.info(
            "Invoice %s tagged as recurring (pattern %s, avg=$%.2f)",
            invoice.id, pattern.id, avg,
        )

        # Fast-track: create approval task immediately if pattern has auto_fast_track
        if pattern.auto_fast_track:
            from app.services.approval import auto_create_approval_task
            auto_create_approval_task(db, invoice.id)
            invoice.status = "matched"
            db.flush()
            logger.info("Invoice %s fast-tracked via recurring pattern", invoice.id)
```

### Fix: Frontend Recurring Badges

Modify `frontend/src/app/(app)/invoices/page.tsx`:
- In the invoice row, if `inv.is_recurring`, show:
  `<Badge className="bg-blue-100 text-blue-700">🔄 Recurring</Badge>`
- Place next to the invoice number or status badge

Modify `frontend/src/app/(app)/invoices/[id]/page.tsx`:
- In the invoice header (near status badge), if `invoice.is_recurring`:
  show `<Badge>🔄 Recurring Invoice</Badge>`
- If invoice came from fast-track (check if ApprovalTask.notes contains "recurring" or
  check `invoice.is_recurring && invoice.status === "matched"`): show info banner:
  `"Recurring invoice detected — pending 1-click approval"`

---

## Gap 4: Per-Role Frontend Route Guards

### Problem
Any authenticated user can navigate to any page (e.g., clerk to /admin/users).
No role-based access control on the frontend.

### Fix: `frontend/src/middleware.ts` (create new file)

```typescript
import { NextRequest, NextResponse } from "next/server";

const ADMIN_ROUTES = [
  "/admin/users",
  "/admin/exception-routing",
  "/admin/approval-matrix",
  "/admin/ai-insights",
  "/admin/fraud",
  "/admin/rules",
  "/admin/settings",
];

const ANALYST_ROUTES = ["/analytics", "/admin/recurring-patterns"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Read role from cookie (set at login)
  const role = request.cookies.get("user_role")?.value;

  if (!role) return NextResponse.next(); // not logged in → let auth guard handle

  const isAdmin = role === "ADMIN";
  const isAnalyst = ["ADMIN", "AP_ANALYST"].includes(role);

  if (ADMIN_ROUTES.some((r) => pathname.startsWith(r)) && !isAdmin) {
    return NextResponse.redirect(new URL("/unauthorized", request.url));
  }

  if (ANALYST_ROUTES.some((r) => pathname.startsWith(r)) && !isAnalyst) {
    return NextResponse.redirect(new URL("/unauthorized", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/admin/:path*", "/analytics/:path*"],
};
```

Also update login flow: when user logs in (`frontend/src/store/auth.ts` or login page),
set a cookie with the user's role so middleware can read it:
```typescript
// After successful login:
document.cookie = `user_role=${user.role}; path=/; samesite=strict`;
```

On logout, clear the cookie:
```typescript
document.cookie = "user_role=; path=/; max-age=0";
```

---

## Gap 5: Cash Flow Forecast API + Frontend

### Problem
No cash flow forecasting. Treasury team can't see upcoming payment obligations.

### Fix: `backend/app/api/v1/kpi.py`

Add two new endpoints at the bottom of the file:

```python
@router.get("/cash-flow-forecast", summary="Weekly cash flow forecast for next 12 weeks")
async def get_cash_flow_forecast(
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role("AP_ANALYST", "ADMIN", "AUDITOR")),
):
    """
    For each pending/matched invoice with a due_date (or estimated from payment_terms):
    - Bucket by week (week_start = Monday)
    - Sum expected outflows per bucket
    Returns 12 weeks of forecast data.
    """
    from datetime import date, timedelta
    from sqlalchemy import func, case

    today = date.today()
    cutoff = today + timedelta(weeks=12)

    # Invoices that are not yet approved/rejected
    pending_statuses = ["ingested", "extracting", "extracted", "matching", "matched", "exception"]
    stmt = select(Invoice).where(
        Invoice.status.in_(pending_statuses),
        Invoice.deleted_at.is_(None),
    )
    invoices = (await db.execute(stmt)).scalars().all()

    # Bucket into weekly bins
    from collections import defaultdict
    buckets: dict[date, dict] = defaultdict(lambda: {"expected_outflow": 0.0, "invoice_count": 0, "confidence": "estimated"})

    for inv in invoices:
        # Determine expected payment date
        if inv.due_date:
            pay_date = inv.due_date.date() if hasattr(inv.due_date, 'date') else inv.due_date
            confidence = "confirmed"
        elif inv.invoice_date:
            inv_date = inv.invoice_date.date() if hasattr(inv.invoice_date, 'date') else inv.invoice_date
            terms = 30  # default
            pay_date = inv_date + timedelta(days=terms)
            confidence = "estimated"
        else:
            continue

        if pay_date > cutoff or pay_date < today:
            continue

        # Week bucket (Monday of the week)
        week_start = pay_date - timedelta(days=pay_date.weekday())
        amount = float(inv.total_amount or 0)
        buckets[week_start]["expected_outflow"] += amount
        buckets[week_start]["invoice_count"] += 1
        if confidence == "confirmed":
            buckets[week_start]["confidence"] = "confirmed"

    # Build 12-week response including empty weeks
    result = []
    for w in range(12):
        week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=w)
        b = buckets.get(week_start, {"expected_outflow": 0.0, "invoice_count": 0, "confidence": "estimated"})
        result.append({
            "week_start": week_start.isoformat(),
            "expected_outflow": round(b["expected_outflow"], 2),
            "invoice_count": b["invoice_count"],
            "confidence": b["confidence"],
        })

    return result


@router.get("/cash-flow-export", summary="CSV export of pending invoice outflows")
async def export_cash_flow(
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role("AP_ANALYST", "ADMIN", "AUDITOR")),
):
    """Returns CSV of all pending invoices with expected payment dates."""
    from fastapi.responses import StreamingResponse
    import csv
    import io

    pending_statuses = ["ingested", "extracting", "extracted", "matching", "matched", "exception"]
    stmt = select(Invoice).where(
        Invoice.status.in_(pending_statuses),
        Invoice.deleted_at.is_(None),
    ).options(selectinload(Invoice.vendor))  # if vendor relationship exists
    invoices = (await db.execute(stmt)).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["invoice_number", "vendor", "amount", "currency", "status", "due_date", "invoice_date"])
    for inv in invoices:
        vendor_name = inv.vendor_name_raw or ""
        writer.writerow([
            inv.invoice_number, vendor_name,
            float(inv.total_amount or 0), inv.currency or "USD",
            inv.status,
            inv.due_date.isoformat() if inv.due_date else "",
            inv.invoice_date.isoformat() if inv.invoice_date else "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.read()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=cash-flow-forecast.csv"},
    )
```

**Note**: Check what imports are already at top of `kpi.py` before adding. The `Invoice` model
and `get_session`, `require_role`, `User` are likely already imported.

### Fix: Frontend — Cash Flow section in Dashboard

Modify `frontend/src/app/(app)/dashboard/page.tsx`:

Add after the existing KPI trend chart section:

```tsx
// Cash flow forecast
const { data: cashFlow } = useQuery({
  queryKey: ["cash-flow-forecast"],
  queryFn: () => api.get("/kpi/cash-flow-forecast").then(r => r.data),
});

// In JSX, add a new Card below the trend chart:
<Card>
  <CardHeader>
    <CardTitle className="text-base font-semibold">Cash Flow Forecast — Next 12 Weeks</CardTitle>
    <div className="flex justify-between items-center">
      <p className="text-sm text-gray-500">Expected AP outflows from pending invoices</p>
      <Button variant="outline" size="sm" asChild>
        <a href="/api/v1/kpi/cash-flow-export" download>Export CSV</a>
      </Button>
    </div>
  </CardHeader>
  <CardContent>
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={cashFlow ?? []}>
        <XAxis dataKey="week_start" tickFormatter={(v) => new Date(v).toLocaleDateString("en-US", {month: "short", day: "numeric"})} />
        <YAxis tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} />
        <Tooltip formatter={(v: number) => [`$${v.toLocaleString()}`, "Expected"]} />
        <Bar dataKey="expected_outflow" fill="#3b82f6" />
      </BarChart>
    </ResponsiveContainer>
    {cashFlow?.length > 0 && (
      <p className="text-xs text-gray-400 mt-2 text-center">
        Total: ${cashFlow.reduce((s: number, w: any) => s + w.expected_outflow, 0).toLocaleString()} expected this period
      </p>
    )}
  </CardContent>
</Card>
```

Use existing imports: `BarChart`, `Bar`, `XAxis`, `YAxis`, `Tooltip`, `ResponsiveContainer` from recharts (already imported in dashboard).

---

## Gap 6: Ask AI Frontend Sidebar Panel

### Problem
`POST /api/v1/ask-ai` backend is complete. But there's no UI to use it.
Users cannot run natural language queries.

### Fix: Create `frontend/src/components/AskAiPanel.tsx`

```tsx
"use client";
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Sparkles, Send } from "lucide-react";
import api from "@/lib/api";

const SUGGESTED = [
  "Show all invoices over $50k this month",
  "Which vendors have the most exceptions?",
  "What is our current approval backlog?",
  "Show invoices pending more than 7 days",
  "Top 5 exception types this quarter",
];

interface AskResult {
  question: string;
  sql_generated: string;
  results: Record<string, unknown>[];
  row_count: number;
}

export function AskAiPanel() {
  const [question, setQuestion] = useState("");
  const [showSql, setShowSql] = useState(false);

  const ask = useMutation({
    mutationFn: (q: string) =>
      api.post<AskResult>("/ask-ai", { question: q }).then((r) => r.data),
  });

  const submit = (q: string) => {
    setQuestion(q);
    ask.mutate(q);
  };

  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2">
          <Sparkles className="h-4 w-4" />
          Ask AI
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="w-[480px] flex flex-col">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-violet-500" />
            Ask AI
          </SheetTitle>
          <p className="text-xs text-gray-500">Natural language queries — read-only, max 100 rows</p>
        </SheetHeader>

        {/* Input */}
        <div className="flex gap-2 mt-4">
          <input
            className="flex-1 border rounded px-3 py-2 text-sm"
            placeholder="Ask anything about invoices..."
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && question && submit(question)}
          />
          <Button size="sm" onClick={() => submit(question)} disabled={!question || ask.isPending}>
            <Send className="h-4 w-4" />
          </Button>
        </div>

        {/* Suggestions */}
        {!ask.data && (
          <div className="mt-4">
            <p className="text-xs text-gray-400 mb-2">Suggested</p>
            <div className="flex flex-col gap-1">
              {SUGGESTED.map((s) => (
                <button
                  key={s}
                  className="text-left text-sm text-blue-600 hover:underline px-1"
                  onClick={() => submit(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Loading */}
        {ask.isPending && (
          <div className="mt-6 text-center text-sm text-gray-400">Thinking...</div>
        )}

        {/* Error */}
        {ask.isError && (
          <div className="mt-4 p-3 bg-red-50 text-red-700 rounded text-sm">
            Query failed. Try rephrasing your question.
          </div>
        )}

        {/* Results */}
        {ask.data && (
          <div className="mt-4 flex-1 overflow-auto">
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-medium">{ask.data.row_count} rows</p>
              <button
                className="text-xs text-gray-400 hover:text-gray-600"
                onClick={() => setShowSql(!showSql)}
              >
                {showSql ? "Hide SQL" : "Show SQL"}
              </button>
            </div>
            {showSql && (
              <pre className="text-xs bg-gray-50 p-2 rounded mb-3 overflow-x-auto">
                {ask.data.sql_generated}
              </pre>
            )}
            <div className="overflow-x-auto">
              <table className="w-full text-xs border-collapse">
                <thead>
                  <tr>
                    {ask.data.results[0] &&
                      Object.keys(ask.data.results[0]).map((k) => (
                        <th key={k} className="text-left p-1 border-b font-medium text-gray-600">
                          {k}
                        </th>
                      ))}
                  </tr>
                </thead>
                <tbody>
                  {ask.data.results.map((row, i) => (
                    <tr key={i} className="border-b hover:bg-gray-50">
                      {Object.values(row).map((v, j) => (
                        <td key={j} className="p-1 text-gray-700">
                          {String(v ?? "")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <button
              className="mt-3 text-xs text-gray-400 hover:underline"
              onClick={() => { ask.reset(); setQuestion(""); }}
            >
              ← New query
            </button>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
```

Then add the `<AskAiPanel />` button to the AppShell header:
In `frontend/src/components/layout/AppShell.tsx`, import `AskAiPanel` and add it to the
right side of the header between the notification bell and the logout button.

---

## Gap 7: Frontend CSV Import Page Wiring

### Problem
Backend import routes (`POST /import/pos`, `/import/grns`, `/import/vendors`) are fully implemented.
The frontend import page exists at `/admin/import/page.tsx` but may not be properly wired.

### Fix: Verify and update `frontend/src/app/(app)/admin/import/page.tsx`

Read the file first. If it's a stub, implement proper wiring:
- Three tabs: POs · GRNs · Vendors
- Each tab: file input (CSV only), upload button
- On upload: `api.post("/import/{type}", formData, { headers: {"Content-Type": "multipart/form-data"} })`
- Show results card: Created: N · Updated: N · Skipped: N
- If errors: show error table (row number + message)
- Download template CSV button per type with expected column names:
  - PO: `po_number, vendor_tax_id, total_amount, currency, issued_at, expires_at`
  - GRN: `gr_number, po_number, received_at, line_number, description, quantity`
  - Vendor: `name, tax_id, email, currency, payment_terms`

---

## Gap 8: Audit Log Export (GDPR)

### Problem
Auditors can't export audit logs for compliance/GDPR purposes.

### Fix: `backend/app/api/v1/analytics.py` or create `backend/app/api/v1/audit_export.py`

Add to the router (register under `/audit` prefix):

```python
@router.get("/export", summary="Export audit log as CSV (AUDITOR, ADMIN)")
async def export_audit_log(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role("AUDITOR", "ADMIN")),
):
    from fastapi.responses import StreamingResponse
    import csv, io
    from app.models.audit_log import AuditLog

    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if start_date:
        stmt = stmt.where(AuditLog.created_at >= datetime.combine(start_date, time.min, tzinfo=timezone.utc))
    if end_date:
        stmt = stmt.where(AuditLog.created_at <= datetime.combine(end_date, time.max, tzinfo=timezone.utc))
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)

    logs = (await db.execute(stmt)).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "action", "entity_type", "entity_id", "actor_email", "created_at", "notes"])
    for log in logs:
        writer.writerow([
            str(log.id), log.action, log.entity_type,
            str(log.entity_id) if log.entity_id else "",
            log.actor_email or "", log.created_at.isoformat(), log.notes or "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.read()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=audit-log-{date.today()}.csv"},
    )
```

Register in router.py under prefix `/audit`.

Also add an "Export Audit Log" button to the invoice detail audit tab
(or to a dedicated `/admin/settings` page).

---

## Success Criteria

1. `docker exec ai-ap-manager-backend-1 python -c "from app.services.approval import _get_next_approval_step; print('OK')"` → OK
2. `docker exec ai-ap-manager-backend-1 python -c "from app.workers.sla_tasks import escalate_overdue_approvals; print('OK')"` → OK
3. `docker exec ai-ap-manager-backend-1 python -c "from app.workers.tasks import _check_recurring_pattern; print('OK')"` → OK
4. `grep "escalate-overdue-approvals" backend/app/workers/celery_app.py` → match found
5. `curl -s http://localhost:8002/api/v1/kpi/cash-flow-forecast -H "Authorization: Bearer <token>"` → JSON array
6. `cd frontend && npm run build` → exit 0, zero TypeScript errors
7. `docker exec ai-ap-manager-backend-1 python -m pytest tests/ -x -q` → all pass
8. Frontend: `/dashboard` shows Cash Flow Forecast bar chart
9. Frontend: AppShell header has "Ask AI" button that opens sidebar panel
10. Frontend: `/admin/import` wired to real backend CSV import endpoints
11. Frontend: `/invoices` shows 🔄 Recurring badge on tagged invoices
12. Frontend: `/approvals` shows step_order column

## Worker Conventions

- Read target files before editing — never modify blindly
- Commit: `committer "feat/fix/chore: msg" file1 file2` (NEVER `git add .`)
- Do NOT run alembic migrations — tables already exist
- After modifying approval.py: `docker exec ai-ap-manager-backend-1 python -c "from app.services.approval import process_approval_decision; print('OK')"`
- After modifying tasks.py: `docker exec ai-ap-manager-backend-1 python -c "from app.workers.tasks import process_invoice; print('OK')"`
- After modifying sla_tasks.py: `docker exec ai-ap-manager-backend-1 python -c "from app.workers.sla_tasks import escalate_overdue_approvals; print('OK')"`
- After modifying kpi.py: `docker exec ai-ap-manager-backend-1 python -c "from app.api.v1.kpi import router; print(len(router.routes), 'routes')"`
