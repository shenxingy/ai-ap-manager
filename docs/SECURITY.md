# Security & Compliance Design

---

## 1. Authentication

- **JWT-based auth**: access token (1h expiry) + refresh token (7d expiry)
- Tokens stored in `httpOnly` cookies (frontend) — not localStorage
- `python-jose` for JWT signing/verification (backend)
- Password storage: `bcrypt` with work factor 12
- Login rate limiting: 5 failed attempts → 15-minute lockout (Redis-backed)
- No OAuth for MVP (can be added for V1 via NextAuth.js)

---

## 2. Authorization — RBAC Model

### Role Matrix

| Action | AP_CLERK | AP_ANALYST | APPROVER | ADMIN | AUDITOR |
|--------|----------|------------|----------|-------|---------|
| Upload invoice | ✓ | ✓ | | ✓ | |
| View invoice list | ✓ | ✓ | ✓ | ✓ | ✓ |
| View invoice detail | ✓ | ✓ | ✓ | ✓ | ✓ |
| Correct extraction fields | | ✓ | | ✓ | |
| Trigger re-match | | ✓ | | ✓ | |
| View exception queue | | ✓ | | ✓ | ✓ |
| Resolve exceptions | | ✓ | | ✓ | |
| View approval tasks | | | ✓ | ✓ | ✓ |
| Approve/reject invoices | | | ✓ | ✓ | |
| View KPI dashboard | | ✓ | | ✓ | ✓ |
| Export audit log | | | | ✓ | ✓ |
| Manage users | | | | ✓ | |
| Configure approval matrix | | | | ✓ | |
| Upload policy documents | | | | ✓ | |
| Review extracted rules | | | | ✓ | |
| Publish rule versions | | | | ✓ | |
| Manage vendor master | | | | ✓ | |
| View all audit logs | | | | ✓ | ✓ |

### Backend Enforcement

```python
from fastapi import Depends, HTTPException
from app.core.security import get_current_user

def require_role(*roles: str):
    async def check(user = Depends(get_current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return check

# Usage in route
@router.post("/rules/versions/{id}/publish")
async def publish_version(
    id: UUID,
    admin: User = Depends(require_role("ADMIN"))
):
    ...
```

### Frontend Guards

```typescript
// middleware.ts (Next.js)
const ROUTE_ROLES: Record<string, string[]> = {
  '/admin': ['ADMIN'],
  '/audit': ['ADMIN', 'AUDITOR'],
  '/approvals': ['APPROVER', 'ADMIN'],
};
```

---

## 3. Data Protection

### Sensitive Field Handling

| Field | Protection |
|-------|-----------|
| `vendor.bank_account` | Masked in API responses for non-ADMIN (show last 4 digits) |
| `vendor.bank_routing` | Masked for non-ADMIN |
| `user.password_hash` | Never returned in any API response |
| Invoice PDFs | Stored in MinIO with bucket policy — backend fetches on behalf, no direct public URLs |

### Masking Example

```python
def mask_bank_account(account: str) -> str:
    return "****" + account[-4:] if len(account) > 4 else "****"
```

### Document Access

- Invoice PDFs served via signed URLs (30-minute expiry) — never expose raw MinIO bucket
- Access check before generating URL: requester must have access to the invoice

---

## 4. Audit & Non-Repudiation

### Requirements
- Every state transition logged to `audit_logs` (immutable, append-only)
- No UPDATE or DELETE on `audit_logs` — enforce via DB policy if needed
- `actor_id` and `actor_type` on every log entry — system actions attributed to "system"
- AI decisions attributed as "ai" with link to `ai_call_logs` for full prompt/response

### Tamper Evidence
For MVP: DB-level protection (no ORM delete route for audit_logs)
For V1: Write audit logs with sequential IDs — any gap in ID sequence indicates tampering

### Retention Policy
- Audit logs: 7 years (compliance requirement for AP)
- Invoice PDFs: 7 years
- AI call logs: 1 year (for model debugging)
- Implement via scheduled Celery job that moves old records to cold storage

---

## 5. API Security

| Control | Implementation |
|---------|---------------|
| Input validation | Pydantic models on all request bodies |
| SQL injection | SQLAlchemy ORM — no raw string queries |
| XSS | React escapes by default; API returns JSON not HTML |
| CSRF | `httpOnly` cookies + `SameSite=Lax`; API checks Origin header |
| Rate limiting | `slowapi` middleware on auth endpoints (5 req/min) |
| File upload | Validate MIME type + file extension + max 20MB |
| CORS | Explicit allowlist (only frontend origin) |
| HTTPS | Enforced in production (nginx terminates TLS) |

---

## 6. Secrets Management

- All secrets in environment variables (never in code or `.env` committed to git)
- `.env.example` documents required vars with placeholder values
- In production: use secrets manager (AWS Secrets Manager / HashiCorp Vault)
- `ANTHROPIC_API_KEY` never logged, never returned in any API response

---

## 7. Production Monitoring Recommendations

| Concern | Tool |
|---------|------|
| Error tracking | Sentry (backend + frontend) |
| Metrics | Prometheus + Grafana |
| Log aggregation | Structured JSON logs → Loki or CloudWatch |
| Uptime | Simple health check endpoint `/health` monitored by UptimeRobot |
| DB backups | Daily `pg_dump` to separate S3 bucket, 30-day retention |
| Celery monitoring | Flower dashboard (internal only) |

### Key Metrics to Alert On
- `exception_rate` > 40% for 1 hour → PagerDuty alert
- `extraction_confidence_avg` < 0.70 → Alert (OCR degradation)
- LLM API error rate > 5% in 10 minutes → Alert (fallback to manual)
- Celery queue depth > 100 tasks → Alert (worker overload)
