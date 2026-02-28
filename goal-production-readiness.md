# Goal: Production Readiness — Make the AP Manager deployable to production

## Context

Working directory: `/home/alexshen/projects/ai-ap-manager`
Backend: FastAPI + SQLAlchemy async, runs in `docker exec ai-ap-manager-backend-1`
Frontend: Next.js 14 App Router in `frontend/`
Commits: `committer "type: msg" file1 file2` — NEVER `git add .`
Migrations ARE allowed for new columns/indexes (non-destructive only).

Verify commands:
- Backend import: `docker exec ai-ap-manager-backend-1 python -c "from app.main import app; print('OK')"`
- Tests: `docker exec ai-ap-manager-backend-1 python -m pytest tests/ -x -q`
- Build: `cd frontend && npm run build`

---

## Gap 1: Fix error message leakage (security)

### Problem
Two endpoints expose raw exception messages to clients — violates OWASP A05.

### Fix 1a: `backend/app/api/v1/approvals.py`
Find all occurrences of `detail=str(exc)` (around lines 171, 228). Replace with safe messages:
```python
# Line ~171 (in approve endpoint):
except ValueError as exc:
    logger.warning("Approval decision failed for task %s: %s", task_id, exc)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid approval request.")

# Line ~228 (in reject endpoint):
except ValueError as exc:
    logger.warning("Rejection decision failed for task %s: %s", task_id, exc)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid rejection request.")
```

### Fix 1b: `backend/app/api/v1/ask_ai.py`
Find `detail=f"Query execution failed: {exc}"` (~line 90). Replace:
```python
except Exception as exc:
    logger.warning("ask_ai SQL execution failed: %s | SQL: %s", exc, sql_query)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Query execution failed. Try rephrasing your question.",
    )
```

### Fix 1c: `backend/app/main.py` — Add global 500 exception handler
After the CORS middleware block, add:
```python
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s %s — %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error."},
    )
```

### Commit
```
committer "fix: remove error message leakage and add global exception handler" \
  backend/app/api/v1/approvals.py \
  backend/app/api/v1/ask_ai.py \
  backend/app/main.py
```

---

## Gap 2: Rate limiting on sensitive endpoints

### Problem
Login, invoice upload, and Ask AI endpoints have no rate limiting — brute force / abuse possible.

### Implementation

1. Add `slowapi` to `backend/requirements.txt`:
```
slowapi==0.1.9              # rate limiting
```

2. Install in container: `docker exec ai-ap-manager-backend-1 pip install slowapi==0.1.9`

3. Update `backend/app/main.py` — add rate limiter:
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

4. Apply to `backend/app/api/v1/auth.py` login endpoint:
```python
from app.main import limiter
from fastapi import Request

@router.post("/token")
@limiter.limit("10/minute")
async def login(request: Request, form_data: ..., db: ...):
    ...
```

5. Apply to `backend/app/api/v1/ask_ai.py`:
```python
from app.main import limiter
from fastapi import Request

@router.post("")
@limiter.limit("20/minute")
async def ask_ai(request: Request, body: ..., ...):
    ...
```

6. Apply to invoice upload in `backend/app/api/v1/invoices.py`:
```python
@router.post("/upload")
@limiter.limit("30/minute")
async def upload_invoice(request: Request, ...):
    ...
```

IMPORTANT: The limiter import must avoid circular imports. Use lazy import or pass limiter via app.state:
```python
from fastapi import Request
request.app.state.limiter  # access via request if needed
```

### Verify
`docker exec ai-ap-manager-backend-1 python -c "from slowapi import Limiter; print('OK')"`

### Commit
```
committer "feat: add rate limiting to login, upload, and ask-ai endpoints" \
  backend/requirements.txt \
  backend/app/main.py \
  backend/app/api/v1/auth.py \
  backend/app/api/v1/ask_ai.py \
  backend/app/api/v1/invoices.py
```

---

## Gap 3: Request ID middleware + structured logging

### Problem
No distributed tracing — impossible to correlate logs across services.

### Implementation

1. Add `python-json-logger==2.0.7` to `backend/requirements.txt`
   Install: `docker exec ai-ap-manager-backend-1 pip install python-json-logger==2.0.7`

2. Create `backend/app/core/logging.py`:
```python
"""Structured JSON logging configuration."""
import logging
import sys
from pythonjsonlogger import jsonlogger

from app.core.config import settings


def setup_logging() -> None:
    """Configure JSON structured logging for production, human-readable for dev."""
    if settings.APP_ENV == "production":
        handler = logging.StreamHandler(sys.stdout)
        formatter = jsonlogger.JsonFormatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level"},
        )
        handler.setFormatter(formatter)
        logging.root.handlers = [handler]
        logging.root.setLevel(logging.INFO)
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(name)s %(levelname)s %(message)s",
        )
```

3. Create `backend/app/middleware/request_id.py`:
```python
"""X-Request-ID middleware for distributed tracing."""
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
```

4. Update `backend/app/main.py`:
```python
from app.core.logging import setup_logging
from app.middleware.request_id import RequestIdMiddleware

setup_logging()  # ← call at top of file, before app creation

# After app creation:
app.add_middleware(RequestIdMiddleware)
```

5. Create `backend/app/middleware/__init__.py` (empty)

### Commit
```
committer "feat: add structured JSON logging and X-Request-ID middleware" \
  backend/requirements.txt \
  backend/app/core/logging.py \
  backend/app/middleware/__init__.py \
  backend/app/middleware/request_id.py \
  backend/app/main.py
```

---

## Gap 4: Sentry error monitoring

### Problem
Unhandled exceptions go unnoticed in production — no alerting.

### Implementation

1. Add to `backend/requirements.txt`:
```
sentry-sdk[fastapi]==2.19.0  # error monitoring (optional — skipped if SENTRY_DSN unset)
```
Install: `docker exec ai-ap-manager-backend-1 pip install "sentry-sdk[fastapi]==2.19.0"`

2. Add to `backend/app/core/config.py`:
```python
SENTRY_DSN: str = ""   # optional — leave empty to disable
SENTRY_TRACES_SAMPLE_RATE: float = 0.1  # 10% tracing in prod
```

3. Update `backend/app/main.py` — init Sentry before app creation:
```python
import sentry_sdk

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        environment=settings.APP_ENV,
        send_default_pii=False,  # GDPR: no PII in Sentry
    )
    logger.info("Sentry initialized (env=%s)", settings.APP_ENV)
```

4. Add to `.env.example`:
```
SENTRY_DSN=                # leave blank to disable, or set your DSN
SENTRY_TRACES_SAMPLE_RATE=0.1
```

### Commit
```
committer "feat: add optional Sentry error monitoring" \
  backend/requirements.txt \
  backend/app/core/config.py \
  backend/app/main.py \
  .env.example
```

---

## Gap 5: Payment tracking — new columns + endpoint

### Problem
Invoices have no payment lifecycle tracking. After approval, nothing happens.

### Step 1: Alembic migration for payment columns

Create migration file `backend/alembic/versions/e3f4a5b6c7d8_add_payment_fields_to_invoices.py`:
```python
"""add payment fields to invoices

Revision ID: e3f4a5b6c7d8
Revises: 136c34490d54  # use latest revision from alembic history
Create Date: 2026-02-28

"""
from alembic import op
import sqlalchemy as sa

revision = 'e3f4a5b6c7d8'
down_revision = None  # SET THIS: run `docker exec ai-ap-manager-backend-1 alembic history` to get latest

def upgrade() -> None:
    op.add_column('invoices', sa.Column('payment_status', sa.String(50), nullable=True, server_default=None))
    op.add_column('invoices', sa.Column('payment_date', sa.DateTime(timezone=True), nullable=True))
    op.add_column('invoices', sa.Column('payment_method', sa.String(50), nullable=True))
    op.add_column('invoices', sa.Column('payment_reference', sa.String(100), nullable=True))
    op.create_index('ix_invoices_payment_status', 'invoices', ['payment_status'], unique=False)

def downgrade() -> None:
    op.drop_index('ix_invoices_payment_status', table_name='invoices')
    op.drop_column('invoices', 'payment_reference')
    op.drop_column('invoices', 'payment_method')
    op.drop_column('invoices', 'payment_date')
    op.drop_column('invoices', 'payment_status')
```

IMPORTANT: Before writing this file:
1. Run `docker exec ai-ap-manager-backend-1 alembic history` to get current head revision
2. Set `down_revision` to the head revision ID found above

Run: `docker exec ai-ap-manager-backend-1 alembic upgrade head`

### Step 2: Update Invoice model `backend/app/models/invoice.py`
Add after `payment_terms` field:
```python
payment_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
payment_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
payment_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
```
Add `from datetime import datetime` to imports if not already there.

### Step 3: Create `backend/app/api/v1/payments.py`
```python
"""Payment recording endpoint.

POST /api/v1/invoices/{invoice_id}/payment  — record payment execution (ADMIN)
GET  /api/v1/invoices?payment_status=pending — filter (already supported via query param)
"""
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_role
from app.db.session import get_session
from app.models.invoice import Invoice
from app.models.user import User
from app.services import audit as audit_svc

router = APIRouter(prefix="/invoices", tags=["payments"])


class PaymentRecordIn(BaseModel):
    payment_method: str   # ACH, Wire, Check
    payment_reference: str | None = None  # ACH trace number, check number
    payment_date: datetime | None = None   # defaults to now


class PaymentRecordOut(BaseModel):
    invoice_id: uuid.UUID
    payment_status: str
    payment_date: datetime
    payment_method: str
    payment_reference: str | None

    model_config = {"from_attributes": True}


@router.post(
    "/{invoice_id}/payment",
    response_model=PaymentRecordOut,
    status_code=status.HTTP_200_OK,
    summary="Record payment execution for an approved invoice (ADMIN)",
)
async def record_payment(
    invoice_id: uuid.UUID,
    body: PaymentRecordIn,
    db: Annotated[AsyncSession, Depends(get_session)],
    current_user: Annotated[User, Depends(require_role("ADMIN"))],
):
    result = await db.execute(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.deleted_at.is_(None))
    )
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    if invoice.status not in ("approved",):
        raise HTTPException(
            status_code=400,
            detail=f"Invoice must be in 'approved' state to record payment (current: {invoice.status}).",
        )

    before = {"status": invoice.status, "payment_status": invoice.payment_status}
    payment_date = body.payment_date or datetime.now(timezone.utc)

    invoice.payment_status = "completed"
    invoice.payment_date = payment_date
    invoice.payment_method = body.payment_method
    invoice.payment_reference = body.payment_reference
    invoice.status = "paid"

    await db.flush()
    audit_svc.log(
        db=db,
        action="payment_recorded",
        entity_type="invoice",
        entity_id=invoice.id,
        actor_id=current_user.id,
        before=before,
        after={"status": "paid", "payment_method": body.payment_method, "payment_reference": body.payment_reference},
        notes=f"Payment recorded: {body.payment_method} ref={body.payment_reference}",
    )
    await db.commit()
    await db.refresh(invoice)
    return PaymentRecordOut(
        invoice_id=invoice.id,
        payment_status=invoice.payment_status,
        payment_date=invoice.payment_date,
        payment_method=invoice.payment_method,
        payment_reference=invoice.payment_reference,
    )
```

### Step 4: Register in `backend/app/api/v1/router.py`
```python
from app.api.v1 import payments as payments_module
api_router.include_router(payments_module.router, tags=["payments"])
```

### Verify
```bash
docker exec ai-ap-manager-backend-1 python -c "from app.api.v1.payments import router; print('OK')"
```

### Commit (separate commits)
```
committer "feat: add payment_status/date/method/reference columns to invoices" \
  backend/alembic/versions/e3f4a5b6c7d8_add_payment_fields_to_invoices.py \
  backend/app/models/invoice.py

committer "feat: add POST /invoices/{id}/payment endpoint to record payment" \
  backend/app/api/v1/payments.py \
  backend/app/api/v1/router.py
```

---

## Gap 6: Database performance indexes

### Problem
Missing indexes on high-frequency query columns cause full table scans.

### Migration

Get latest alembic head: `docker exec ai-ap-manager-backend-1 alembic history | head -3`

Create `backend/alembic/versions/f4a5b6c7d8e9_add_performance_indexes.py`:
```python
"""add performance indexes

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8  # the payment migration above
"""
from alembic import op

revision = 'f4a5b6c7d8e9'
down_revision = 'e3f4a5b6c7d8'

def upgrade() -> None:
    # Invoices — most queried table
    op.create_index('ix_invoices_status', 'invoices', ['status'])
    op.create_index('ix_invoices_created_at', 'invoices', ['created_at'])
    op.create_index('ix_invoices_due_date', 'invoices', ['due_date'])
    op.create_index('ix_invoices_status_created_at', 'invoices', ['status', 'created_at'])

    # Approval tasks — SLA queries
    op.create_index('ix_approval_tasks_due_at', 'approval_tasks', ['due_at'])
    op.create_index('ix_approval_tasks_status_due_at', 'approval_tasks', ['status', 'due_at'])

    # Exception records — queue queries
    op.create_index('ix_exceptions_status_severity', 'exception_records', ['status', 'severity'])

    # Audit logs — timeline queries
    op.create_index('ix_audit_logs_entity_id_created_at', 'audit_logs', ['entity_id', 'created_at'])

    # Vendor messages — unread count subquery
    op.create_index('ix_vendor_messages_invoice_direction', 'vendor_messages', ['invoice_id', 'direction'])

def downgrade() -> None:
    op.drop_index('ix_vendor_messages_invoice_direction', 'vendor_messages')
    op.drop_index('ix_audit_logs_entity_id_created_at', 'audit_logs')
    op.drop_index('ix_exceptions_status_severity', 'exception_records')
    op.drop_index('ix_approval_tasks_status_due_at', 'approval_tasks')
    op.drop_index('ix_approval_tasks_due_at', 'approval_tasks')
    op.drop_index('ix_invoices_status_created_at', 'invoices')
    op.drop_index('ix_invoices_due_date', 'invoices')
    op.drop_index('ix_invoices_created_at', 'invoices')
    op.drop_index('ix_invoices_status', 'invoices')
```

Run: `docker exec ai-ap-manager-backend-1 alembic upgrade head`

### Verify
```bash
docker exec ai-ap-manager-backend-1 python -c "
from sqlalchemy import create_engine, inspect
from app.core.config import settings
engine = create_engine(settings.DATABASE_URL_SYNC)
insp = inspect(engine)
idxs = [i['name'] for i in insp.get_indexes('invoices')]
assert 'ix_invoices_status' in idxs, 'Missing index'
print('Indexes OK:', idxs)
"
```

### Commit
```
committer "perf: add composite and range query indexes for invoices, approvals, exceptions" \
  backend/alembic/versions/f4a5b6c7d8e9_add_performance_indexes.py
```

---

## Gap 7: Production deployment configuration

### Problem
Only `docker-compose.yml` exists — it's for local dev. No production config.

### Files to create

#### `docker-compose.prod.yml`
```yaml
version: "3.9"

services:
  postgres:
    restart: always
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5
    deploy:
      resources:
        limits:
          memory: 2G

  redis:
    restart: always
    command: redis-server --requirepass ${REDIS_PASSWORD}
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    deploy:
      resources:
        limits:
          memory: 512M

  backend:
    restart: always
    command: gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 --timeout 120 --keep-alive 5
    ports: []   # not exposed directly — nginx handles it
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    deploy:
      resources:
        limits:
          memory: 1G

  celery_worker:
    restart: always
    command: celery -A app.workers.celery_app worker --loglevel=info --concurrency=4 --max-tasks-per-child=100
    healthcheck:
      test: ["CMD", "celery", "-A", "app.workers.celery_app", "inspect", "ping"]
      interval: 60s
      timeout: 10s
      retries: 3
    deploy:
      resources:
        limits:
          memory: 1G

  celery_beat:
    restart: always
    command: celery -A app.workers.celery_app beat --loglevel=info --schedule /tmp/celerybeat-schedule

  nginx:
    image: nginx:1.25-alpine
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
    depends_on:
      - backend
      - frontend

  frontend:
    restart: always
    environment:
      - NODE_ENV=production
    deploy:
      resources:
        limits:
          memory: 512M
```

#### `nginx/nginx.conf`
```nginx
events { worker_connections 1024; }

http {
    # Rate limiting zones
    limit_req_zone $binary_remote_addr zone=login:10m rate=10r/m;
    limit_req_zone $binary_remote_addr zone=api:10m rate=100r/m;
    limit_req_zone $binary_remote_addr zone=upload:10m rate=30r/m;

    # Logging
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for" '
                    'req_id=$http_x_request_id';
    access_log /var/log/nginx/access.log main;

    # Gzip
    gzip on;
    gzip_types text/plain application/json application/javascript text/css;

    # Security headers
    add_header X-Frame-Options SAMEORIGIN;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Referrer-Policy "strict-origin-when-cross-origin";

    server {
        listen 80;
        server_name _;
        return 301 https://$host$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name _;

        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;

        client_max_body_size 25M;  # match 20MB invoice upload limit + overhead

        # API backend
        location /api/ {
            limit_req zone=api burst=20 nodelay;

            proxy_pass http://backend:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Request-ID $request_id;
            proxy_read_timeout 120s;
        }

        location /api/v1/auth/token {
            limit_req zone=login burst=5 nodelay;
            proxy_pass http://backend:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }

        location /api/v1/invoices/upload {
            limit_req zone=upload burst=10 nodelay;
            proxy_pass http://backend:8000;
            proxy_set_header Host $host;
            proxy_read_timeout 180s;
        }

        # Frontend
        location / {
            proxy_pass http://frontend:3000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }
    }
}
```

#### `.env.prod.example`
```bash
# ─── Application ──────────────────────────────────────
APP_ENV=production
APP_BASE_URL=https://your-domain.com
FRONTEND_URL=https://your-domain.com
CORS_ORIGINS=https://your-domain.com

# ─── Database ──────────────────────────────────────────
POSTGRES_USER=ap_user
POSTGRES_PASSWORD=<strong-random-password>
POSTGRES_DB=ap_db
DATABASE_URL=postgresql+asyncpg://ap_user:<password>@postgres:5432/ap_db
DATABASE_URL_SYNC=postgresql://ap_user:<password>@postgres:5432/ap_db

# ─── Redis ─────────────────────────────────────────────
REDIS_PASSWORD=<strong-random-password>
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD}@redis:6379/1

# ─── MinIO ─────────────────────────────────────────────
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=<access-key>
MINIO_SECRET_KEY=<secret-key>
MINIO_BUCKET_NAME=ap-documents
MINIO_SECURE=true

# ─── Security (MUST change — minimum 64 chars random) ──
JWT_SECRET=<generate with: openssl rand -hex 32>
APPROVAL_TOKEN_SECRET=<generate with: openssl rand -hex 32>

# ─── AI ────────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...

# ─── Monitoring ────────────────────────────────────────
SENTRY_DSN=https://...@sentry.io/...
SENTRY_TRACES_SAMPLE_RATE=0.1

# ─── Email ─────────────────────────────────────────────
MAIL_ENABLED=true
MAIL_FROM=ap@yourcompany.com
```

#### `gunicorn.conf.py`
```python
"""Gunicorn production configuration."""
import multiprocessing

bind = "0.0.0.0:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
timeout = 120
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
preload_app = True
accesslog = "-"
errorlog = "-"
loglevel = "info"
```

Also add `gunicorn` to `backend/requirements.txt`:
```
gunicorn==23.0.0            # production WSGI server
```

### Commit
```
committer "feat: add production deployment config (docker-compose.prod, nginx, gunicorn)" \
  docker-compose.prod.yml \
  nginx/nginx.conf \
  .env.prod.example \
  gunicorn.conf.py \
  backend/requirements.txt
```

---

## Gap 8: Login/logout audit events

### Problem
User logins and logouts are not tracked — required for SOC2/SOX compliance.

### Fix: `backend/app/api/v1/auth.py`

In the login endpoint (after successful authentication, before returning token):
```python
# After: user = authenticate_user(...)
# Add:
audit_svc.log(
    db=db,
    action="user_login",
    entity_type="user",
    entity_id=user.id,
    actor_id=user.id,
    after={"email": user.email, "role": user.role, "ip": request.client.host if request.client else None},
    notes=f"Login from IP {request.client.host if request.client else 'unknown'}",
)
```

Add `request: Request` parameter to the login endpoint signature.
Import: `from fastapi import Request`
Import audit service: `from app.services import audit as audit_svc`

Also add to token refresh endpoint: `action="token_refreshed"`.

### Commit
```
committer "feat: audit log user login and token refresh events" \
  backend/app/api/v1/auth.py
```

---

## Gap 9: Additional security tests

### Create `backend/tests/test_security.py`
```python
"""Security and edge case tests."""

def test_login_returns_no_password_hash(client, admin_token):
    """User endpoint must never return password hash."""
    resp = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert "password" not in body
    assert "hashed_password" not in body

def test_ask_ai_blocked_keywords(client, analyst_token):
    """Ask AI must reject DML keywords."""
    for keyword in ["DROP TABLE", "DELETE FROM", "INSERT INTO", "UPDATE invoices SET"]:
        resp = client.post(
            "/api/v1/ask-ai",
            json={"question": keyword},
            headers={"Authorization": f"Bearer {analyst_token}"},
        )
        assert resp.status_code == 400, f"Should block: {keyword}"

def test_ask_ai_requires_auth(client):
    """Ask AI must reject unauthenticated requests."""
    resp = client.post("/api/v1/ask-ai", json={"question": "show invoices"})
    assert resp.status_code == 401

def test_payment_requires_admin(client, analyst_token, seed_invoice_id):
    """Payment endpoint requires ADMIN role."""
    resp = client.post(
        f"/api/v1/invoices/{seed_invoice_id}/payment",
        json={"payment_method": "ACH"},
        headers={"Authorization": f"Bearer {analyst_token}"},
    )
    assert resp.status_code == 403

def test_payment_requires_approved_status(client, admin_token, seed_invoice_id):
    """Payment can only be recorded for approved invoices."""
    # seed_invoice_id should be in 'ingested' status
    resp = client.post(
        f"/api/v1/invoices/{seed_invoice_id}/payment",
        json={"payment_method": "ACH"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 400
    assert "approved" in resp.json()["detail"].lower()

def test_vendor_portal_isolation(client, seed_vendor_id, seed_other_vendor_id):
    """Vendor portal must not expose other vendors' invoices."""
    # Issue portal token for vendor A, try to access vendor B's invoice
    invite_resp = client.post(
        "/api/v1/portal/auth/invite",
        json={"vendor_id": str(seed_vendor_id)},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    token = invite_resp.json()["token"]
    # Try to access invoice owned by other vendor — must 404
    resp = client.get(
        f"/api/v1/portal/invoices/{seed_other_vendor_invoice_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
```

Use the same `client`, `admin_token`, `analyst_token` fixtures from `conftest.py` or `test_auth.py`.

### Commit
```
committer "test: add security tests for auth, ask-ai, payment, and portal isolation" \
  backend/tests/test_security.py
```

---

## Gap 10: Frontend — payment status display + admin payment action

### Problem
Frontend has no way for ADMIN to mark an invoice as paid.

### Fix: `frontend/src/app/(app)/invoices/[id]/page.tsx`

In the invoice detail header action bar, when `invoice.status === "approved"` AND user is ADMIN, show a "Record Payment" button:
```tsx
{invoice.status === "approved" && user?.role === "ADMIN" && (
  <RecordPaymentDialog invoiceId={invoice.id} onSuccess={() => refetch()} />
)}
```

Create inline dialog component in the same file:
```tsx
function RecordPaymentDialog({ invoiceId, onSuccess }: { invoiceId: string; onSuccess: () => void }) {
  const [open, setOpen] = useState(false);
  const [method, setMethod] = useState("ACH");
  const [reference, setReference] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    setLoading(true);
    try {
      await api.post(`/invoices/${invoiceId}/payment`, {
        payment_method: method,
        payment_reference: reference || null,
      });
      setOpen(false);
      onSuccess();
    } catch { /* toast error */ } finally { setLoading(false); }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" className="border-green-300 text-green-700">Record Payment</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Record Payment</DialogTitle></DialogHeader>
        <div className="space-y-4">
          <div>
            <Label>Payment Method</Label>
            <Select value={method} onValueChange={setMethod}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="ACH">ACH</SelectItem>
                <SelectItem value="Wire">Wire Transfer</SelectItem>
                <SelectItem value="Check">Check</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Reference / Trace Number (optional)</Label>
            <Input value={reference} onChange={e => setReference(e.target.value)} placeholder="ACH trace number or check #" />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={handleSubmit} disabled={loading}>
            {loading ? "Recording..." : "Confirm Payment"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

### Commit
```
committer "feat: add Record Payment dialog in invoice detail for ADMIN" \
  "frontend/src/app/(app)/invoices/[id]/page.tsx"
```

---

## STATUS

- [ ] Gap 1: Error leakage fix + global 500 handler
- [ ] Gap 2: Rate limiting (slowapi)
- [ ] Gap 3: Request ID middleware + structured logging
- [ ] Gap 4: Sentry integration
- [x] Gap 5: Payment columns migration + endpoint
- [x] Gap 6: Performance indexes migration
- [ ] Gap 7: Production deployment config (docker-compose.prod, nginx, gunicorn)
- [ ] Gap 8: Login audit events
- [ ] Gap 9: Security tests
- [ ] Gap 10: Frontend payment dialog

STATUS: NOT CONVERGED
