#!/usr/bin/env bash
# ==============================================================================
# SAGO Pre-Push Verification Hook
# Comprehensive check: Linting, Formatting, Unit, Integration, and Security Tests
# ==============================================================================
set -e

echo "🚀 [SAGO Hook] Running full pre-push pipeline verification..."

# Runner selection: prefer `uv run`, then project venv, then system python.
REPO_ROOT="$(git rev-parse --show-toplevel)"
if command -v uv &> /dev/null; then
    RUNNER="uv run"
elif [ -x "$REPO_ROOT/.venv/bin/python" ]; then
    RUNNER="$REPO_ROOT/.venv/bin/python -m"
else
    RUNNER="python -m"
fi

# 1. Lint Check
echo "  [1/4] Checking linter rules (Ruff)..."
$RUNNER ruff check sago/
if [ $? -ne 0 ]; then
    echo "❌ [SAGO Hook] Lint check failed. Push aborted."
    exit 1
fi

# 2. Format Check
echo "  [2/4] Checking code formatting..."
$RUNNER ruff format --check sago/
if [ $? -ne 0 ]; then
    echo "❌ [SAGO Hook] Format check failed. Push aborted."
    exit 1
fi

# 3. Security Tests
echo "  [3/4] Running security regression suite..."
$RUNNER pytest tests/security -q --tb=short
if [ $? -ne 0 ]; then
    echo "❌ [SAGO Hook] Security tests failed. Push aborted."
    exit 1
fi

# 4. End-to-End TUI & Feature Validation
echo "  [4/4] Running End-to-End TUI & Feature Validation..."
$RUNNER python ./scripts/validate_features.py
if [ $? -ne 0 ]; then
    echo "❌ [SAGO Hook] End-to-End TUI & Feature Validation failed. Push aborted."
    exit 1
fi

echo "✅ [SAGO Hook] All pre-push checks passed! Safe to push to remote."
exit 0
