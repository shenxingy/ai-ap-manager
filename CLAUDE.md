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
├── frontend/               # Next.js app
│   ├── app/                # App Router pages
│   ├── components/         # Shared UI components
│   └── lib/                # API clients, utils
├── backend/                # FastAPI app
│   ├── app/
│   │   ├── api/            # Route handlers (v1/)
│   │   ├── core/           # Config, security, deps
│   │   ├── models/         # SQLAlchemy models
│   │   ├── schemas/        # Pydantic schemas
│   │   ├── services/       # Business logic
│   │   ├── rules/          # Rule engine (deterministic)
│   │   ├── ai/             # LLM integration layer
│   │   └── workers/        # Celery tasks
│   ├── alembic/            # DB migrations
│   └── tests/
├── docs/                   # All design docs
│   └── plans/              # Per-feature implementation plans
├── scripts/                # Dev utility scripts
├── docker-compose.yml
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
