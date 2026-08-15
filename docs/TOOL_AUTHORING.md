# Tool Authoring Guide

This guide explains how to write a new tool for SAGO. Tools are the unit of
capability the agents call via the LLM function-calling loop. Everything below
reflects the real API in `sago/tools/base.py`.

## Core concepts

All tools subclass `BaseTool` (`sago/tools/base.py:47`). A tool declares:

- `name: str` — unique, stable identifier used by the LLM and discovery cache.
- `description: str` — natural-language description exposed to the model.
- `category: ToolCategory` — a `ToolCategory` (StrEnum) for grouping.
- `args_model: type[BaseModel] | None` — a Pydantic model describing parameters.
- `_run(self, **kwargs) -> str` — the abstract method containing the logic.

### `ToolCategory` (StrEnum)

Defined in `sago/tools/base.py:20`. Valid values:

```
CODING, FILE, SHELL, NETWORK, SYSTEM, WEB, SSH, DATABASE,
SESSION, SECURITY, AGENT, ADMIN, GENERAL
```

Pick the one that best matches the tool's purpose (it is documentation/grouping,
not enforced by discovery).

### `ToolResult` (BaseModel)

`ToolResult` (`sago/tools/base.py:38`) is an optional *rich* return type:

```
output: str = ""
success: bool = True
error: str | None = None
metadata: dict[str, Any] = {}
```

You can return a plain `str` from `_run` (the common case) or, when you want
structured output/metadata, implement an `execute(...)` helper that returns a
`ToolResult` and have `_run` return `result.output`. See
`sago/tools/coding/hybrid_search_tool.py` for the pattern.

### `_run` vs `run` vs `execute`

- `_run(**kwargs) -> str` — the abstract method you implement. Receives the
  validated arguments as keyword args. **Must never raise** to the caller;
  return an error string instead (see Error handling below).
- `run(**kwargs) -> str` — the public entry point the executor calls. It wraps
  `_run` in a `try/except`, consults the learning store for known fixes, records
  the failure, and returns a safe `Error in <name>: ...` string. Permission
  checks are handled upstream by the executor, **not** here.
- `execute(...)` — *optional* tool-specific typed method returning `ToolResult`.
  The hybrid search tool uses this so callers can get metadata without parsing
  the string.

## Minimal complete example

Mirror the pattern in `sago/tools/coding/hybrid_search_tool.py`. The smallest
valid tool:

```python
# sago/tools/system/my_echo_tool.py
"""Echo tool — minimal example."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool, ToolCategory


class EchoArgs(BaseModel):
    text: str = Field(..., description="Text to echo back.")
    shout: bool = Field(default=False, description="Uppercase the output.")


class EchoTool(BaseTool):
    name: str = "echo"
    description: str = "Return the provided text, optionally uppercased."
    category: ToolCategory = ToolCategory.GENERAL
    args_model: type[BaseModel] | None = EchoArgs

    def _run(self, text: str, shout: bool = False, **kwargs: Any) -> str:
        return text.upper() if shout else text
```

That is it — drop the file anywhere under `sago/tools/**/` and it is discovered
automatically (no registration call).

## A richer example (mirrors hybrid_search_tool.py)

```python
from sago.tools.base import BaseTool, ToolCategory, ToolResult
from pydantic import BaseModel, Field


class CountArgs(BaseModel):
    text: str = Field(..., description="Text to count words in.")


class WordCountTool(BaseTool):
    name: str = "word_count"
    description: str = "Count whitespace-delimited words in text."
    category: ToolCategory = ToolCategory.GENERAL
    args_model: type[BaseModel] | None = CountArgs

    def _run(self, text: str, **kwargs) -> str:
        result = self.execute(text=text)
        return result.output

    def execute(self, text: str) -> ToolResult:
        try:
            n = len(text.split())
            return ToolResult(output=f"{n} words", metadata={"count": n})
        except Exception as e:
            return ToolResult(output=f"Error: {e}", success=False, error=str(e))
```

## Auto-registration

Discovery is filesystem-driven (`sago/engine/simple_executor.py:484`,
`_discover_tools`):

1. `tools_dir.rglob("*.py")` walks every `.py` file under `sago/tools/`.
2. Files starting with `_` or named `base.py` are skipped.
3. Each remaining module is imported as `sago.tools.<dotted.path>`.
4. Every attribute that is a `BaseTool` subclass (not `BaseTool` itself) with a
   non-empty `name` is added to `_TOOL_CLASSES[name]`.
5. The map is cached behind `_tool_discovery_lock` for the process lifetime.

The same walk is reproduced in `sago/workflow/langgraph_engine.py`,
`sago/tools/crewai_wrappers.py`, and `sago/mcp/server.py` so all integrations
see the same tool set.

**To add a tool:** create `sago/tools/<category>/<your_tool>.py` defining one
`BaseTool` subclass. No `__init__.py` edit, decorator, or registry call is
required. Use a unique `name`.

## Parameters & validation

- Declare every argument in a Pydantic `BaseModel` (`args_model`).
- The executor converts the model fields to a JSON Schema for the LLM
  (`_pydantic_field_to_schema` in `simple_executor.py`), including `description`
  and required vs default handling.
- Inside `_run`, read args from `kwargs` (or declare them as explicit params and
  accept `**kwargs`). Validate/guard unexpected values yourself and return a
  clear error string rather than raising.
- Use `Field(..., description="...")` so the model and the LLM both understand
  each parameter.

## Timeouts & cross-platform execution

`BaseTool` provides helpers so you do not reimplement them:

- `_run_command(command, timeout=300, cwd=None, shell=True, capture_output=True)`
  runs a subprocess cross-platform and returns `subprocess.CompletedProcess`.
  Pass `timeout` (seconds) to bound long-running commands.
- `_get_shell()` returns `powershell` on Windows, else `$SHELL`/`/bin/bash`.
- `_is_windows() / _is_macos() / _is_linux()` for OS branching.
- `_expand_path(path_str)` expands `~` and `$VAR` and resolves to an absolute
  `Path`.
- `_get_temp_dir()` returns an OS-appropriate temp dir under `sago/`.

Example: `result = self._run_command("git status", cwd=self._expand_path(cwd),
timeout=60)`.

## Error handling — return, don't crash

`_run` should **never** let an exception propagate. Two layers protect you:

1. `BaseTool.run()` already catches exceptions from `_run`, looks up known fixes
   in `sago/learning.py`, records the failure, and returns
   `f"Error in {self.name}: {type(e).__name__}: {e}"`. So even an uncaught
   exception becomes a safe string.
2. Best practice: catch expected failures inside `_run` and return a descriptive
   string (or a `ToolResult(success=False, error=...)`), e.g. invalid operation
   names or missing files. See `sago/tools/system/git_ops.py`, which returns
   `"Error: Invalid operation '...'"` for unrecognized operations instead of
   raising.

This keeps a single failing tool from aborting the whole agent loop.

## Real examples to study

- `sago/tools/system/git_ops.py` (`GitOps`) — argument validation against a
  `VALID_OPERATIONS` allow-list, uses `_run_command` with a timeout, returns
  error strings for bad input. A clean reference for shell-wrapper tools.
- `sago/tools/coding/hybrid_search_tool.py` (`HybridSearchTool`) — the
  `execute() -> ToolResult` pattern, lazy optional imports (sentence-transformers),
  and graceful fallback when an optional dependency is missing.
- `sago/tools/file/glob_files.py` and `sago/tools/file/grep_content.py` — file
  search tools using `_expand_path` and returning formatted results.
- `sago/tools/network/web_crawler.py` and `sago/tools/web/search.py` — web
  fetching/search tools; good references if you are adding network I/O, timeouts,
  and error handling for remote calls.

## Cross-integration

Once a tool is discovered, it is automatically available to:

- the simple executor (native function calling),
- the unified/production engines (`sago/engine/unified.py`, `production.py`),
- the LangGraph workflow engine (`sago/workflow/langgraph_engine.py`),
- the CrewAI wrapper layer (`sago/tools/crewai_wrappers.py`), and
- the MCP server (`sago/mcp/server.py`).

No further wiring is needed.
