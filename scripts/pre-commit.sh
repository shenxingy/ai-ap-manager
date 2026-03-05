#!/usr/bin/env bash
# Pre-commit hook: runs the same checks as CI before allowing a commit.
# Install: ln -sf ../../scripts/pre-commit.sh .git/hooks/pre-commit
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"

# ─── Detect what changed ───
CHANGED_PY=$(git diff --cached --name-only --diff-filter=ACM -- '*.py' || true)
CHANGED_TS=$(git diff --cached --name-only --diff-filter=ACM -- 'frontend/src/**' || true)

# ─── Backend lint (only if Python files changed) ───
if [ -n "$CHANGED_PY" ]; then
    echo "🔍 Running ruff check..."
    cd "$REPO_ROOT/backend"
    ruff check app || { echo "❌ ruff check failed"; exit 1; }

    echo "🔍 Running mypy..."
    mypy app --ignore-missing-imports || { echo "❌ mypy failed"; exit 1; }
    cd "$REPO_ROOT"
fi

# ─── Frontend type check (only if TS/TSX files changed) ───
if [ -n "$CHANGED_TS" ]; then
    echo "🔍 Running next build..."
    cd "$REPO_ROOT/frontend"
    npm run build || { echo "❌ frontend build failed"; exit 1; }
    cd "$REPO_ROOT"
fi

echo "✅ Pre-commit checks passed"
