# AI AP Operations Manager

AI-driven Accounts Payable automation platform for manufacturing and supply chain enterprises.

## What It Does

End-to-end AP automation: invoice ingestion → OCR extraction → 2/3/4-way matching → exception handling → approval workflows → payment recommendations → KPI reporting.

**Key principle**: Deterministic rule engine owns all business decisions. LLM is used only for structuring (OCR correction, policy parsing, root-cause narration) — never for final approval decisions.

## Feature Highlights

| Module | Features |
|--------|---------|
| **Ingestion** | Email IMAP polling, PDF/image upload, OCR extraction, recurring invoice detection |
| **Matching** | 2-way (Invoice vs PO), 3-way (+ GRN), 4-way (+ inspection), multi-currency FX |
| **Exceptions** | Auto-routing rules, exception queue, vendor communication hub |
| **Approvals** | Multi-level matrix, email-token approval, escalation, Slack/Teams alerts |
| **Intelligence** | GL ML classifier (TF-IDF + LR), fraud scoring, rule self-optimization |
| **Analytics** | KPI dashboard, cash flow forecast, industry benchmarks, root cause AI |
| **Vendor Portal** | Invoice status, disputes, template-based submissions |
| **Admin** | ERP CSV sync (SAP/Oracle), multi-entity, GDPR retention, vendor risk scores |

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
| ML | scikit-learn (GL coding classifier) |
| Infra | Docker Compose |

## Quick Start

```bash
cp .env.example .env
# Fill in ANTHROPIC_API_KEY and other vars

docker-compose up -d

# Run migrations
docker exec ai-ap-manager-backend-1 alembic -c alembic.ini upgrade head

# Seed demo data
docker exec ai-ap-manager-backend-1 python scripts/seed.py

# Frontend:     http://localhost:3000
# Backend API:  http://localhost:8002/docs
# MinIO Console: http://localhost:9001
```

Default demo credentials (seeded):
- Admin: `admin@example.com` / `admin123`
- Analyst: `analyst@example.com` / `analyst123`

## Project Documentation

| Doc | Description |
|-----|-------------|
| [GOALS.md](GOALS.md) | Vision, milestones, north star metrics |
| [TODO.md](TODO.md) | Task backlog (P0/P1/P2/P3) |
| [PROGRESS.md](PROGRESS.md) | Development log and lessons learned |
| [docs/PRD.md](docs/PRD.md) | Product requirements, user journeys |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture, data flow, module map |
| [docs/DATABASE.md](docs/DATABASE.md) | ERD, all table schemas |
| [docs/API.md](docs/API.md) | REST API endpoints with examples |
| [docs/RULES_ENGINE.md](docs/RULES_ENGINE.md) | Match engine, tolerance config, exception taxonomy |
| [docs/AI_MODULES.md](docs/AI_MODULES.md) | LLM integration design and safety guardrails |
| [docs/GAP_ANALYSIS.md](docs/GAP_ANALYSIS.md) | Feature completion audit (all gaps closed) |
| [docs/SECURITY.md](docs/SECURITY.md) | RBAC, auth, audit, data protection |
| [docs/TESTING.md](docs/TESTING.md) | Test cases, E2E scenarios, acceptance criteria |

## Implementation Status

All planned features through V2 are implemented:

- ✅ **MVP (P0)**: Invoice upload → OCR → 2-way match → exception queue → approval → KPI
- ✅ **V1 (P1)**: 3-way match + email IMAP + multi-level approval + recurring detection + vendor portal
- ✅ **V2 (P2)**: ERP CSV sync + FX rates + GL ML classifier + 4-way match + multi-entity + fraud upgrades
- ✅ **Selected P3**: Slack/Teams alerts + vendor risk scoring + GDPR retention + invoice templates

Remaining roadmap items (not gaps): PWA service worker, in-app notifications, live ERP API connectors (BAPI/REST), E2E test suite, Prometheus metrics.

## User Roles

`AP_CLERK` · `AP_ANALYST` · `APPROVER` · `ADMIN` · `AUDITOR`

- **AP Clerk**: Upload invoices, view status
- **AP Analyst**: Manage exceptions, GL coding, vendor communication
- **Approver**: Review and approve/reject pending invoices
- **Admin**: Full access, user management, rules, ERP config
- **Auditor**: Read-only audit trail access

## Development

```bash
# Backend dev server (hot reload)
cd backend && uvicorn app.main:app --reload --port 8002

# Frontend dev server
cd frontend && npm run dev

# Generate a new migration
docker exec ai-ap-manager-backend-1 alembic -c alembic.ini revision --autogenerate -m "description"

# Run backend tests
cd backend && pytest

# Docker ports
# PostgreSQL: 5433 (host) → 5432 (container)
# Redis:      6380 (host) → 6379 (container)
# MinIO:      9000/9001 (host)
# Backend:    8002 (host)
# Frontend:   3000 (host)
```
