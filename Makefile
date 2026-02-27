.PHONY: up down logs migrate seed shell-db test lint

# ─── Docker ───
up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f backend worker

restart-backend:
	docker-compose restart backend worker

# ─── Database ───
migrate:
	docker-compose exec backend alembic upgrade head

migrate-gen:
	docker-compose exec backend alembic revision --autogenerate -m "$(MSG)"

migrate-down:
	docker-compose exec backend alembic downgrade -1

seed:
	docker-compose exec backend python scripts/seed.py

shell-db:
	docker-compose exec db psql -U ap_user -d ap_manager

# ─── Development ───
backend-dev:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend-dev:
	cd frontend && npm run dev

# ─── Testing ───
test:
	docker-compose exec backend pytest -v

test-coverage:
	docker-compose exec backend pytest --cov=app --cov-report=html

lint:
	cd backend && ruff check app && mypy app
