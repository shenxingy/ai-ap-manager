# AI AP Operations Manager

AI-driven Accounts Payable automation platform for manufacturing and supply chain enterprises.

## What It Does

End-to-end AP automation: invoice ingestion → OCR extraction → 2/3-way matching → exception handling → approval workflows → payment recommendations → KPI reporting.

**Key principle**: Deterministic rule engine owns all business decisions. LLM is used only for structuring (OCR correction, policy parsing) — never for final approval decisions.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, TypeScript, shadcn/ui, TanStack Query |
| Backend | FastAPI, SQLAlchemy 2.0, Alembic |
| Database | PostgreSQL 16 |
| Queue | Celery + Redis |
| Storage | MinIO (S3-compatible) |
| OCR | Tesseract |
| AI | Claude claude-sonnet-4-6 (Anthropic) |
| Infra | Docker Compose |

## Quick Start

```bash
cp .env.example .env
# Fill in ANTHROPIC_API_KEY and other vars

docker-compose up -d
cd backend && alembic upgrade head
python scripts/seed.py

# Frontend: http://localhost:3000
# Backend API: http://localhost:8000/docs
# MinIO Console: http://localhost:9001
```

## Project Documentation

| Doc | Description |
|-----|-------------|
| [GOALS.md](GOALS.md) | Vision, milestones, success metrics |
| [TODO.md](TODO.md) | Task backlog (P0/P1/P2) |
| [docs/PRD.md](docs/PRD.md) | Product requirements, user journeys, scenarios |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture, data flow, module map |
| [docs/DATABASE.md](docs/DATABASE.md) | ERD, all table schemas |
| [docs/API.md](docs/API.md) | REST API endpoints with examples |
| [docs/RULES_ENGINE.md](docs/RULES_ENGINE.md) | Match engine, tolerance config, exception taxonomy |
| [docs/AI_MODULES.md](docs/AI_MODULES.md) | LLM integration design and safety guardrails |
| [docs/UI_IA.md](docs/UI_IA.md) | UI pages, components, table columns |
| [docs/SECURITY.md](docs/SECURITY.md) | RBAC, auth, audit, data protection |
| [docs/TESTING.md](docs/TESTING.md) | Test cases, E2E scenarios, acceptance criteria |
| [docs/MILESTONES.md](docs/MILESTONES.md) | Week-by-week development plan |

## Milestone Overview

- **MVP (Weeks 1-4)**: Upload → Extract → 2-way Match → Exception Queue → Single Approval → KPI
- **V1 (Weeks 5-8)**: 3-way Match + Multi-level Approval + CSV Import + Policy Rule Extraction
- **V2 (Weeks 9-12)**: AI Self-optimization + Root Cause Analysis + ERP Integration

## User Roles

`AP_CLERK` · `AP_ANALYST` · `APPROVER` · `ADMIN` · `AUDITOR`
