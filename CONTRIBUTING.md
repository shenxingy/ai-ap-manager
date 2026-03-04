# Contributing to AI AP Manager

Thank you for your interest in contributing! This guide will help you get started.

## Development Setup

### Prerequisites

- Docker & Docker Compose
- Node.js 20+ (for frontend development)
- Python 3.11+ (for backend development)

### Quick Start

```bash
git clone https://github.com/shenxingy/ai-ap-manager.git
cd ai-ap-manager
make demo
```

This starts all services, runs migrations, and loads seed data. See [README.md](README.md) for details.

### Running Without Docker

**Backend:**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8002
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

## Code Style

### Backend (Python)

- Follow PEP 8 with type hints on all function signatures
- Max line length: 120 characters
- Linting: `ruff check app` and `mypy app`
- Formatting: `ruff format app`

### Frontend (TypeScript)

- Strict TypeScript mode enabled
- Components use functional style with hooks
- UI built with shadcn/ui + Tailwind CSS

## Making Changes

1. **Fork** the repository and create a branch from `main`
2. **Write code** following the conventions above
3. **Test** your changes:
   ```bash
   make test          # Backend tests
   cd frontend && npm run build   # Frontend build check
   make lint          # Linting
   ```
4. **Commit** with clear, descriptive messages (conventional commits preferred):
   ```
   feat: add vendor risk threshold configuration
   fix: correct 3-way match tolerance calculation
   docs: update API endpoint reference
   ```
5. **Open a Pull Request** against `main`

## Pull Request Guidelines

- Keep PRs focused — one feature or fix per PR
- Include tests for new functionality
- Update documentation if you change APIs or configuration
- All CI checks must pass before merge

## Architecture Notes

- **Rule engine owns all business decisions** — the LLM assists with structuring (OCR, parsing) but never makes final approve/reject calls
- **Audit everything** — all state transitions must be logged
- **Soft delete only** — never hard-delete invoices or financial records
- See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full system design

## Reporting Issues

- Use the [Bug Report](https://github.com/shenxingy/ai-ap-manager/issues/new?template=bug_report.md) template for bugs
- Use the [Feature Request](https://github.com/shenxingy/ai-ap-manager/issues/new?template=feature_request.md) template for ideas
- Check existing issues before creating a new one

## Good First Issues

Look for issues labeled [`good first issue`](https://github.com/shenxingy/ai-ap-manager/labels/good%20first%20issue) — these are beginner-friendly tasks with clear scope.

## License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).
