# AI AP Operations Manager — Claude Code Briefing

## Project Overview
Enterprise-grade AI-driven Accounts Payable (AP) automation platform.
Covers the full AP lifecycle: invoice ingestion → extraction → 2/3-way matching
→ exception handling → approval workflow → payment recommendation → KPI reporting.

## Tech Stack

### Frontend
- Next.js 14 (App Router) + TypeScript
- Tailwind CSS + shadcn/ui components
- React Query (TanStack) for server state
- Zustand for client state
- Located in: `frontend/`

### Backend
- FastAPI (Python 3.11) + SQLAlchemy 2.0 (async) + Alembic migrations
- Celery + Redis for async job queue
- Located in: `backend/`

### Database
- PostgreSQL 16 (primary data store)
- Redis 7 (cache + Celery broker)

### Storage
- MinIO (local S3-compatible) for invoice images and documents
- Bucket: `ap-documents`

### AI/ML
- OCR: Tesseract (local) / Google Cloud Vision (production)
- LLM: Claude claude-sonnet-4-6 via Anthropic API (`anthropic` Python SDK)
- LLM is ONLY used for: field extraction correction, policy parsing, root-cause narration
- LLM NEVER makes final match/approval decisions — deterministic rule engine does

### Infrastructure
- Docker Compose for local dev (see `docker-compose.yml`)
- No Kubernetes for MVP

## Directory Structure

```
ai-ap-manager/
├── frontend/               # Next.js 14 app
│   ├── src/
│   │   ├── app/            # App Router pages (including portal, auth)
│   │   ├── components/     # Shared UI components (layout, providers, ui, AskAiPanel)
│   │   ├── lib/            # API clients, utils, tests
│   │   └── store/          # Zustand state stores
│   └── public/             # Static assets
├── backend/                # FastAPI app
│   ├── app/
│   │   ├── api/            # Route handlers (v1/)
│   │   ├── core/           # Config, security, deps
│   │   ├── db/             # Database session management
│   │   ├── middleware/     # Request/response middleware (metrics, request-id)
│   │   ├── models/         # SQLAlchemy ORM models
│   │   ├── schemas/        # Pydantic request/response schemas
│   │   ├── services/       # Business logic (approval, fraud, GL, notifications, etc.)
│   │   ├── rules/          # Rule engine (deterministic match engine)
│   │   ├── ai/             # LLM integration layer
│   │   ├── integrations/   # ERP CSV imports (SAP, Oracle)
│   │   └── workers/        # Celery tasks + beat scheduler
│   ├── alembic/            # Database migrations
│   ├── tests/              # Test suite
│   └── scripts/            # Database seeding scripts
├── docs/                   # All design docs (architecture, API, rules, security, etc.)
│   ├── plans/              # Per-feature implementation plans
│   └── loop-history/       # Loop iteration logs and summaries
├── scripts/                # Root-level dev utility scripts
├── nginx/                  # Production reverse proxy config
├── docker-compose.yml      # Local development stack
├── docker-compose.prod.yml # Production stack (Nginx + Gunicorn)
├── Makefile                # Dev workflow shortcuts
└── .env.example
```

## Key Commands

```bash
# Start full stack locally
docker-compose up -d

# Backend dev server
cd backend && uvicorn app.main:app --reload

# Frontend dev server
cd frontend && npm run dev

# Run migrations
cd backend && alembic upgrade head

# Run backend tests
cd backend && pytest

# Run frontend tests
cd frontend && npm test

# Generate migration
cd backend && alembic revision --autogenerate -m "description"
```

## Coding Conventions

- All Python code: PEP 8, type hints required, docstrings on public functions
- All TypeScript: strict mode enabled
- API versioned at `/api/v1/`
- All LLM calls must log: prompt, response, token count, latency → `ai_call_logs` table
- All rule engine decisions must log: input snapshot, rule version used, output → `audit_logs`
- No hardcoded credentials — use `.env` / environment variables

## Things NOT To Do

- Do NOT let LLM directly approve/reject invoices or modify match results
- Do NOT skip audit logging for any state transition
- Do NOT delete invoices — soft-delete only (`deleted_at` timestamp)
- Do NOT bypass rule version draft→review→published flow
- Do NOT store raw credentials in database or code

## Environment Variables (see .env.example)

```
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://localhost:6379/0
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=...
MINIO_SECRET_KEY=...
ANTHROPIC_API_KEY=...
JWT_SECRET=...
```
