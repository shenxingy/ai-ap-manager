<h1 align="center">AI AP Operations Manager</h1>

<p align="center">
  <strong>AI-native Accounts Payable automation for manufacturing and supply chain enterprises.</strong>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License"></a>
  <a href="https://github.com/shenxingy/ai-ap-manager/actions"><img src="https://github.com/shenxingy/ai-ap-manager/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11-blue.svg" alt="Python"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.115-009688.svg" alt="FastAPI"></a>
  <a href="https://nextjs.org/"><img src="https://img.shields.io/badge/Next.js-14-black.svg" alt="Next.js"></a>
  <a href="https://docs.docker.com/compose/"><img src="https://img.shields.io/badge/Docker-Compose-2496ED.svg" alt="Docker"></a>
</p>

<p align="center">
  End-to-end AP automation: invoice ingestion &rarr; OCR extraction &rarr; 2/3/4-way matching &rarr; exception handling &rarr; approval workflows &rarr; payment tracking &rarr; KPI reporting.
</p>

---

<!-- TODO: Add screenshots after running Docker with seed data
<p align="center">
  <img src="docs/screenshots/dashboard.png" width="800" alt="Dashboard">
</p>
-->

## Key Principle

A **deterministic rule engine** owns all business decisions. The LLM assists with structuring tasks (OCR correction, policy parsing, root-cause narration) but **never** makes final approve/reject decisions. Every decision is auditable and traceable to a specific rule version.

---

## Quick Start

```bash
git clone https://github.com/shenxingy/ai-ap-manager.git
cd ai-ap-manager
make demo
```

That's it. The script will:
1. Copy `.env.example` -> `.env` (LLM defaults to `claude_code` -- free, no API key needed)
2. Start all Docker services
3. Run database migrations
4. Load seed data (vendors, POs, invoices, users)
5. Print access URLs and demo credentials

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:3000 |
| API Docs (Swagger) | http://localhost:8002/docs |
| MinIO Console | http://localhost:9001 |

**Demo accounts** (password: `changeme123`):

| Role | Email |
|------|-------|
| Admin | admin@example.com |
| AP Analyst | analyst@example.com |
| Approver | approver@example.com |
| AP Clerk | clerk@example.com |

---

## Features

### Ingestion & Extraction
- Email IMAP polling (monitors AP mailbox, extracts attachments)
- PDF/image upload via UI or API
- Tesseract OCR + LLM field correction
- Recurring invoice detection and duplicate detection

### Matching Engine
- **2-way match**: Invoice vs Purchase Order (amount + quantity tolerance)
- **3-way match**: + Goods Receipt Note (partial receipt, multi-GRN aggregation)
- **4-way match**: + Inspection Report (quality-inspection workflows)
- Per-vendor / per-category / per-currency tolerance overrides
- Multi-currency with daily ECB FX rates

### Exception Handling
- Typed exception taxonomy: `PRICE_OVER_TOLERANCE`, `QTY_OVER_RECEIPT`, `GRN_NOT_FOUND`, `DUPLICATE`, `FRAUD_SUSPECT`, etc.
- Auto-routing rules (assign exceptions to teams/users by type/vendor/amount)
- Exception comment threads and vendor portal

### Approval Workflow
- Multi-level approval matrix (configurable by amount tier and department)
- Email-token approvals (HMAC-signed, one-click approve/reject)
- Approval escalation with configurable SLA
- Slack/Teams webhook notifications

### Intelligence Layer
- **GL ML Classifier**: TF-IDF + Logistic Regression, weekly auto-retrain
- **Fraud Scoring**: Rule-based (duplicate vendor/bank, round-amount flags, velocity checks)
- **Rule Self-Optimization**: Recommendations from override history
- **Root Cause Analysis**: LLM-generated narrative for exception spikes
- **Policy Parsing**: Upload a policy PDF, LLM extracts rules, human reviews, then publish

### Analytics & KPI
- KPI dashboard: touchless rate, cycle time, exception rate, GL accuracy, fraud catch rate
- Industry benchmarks comparison
- Cash flow forecast and audit trail export (CSV)

### Admin & Operations
- RBAC: `AP_CLERK`, `AP_ANALYST`, `APPROVER`, `ADMIN`, `AUDITOR`
- Multi-entity support (subsidiaries with entity selector)
- ERP CSV sync: SAP PO import, Oracle GRN import
- GDPR data retention automation
- Vendor risk scoring and in-app notification center

---

## Architecture

```mermaid
graph TB
    subgraph Ingestion
        A[Email IMAP] --> C[Celery Worker]
        B[PDF/Image Upload] --> C
        C --> D[OCR - Tesseract]
        D --> E[LLM Field Correction]
    end

    subgraph Core Pipeline
        E --> F[Match Engine]
        F --> G{Match Result}
        G -->|matched| H[Approval Workflow]
        G -->|exception| I[Exception Queue]
        I --> J[Auto-Routing Rules]
        J --> H
    end

    subgraph Intelligence
        K[GL ML Classifier] --> H
        L[Fraud Scoring] --> F
        M[Rule Self-Optimization] --> F
        N[Recurring Detection] --> C
    end

    subgraph Output
        H --> O[Payment Tracking]
        O --> P[KPI Dashboard]
        P --> Q[Cash Flow Forecast]
    end

    subgraph External
        R[Vendor Portal] --> I
        S[ERP CSV Sync] --> F
        T[Slack/Teams Alerts] --> H
    end

    style Ingestion fill:#e8f4fd,stroke:#1e88e5
    style Core Pipeline fill:#f3e5f5,stroke:#8e24aa
    style Intelligence fill:#e8f5e9,stroke:#43a047
    style Output fill:#fff3e0,stroke:#fb8c00
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, TypeScript, shadcn/ui, Recharts |
| Backend | FastAPI, SQLAlchemy 2.0, Alembic, Pydantic |
| Database | PostgreSQL 16 |
| Queue | Celery + Redis 7 |
| Storage | MinIO (S3-compatible) |
| OCR | Tesseract (local) / Google Vision (prod) |
| AI/LLM | Claude Sonnet via Anthropic API |
| ML | scikit-learn (TF-IDF + Logistic Regression) |
| Infra | Docker Compose (dev) / Nginx + Gunicorn (prod) |

---

## LLM Configuration

Four backends, switchable via `.env` -- no code changes needed:

| Provider | Setup | Cost | Notes |
|----------|-------|------|-------|
| `claude_code` | Claude Code CLI installed | **Free** | Default for local dev |
| `anthropic` | `ANTHROPIC_API_KEY` in `.env` | Pay-per-token | Required for Ask AI feature |
| `ollama` | Ollama running locally | Free | Privacy-first self-hosting |
| `none` | Nothing | Free | Disables AI, manual review only |

Per-use-case overrides: set `LLM_PROVIDER_EXTRACTION`, `LLM_PROVIDER_POLICY`, `LLM_PROVIDER_ANALYTICS`, `LLM_PROVIDER_ASK_AI` independently in `.env`.

---

## Project Structure

```
ai-ap-manager/
├── frontend/               # Next.js 14 (App Router)
│   ├── src/app/            # Pages: dashboard, invoices, exceptions, approvals, admin, portal
│   ├── src/components/     # UI components (shadcn/ui based)
│   └── src/lib/            # Axios API client, React Query hooks, Zustand stores
├── backend/
│   ├── app/
│   │   ├── api/v1/         # REST endpoints
│   │   ├── core/           # Config, security, dependencies
│   │   ├── models/         # SQLAlchemy ORM models
│   │   ├── schemas/        # Pydantic request/response schemas
│   │   ├── services/       # Business logic
│   │   ├── rules/          # Deterministic match engine (2/3/4-way)
│   │   ├── ai/             # LLM abstraction layer (4 providers)
│   │   ├── integrations/   # ERP CSV imports (SAP, Oracle)
│   │   └── workers/        # Celery tasks + beat schedule
│   ├── alembic/            # Database migrations
│   └── tests/              # Test suite
├── docs/                   # Architecture, API, rules engine, security docs
├── nginx/                  # Production reverse proxy config
├── docker-compose.yml      # Local development stack
├── docker-compose.prod.yml # Production stack
└── Makefile                # Dev workflow shortcuts
```

---

## Development

```bash
make up              # Start all Docker services
make migrate         # Run Alembic migrations
make seed            # Load demo data (idempotent)
make logs            # Tail backend + worker logs
make test            # Run backend tests
make test-coverage   # Tests with HTML coverage report
make lint            # ruff + mypy

# Generate a new migration
make migrate-gen MSG="add vendor risk table"
```

**Running without Docker (backend only)**:
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8002
```

| Service | Host Port |
|---------|-----------|
| Frontend | 3000 |
| Backend API | 8002 |
| PostgreSQL | 5433 |
| Redis | 6380 |
| MinIO API | 9000 |
| MinIO Console | 9001 |

---

## Production Deployment

A production-ready `docker-compose.prod.yml` with Nginx reverse proxy and Gunicorn (120s timeout for LLM calls) is included:

```bash
cp .env.example .env.prod
# Edit: set ANTHROPIC_API_KEY, strong JWT_SECRET, production DB creds, DOMAIN_NAME

docker compose -f docker-compose.prod.yml up -d
```

---

## Documentation

| Doc | Description |
|-----|-------------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture, data flow, module map |
| [PRD.md](docs/PRD.md) | Product requirements and user journeys |
| [DATABASE.md](docs/DATABASE.md) | ERD and all table schemas |
| [API.md](docs/API.md) | REST API endpoint reference |
| [RULES_ENGINE.md](docs/RULES_ENGINE.md) | Match engine design, tolerance config, exception taxonomy |
| [AI_MODULES.md](docs/AI_MODULES.md) | LLM integration design and safety guardrails |
| [SECURITY.md](docs/SECURITY.md) | RBAC, authentication, audit, data protection |

---

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions and guidelines.

```bash
make test   # Run tests before submitting
make lint   # Check linting
```

---

## License

[Apache License 2.0](LICENSE)
