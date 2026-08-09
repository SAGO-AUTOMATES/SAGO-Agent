# SAGO-Agent — Build & Development Guide

> Complete guide for building, testing, and developing Sago.

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
uv run pytest
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

## Testing

Sago includes **122 tests** across unit, integration, and security categories.

### Run All Tests

```bash
# Using uv
uv run pytest tests/ -v

# Using pytest directly
pytest tests/ -v
```

### Run Specific Test Categories

```bash
# Unit tests (tools, permissions, agents)
uv run pytest tests/unit/ -v

# Integration tests (executor, server, workflow, MCP)
uv run pytest tests/integration/ -v

# Security tests (path traversal, injection, bypass)
uv run pytest tests/security/ -v
```

### Run Specific Tests

```bash
# Single test file
uv run pytest tests/unit/test_tools.py

# Single test
uv run pytest tests/unit/test_tools.py::TestReadFileTool::test_read_file

# By pattern
uv run pytest -k "permission"

# With coverage
uv run pytest tests/ --cov=sago --cov-report=html
```

### Test Structure

```
tests/
├── __init__.py
├── unit/
│   ├── test_tools.py          # 30 tests - All 45 tools
│   ├── test_permissions.py    # 14 tests - Permission system
│   └── test_agents.py         # 13 tests - Agent registry
├── integration/
│   ├── test_executor.py       # 10 tests - Executor engine
│   ├── test_server.py         # 6 tests  - TCP daemon
│   ├── test_workflow.py       # 9 tests  - Workflow engine
│   └── test_mcp.py            # 7 tests  - MCP server
└── security/
    └── test_security.py       # 16 tests - Security audit
```

### Test Coverage

| Category | Tests | What's Tested |
|----------|-------|---------------|
| Unit - Tools | 30 | All 45 tools with proper arguments |
| Unit - Permissions | 14 | Risk levels, blocking, approval workflow |
| Unit - Agents | 13 | Registry, profiles, lookup, reload |
| Integration - Executor | 10 | Tool discovery, task detection, extraction |
| Integration - Server | 6 | Daemon init, client, protocol |
| Integration - Workflow | 9 | Engine, steps, dependencies, cancellation |
| Integration - MCP | 7 | Server creation, tools, registration |
| Security | 16 | Path traversal, injection, bypass, validation |
| **Total** | **122** | **All passing** |

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

### Run Tests Manually

```bash
# Test agent loading
uv run python -c "
from sago.agents.registry import list_agents
agents = list_agents()
print(f'Loaded {len(agents)} agents')
"

# Test tools
uv run python -c "
from sago.engine.simple_executor import _discover_tools
tools = _discover_tools()
print(f'Discovered {len(tools)} tools')
"

# Test permissions
uv run python -c "
from sago.permissions import get_permission_manager
pm = get_permission_manager()
allowed, reason = pm.check_permission('read_file')
print(f'read_file: {allowed} ({reason})')
"
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
test: add unit tests for scanner
chore: update dependencies
```

## CI/CD

GitHub Actions runs on every push and PR:

1. **Lint** — Ruff code quality check
2. **Unit Tests** — Tool, permission, agent tests
3. **Integration Tests** — Executor, server, workflow, MCP tests
4. **Security Tests** — Vulnerability checks
5. **Build** — Package build verification

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
# Run: uv run python -c "import sago"

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
git tag v0.1.0
git push origin v0.1.0
```
