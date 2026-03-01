# Goal: Final Polish Sprint

## Context

The product is feature-complete for demo. Seed data is in DB (10 invoices, 3 vendors, 6 POs).
All P0/P1/P2 backend APIs exist and most frontend pages are wired.

Working directory: `/home/alexshen/projects/ai-ap-manager`
Backend container: `docker exec ai-ap-manager-backend-1`
Frontend build check: `cd frontend && npm run build`
Tests: `docker exec ai-ap-manager-backend-1 python -m pytest tests/ -x -q`

---

## Gap 1: Delete User Endpoint (Backend) ✅ DONE

**Problem**: `backend/app/api/v1/admin.py` has `GET /admin/users`, `POST /admin/users`,
`PATCH /admin/users/{id}` but NO delete endpoint. The admin users page can't deactivate users.

**Fix**: Add to `backend/app/api/v1/admin.py`:

```python
@router.delete(
    "/users/{user_id}",
    status_code=204,
    summary="Soft-delete a user (ADMIN only)",
)
async def delete_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_role("ADMIN")),
):
    user = await db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    user.deleted_at = datetime.now(timezone.utc)
    audit_svc.log(db, action="user.deleted", entity_type="user", entity_id=user_id,
                  actor_id=current_user.id, actor_email=current_user.email,
                  after={"deleted": True})
    await db.commit()
```

The `datetime` and `timezone` imports are already at the top of admin.py. Also need `uuid`.
Check what's already imported before adding imports.

---

## Gap 2: Vendor Compliance Doc Expiry Beat Task (Backend)

**Problem**: `VendorComplianceDoc` has `expiry_date` and `status` fields, but there's no
automated job to mark approved/active docs as "expired" when their `expiry_date` passes.

**Fix**: Add a function `expire_compliance_docs()` to `backend/app/workers/sla_tasks.py`:

```python
@celery_app.task(name="tasks.expire_compliance_docs")
def expire_compliance_docs():
    """Weekly job: mark approved/active compliance docs with past expiry_date as expired."""
    from app.models.vendor import VendorComplianceDoc
    from datetime import date
    db = _get_sync_session()
    try:
        today = date.today()
        docs = db.execute(
            select(VendorComplianceDoc).where(
                VendorComplianceDoc.expiry_date < today,
                VendorComplianceDoc.status.in_(["approved", "active"]),
            )
        ).scalars().all()
        for doc in docs:
            doc.status = "expired"
        db.commit()
        print(f"[expire_compliance_docs] Marked {len(docs)} docs as expired.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

Then add to `backend/app/workers/celery_app.py` beat_schedule (append, do NOT overwrite):

```python
"expire-compliance-docs-weekly": {
    "task": "tasks.expire_compliance_docs",
    "schedule": crontab(hour=1, minute=0, day_of_week="mon"),
},
```

Check what's already in `sla_tasks.py` before adding — use the same `_get_sync_session` pattern
and the same imports at the top. The `select` import and `VendorComplianceDoc` import should be
lazy (inside the function) or added to the top — match the existing pattern in that file.

---

## Gap 3: Delete User Button in Admin/Users Frontend ✅ DONE

**Problem**: `frontend/src/app/(app)/admin/users/page.tsx` currently shows user list with
edit/deactivate actions but no delete capability that calls `DELETE /admin/users/{id}`.

**Fix**: Add a "Delete" action to the user row in `admin/users/page.tsx`:
- Only visible to ADMIN role
- Confirmation dialog: "Delete {name}? This cannot be undone."
- On confirm: `api.delete(\`/admin/users/${user.id}\`)` → invalidate users query → toast "User deleted"
- Use `useMutation` pattern matching existing mutations in that file
- Use `AlertDialog` or a simple `Dialog` from shadcn/ui for confirmation

Check what shadcn/ui components are already imported in that file before adding new ones.

---

## Gap 4: Notification Bell in AppShell Header ✅ DONE

**Problem**: `frontend/src/components/layout/AppShell.tsx` has a top header bar but no
notification bell. There's no way to see pending approvals / unread vendor messages at a glance.

**Fix**: Add a notification bell to the right side of the header in AppShell.tsx:

```tsx
// Fetch count of pending approval tasks assigned to current user
const { data: pendingCount } = useQuery({
  queryKey: ["pending-approvals-count"],
  queryFn: () => api.get("/approvals?status=pending&page_size=1").then(r => r.data.total ?? 0),
  refetchInterval: 30000,  // refresh every 30s
});

// In the header JSX, add to the right side:
<Link href="/approvals">
  <Button variant="ghost" size="icon" className="relative">
    <Bell className="h-5 w-5" />
    {pendingCount > 0 && (
      <span className="absolute -top-1 -right-1 h-4 w-4 rounded-full bg-red-500 text-xs text-white flex items-center justify-center">
        {pendingCount > 9 ? "9+" : pendingCount}
      </span>
    )}
  </Button>
</Link>
```

Import `Bell` from `lucide-react`. Import `useQuery` from `@tanstack/react-query`.
Import `api` from `@/lib/api`. Import `Link` from `next/link`.
Check if `useAuth` is already available in AppShell.tsx — only show bell if user is logged in.
The component currently has `useState` already. Add the query hook inside the component.

---

## Gap 5: Additional Tests for P2 Endpoints ✅ DONE

**Problem**: The test suite (34 tests) doesn't cover the new P2 endpoints added in recent sprints.

**Fix**: Add `backend/tests/test_p2_endpoints.py` with tests for:

1. `GET /api/v1/invoices?overdue=true` — returns 200, response has `items` and `total`
2. `POST /api/v1/exceptions/bulk-update` — with valid payload `{"items": [...]}` returns 200
3. `POST /api/v1/approvals/bulk-approve` — with ADMIN token, returns 200
4. `GET /api/v1/ask-ai` ... actually this is a POST. Test `POST /api/v1/ask-ai` with question returns 200 or 422 (if no API key)
5. `GET /api/v1/admin/rule-recommendations` — returns 200 (empty list OK)
6. `GET /api/v1/analytics/reports` — returns 200 (list)

Use the same test pattern as `tests/test_auth.py` and `tests/test_health.py`:
- `httpx.AsyncClient` with `ASGITransport`
- `app.dependency_overrides[get_session] = override_get_session`
- Get a JWT token first via `POST /api/v1/auth/login` with the seed admin credentials
- All tests use `pytest.mark.asyncio`

Look at existing test files first to copy the exact pattern before writing new tests.

---

## Success Criteria

1. `docker exec ai-ap-manager-backend-1 python -c "from app.api.v1.admin import router; print('OK')"` → OK
2. `DELETE /api/v1/admin/users/{id}` with ADMIN token returns 204
3. `docker exec ai-ap-manager-backend-1 python -c "from app.workers.sla_tasks import expire_compliance_docs; print('OK')"` → OK
4. `grep "expire-compliance-docs-weekly" backend/app/workers/celery_app.py` finds a match
5. `cd frontend && npm run build` exits 0
6. `docker exec ai-ap-manager-backend-1 python -m pytest tests/ -x -q` — all pass (≥ 38 tests)
7. AppShell header has a Bell icon that shows pending approval count

## Worker Notes

- Work from `/home/alexshen/projects/ai-ap-manager`
- Backend in Docker: `docker exec ai-ap-manager-backend-1 <cmd>`
- Commits: `committer "feat/fix/test/chore: message" file1 file2` — NEVER `git add .`
- Do NOT run alembic migrations (hook blocks it) — no new tables needed for this sprint
- After modifying admin.py: verify with `docker exec ai-ap-manager-backend-1 python -c "from app.api.v1.admin import router; print(len(router.routes))"`
- After modifying sla_tasks.py: verify with `docker exec ai-ap-manager-backend-1 python -c "from app.workers.sla_tasks import expire_compliance_docs; print('OK')"`
