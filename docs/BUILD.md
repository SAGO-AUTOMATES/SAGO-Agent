# SAGO-Agent — Build & Development Guide

> Complete guide for building, developing, and deploying Sago.

## Prerequisites

```bash
# Python 3.11+
python --version  # Should be 3.11+

# uv package manager (recommended)
pip install uv
# or
curl -LsSf https://astral.sh/uv/install.sh | sh

# Git
git --version
```

## Quick Start

```bash
# Clone the repo
git clone https://github.com/SAGO-AUTOMATES/SAGO-Agent.git
cd SAGO-Agent

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e ".[dev]"

# Set API keys
export OPENROUTER_API_KEY="your-key"

# Run
sago --help
sago tui
```

## Development Setup

### Using uv (Recommended)

```bash
# Install uv
pip install uv

# Sync dependencies
uv sync

# Run commands
uv run python -m sago --help
uv run ruff check .
```

### Using pip

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e ".[dev]"
```

## Build Commands

### Package Build

```bash
# Build wheel and sdist
uv build

# Install locally
uv pip install -e .

# Uninstall
pip uninstall sago
```

### Code Quality

```bash
# Lint
uv run ruff check sago/

# Lint with auto-fix
uv run ruff check --fix sago/

# Format
uv run ruff format sago/
```

## Local Development

### Run CLI

```bash
# Direct run
uv run python -m sago --help

# Or via entry point
sago --help

# Run task
sago smart "Fix the bug"

# Run TUI
sago tui
```

## Database

### SQLite Location

```bash
# Default: ~/.sago/data/sago.db
ls ~/.sago/data/

# Reset database
rm ~/.sago/data/sago.db
sago status  # Will recreate
```

## Configuration

### Environment Variables

```bash
# Required for OpenRouter (default provider)
export OPENROUTER_API_KEY="sk-or-..."

# Optional for OpenAI
export OPENAI_API_KEY="sk-..."

# Optional for Gemini
export GEMINI_API_KEY="AIza..."

# Optional for Claude
export ANTHROPIC_API_KEY="sk-ant-..."

# Debug mode
export SAGO_DEBUG=1

# Custom home directory
export SAGO_HOME=~/.custom-sago
```

### Project Config

```bash
# Initialize in project
cd your-project
sago init

# Creates config.sago.json
cat config.sago.json
```

## Git Workflow

### Branches

```bash
main        # Production code
develop     # Development branch
feature/*   # Feature branches
fix/*       # Bug fixes
```

### Commit Messages

```bash
feat: add new tool
fix: resolve agent loading issue
docs: update README
refactor: simplify caching logic
chore: update dependencies
```

## CI/CD

GitHub Actions runs on every push and PR:

1. **Lint** — Ruff code quality check
2. **Build** — Package build verification

See `.github/workflows/ci.yml` for the full pipeline.

## Troubleshooting

### Common Issues

```bash
# Module not found
uv sync  # Reinstall dependencies

# Import errors
pip install -e .  # Reinstall in dev mode

# LSP errors (false positives)
# LSP doesn't use uv virtualenv
# Verify with:
uv run python -c "import sago"

# Database locked
rm ~/.sago/data/sago.db  # Reset
```

## IDE Setup

### VS Code

```json
{
  "python.defaultInterpreterPath": ".venv/bin/python",
  "python.terminal.activateEnvironment": true,
  "editor.formatOnSave": true
}
```

## Release

```bash
# Build
uv build

# Check
twine check dist/*

# Upload to PyPI
twine upload dist/*

# Tag
git tag v0.1.6
git push origin v0.1.6
```

## Git Pre-Commit & Pre-Push Hooks

To install automated local lint, format, and test verification before commits/pushes:

```bash
./scripts/install-hooks.sh
```
