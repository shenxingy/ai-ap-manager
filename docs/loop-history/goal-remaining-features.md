# Goal: Remaining Features — Final Completion

## Context

Working directory: `/home/alexshen/projects/ai-ap-manager`
Backend: FastAPI + SQLAlchemy async, runs in `docker exec ai-ap-manager-backend-1`
Frontend: Next.js 14 App Router in `frontend/`
Commits: `committer "type: msg" file1 file2` — NEVER `git add .`
DO NOT run alembic migrations. All needed tables already exist.

Verify commands:
- Backend import: `docker exec ai-ap-manager-backend-1 python -c "from app.api.v1.router import api_router; print('OK')"`
- Tests: `docker exec ai-ap-manager-backend-1 python -m pytest tests/ -x -q`
- Build: `cd frontend && npm run build`

---

## Gap 1: Vendor Portal dispute endpoint

### Problem
`backend/app/api/v1/portal.py` has auth, invoice list, invoice detail, and vendor reply.
But there is NO dispute submission endpoint — vendor cannot formally dispute an invoice.

### Backend Fix: `backend/app/api/v1/portal.py`

Add to the existing file (after the `vendor_reply` endpoint):

```python
class VendorDisputeIn(BaseModel):
    reason: str  # e.g. "incorrect_amount", "duplicate", "already_paid", "other"
    description: str

class VendorDisputeResponse(BaseModel):
    status: str
    exception_id: uuid.UUID
    message_id: uuid.UUID

@router.post(
    "/invoices/{invoice_id}/dispute",
    response_model=VendorDisputeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Vendor submits a dispute for an invoice",
)
async def submit_vendor_dispute(
    invoice_id: uuid.UUID,
    body: VendorDisputeIn,
    db: Annotated[AsyncSession, Depends(get_session)],
    vendor_id: Annotated[uuid.UUID, Depends(get_current_vendor_id)],
):
```
- Verify invoice belongs to this vendor (ownership check same as get_vendor_invoice)
- Import `ExceptionRecord` from `app.models.exception_record`
- Import `VendorMessage` from `app.models.approval`
- Create `ExceptionRecord(invoice_id=invoice_id, exception_code="VENDOR_DISPUTE", description=f"Vendor dispute: {body.reason} — {body.description}", severity="medium", status="open")`
- Create `VendorMessage(invoice_id=invoice_id, sender_id=None, sender_email=None, direction="inbound", body=f"[DISPUTE] {body.reason}: {body.description}", is_internal=False, attachments=[])`
- db.add() both, await db.commit()
- Return `VendorDisputeResponse(status="dispute_submitted", exception_id=exc.id, message_id=msg.id)`

---

## Gap 2: Vendor Portal frontend (`/portal/*`)

### Problem
The backend at `/api/v1/portal/*` is fully built but there are NO vendor-facing frontend pages.
The vendor portal uses a separate JWT (vendor_id scoped, 30-day expiry).

### Existing Backend API
- `POST /api/v1/portal/auth/invite` — ADMIN issues JWT token for a vendor (no frontend needed for this — ADMIN already does it from admin UI)
- `GET /api/v1/portal/invoices` — vendor's invoices (requires Bearer token = vendor portal JWT)
- `GET /api/v1/portal/invoices/{id}` — single invoice detail
- `POST /api/v1/portal/invoices/{id}/dispute` — submit dispute (after Gap 1 is done)

### Implementation Plan

Create a separate Next.js layout at `frontend/src/app/portal/`:

#### `frontend/src/app/portal/layout.tsx` — minimal layout (no AppShell, no sidebar)
```tsx
// Simple vendor portal layout: just the page content + a small header
export default function PortalLayout({ children }: { children: React.ReactNode }) {
  return (
    <html>
      <body>
        <div className="min-h-screen bg-gray-50">
          <header className="bg-white border-b px-6 py-4 flex items-center gap-3">
            <div className="font-bold text-lg">AP Vendor Portal</div>
          </header>
          <main className="container mx-auto py-8 px-4">{children}</main>
        </div>
      </body>
    </html>
  );
}
```
IMPORTANT: This is a separate root layout — it does NOT extend the (app) group. Path must be `frontend/src/app/portal/layout.tsx`.

#### `frontend/src/app/portal/login/page.tsx` — Token entry page
Vendors get a JWT token via email (ADMIN issues it). Vendor pastes token into the form.
```tsx
"use client";
// State: token input (textarea), error message
// On Submit: store token in localStorage as "vendor_portal_token"
// Then redirect to /portal/invoices
// UI: Simple card with textarea for token paste + Submit button
// "Paste the portal access token from your invitation email"
```

#### `frontend/src/app/portal/invoices/page.tsx` — Vendor invoice list
```tsx
"use client";
// Read vendor_portal_token from localStorage
// GET /api/v1/portal/invoices with Authorization: Bearer {token}
// Use regular fetch() (not the staff api.ts which uses staff JWT)
// Show table: invoice_number | status | total_amount | currency | due_date
// Status badge: color-coded
// Row click → /portal/invoices/{id}
// If no token → redirect to /portal/login
// Pagination: skip/limit params
```

#### `frontend/src/app/portal/invoices/[id]/page.tsx` — Vendor invoice detail
```tsx
"use client";
// GET /api/v1/portal/invoices/{id}
// Show: invoice_number, status, total_amount, currency, invoice_date, due_date
// "Submit Dispute" button → opens a modal with reason select + description textarea
// POST /api/v1/portal/invoices/{id}/dispute on submit
// Show success message on dispute submitted
```

### Important: vendor portal uses fetch() not api.ts
The vendor portal uses a DIFFERENT token. Use raw `fetch()`:
```ts
const vendorToken = localStorage.getItem("vendor_portal_token");
const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/portal/invoices`, {
  headers: { Authorization: `Bearer ${vendorToken}` },
});
```

---

## Gap 3: Approval Delegation wiring

### Problem
`approval_tasks.delegated_to` column exists and `user_delegations` table exists, but
`create_approval_task()` in `backend/app/services/approval.py` never checks for active delegations.
If user A has delegated to user B for the current period, tasks assigned to A should be
re-routed to B, with `delegated_to` set to A's id and `approver_id` set to B's id.

### Existing Schema
- `user_delegations`: id, delegator_id, delegate_id, valid_from, valid_until, is_active, created_at, updated_at
- `approval_tasks.delegated_to` column exists (nullable UUID)

### Fix: `backend/app/services/approval.py`

In `create_approval_task()`, AFTER the compliance doc check and BEFORE `task = ApprovalTask(...)`:

```python
# ─── Check for active delegation ───
from app.models.approval_matrix import UserDelegation
from datetime import datetime, timezone
now_utc = datetime.now(timezone.utc)
delegation = db.execute(
    select(UserDelegation).where(
        UserDelegation.delegator_id == approver_id,
        UserDelegation.is_active.is_(True),
        UserDelegation.valid_from <= now_utc,
        UserDelegation.valid_until >= now_utc,
    )
).scalars().first()

original_approver_id = approver_id
if delegation is not None:
    approver_id = delegation.delegate_id  # re-route to delegate
    logger.info(
        "create_approval_task: delegation active — routing from %s to %s",
        original_approver_id, approver_id,
    )
```

Then when creating the ApprovalTask, set:
```python
task = ApprovalTask(
    invoice_id=invoice_id,
    approver_id=approver_id,             # delegate (or original if no delegation)
    delegated_to=None if delegation is None else original_approver_id,  # ← the original
    step_order=step_order,
    approval_required_count=required_count,
    due_at=expires_at,
    status="pending",
)
```

Note: `ApprovalTask` model is in `app/models/approval.py`. The `delegated_to` field is a nullable UUID. No import of `UserDelegation` is needed if using the lazy import pattern above.

### Verify
```bash
docker exec ai-ap-manager-backend-1 python -c "
from app.services.approval import create_approval_task
print('OK')
"
```

---

## Gap 4: Invoice source badge (email vs upload) in frontend

### Problem
`invoices.source` column exists with values like `"upload"` or `"email"`. The invoice list
page does NOT show this. Invoice list should show a small badge/tag for email-ingested invoices.

### Fix: `frontend/src/app/(app)/invoices/page.tsx`

Find where `invoice_number` is rendered in the table row. Add a small inline badge next to it:
```tsx
// After invoice_number cell content:
{invoice.source === "email" && (
  <Badge variant="outline" className="ml-1 text-xs font-normal text-blue-600 border-blue-300">
    email
  </Badge>
)}
```

Also update the TypeScript type for InvoiceListItem to include `source?: string`.

### Acceptance Criteria
- Badge "email" appears on email-sourced invoices in the invoice list
- No TypeScript errors

---

## Gap 5: Approval chain step timeline in Invoice Detail → Approvals tab

### Problem
The invoice detail page Approvals tab shows tasks but does NOT show a clear step-by-step
timeline indicating multi-step approval progress (Step 1 of 2: Approved → Step 2 of 2: Pending).

### Backend Read
- `GET /api/v1/approvals?invoice_id={id}` — returns list of ApprovalTask for this invoice
- Each task has: `step_order`, `status`, `approver_id`, `due_at`, `decided_at`, `delegated_to`, `decision_channel`

### Fix: `frontend/src/app/(app)/invoices/[id]/page.tsx`

In the **Approvals tab** section, add a timeline view above the existing table:

```tsx
// Sort tasks by step_order ascending
// For each task:
//   Step {task.step_order}: {status badge} — approver name — due {due_at}
//   If delegated_to: "(delegated from original approver)"
//   Status colors: pending=yellow, approved=green, rejected=red, partially_approved=blue

const sortedTasks = [...approvalTasks].sort((a, b) => a.step_order - b.step_order);
const totalSteps = sortedTasks.length;
```

Use a vertical stepper component:
```tsx
<div className="space-y-3 mb-6">
  <h3 className="text-sm font-medium text-gray-700">Approval Chain ({totalSteps} step{totalSteps > 1 ? 's' : ''})</h3>
  {sortedTasks.map((task, idx) => (
    <div key={task.id} className="flex items-start gap-3">
      <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0 ${
        task.status === 'approved' ? 'bg-green-500' :
        task.status === 'rejected' ? 'bg-red-500' :
        task.status === 'partially_approved' ? 'bg-blue-500' : 'bg-gray-300'
      }`}>{idx + 1}</div>
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Step {task.step_order}</span>
          <Badge variant="outline" className="text-xs">{task.status}</Badge>
        </div>
        <div className="text-xs text-gray-500">Due: {format(new Date(task.due_at), 'MMM d, yyyy')}</div>
        {task.decided_at && <div className="text-xs text-gray-500">Decided: {format(new Date(task.decided_at), 'MMM d, yyyy')}</div>}
      </div>
    </div>
  ))}
</div>
```

### Acceptance Criteria
- Multi-step approval chains are visible as a numbered stepper in the Approvals tab
- Single-step invoices show "Approval Chain (1 step)"
- No TypeScript errors

---

## Gap 6: Additional tests for portal and delegation

### Backend tests file: `backend/tests/test_portal_and_delegation.py`

Pattern: use existing test structure from `backend/tests/test_approvals.py`

```python
# Tests to write:

# 1. test_portal_invite_requires_admin
# POST /api/v1/portal/auth/invite with non-ADMIN token → 403

# 2. test_portal_invite_success
# POST /api/v1/portal/auth/invite with ADMIN token + valid vendor_id → 201 + {token, vendor_id}

# 3. test_portal_invoice_list
# GET /api/v1/portal/invoices with vendor portal JWT → 200 + {items, total}
# (vendor should see only their own invoices)

# 4. test_portal_dispute_submission
# POST /api/v1/portal/invoices/{invoice_id}/dispute → 201 + {status, exception_id, message_id}
# Verify ExceptionRecord with code="VENDOR_DISPUTE" was created in DB

# 5. test_delegation_check
# Given: userA (APPROVER) + userB (APPROVER) + active delegation userA→userB
# Call create_approval_task(approver_id=userA.id, ...)
# Check: returned task.approver_id == userB.id AND task.delegated_to == userA.id
```

Use sync DB session for create_approval_task test (same pattern as test_approvals.py).
Use TestClient for portal endpoint tests.

---

## STATUS

- [ ] Gap 1: Vendor portal dispute endpoint (backend/app/api/v1/portal.py)
- [x] Gap 2: Vendor portal frontend (frontend/src/app/portal/*.tsx)
- [ ] Gap 3: Approval delegation wiring (backend/app/services/approval.py)
- [x] Gap 4: Invoice source badge frontend (frontend/src/app/(app)/invoices/page.tsx)
- [x] Gap 5: Approval chain step timeline (frontend/src/app/(app)/invoices/[id]/page.tsx)
- [x] Gap 6: Tests for portal and delegation (backend/tests/test_portal_and_delegation.py)

STATUS: NOT CONVERGED
