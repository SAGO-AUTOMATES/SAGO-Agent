#!/usr/bin/env bash
# ==============================================================================
# SAGO Pre-Commit Verification Hook
# Fast check: linting and formatting check across staged / modified files
# ==============================================================================
set -e

echo "🔍 [SAGO Hook] Running pre-commit validation..."

# 1. Check if uv is available
if command -v uv &> /dev/null; then
    RUNNER="uv run --with ruff --with pytest"
else
    RUNNER="python -m"
fi

# 2. Run Ruff Lint Check
echo "  ↳ Checking code style with Ruff..."
$RUNNER ruff check sago/
if [ $? -ne 0 ]; then
    echo "❌ [SAGO Hook] Ruff lint check failed. Fix lint issues or run: uv run --with ruff ruff check sago/ --fix"
    exit 1
fi

# 3. Run Ruff Format Check
echo "  ↳ Checking code formatting with Ruff..."
$RUNNER ruff format --check sago/
if [ $? -ne 0 ]; then
    echo "❌ [SAGO Hook] Ruff format check failed. Auto-format with: uv run --with ruff ruff format sago/"
    exit 1
fi

echo "✅ [SAGO Hook] Pre-commit lint and format checks passed!"
exit 0
