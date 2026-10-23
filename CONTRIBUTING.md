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

## Error Handling & Logging

### Use `log_exception()` instead of silent `pass`

```python
# BAD - silent error, impossible to debug
except Exception:
    pass

# GOOD - error is logged with context
except Exception as e:
    log_exception(e, "Failed to load config")
```

Import from: `from sago.utils.safe import log_exception`

### Logging Levels

- `logger.debug()` - Verbose details (tool args, API responses, file contents)
- `logger.info()` - Important milestones (task started, agent selected, verification complete)
- `logger.warning()` - Recoverable issues (fallback used, retry needed)
- `logger.error()` - Failures that need attention

### Log Files

Logs are written to `~/.sago/logs/sago.log` with daily rotation. When reporting bugs, include relevant log excerpts.

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

### API Mode Changes

When making API-related changes, ensure all of the following:

- [ ] All existing TUI tests pass: `uv run pytest tests/tui/ -x`
- [ ] All existing unit tests pass: `uv run pytest tests/unit/ -x`
- [ ] All existing integration tests pass: `uv run pytest tests/integration/ -x`
- [ ] Feature parity: Sample task run via API, compare results to native
- [ ] State recovery: Kill API server, resume task via native, verify state
- [ ] Permission system: Verify both paths respect same permissions.json
- [ ] Hallucination verification: Same results on sample hallucinated content
- [ ] Checkpoint system: Create/restore via both paths produce same workspace
- [ ] Session persistence: Save/load via both paths produce same data
- [ ] Developer mode: `/dev` features work via both paths
- [ ] Hot-reload: Switch config from native to api, TUI auto-reloads
- [ ] No existing functionality removed or changed
- [ ] All features from preservation matrix verified
- [ ] Documentation updated: README, contributing, API guide
- [ ] Rollback procedures tested and documented
- [ ] API is truly opt-in (no default-on for existing users)

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

## API Mode Development Guidelines

### Core Principles

1. **Opt-In Only**: API mode is purely opt-in. Default must remain `native`. Existing
   TUI/CLI workflows must work unchanged without any config modification.

2. **Feature Parity**: Every feature available in native mode must also be available
   in API mode. The feature preservation matrix in `docs/API_MIGRATION_GUIDE.md`
   tracks this guarantee.

3. **Backward Compatibility**: All config changes must be backward compatible.
   New config keys must have sensible defaults so existing configs continue to work.

4. **Hot-Reload Robustness**: Config changes must work without server restart.
   Use the filesystem watcher or `/reload` endpoint.

5. **Identical Results**: Same task, native vs API, must produce identical results
   (output, tool calls, iterations, tokens, confidence).

### Adding New API Endpoints

1. Add endpoint to `sago/api/server.py`
2. Ensure execution uses `unified.execute()` (same flow as TUI)
3. Return structured results matching the TUI format
4. Add test coverage in `tests/integration/`
5. Update `docs/API_MIGRATION_GUIDE.md` feature preservation matrix
6. Ensure backward compatibility — default mode must remain `native`

### Config Changes

1. Add new config keys to `ExecutionConfig` in `sago/config/loader.py`
2. Add default values so existing configs remain valid
3. Test hot-reload after config changes
4. Ensure changes are backward compatible (no breaking defaults)
5. Update `docs/API_MIGRATION_GUIDE.md` matrix

### Rollback Plan

If API mode introduces a critical issue:

1. Edit `config.yaml`: `execution.mode: "native"`
2. Restart TUI: `sago tui` (reads config on start, switches to native)
3. Or kill API server: `pkill -f "uvicorn sago.api.server"`
4. Verify: `sago tui` and `sago run "test task"` work as before

### Documentation Requirements

Before merging API-related changes:

- [ ] `README.md` updated with API mode section (opt-in only)
- [ ] `docs/API_MIGRATION_GUIDE.md` created with feature preservation matrix
- [ ] `docs/HOT_RELOAD_GUIDE.md` created for developers
- [ ] `CONTRIBUTING.md` updated with API mode development guidelines
- [ ] All existing docs still apply to native mode
- [ ] Migration checklist added to `migration.md`
