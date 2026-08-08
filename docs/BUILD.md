# Sago - Build & Development Guide

> Complete guide for building, testing, and developing Sago locally.

## Prerequisites

```bash
# Python 3.11+
python --version  # Should be 3.11+

# uv package manager
pip install uv
# or
curl -LsSf https://astral.sh/uv/install.sh | sh

# Git
git --version
```

## Quick Start

```bash
# Clone the repo
git clone <repo-url>
cd sago

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e ".[dev]"

# Set API keys
export GEMINI_API_KEY="your-key"
export OPENAI_API_KEY="your-key"  # Optional

# Run
sago --help
sago tui
```

## Development Setup

### Using uv (Recommended)

```bash
# Install uv
pip install uv

# Create virtual environment
uv venv

# Activate
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate     # Windows

# Install dependencies
uv sync

# Add dev dependencies
uv add --dev pytest pytest-asyncio black ruff mypy

# Run commands
uv run python -m sago --help
uv run pytest
uv run black .
uv run ruff check .
uv run mypy sago/
```

### Using pip

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e ".[dev]"

# Install dev tools
pip install pytest pytest-asyncio black ruff mypy
```

## Build Commands

### Package Build

```bash
# Build wheel and sdist
uv build
# or
python -m build

# Install locally
uv pip install -e .
# or
pip install -e .

# Uninstall
pip uninstall sago
```

### Code Quality

```bash
# Format code
uv run black .
# or
black .

# Lint
uv run ruff check .
# or
ruff check .

# Lint with auto-fix
uv run ruff check --fix .
# or
ruff check --fix .

# Type check
uv run mypy sago/
# or
mypy sago/

# All checks
uv run black . && uv run ruff check . && uv run mypy sago/
```

## Testing

### Run All Tests

```bash
# Using uv
uv run pytest

# Using pytest directly
pytest

# With verbose output
uv run pytest -v

# With coverage
uv run pytest --cov=sago --cov-report=html
```

### Run Specific Tests

```bash
# Single test file
uv run pytest tests/test_agents.py

# Single test
uv run pytest tests/test_agents.py::test_load_agents

# By pattern
uv run pytest -k "agent"

# By marker
uv run pytest -m "slow"
```

### Test Categories

```bash
# Unit tests
uv run pytest tests/unit/

# Integration tests
uv run pytest tests/integration/

# CLI tests
uv run pytest tests/cli/

# TUI tests
uv run pytest tests/tui/
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
from sago.tools.file.directory_scanner import DirectoryScanner
scanner = DirectoryScanner()
result = scanner.scan('.')
print(f'Found {result.total_files} files')
print(f'Languages: {result.languages}')
"

# Test LLM
uv run python -c "
from sago.llm.factory import LLMFactory
factory = LLMFactory()
print('LLM Factory initialized')
"
```

### Debug Mode

```bash
# Enable debug logging
SAGO_DEBUG=1 sago smart "test task"

# Python debugger
uv run python -m pdb -m sago --help

# Verbose output
uv run python -m sago --verbose smart "test"
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

### Cache Location

```bash
# Default: ~/.sago/cache.json
cat ~/.sago/cache.json

# Clear cache
rm ~/.sago/cache.json
```

## Configuration

### Environment Variables

```bash
# Required for Gemini
export GEMINI_API_KEY="AIza..."

# Optional for OpenAI
export OPENAI_API_KEY="sk-..."

# Optional for Claude
export ANTHROPIC_API_KEY="sk-ant-..."

# Optional for OpenRouter
export OPENROUTER_API_KEY="sk-or-..."

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

## Code Style

### Python Style

- **Formatter**: Black (line length 88)
- **Linter**: Ruff
- **Type hints**: Required for all functions
- **Docstrings**: Google style

### Example

```python
"""Module docstring."""

from __future__ import annotations

from typing import Any


def my_function(arg: str, optional: int = 0) -> dict[str, Any]:
    """Function docstring.

    Args:
        arg: Description
        optional: Description

    Returns:
        Description
    """
    return {"key": arg}
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
docs: update PROJECT.md
refactor: simplify caching logic
test: add unit tests for scanner
chore: update dependencies
```

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

# Cache issues
rm ~/.sago/cache.json  # Clear
```

### Performance

```bash
# Profile Python
uv run python -m cProfile -s cumtime -m sago --help

# Memory usage
uv run python -m tracemalloc -m sago --help

# Cache stats
sago usage
```

## IDE Setup

### VS Code

```json
{
  "python.defaultInterpreterPath": ".venv/bin/python",
  "python.terminal.activateEnvironment": true,
  "editor.formatOnSave": true,
  "python.formatting.provider": "black"
}
```

### PyCharm

1. Set Python interpreter to `.venv/bin/python`
2. Enable Black formatter
3. Configure Ruff as linter

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
