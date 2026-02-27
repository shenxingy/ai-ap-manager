# Goal: Plan and Build Approval Workflow

## Context
2-way match engine is complete. Invoices flow: ingested → extracting → extracted → matching → matched/exception/approved.
Auto-approve already works for matched invoices under threshold.
Next P0: manual approval workflow — in-app decisions + email-based token approval (Tipalti-style).

## Architecture Notes
- `ApprovalTask` = one approval step for one approver on one invoice
- `ApprovalToken` = HMAC-signed one-time token sent in email, used without logging in
- Email in MVP = print to console/logs (MAIL_ENABLED=false), not real SMTP
- `create_approval_token()` and `verify_approval_token()` already exist in `app/core/security.py`
- Approval decisions must write to `audit_logs` with actor, action, invoice snapshot

## Requirements

### Phase 1: Approval Service
Create `app/services/approval.py`:

**`create_approval_task(db, invoice_id, approver_id, step_order=1, due_hours=48) -> ApprovalTask`**
- Creates an `ApprovalTask` row (status=pending)
- Generates two `ApprovalToken` rows (action=approve + action=reject) using `create_approval_token()`
- Stores `token_hash` in DB, returns raw tokens in a dict for email embedding
- Logs to audit_logs: action="approval_task_created"

**`process_approval_decision(db, task_id, action, actor_id=None, token_raw=None, channel="web") -> ApprovalTask`**
- `action`: "approve" or "reject"
- If `channel="email"`: validate raw token against stored hash via `verify_approval_token()`; check token not expired, not already used; mark token `is_used=True`
- If `channel="web"`: validate actor has approver role for this invoice
- Set `ApprovalTask.status` = approved/rejected, `decided_at`, `decision_channel`
- Update `Invoice.status` = approved/rejected
- Write audit log: action="invoice_approved"/"invoice_rejected", before/after snapshot
- Return updated task

**`get_pending_tasks_for_approver(db, approver_id) -> list[ApprovalTask]`**
- Returns all pending ApprovalTasks for a given approver, joined with invoice summary

**`auto_create_approval_task(db, invoice_id) -> ApprovalTask | None`**
- Called after match succeeds but invoice is NOT auto-approved (amount > threshold)
- Looks up which user has APPROVER role (first one found, MVP simplification)
- Creates approval task for that approver
- Returns None if no approver found (log warning)

### Phase 2: Wire into Match Engine
Update `app/rules/match_engine.py` → in `run_2way_match()`:
- After setting `invoice.status = matched` (not auto-approved): call `auto_create_approval_task(db, invoice_id)`

### Phase 3: Approval API Endpoints
Create `app/api/v1/approvals.py`:

**In-app approval (requires JWT auth):**
- `GET /api/v1/approvals` — list pending approval tasks for current user (APPROVER+)
- `GET /api/v1/approvals/{task_id}` — task detail with invoice summary
- `POST /api/v1/approvals/{task_id}/approve` — body: `{notes?: string}` → calls `process_approval_decision(channel="web")`
- `POST /api/v1/approvals/{task_id}/reject` — body: `{notes: string}` → calls `process_approval_decision(channel="web")`

**Email token approval (no auth required):**
- `GET /api/v1/approvals/email` — query param: `token=<raw_token>` → parse task_id+action from token prefix, validate, execute decision, return HTML confirmation page (simple string, not React)

Add `app/schemas/approval.py`:
- `ApprovalTaskOut` — id, invoice_id, status, step_order, due_at, decided_at, decision_channel, invoice summary fields (invoice_number, vendor_name_raw, total_amount)
- `ApprovalDecisionRequest` — notes: str | None
- `ApprovalListResponse` — items, total

### Phase 4: Email Notification (Console Mock)
Create `app/services/email.py`:
- `send_approval_request_email(task, invoice, approve_url, reject_url)` — if `settings.MAIL_ENABLED=False`: log to console with `logger.info()`. Format:
  ```
  === APPROVAL REQUEST EMAIL ===
  To: approver@example.com
  Subject: Action Required: Invoice {invoice_number} — ${total_amount}
  Approve: {approve_url}
  Reject:  {reject_url}
  ==============================
  ```
- Called from `create_approval_task()` after task is created

### Phase 5: Approval Seed User
Update `backend/scripts/seed.py` — add an APPROVER user:
- `approver@example.com` / `changeme123` / role=APPROVER

### Phase 6: Wire Router
Add approval router to `app/api/v1/router.py`.

## File Change Summary
```
backend/app/services/approval.py      # NEW - approval task lifecycle
backend/app/services/email.py         # NEW - email mock (console log)
backend/app/schemas/approval.py       # NEW - Pydantic schemas
backend/app/api/v1/approvals.py       # NEW - in-app + email token endpoints
backend/app/api/v1/router.py          # MODIFY - wire approval router
backend/app/rules/match_engine.py     # MODIFY - auto-create approval task post-match
backend/scripts/seed.py               # MODIFY - add APPROVER user
backend/app/scripts/seed.py           # MODIFY - same
```

## Success Criteria
- `POST /api/v1/approvals/{task_id}/approve` sets invoice status=approved, writes audit log
- `POST /api/v1/approvals/{task_id}/reject` sets invoice status=rejected, writes audit log
- `GET /api/v1/approvals/email?token=<raw>` works without JWT, validates HMAC, marks token used
- Re-using a token returns 400 (already used)
- Expired token returns 400 (expired)
- Console log shows approval email when task is created
- After seeding an APPROVER user + uploading invoice with total > $5000 → approval task auto-created → email logged to console
- All decisions recorded in audit_logs with before/after invoice status snapshot
- Commit each logical unit with committer.sh, push at end
