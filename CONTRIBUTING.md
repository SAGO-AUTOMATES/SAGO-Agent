# Contributing to Sago

Thanks for your interest in contributing to Sago!

## Development Setup

1. Clone the repo:
```bash
git clone https://github.com/CrimsonDevil333333/sago.git
cd sago
```

2. Install dependencies:
```bash
uv sync --extra dev
```

3. Run the linter:
```bash
uv run ruff check sago/
```

4. Run type checker:
```bash
uv run mypy sago/
```

## Code Style

- Use type hints for all functions
- Keep each tool in its own file (1 tool per file)
- Follow PEP 8 (enforced by ruff)
- Add docstrings for public methods

## Adding a New Tool

1. Create a new file in the appropriate `sago/tools/<category>/` directory
2. Inherit from `BaseTool` in `sago/tools/base.py`
3. Implement the `_run()` method
4. Add an `ArgsModel` using Pydantic
5. Register the tool in `sago/config/tools.yaml`
6. Add the tool to the orchestrator's tool map in `sago/orchestrator/engine.py`

Example:

```python
"""My New Tool - Brief description."""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field
from sago.tools.base import BaseTool


class MyNewToolArgs(BaseModel):
    """Arguments for MyNewTool."""

    input_text: str = Field(description="Input text")


class MyNewTool(BaseTool):
    """Tool for doing something awesome."""

    name = "my_new_tool"
    description = "Description of what the tool does"
    args_model = MyNewToolArgs

    def _run(self, input_text: str, **kwargs: Any) -> str:
        """Execute the tool."""
        return f"Processed: {input_text}"
```

## Adding a New Agent

1. Add the agent config to `sago/config/agents.yaml`
2. Add routing triggers to `sago/config/sago.yaml`
3. Add the agent to `config.agents.enabled`

## Reporting Issues

- Use GitHub Issues
- Include steps to reproduce
- Include OS and Python version

## Pull Requests

1. Fork the repo
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Run linter and type checker
6. Submit a PR

## Testing Hallucination Prevention

The project has extensive hallucination prevention tests that must pass:

```bash
# Run hallucination prevention tests
python -m pytest tests/unit/test_hallucination_prevention.py -v

# Run hallucination verifier tests
python -m pytest tests/unit/test_hallucination_verifier.py -v

# Run all unit tests
python -m pytest tests/unit/ -q
```

When adding new features, ensure:
- No new fabrication phrases are introduced without tool verification
- Any new code block languages are added to `_CODE_BLOCK_LANGS` and `_CODE_EXTS`
- Any new tool categories are added to claim verification patterns
