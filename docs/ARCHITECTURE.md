# System Architecture — AI AP Operations Manager

## Architecture Principles

1. **Deterministic rule engine owns all business decisions** — LLM is advisory only
2. **Every state transition is audited** — immutable append-only event log
3. **Async by default** — OCR/LLM extraction runs in background workers
4. **Rule versioning** — all match decisions reference a specific published rule version
5. **Fail safe** — if OCR or LLM fails, invoice goes to manual review queue, never silently dropped

---

## Module Map

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js)                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────┐ │
│  │ Workbench│ │Exception │ │ Approval │ │   KPI    │ │ Admin │ │
│  │Dashboard │ │  Queue   │ │  Tasks   │ │ Dashboard│ │ Panel │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └───┬───┘ │
└───────┼────────────┼────────────┼─────────────┼───────────┼─────┘
        │            │            │             │           │
        └────────────┴────────────┴─────────────┴───────────┘
                                  │ REST API (JWT)
┌─────────────────────────────────▼───────────────────────────────┐
│                       BACKEND (FastAPI)                          │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    API Layer (v1/)                         │  │
│  │  /invoices  /exceptions  /approvals  /kpi  /rules  /auth  │  │
│  └───────────────────────┬───────────────────────────────────┘  │
│                          │                                       │
│  ┌────────────┐  ┌────────▼───────┐  ┌───────────────────────┐  │
│  │  Services  │  │ Rule Engine    │  │   AI Layer            │  │
│  │ (business  │  │ (deterministic │  │ (LLM calls, always    │  │
│  │  logic)    │  │  match/route)  │  │  logged, never direct │  │
│  └──────┬─────┘  └────────────────┘  │  decision authority)  │  │
│         │                            └───────────────────────┘  │
│  ┌──────▼────────────────────────────────────────────────────┐  │
│  │               Celery Workers (async tasks)                 │  │
│  │   OCRWorker  │  ExtractionWorker  │  MatchWorker  │  Import│  │
│  └──────┬────────────────────────────────────────────────────┘  │
│         │                                                        │
│  ┌──────▼────────────────────────────────────────────────────┐  │
│  │                  Data Layer                                │  │
│  │  SQLAlchemy ORM  │  Alembic migrations  │  Audit logger   │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
        │              │              │              │
   ┌────▼────┐    ┌────▼────┐   ┌────▼────┐   ┌────▼────┐
   │Postgres │    │  Redis  │   │  MinIO  │   │Anthropic│
   │  (data) │    │(queue/  │   │(storage)│   │   API   │
   │         │    │ cache)  │   │         │   │  (LLM)  │
   └─────────┘    └─────────┘   └─────────┘   └─────────┘
```

---

## Data Flow: Invoice Ingestion to Approval

```
1. INGESTION
   User uploads PDF → API → save to MinIO → create invoice(status=received)
   → publish Celery task: ocr_extract(invoice_id)
   → return {id, status: "received", job_id}

2. OCR EXTRACTION (async worker)
   Celery picks up task → read PDF from MinIO
   → Tesseract OCR → raw text
   → invoice.status = "extracting"
   → ai_extract(raw_text) → structured JSON (LLM)
   → store in invoices + invoice_line_items
   → log to ai_call_logs
   → invoice.status = "extracted"
   → if confidence < threshold → create OCR_LOW_CONFIDENCE exception

3. MASTER DATA VALIDATION (sync, in worker)
   vendor_id resolved? (fuzzy match on name/tax_id)
   PO number valid? (lookup in purchase_orders)
   Duplicate check (query invoices table)
   → update invoice.vendor_id, invoice.po_id
   → if duplicate → create DUPLICATE_INVOICE exception, stop
   → invoice.status = "validating" → "matching"

4. MATCH ENGINE (sync, in worker)
   Load active rule_version (status=published)
   run_2way_match() or run_3way_match()
   → store match_results (each line)
   → if all MATCHED and total < auto_approve_threshold → auto-approve
   → else if any MISMATCH → create exceptions
   → invoice.status = "matched" | "exception"
   → log all decisions to audit_logs with rule_version_id

5. EXCEPTION HANDLING (human async)
   AP Analyst opens exception queue
   Reviews match evidence, contacts vendor, adds comments
   Marks exception resolved → invoice → pending_approval

6. APPROVAL ROUTING (sync, triggered on exception resolve or auto)
   route_approval(invoice) → lookup approval_matrix
   create ApprovalTask records (one per level)
   notify approvers (email/in-app)
   → invoice.status = "pending_approval"

7. APPROVAL DECISION (human async)
   Approver opens approval task
   Reviews invoice + supporting docs
   Approve → if last level → invoice.status = "approved"
   Reject → invoice.status = "rejected", notify AP Analyst
   → log to audit_logs

8. PAYMENT RECOMMENDATION
   Approved invoice → generate payment_record (due_date, vendor bank, amount)
   → push to ERP (SAP/Oracle) via integration adapter
   → invoice.status = "paid"
   → KPI updated
```

---

## Event Log & Audit Chain Design

The `audit_logs` table is the **immutable event source** for all state changes.

### Audit Log Entry Anatomy
```json
{
  "id": 10042,                      // sequential (ordering guaranteed)
  "entity_type": "invoice",
  "entity_id": "inv-uuid",
  "actor_id": "user-uuid",          // null for system actions
  "actor_type": "user|system|ai",
  "action": "status_changed",
  "old_value": { "status": "extracting" },
  "new_value": { "status": "extracted" },
  "metadata": {
    "ai_call_log_id": "ai-log-uuid",
    "rule_version_id": "rv-uuid",
    "confidence": 0.92
  },
  "created_at": "2026-02-26T10:00:18Z"
}
```

### Audit Middleware (FastAPI)
Every API route that mutates state calls `audit_log()` before returning.
Celery tasks do the same at each step transition.

```python
# Decorator for automatic audit logging
def audited(action: str):
    def decorator(fn):
        async def wrapper(*args, **kwargs):
            old_state = snapshot_entity(...)
            result = await fn(*args, **kwargs)
            new_state = snapshot_entity(...)
            await write_audit_log(action, old_state, new_state, actor=current_user)
            return result
        return wrapper
    return decorator
```

### Audit Replay
Given any invoice ID at any point in time, reconstruct its full decision history:
```sql
SELECT * FROM audit_logs
WHERE entity_type = 'invoice' AND entity_id = $1
ORDER BY id ASC;
```

---

## Integration Architecture

```
External Sources                    Integration Adapters
─────────────                      ──────────────────────
Email (AP mailbox)  → EmailPoller → POST /invoices/upload
ERP CSV export      → CSV Import  → POST /import/purchase-orders
ERP REST API (SAP)  → ERPAdapter  → sync POs/GRNs, push vouchers
Cloud OCR API       → OCRAdapter  → fallback if Tesseract confidence low
```

All integrations are wrapped in adapter classes so implementations are swappable.
For MVP, only CSV import and manual upload are required.

---

## Tech Stack Details

| Layer | Technology | Version | Rationale |
|-------|-----------|---------|-----------|
| Frontend | Next.js | 14 (App Router) | Full-stack React, SSR for SEO, API routes available |
| UI Library | shadcn/ui + Tailwind | latest | Accessible, customizable components |
| State (server) | TanStack Query | v5 | Cache management, optimistic updates |
| State (client) | Zustand | v4 | Simple, no boilerplate |
| Backend | FastAPI | 0.110 | Python, async, OpenAPI auto-docs |
| ORM | SQLAlchemy | 2.0 async | Typed queries, Alembic migrations |
| Task Queue | Celery + Redis | 5.3 | Mature, reliable, supports priority queues |
| Database | PostgreSQL | 16 | JSONB for flexible fields, full-text search |
| Cache | Redis | 7 | Celery broker + result backend |
| Storage | MinIO | latest | S3-compatible, runs locally |
| OCR | Tesseract | 5 | Open source, good enough for printed invoices |
| LLM | Claude claude-sonnet-4-6 | API | Structured output, high accuracy for extraction |
| Auth | JWT (python-jose) | — | Stateless, no session store needed |
| Dev infra | Docker Compose | — | One command local stack |

---

## Local Development Setup

```yaml
# docker-compose.yml (abbreviated)
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: ap_db
      POSTGRES_USER: ap_user
      POSTGRES_PASSWORD: ap_pass
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - miniodata:/data

  backend:
    build: ./backend
    command: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    volumes:
      - ./backend:/app
    env_file: .env
    depends_on: [db, redis, minio]
    ports:
      - "8000:8000"

  worker:
    build: ./backend
    command: celery -A app.workers.celery_app worker --loglevel=info
    volumes:
      - ./backend:/app
    env_file: .env
    depends_on: [db, redis, minio]

  frontend:
    build: ./frontend
    command: npm run dev
    volumes:
      - ./frontend:/app
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000
    ports:
      - "3000:3000"

volumes:
  pgdata:
  miniodata:
```
