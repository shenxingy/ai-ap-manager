# Goal: Comprehensive Gap Audit — Find ALL Unimplemented Features

## Mission

Do a THOROUGH audit of the entire codebase and all planning documents.
Produce `docs/GAP_ANALYSIS.md` — a complete, prioritized list of every feature that is
**planned but not implemented**. No gap should be missing. No already-done item should be listed.

This is a **research + documentation task**, not an implementation task.
Workers: read files, grep code, verify endpoints, check frontend pages. Do NOT write code.

---

## Scope

Compare the following planned features against actual code:

### Source 1: GOALS.md phase milestones
Read `/home/alexshen/projects/ai-ap-manager/GOALS.md` — three phases (MVP, V1, V2).
For each success criterion, check whether it is actually implemented.

### Source 2: TODO.md open items
Read `/home/alexshen/projects/ai-ap-manager/TODO.md`.
Find every item marked `- [ ]` (open) — these are confirmed gaps.
Also spot-check some `- [x]` items for drift (marked done but may be stubs).

### Source 3: All goal files
Read each of these and note their open gaps:
- `goal-production-readiness.md` — STATUS: NOT CONVERGED (has gaps despite all checked)
- `goal-completeness.md` — seed data, recurring beat, compliance expiry
- `goal-p1p2-completion.md` — 8 gaps including email ingestion, policy upload, cash flow, etc.

### Source 4: Backend API audit
Run: `docker exec ai-ap-manager-backend-1 python -c "
from app.main import app
routes = [(r.path, list(r.methods)) for r in app.routes]
for r in sorted(routes): print(r)
"`
Cross-check planned API endpoints vs. actually registered routes.

### Source 5: Frontend page audit
List all frontend pages:
`find /home/alexshen/projects/ai-ap-manager/frontend/src/app -name "page.tsx" | sort`

Check each page for stub vs. real implementation. A stub typically has:
- Empty return `<div>TODO</div>` or `<div>Coming soon</div>`
- No data fetching (no useQuery, no api calls)
- Missing key interactive elements

---

## What to Check (Feature List)

### P0 (MVP) — should be 100% done
1. Email ingestion pipeline — `POST /import/email-config` or email monitor service
2. Audit trail completeness — every state transition logged?
3. Seed data — 10 invoices, 3 vendors, KPI shows non-zero?

### P1 (V1) — partially done
4. 3-way match — frontend wiring complete?
5. Multi-level approval with authorization matrix — chain auto-progression?
6. CSV import frontend `/admin/import` — real implementation or stub?
7. Email ingestion (monitored AP mailbox → extract attachments)
8. Policy/contract upload → LLM rule extraction → human review → publish
9. Role-based access control frontend (middleware.ts route guards)
10. Full audit replay — audit export endpoint?

### P2 (V2) — may not be started
11. Rule self-optimization (rule recommendations based on override history)
12. Root cause analysis (exception rate spike → identify why)
13. ERP integration (SAP/Oracle API or CSV connector)
14. Multi-currency support with FX tolerance
15. Vendor portal enhancements (submit disputes endpoint — `/portal/disputes`)
16. Configurable SLA alerts — overdue invoice notifications
17. Mobile-friendly approver view

### Production Readiness (from goal-production-readiness.md)
All 10 gaps are checked as done. Verify each:
18. Rate limiting (slowapi) — `grep -r "limiter" backend/app/api`
19. Request ID middleware — `ls backend/app/middleware/`
20. Sentry integration — `grep "sentry" backend/app/main.py`
21. Payment tracking — `POST /invoices/{id}/payment` endpoint exists?
22. Performance indexes — `alembic history | grep indexes`
23. Production docker-compose — `ls docker-compose.prod.yml nginx/`
24. Login audit events — `grep "user_login" backend/app/api/v1/auth.py`

### P1/P2 gaps from goal-p1p2-completion.md
25. Ask AI frontend panel (AskAiPanel component in AppShell)
26. Cash flow forecast API (`GET /kpi/cash-flow-forecast`)
27. Cash flow frontend chart on dashboard
28. Approval escalation beat task (`escalate_overdue_approvals`)
29. Recurring invoice tagging in pipeline (`_check_recurring_pattern`)
30. Audit log CSV export endpoint

---

## Output Format

Write `docs/GAP_ANALYSIS.md` with this structure:

```markdown
# Gap Analysis — AI AP Manager
Generated: [date]

## Summary
- Total planned features: N
- Implemented: N
- Gaps found: N

## Confirmed Gaps (sorted by priority)

### P0 Gaps (MVP — must fix before demo)
| # | Feature | Location | Evidence of missing |
|---|---------|----------|---------------------|
| 1 | ... | ... | ... |

### P1 Gaps (V1 — production-ready)
| # | Feature | Location | Evidence of missing |
...

### P2 Gaps (V2 — intelligence layer)
| # | Feature | Location | Evidence of missing |
...

### Production Readiness Gaps
| # | Feature | Location | Evidence of missing |
...

## Verified as Done (spot-checked)
List 10-15 key features confirmed implemented with evidence.

## Drift Items (marked done in TODO but may be stubs)
| # | Feature | File | Issue |
...
```

---

## How to Verify Each Item

For backend features, use these verification patterns:

```bash
# Check if endpoint exists
docker exec ai-ap-manager-backend-1 python -c "
from app.main import app
paths = [r.path for r in app.routes]
print('Found' if '/api/v1/kpi/cash-flow-forecast' in paths else 'MISSING')
"

# Check if function/class exists
grep -r "cash_flow_forecast\|cash-flow-forecast" backend/app/

# Check celery beat schedule
grep -A 5 "beat_schedule" backend/app/workers/celery_app.py

# Check middleware
ls backend/app/middleware/

# Check frontend component
ls frontend/src/components/AskAiPanel.tsx 2>/dev/null && echo "EXISTS" || echo "MISSING"
grep -r "AskAiPanel\|ask-ai" frontend/src/
```

For frontend features:
- Read the page file (don't just check if it exists — check if it's a stub)
- Look for data fetching, interactive elements, real API calls

---

## Success Criteria

The goal is CONVERGED when:
1. `docs/GAP_ANALYSIS.md` exists and is complete (all 30 items above verified)
2. Every gap has evidence (grep output, "file not found", empty implementation)
3. Every "done" check has evidence (line numbers, function names)
4. The report is internally consistent — no item listed in both "done" and "gap"
5. Workers have re-verified the previous iteration's findings (cross-check previous report)

STATUS: NOT CONVERGED

---

## Worker Conventions

- Working directory: `/home/alexshen/projects/ai-ap-manager`
- Backend container: `docker exec ai-ap-manager-backend-1`
- DO NOT modify any code — this is read-only audit
- Commit only `docs/GAP_ANALYSIS.md` and any updates to it
- Commits: `committer "docs: gap analysis audit [iter N]" docs/GAP_ANALYSIS.md`
- If a gap was already listed in a previous iteration, re-verify rather than blindly copying
