#!/usr/bin/env bash
# scripts/demo.sh — One-command demo startup for AI AP Manager
set -euo pipefail

BOLD="\033[1m"
GREEN="\033[0;32m"
CYAN="\033[0;36m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

info()    { echo -e "${CYAN}[demo]${RESET} $*"; }
success() { echo -e "${GREEN}[demo]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[demo]${RESET} $*"; }
die()     { echo -e "${RED}[demo] ERROR:${RESET} $*" >&2; exit 1; }

# ─── Prereq checks ───────────────────────────────────────────
command -v docker  >/dev/null 2>&1 || die "Docker not found. Install from https://docs.docker.com/get-docker/"
command -v docker-compose >/dev/null 2>&1 || die "docker-compose not found. Install Docker Desktop or docker-compose CLI."

# ─── .env setup ──────────────────────────────────────────────
if [ ! -f .env ]; then
  info "Creating .env from .env.example ..."
  cp .env.example .env
  warn ".env created. LLM_PROVIDER=claude_code (uses Claude Code CLI, free)."
  warn "To use Anthropic API instead, set ANTHROPIC_API_KEY in .env and LLM_PROVIDER=anthropic."
fi

# ─── Start services ──────────────────────────────────────────
info "Starting Docker services ..."
docker-compose up -d --remove-orphans

# ─── Wait for Postgres ───────────────────────────────────────
info "Waiting for PostgreSQL to be ready ..."
RETRIES=30
until docker-compose exec -T db pg_isready -U ap_user -d ap_db -q 2>/dev/null; do
  RETRIES=$((RETRIES - 1))
  [ "$RETRIES" -le 0 ] && die "PostgreSQL did not become ready in time."
  printf "."
  sleep 2
done
echo ""
success "PostgreSQL is ready."

# ─── Wait for backend ────────────────────────────────────────
info "Waiting for backend API to start ..."
RETRIES=30
until curl -s http://localhost:8002/health >/dev/null 2>&1; do
  RETRIES=$((RETRIES - 1))
  [ "$RETRIES" -le 0 ] && die "Backend did not start in time. Run 'make logs' to diagnose."
  printf "."
  sleep 2
done
echo ""
success "Backend is ready."

# ─── Migrations ──────────────────────────────────────────────
info "Running database migrations ..."
docker-compose exec -T backend alembic -c alembic.ini upgrade head
success "Migrations applied."

# ─── Seed data ───────────────────────────────────────────────
info "Seeding demo data (idempotent) ..."
docker-compose exec -T backend python scripts/seed.py
success "Seed data loaded."

# ─── Done ────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD}  AI AP Manager is ready!${RESET}"
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""
echo -e "  ${BOLD}Dashboard:${RESET}      http://localhost:3000"
echo -e "  ${BOLD}API Docs:${RESET}       http://localhost:8002/docs"
echo -e "  ${BOLD}MinIO Console:${RESET}  http://localhost:9001"
echo ""
echo -e "  ${BOLD}Demo accounts:${RESET}"
echo -e "  ┌─────────────────────────────────────────────────┐"
echo -e "  │  Role        Email                   Password   │"
echo -e "  │  ──────────  ──────────────────────  ─────────  │"
echo -e "  │  Admin       admin@example.com        changeme123│"
echo -e "  │  AP Analyst  analyst@example.com      changeme123│"
echo -e "  │  Approver    approver@example.com     changeme123│"
echo -e "  │  AP Clerk    clerk@example.com        changeme123│"
echo -e "  └─────────────────────────────────────────────────┘"
echo ""
echo -e "  ${BOLD}Useful commands:${RESET}"
echo -e "  make logs          — tail backend + worker logs"
echo -e "  make down          — stop all services"
echo -e "  make test          — run backend tests"
echo ""
