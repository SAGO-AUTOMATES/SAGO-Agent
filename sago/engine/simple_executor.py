"""Smart Executor - Handles complex multi-step tasks using native function calling."""

from __future__ import annotations

import ast
import contextvars
import json
import logging
import os
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sago.tools.base import BaseTool
from sago.utils.safe import log_exception

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Unified callback propagation — contextvars so callbacks flow from
# the outer processor into spawned agents automatically.
# ---------------------------------------------------------------------------
_current_tool_call: contextvars.ContextVar[Callable | None] = contextvars.ContextVar(
    "current_tool_call", default=None
)
_current_tool_result: contextvars.ContextVar[Callable | None] = contextvars.ContextVar(
    "current_tool_result", default=None
)
_current_thinking: contextvars.ContextVar[Callable | None] = contextvars.ContextVar(
    "current_thinking", default=None
)
_current_todo_update: contextvars.ContextVar[Callable | None] = contextvars.ContextVar(
    "current_todo_update", default=None
)
_current_todo_created: contextvars.ContextVar[Callable | None] = contextvars.ContextVar(
    "current_todo_created", default=None
)
_current_request_input: contextvars.ContextVar[Callable | None] = contextvars.ContextVar(
    "current_request_input", default=None
)


def set_execution_callbacks(
    on_tool_call: Callable | None = None,
    on_tool_result: Callable | None = None,
    on_thinking: Callable | None = None,
    on_todo_update: Callable | None = None,
    on_todo_created: Callable | None = None,
    on_request_input: Callable | None = None,
) -> None:
    """Set callbacks in the current context. Call this before executing tools or agent tasks."""
    _current_tool_call.set(on_tool_call)
    _current_tool_result.set(on_tool_result)
    _current_thinking.set(on_thinking)
    _current_todo_update.set(on_todo_update)
    _current_todo_created.set(on_todo_created)
    _current_request_input.set(on_request_input)


def get_execution_callbacks() -> dict[str, Callable | None]:
    """Get the current context's callbacks. Used by SpawnAgentTool to inherit parent callbacks."""
    return {
        "on_tool_call": _current_tool_call.get(),
        "on_tool_result": _current_tool_result.get(),
        "on_thinking": _current_thinking.get(),
        "on_todo_update": _current_todo_update.get(),
        "on_todo_created": _current_todo_created.get(),
        "on_request_input": _current_request_input.get(),
    }


# Auto-discover all tools
_TOOL_CLASSES: dict[str, type[BaseTool]] = {}
_TOOL_DESCRIPTIONS = ""
_tool_discovery_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Native function calling: convert Pydantic args_model -> OpenAI tool schema
# ---------------------------------------------------------------------------

_PYTYPE_TO_JSON: dict[str, str] = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
    "list": "array",
    "dict": "object",
}


def _pydantic_field_to_schema(field_info: Any) -> dict[str, Any]:
    """Convert a single Pydantic field info to a JSON Schema property."""
    annotation = field_info.annotation
    schema: dict[str, Any] = {}

    # Handle Optional[X] -> X
    origin = getattr(annotation, "__origin__", None)
    if origin is type(None):
        return {"type": "string"}

    # Get type name
    _type_name = getattr(annotation, "__name__", str(annotation))

    # Handle Literal types
    if origin is not None and getattr(annotation, "__module__", "") == "typing":
        # typing.Literal
        args = getattr(annotation, "__args__", ())
        if args and all(isinstance(a, str) for a in args):
            schema["type"] = "string"
            schema["enum"] = list(args)
            return schema

    # Check if Optional (Union[X, None])
    if origin is getattr(__import__("typing"), "Union", None) or (
        hasattr(annotation, "__class__") and annotation.__class__.__name__ == "_GenericAlias"
    ):
        args = getattr(annotation, "__args__", ())
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _pydantic_field_to_schema_simple(non_none[0], field_info)

    return _pydantic_field_to_schema_simple(annotation, field_info)


def _pydantic_field_to_schema_simple(annotation: Any, field_info: Any) -> dict[str, Any]:
    """Convert a simple type annotation to JSON Schema."""
    type_name = getattr(annotation, "__name__", str(annotation))
    schema: dict[str, Any] = {}

    # Handle basic types
    json_type = _PYTYPE_TO_JSON.get(type_name)
    if json_type:
        schema["type"] = json_type
    elif type_name == "list" or type_name == "List":
        schema["type"] = "array"
        inner = getattr(annotation, "__args__", (str,))
        if inner:
            item_type = getattr(inner[0], "__name__", str(inner[0]))
            item_json = _PYTYPE_TO_JSON.get(item_type, "string")
            schema["items"] = {"type": item_json}
    elif type_name == "dict" or type_name == "Dict":
        schema["type"] = "object"
    else:
        schema["type"] = "string"  # fallback

    # Add description from field info if available
    if hasattr(field_info, "description") and field_info.description:
        schema["description"] = field_info.description

    return schema


def _build_openai_tools(tool_classes: dict[str, type[BaseTool]]) -> list[dict[str, Any]]:
    """Convert tool classes to concise OpenAI function calling tool definitions.

    Optimized to minimize input token overhead while maintaining full precision for the LLM.
    """
    openai_tools: list[dict[str, Any]] = []

    for name, cls in sorted(tool_classes.items()):
        raw_desc = (cls.description or name).strip()
        # Keep full first-line description for surgical tools so the LLM sees
        # the "PREFER for existing files" guidance (was truncated to 160).
        first_line = raw_desc.split("\n", 1)[0].strip()
        # Only truncate extremely long descriptions (>280) to save tokens
        if len(first_line) > 280:
            first_line = first_line[:277] + "..."
        description = first_line or name

        parameters: dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        if cls.args_model:
            fields = cls.args_model.model_fields
            for field_name, field_info in fields.items():
                prop = _pydantic_field_to_schema(field_info)
                # Keep fuller param descriptions so old_string/new_string guidance survives
                if "description" in prop and isinstance(prop["description"], str):
                    pdesc = prop["description"].split("\n", 1)[0].strip()
                    if len(pdesc) > 200:
                        pdesc = pdesc[:197] + "..."
                    prop["description"] = pdesc
                parameters["properties"][field_name] = prop
                if field_info.is_required():
                    parameters["required"].append(field_name)

        openai_tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            }
        )

    return openai_tools


def _is_complex_task(task: str) -> bool:
    """Detect if a task is complex and needs a todo list."""
    task_lower = task.lower().strip()

    # Casual, conversational, or creative requests never need multi-step coding plans
    chat_patterns = [
        r"\b(joke|jokes|pun|puns|funny|riddle|riddles|story|stories|poem|poems|greeting|hello|hi|hey|thanks|thank you)\b",
        r"\b(who are you|how are you|tell me about yourself|what can you do)\b",
        r"^(tell me|give me|write me|share)\s+(a|some|another|more|\d+)\s+(joke|jokes|pun|puns|story|poem)",
        r"^\d+-\d+\s+more",
    ]
    if any(re.search(p, task_lower) for p in chat_patterns):
        return False

    complex_indicators = [
        r"\b(and then|after that|next step|first.*then|step \d)\b",
        r"\b(build.*project|create.*project|set up|setup)\b",
        r"\b(refactor|migrate|upgrade|deploy)\b",
        r"\b(implement.*feature|add.*feature|create.*feature)\b",
        r"\b(restructure|reorganize|rewrite)\b",
        r"\b(test.*and|fix.*and|update.*and)\b",
        r"\b(multiple|several|various|many)\b",
        r"\b(full|complete|entire|whole)\b",
    ]
    for pattern in complex_indicators:
        if re.search(pattern, task_lower):
            return True
    # Also complex if task is very long
    if len(task.split()) > 30:
        return True
    return False


def _auto_install_deps(files_created: list[str], on_thinking: Callable | None = None) -> None:
    """Auto-detect and install dependencies based on created files."""

    # Check what files were created
    has_python = any(f.endswith(".py") for f in files_created)
    has_node = any(f.endswith((".js", ".ts", ".jsx", ".tsx")) for f in files_created)
    has_rust = any(f.endswith(".rs") for f in files_created)
    has_go = any(f.endswith(".go") for f in files_created)

    # Check for dependency files

    # Find execute_shell tool
    shell_tool_class = None
    for tool_name, tool_class in _discover_tools().items():
        if tool_name == "execute_shell":
            shell_tool_class = tool_class
            break

    if not shell_tool_class:
        return

    shell_tool = shell_tool_class()

    # Install dependencies for each detected language
    install_commands = []
    if has_python:
        install_commands.append(
            "pip install -r requirements.txt 2>/dev/null || pip install -e . 2>/dev/null || true"
        )
    if has_node:
        install_commands.append("npm install 2>/dev/null || yarn install 2>/dev/null || true")
    if has_rust:
        install_commands.append("cargo fetch 2>/dev/null || true")
    if has_go:
        install_commands.append("go mod download 2>/dev/null || true")

    for cmd in install_commands:
        if on_thinking:
            on_thinking(f"Installing dependencies: {cmd[:50]}...")
        try:
            shell_tool.run(command=cmd, timeout=60)
        except Exception as e:
            if on_thinking:
                on_thinking(f"Dependency install failed: {type(e).__name__}: {e}")


def _run_tests_if_exist(
    files_created: list[str],
    tools: dict[str, type[BaseTool]],
) -> tuple[bool, str] | None:
    """Run tests if test files exist. Returns (passed, output) or None if no tests."""
    import subprocess

    # Check for test files
    test_patterns = ["test_*.py", "*_test.py", "*.test.js", "*.test.ts", "*.spec.js", "*.spec.ts"]
    has_test_files = False

    for pattern in test_patterns:
        import glob

        if glob.glob(pattern):
            has_test_files = True
            break

    if not has_test_files:
        return None

    # Try to run tests
    test_commands = [
        ["python", "-m", "pytest", "--tb=short", "-q"],
        ["npm", "test", "--", "--passWithNoTests"],
        ["cargo", "test"],
        ["go", "test", "./..."],
    ]

    for cmd in test_commands:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            output = result.stdout + "\n" + result.stderr
            if result.returncode == 0:
                return True, output
            else:
                return False, output
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

    return None


_project_context_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_project_context_lock = threading.Lock()


def _get_executor_config() -> Any:
    """Get executor configuration with environment variable fallbacks."""
    try:
        from sago.config.loader import get_config

        return get_config().executor
    except Exception:
        from sago.config.loader import ExecutorConfig

        return ExecutorConfig()


def _detect_project_context(cwd: str | None = None) -> dict[str, Any]:
    """Detect existing project language, framework, and structure from files.

    Returns a dict with detected info that helps the LLM understand the project.
    Results are cached for configured TTL to avoid repeated subprocess calls.
    """
    import subprocess

    work_dir = cwd or os.getcwd()
    cfg = _get_executor_config()
    ttl = int(os.environ.get("SAGO_PROJECT_CONTEXT_TTL", str(cfg.project_context_ttl)))

    # Check cache
    now = time.time()
    with _project_context_lock:
        cached = _project_context_cache.get(work_dir)
        if cached and (now - cached[0]) < ttl:
            return cached[1]

    context: dict[str, Any] = {
        "languages": [],
        "frameworks": [],
        "package_managers": [],
        "build_tools": [],
        "test_frameworks": [],
        "project_structure": [],
    }

    work_dir = cwd or os.getcwd()

    # Detect by config files
    config_indicators = {
        "pyproject.toml": ("python", ["hatchling", "poetry", "setuptools"]),
        "setup.py": ("python", ["setuptools"]),
        "setup.cfg": ("python", ["setuptools"]),
        "requirements.txt": ("python", ["pip"]),
        "Pipfile": ("python", ["pipenv"]),
        "poetry.lock": ("python", ["poetry"]),
        "package.json": ("javascript", ["npm", "yarn"]),
        "package-lock.json": ("javascript", ["npm"]),
        "yarn.lock": ("javascript", ["yarn"]),
        "tsconfig.json": ("typescript", ["npm"]),
        "Cargo.toml": ("rust", ["cargo"]),
        "go.mod": ("go", ["go"]),
        "go.sum": ("go", ["go"]),
        "pom.xml": ("java", ["maven"]),
        "build.gradle": ("java", ["gradle"]),
        "Gemfile": ("ruby", ["bundler"]),
        "composer.json": ("php", ["composer"]),
        "CMakeLists.txt": ("c++", ["cmake"]),
        "Makefile": ("c", ["make"]),
        "Dockerfile": ("docker", ["docker"]),
        "docker-compose.yml": ("docker", ["docker-compose"]),
        ".github/workflows": ("ci", ["github-actions"]),
    }

    for filename, (lang, managers) in config_indicators.items():
        path = os.path.join(work_dir, filename)
        if os.path.exists(path):
            if lang not in context["languages"]:
                context["languages"].append(lang)
            for m in managers:
                if m not in context["package_managers"]:
                    context["package_managers"].append(m)

    # Detect frameworks from package.json dependencies
    pkg_json = os.path.join(work_dir, "package.json")
    if os.path.exists(pkg_json):
        try:
            with open(pkg_json) as f:
                pkg = json.load(f)
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            framework_map = {
                "react": "react",
                "next": "nextjs",
                "vue": "vue",
                "angular": "angular",
                "svelte": "svelte",
                "express": "express",
                "fastify": "fastify",
                "nestjs": "nestjs",
                "electron": "electron",
            }
            for dep in framework_map:
                if dep in deps:
                    context["frameworks"].append(framework_map[dep])
        except Exception as e:
            log_exception(e, "Failed to parse package.json for framework detection")

    # Detect Python frameworks from imports in existing files
    pyproject = os.path.join(work_dir, "pyproject.toml")
    if os.path.exists(pyproject):
        try:
            content = open(pyproject).read()
            py_frameworks = {
                "flask": "flask",
                "django": "django",
                "fastapi": "fastapi",
                "starlette": "starlette",
                "pytest": "pytest",
            }
            for keyword, framework in py_frameworks.items():
                if keyword in content.lower():
                    context["frameworks"].append(framework)
        except Exception as e:
            log_exception(e, "Failed to read pyproject.toml for framework detection")

    # Detect test frameworks
    test_indicators = {
        "pytest": ["pytest.ini", "conftest.py", "pyproject.toml"],
        "jest": ["jest.config.js", "jest.config.ts"],
        "vitest": ["vitest.config.ts", "vitest.config.js"],
        "mocha": [".mocharc.yml", ".mocharc.json"],
        "cargo-test": ["Cargo.toml"],
        "go-test": ["go.mod"],
    }
    for framework, indicators in test_indicators.items():
        for indicator in indicators:
            if os.path.exists(os.path.join(work_dir, indicator)):
                if framework not in context["test_frameworks"]:
                    context["test_frameworks"].append(framework)

    # Detect project structure (depth 2)
    try:
        result = subprocess.run(
            [
                "find",
                work_dir,
                "-maxdepth",
                "2",
                "-type",
                "f",
                "-not",
                "-path",
                "*/node_modules/*",
                "-not",
                "-path",
                "*/.git/*",
                "-not",
                "-path",
                "*/target/*",
                "-not",
                "-path",
                "*/vendor/*",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            files = result.stdout.strip().split("\n")[:30]
            context["project_structure"] = [os.path.relpath(f, work_dir) for f in files if f]
    except Exception as e:
        log_exception(e, "Failed to detect project structure via subprocess")

    # Cache the result
    with _project_context_lock:
        _project_context_cache[work_dir] = (time.time(), context)
    return context


def _generate_plan_with_llm(
    task: str,
    client: Any,
    model: str,
    tools_desc: str,
) -> list[str]:
    """Use LLM to break down a complex task into steps."""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a task planner. Break down the user's task into clear, actionable steps.\n"
                        "Reply with ONLY a JSON array of step descriptions. No explanation.\n"
                        "Each step should be a single clear action.\n"
                        'Example: ["Step 1 description", "Step 2 description"]\n'
                        "Keep it to 3-8 steps. Be specific and actionable."
                    ),
                },
                {"role": "user", "content": f"Break down this task into steps:\n\n{task}"},
            ],
            max_tokens=1024,
            temperature=0.3,
        )
        content = response.choices[0].message.content or ""
        # Extract JSON array from response - try strict parsing first, then regex fallback
        try:
            steps = json.loads(content.strip())
            if isinstance(steps, list) and all(isinstance(s, str) for s in steps):
                return steps
        except (json.JSONDecodeError, ValueError):
            logger.debug("LLM plan response was not valid JSON, trying regex fallback")
        # Regex fallback: find first complete JSON array
        match = re.search(r"\[(?:[^\[\]]*(?:\"[^\"]*\")[^\[\]]*)*\]", content, re.DOTALL)
        if match:
            try:
                steps = json.loads(match.group())
                if isinstance(steps, list) and all(isinstance(s, str) for s in steps):
                    return steps
            except (json.JSONDecodeError, ValueError):
                logger.debug("Regex-extracted JSON array was invalid")
    except Exception as e:
        log_exception(e, "Failed to generate plan via LLM")
    # Fallback: create generic steps
    return [
        "Analyze the task and understand requirements",
        "Explore existing code/structure",
        "Implement the changes",
        "Verify and test",
    ]


def _discover_tools() -> dict[str, type[BaseTool]]:
    global _TOOL_CLASSES, _TOOL_DESCRIPTIONS
    if _TOOL_CLASSES and _TOOL_DESCRIPTIONS:
        logger.debug("Tool cache hit: %d tools available", len(_TOOL_CLASSES))
        return _TOOL_CLASSES

    with _tool_discovery_lock:
        if _TOOL_CLASSES and _TOOL_DESCRIPTIONS:
            logger.debug("Tool cache hit (double-check): %d tools", len(_TOOL_CLASSES))
            return _TOOL_CLASSES

        from sago.tools.registry import discover_tools

        logger.info("Starting tool discovery from registry")
        discovered = discover_tools()
        _TOOL_CLASSES = {name: tdef.tool_class for name, tdef in discovered.items()}
        logger.info(
            "Discovered %d tools: %s",
            len(_TOOL_CLASSES),
            ", ".join(sorted(_TOOL_CLASSES.keys())[:20]),
        )

        lines = []
        for name, tdef in sorted(discovered.items()):
            desc = tdef.description or name
            args = ""
            if tdef.args_model:
                try:
                    fields = tdef.args_model.model_fields
                    parts = []
                    for fn, fi in fields.items():
                        req = "REQ" if fi.is_required() else f"={fi.default}"
                        parts.append(f"{fn}({req})")
                    args = ", ".join(parts)
                except Exception as e:
                    log_exception(e, "Failed to extract tool argument fields")
                    args = ""
            lines.append(f"- {name}({args}): {desc}")
        _TOOL_DESCRIPTIONS = "\n".join(lines)
        return _TOOL_CLASSES


def _get_context(cwd: str | None = None) -> str:
    """Get compact workspace context without massive token dumping."""
    work_dir = Path(cwd) if cwd else Path.cwd()
    lines = [f"Workspace: {work_dir}"]

    skip = {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        ".tox",
        "dist",
        "build",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
    files = []
    dirs = []
    try:
        for item in sorted(work_dir.iterdir()):
            if item.name.startswith(".") or item.name in skip:
                continue
            if item.is_dir():
                dirs.append(f"{item.name}/")
            else:
                files.append(item.name)
    except (PermissionError, FileNotFoundError):
        pass

    if dirs:
        lines.append(f"Dirs: {', '.join(dirs[:15])}")
    if files:
        lines.append(f"Files: {', '.join(files[:25])}")

    try:
        import subprocess

        r = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            timeout=3,
            cwd=str(work_dir),
        )
        if r.returncode == 0 and r.stdout.strip():
            git_lines = r.stdout.strip().splitlines()
            if len(git_lines) > 8:
                summary = "\n".join(git_lines[:8]) + f"\n... (+{len(git_lines) - 8} more files)"
            else:
                summary = "\n".join(git_lines)
            lines.append(f"Git status:\n{summary}")
    except Exception as e:
        log_exception(e, "Failed to get git status")

    return "\n".join(lines)


# Task-specific system prompts (tools are now passed via API, not in text)
PROMPTS = {
    "chat": """You are {agent_role}, a helpful, knowledgeable, and friendly AI assistant.

{project_ctx}

ABSOLUTE RULES - VIOLATION = FAILURE:
1. NEVER hallucinate tool results or file contents. If you haven't read a file, don't claim what it contains.
2. NEVER claim the user mentioned specific files or code unless they literally said the file names in their message.
3. NEVER claim "the codebase has X files", "the project uses Y", or "there are Z classes" without using tools to verify.
4. NEVER list files as "available" or "related" without first discovering them via tools.
5. NEVER make structural or architectural claims without reading the relevant files.
6. If uncertain about something, say "I'm not sure" rather than guessing.
7. Keep responses concise and appropriate to the question complexity.

COMPLEXITY CALIBRATION:
- Simple questions ("hi", "what is 2+2", "what time is it") → answer in 1-2 sentences. Do NOT overthink.
- Medium questions ("explain X", "what does Y do") → answer in a short paragraph.
- Complex questions ("compare X and Y", "design a system for Z") → only then provide detailed analysis.

THINKING STEP:
Before responding, verify: Am I making ANY claims about files, code, structure, or tool results that I haven't actually verified with tools? If yes, use the appropriate tool first. Am I overcomplicating a simple question? If yes, simplify.""",
    "query": """You are {agent_role}. The user has a quick information request about a specific file, function, or concept.

{project_ctx}

ABSOLUTE RULES - VIOLATION = FAILURE:
1. NEVER claim what a file contains without reading it first with read_file tool.
2. NEVER guess — if you haven't read it, say "I haven't read that file yet, let me check."
3. NEVER claim the user mentioned specific files unless they literally said the names.
4. NEVER list files as "available" without first discovering them via glob_files or grep_content.
5. Report ONLY what you actually see in the tool results.
6. If the user asks "what's in this file", read that ONE file and summarize briefly.
7. If the user asks "where is X defined", search for X and report the location.

STRICT LIMITS:
- Maximum 1 tool call for simple questions ("what's in this file").
- Maximum 2-3 tool calls for slightly broader questions ("where is X used").
- NEVER read more than 2 files unless the user explicitly asks for comprehensive analysis.
- NEVER run tests, linters, or build commands unless asked.
- NEVER create or modify files unless asked.

THINKING STEP:
Before responding, ask yourself: (1) Did I actually read the file(s) the user asked about? (2) Am I making claims without tool evidence? (3) Am I overcomplicating this? If yes, simplify to 1-3 sentences.""",
    "create": """You are {agent_role}. The user wants you to create, implement, or modify code and files.

{project_ctx}

ABSOLUTE RULES - VIOLATION = FAILURE:
1. You MUST use tools (read_file, write_file, edit_file, execute_shell) to interact with the system. NEVER fabricate tool results.
2. NEVER claim a file was created, edited, read, or modified without actually calling the corresponding tool.
3. NEVER say "the file contains", "I read the file", "the code shows", "I created the file" unless you actually used a tool to do so.
4. NEVER claim the user mentioned specific files unless they literally said the names.
5. NEVER list files as "available" or "related" without first discovering them via tools.
6. If you need to read a file, use read_file tool FIRST. If you need to create/edit a file, use write_file or edit_file tool.
7. Report tool results EXACTLY as the tool returns them. Do not embellish or fabricate additional details.
8. ALWAYS verify code syntax before claiming it works. Use execute_shell to run syntax checks.
9. NEVER claim "tests pass" or "all tests pass" without actually running the tests via execute_shell.
10. NEVER claim code is "production-ready", "fully tested", or "complete" unless you have verified it with tools.

SMART TOOL USAGE (not dumb):
- Discovery FIRST: glob_files, file_search, grep_content, hybrid_search, search_symbol BEFORE read_file. Don't guess file names.
- Structure: use ast_grep, search_symbol, hybrid_search to understand architecture, not just raw read_file dumps.
- Use read_file only after you know *which* file matters (via search). For 2+ files, use batch reads.
- For changes: write_file/edit_file with resilient matching, then verify with execute_shell (pytest, ruff, tsc, go vet, etc.).
- For large tasks, plan via todo list and execute stepwise — do not read one file and hallucinate the rest.

WORKFLOW:
- Discover via search tools FIRST (hybrid_search / grep_content / glob_files), then read_file on top 2-3 hits.
- Use ast_grep/search_symbol for code structure, not just string reads.
- Use write_file or edit_file tools to create/modify files. Show exact code.
- Use execute_shell to run tests or verify your work.
- Report what tools actually returned. If a tool fails, say it failed.
- For simple conversational queries, reply directly without calling tools.

COMPLEXITY CALIBRATION:
- For simple tasks (rename a variable, add a comment, fix a typo): do it directly, minimal explanation.
- For medium tasks (add a function, fix a bug): show the change, brief explanation.
- For complex tasks (refactor a module, implement a feature): structured approach with clear steps.

QUALITY STANDARDS:
- Write production-ready code with proper error handling, types, and documentation.
- Follow existing code conventions in the project.
- Use meaningful variable and function names.
- Handle edge cases and error conditions.
- Never leave TODO comments or placeholder code unless explicitly asked.

THINKING STEP:
Before responding, verify: (1) Did I actually use tools to read/create/modify files? (2) Am I claiming test results without running tests? (3) Am I claiming user said things they didn't? (4) Am I listing files without searching? (5) Is my code syntactically valid? Fix any issues before responding.""",
    "fix": """You are {agent_role}. The user wants you to fix an issue, bug, or error.

{project_ctx}

ABSOLUTE RULES - VIOLATION = FAILURE:
1. You MUST use tools to inspect and fix code. NEVER fabricate file contents or tool results.
2. NEVER claim a file was fixed without actually calling edit_file or write_file tool.
3. NEVER guess what code looks like. Always use read_file to see the actual code first.
4. NEVER claim the user mentioned specific files unless they literally said the names.
5. NEVER list files as "available" or "related" without first discovering them via tools.
6. Report tool results EXACTLY as the tool returns them.
7. NEVER claim "tests pass" without actually running them via execute_shell.
8. NEVER claim "the issue is fixed" without verifying the fix actually works.
9. NEVER claim code is "correct" or "working" without running it or its tests.

WORKFLOW:
- Use read_file to inspect ALL relevant files before making changes.
- Identify root cause from actual file contents, not assumptions.
- Use edit_file to make precise, minimal fixes.
- Use execute_shell to run tests and verify changes work.
- Report what tools actually returned.

COMPLEXITY CALIBRATION:
- For simple fixes (typo, missing import, off-by-one): fix it directly, show minimal context.
- For moderate fixes (logic error, race condition): explain root cause briefly, show fix.
- For complex fixes (architecture issue, security vulnerability): detailed analysis, structured fix.

QUALITY STANDARDS:
- Make the minimal change necessary to fix the issue.
- Preserve existing code style and conventions.
- Ensure the fix doesn't introduce new bugs.
- Add comments explaining the fix if the root cause is non-obvious.

THINKING STEP:
Before responding, verify: (1) Did I actually read the problematic code? (2) Did I verify my fix works? (3) Am I claiming success without evidence? (4) Am I claiming user said things they didn't? (5) Is my fix minimal and targeted? If any answer is no, use the appropriate tool first.""",
    "analyze": """You are {agent_role}. The user wants you to analyze code or architecture.

{project_ctx}

ABSOLUTE RULES - VIOLATION = FAILURE:
1. You MUST use read_file tool to inspect files. NEVER fabricate file contents.
2. NEVER say "the file contains", "I can see that", "the code shows" unless you actually read the file with a tool.
3. Report findings based ONLY on what tools actually returned.
4. NEVER claim "the codebase has X files" or "there are Y classes" without actually counting via tools.
5. NEVER claim "the architecture is" without actually reading the relevant files.
6. NEVER claim code is "well-structured", "clean", or "production-ready" without evidence from tools.
7. NEVER claim the user mentioned specific files unless they literally said the file names. If unsure what files exist, use glob_files or grep_content to search.
8. NEVER list files as "available" or "related" without first discovering them via glob_files, file_search, or grep_content tools.

SMART ANALYSIS STACK (use it, don't just read_file):
- Discovery: hybrid_search (semantic) + grep_content (lexical) + glob_files for file lists — run BEFORE any read.
- Structure: ast_grep / search_symbol for functions/classes/calls, not just string matching.
- Quantify via tools: use count, symbol graphs, not guesses.
- For large codebases, use the project graph (project_graph) and symbol map (search_symbol) first.

WORKFLOW:
- Discovery via hybrid_search + grep_content + glob_files FIRST to find relevant files.
- Then read_file on top 2-4 hits only — not the whole repo.
- Use ast_grep/search_symbol to extract structure (functions, classes, decorators, call graphs).
- Use file_search/hybrid_search for cross-file patterns.
- Provide structured, actionable analysis based on actual file contents.
- If you cannot find something, say so honestly.

COMPLEXITY CALIBRATION:
- For simple questions ("what does X do"): hybrid_search X, read the ONE file that defines X, give a 1-2 sentence answer.
- For moderate analysis ("review this function"): search_symbol for the function + read its file, give focused findings.
- For complex analysis ("review the architecture"): project_graph + hybrid_search + read key files systematically, give comprehensive report.
- DO NOT read files the user didn't ask about unless you need them for context.

QUALITY STANDARDS:
- Provide specific file paths and line numbers for findings.
- Quantify where possible (e.g., "3 classes, 12 functions") via tool counts.
- Identify both strengths and weaknesses.
- Prioritize findings by impact and severity.

THINKING STEP:
Before responding, verify: (1) Did I run search tools before reading? (2) Did I use ast_grep/search_symbol for structure? (3) Are my findings specific and tool-verified? (4) Am I over-analyzing a simple question? If any answer is no, use the appropriate tool first.""",
    "test": """You are {agent_role}. The user wants you to write, run, or fix tests.

{project_ctx}

ABSOLUTE RULES - VIOLATION = FAILURE:
1. You MUST use tools (read_file, write_file, execute_shell) to interact with the system. NEVER fabricate test results.
2. NEVER claim "tests pass" or "all tests pass" without actually running them via execute_shell.
3. NEVER claim "coverage is X%" without actually measuring it.
4. NEVER claim the user mentioned specific files unless they literally said the names.
5. NEVER list files as "available" or "related" without first discovering them via tools.
6. Report tool results EXACTLY as the tool returns them.
7. NEVER claim tests are "comprehensive" or "complete" without evidence.
8. NEVER claim code is "well-tested" without actually running the test suite.

WORKFLOW:
- Use read_file to understand the code you're testing.
- Use write_file to create or modify test files.
- Use execute_shell to run the tests.
- Report actual test output, not fabricated results.

COMPLEXITY CALIBRATION:
- For simple test requests ("add a test for X"): write focused test, run it.
- For moderate requests ("improve test coverage"): identify gaps, add targeted tests.
- For complex requests ("test the entire module"): systematic approach, run full suite.

QUALITY STANDARDS:
- Write tests that cover both happy path and edge cases.
- Use descriptive test names that explain what's being tested.
- Include assertions that verify expected behavior.
- Test error conditions and boundary cases.

THINKING STEP:
Before responding, verify: (1) Did I actually run the tests? (2) Am I claiming test results without evidence? (3) Am I claiming user said things they didn't? (4) Do my tests actually verify the behavior? If any answer is no, use the appropriate tool first.""",
}

# ── Always-on reasoning protocol ──
# Reasoning was previously disabled for lightweight "chat"/"query" tasks to avoid
# overthinking, but that produced shallow, hallucinated answers. This protocol
# is now appended to EVERY system prompt (even chat) with a brief, calibrated
# thinking step and a self-realization guard against loops.
# NOTE: Thinking MUST be wrapped in <thinking>...</thinking> tags so it appears
# in the Developer Telemetry & Execution Inspector's "Thinking" tab.
REASONING_PROTOCOL = """
REASONING PROTOCOL (always enabled, calibrated):
- Before acting, think 1-3 sentences: what is the user's intent, what is the minimal next step, what could go wrong? Even for simple "hi" or "what is X", do this brief check. WRAP this brief reasoning in <thinking>...</thinking> tags.
- After each tool result, reflect 1 sentence inside <thinking> tags: what did you learn, what remains, should you continue or conclude?
- If you notice you are repeating the same tool/args or same reasoning as the last 2 turns, trigger SELF-REALIZATION: pause, wrap a summary in <thinking> tags, and either answer concisely or try a *different* approach. Do NOT loop. This is your anti-overthinking brake.
- Prefer concise, tool-verified answers over long speculation. If uncertain, say so and show what you *did* verify.
- Always produce a <thinking> block before any tool call or final answer — this is how your reasoning is displayed in the UI. Example: <thinking>Intent is X, next step is Y, risk is Z</thinking>
"""


def _detect_task_type(task: str) -> str:
    """Detect task type using semantic IntentClassifier with micro-LLM and fast-path cache."""
    from sago.engine.intent_classifier import get_intent_classifier

    logger.debug("Classifying task intent: %.100s", task)
    try:
        result = get_intent_classifier().classify(task)
        logger.info(
            "Task classified: type=%s, confidence=%.2f, source=%s",
            result.task_type,
            result.confidence,
            result.source,
        )
        return result.task_type
    except Exception as e:
        log_exception(e, "Failed to classify task intent, defaulting to create")
        return "create"


def _detect_file_count(task: str, cwd: str | None = None) -> int | None:
    """Quick probe: count files for paths mentioned in task (glob_files first)."""
    import re as _re
    from pathlib import Path as _Path

    candidates: list[str] = []
    # Extract quoted or plain absolute paths like /tmp/sago_sample_test
    for m in _re.finditer(r"(?:\"|')?(/[\w\-/\.]+)(?:\"|')?", task):
        p = m.group(1).rstrip(".,;:")
        if len(p) > 4 and _Path(p).exists():
            candidates.append(p)
    # Also try cwd-adjacent relative hint if cwd is a valid dir
    if cwd and _Path(cwd).is_dir():
        candidates.append(cwd)
    _skip_parts = {
        ".git",
        ".sago",
        "__pycache__",
        ".ruff_cache",
        ".pytest_cache",
        ".mypy_cache",
        ".venv",
        "venv",
        "node_modules",
        "env",
    }
    _skip_suffixes = {".pyc", ".pyo", ".bak", ".orig"}
    best: int | None = None
    for cand in candidates:
        try:
            p = _Path(cand)
            if p.is_file():
                return 1
            if p.is_dir():
                # Count files recursively, capped at 50, ignore caches/hidden/backup
                count = 0
                for sub in p.rglob("*"):
                    if not sub.is_file():
                        continue
                    if any(part in _skip_parts for part in sub.parts):
                        continue
                    if any(part.startswith(".") and part not in (".", "..") for part in sub.parts):
                        # Skip hidden dirs like .ruff_cache already, but also hidden files
                        if sub.name.startswith("."):
                            continue
                    if sub.suffix.lower() in _skip_suffixes:
                        continue
                    if sub.suffix.lower() == ".md":
                        continue
                    if sub.name in ("package-lock.json", "package.json"):
                        # Config/lock files often inflate count but not relevant for tiny-code analyze
                        continue
                    # Skip top-level export artifacts like 0ba...md when they are not code
                    # Keep code-relevant files: .py, .js, .ts, .html, .css, .json (but not package-lock)
                    # For tiny probe, count all non-skip files; the extra filter below keeps count low
                    count += 1
                    if count > 50:
                        break
                return count
        except Exception:
            continue
        if best is None and candidates:
            best = None
    # Fallback: try glob_files tool via direct filesystem if no abs path found
    # e.g. task says "analyze /tmp/sago_sample_test"
    return best


def _is_simple_analyze(task_type: str, file_count: int | None) -> bool:
    """True for tiny analyze tasks that must be capped (≤5 files, spec also ≤10)."""
    return task_type == "analyze" and file_count is not None and file_count <= 5


_SIMPLE_ANALYZE_CAPS = {"max_tool_calls": 15, "max_iterations": 8, "max_tokens": 8000}


def _load_agent_profile(agent_name: str) -> dict[str, Any] | None:
    """Load agent profile metadata if available."""
    try:
        from sago.agents.registry import get_agent

        # Try common name formats
        for name_variant in [
            agent_name,
            agent_name.lower(),
            agent_name.replace(" ", "-"),
            agent_name.replace(" ", "_"),
        ]:
            agent_def = get_agent(name_variant)
            if agent_def:
                return {
                    "name": agent_def.name,
                    "role": agent_def.role,
                    "system_prompt": agent_def.system_prompt,
                    "tools": agent_def.tools,
                    "handoff_to": agent_def.handoff_to,
                    "model_preference": agent_def.model_preference,
                    "temperature": agent_def.temperature,
                    "max_iterations": agent_def.max_iterations,
                }
    except Exception as e:
        log_exception(e, f"Failed to load agent profile for '{agent_name}'")
    return None


# ---- Module-level hallucination detection functions ----

# Fabrication phrases: common LLM patterns that claim verification without tool evidence
_FABRICATION_PHRASES = [
    # Verification claims
    r"\bi(?:'ve| have)\s+(?:verified|confirmed|checked|validated|tested|confirmed that|run)\b",
    r"\bverified\s+(?:that\s+)?(?:the\s+)?(?:code|fix|change|implementation)\b",
    r"\bconfirmed\s+(?:that\s+)?(?:the\s+)?(?:code|fix|change|implementation)\b",
    r"\bchecked\s+(?:that\s+)?(?:the\s+)?(?:code|fix|change|implementation)\b",
    # Test claims
    r"\bthe\s+tests?\s+(?:pass|passes|passed|are\s+passing|all\s+pass)\b",
    r"\b(?:all|every|each)\s+tests?\s+(?:pass|passes|passed|are\s+passing)\b",
    r"\b(?:no|zero)\s+test\s+failures?\b",
    r"\b(?:every|all)\s+assertions?\s+pass\b",
    r"\btest\s+(?:suite|coverage)\s+(?:is|shows?|indicates?)\b",
    r"\b\d+\s+(?:out\s+of|\/)\s+\d+\s+tests?\s+pass\b",
    # Lint/type check claims
    r"\b(?:lint|type\s*check|static\s+analysis)\s+(?:passes?|passes|clean|clear|no\s+errors?)\b",
    r"\bno\s+(?:lint|linting|type)\s+errors?\b",
    r"\bcode\s+(?:passes?|is)\s+(?:linting|type\s+checking|formatting)\b",
    # Code quality claims
    r"\bthe\s+code\s+(?:compiles?|builds?|works?|runs?)\b",
    r"\bthe\s+code\s+(?:is|follows?)\s+(?:clean|proper|correct|valid)\b",
    r"\bcode\s+(?:is|follows?)\s+PEP\s+\d+\b",
    r"\bno\s+(?:syntax|runtime|type)\s+errors?\b",
    # Fix claims
    r"\bi(?:'ve| have)\s+(?:fixed|resolved|patched|corrected|addressed)\b",
    r"\bthis\s+(?:fix|change|patch|modification)\s+(?:resolves?|fixes?|solves?|addresses?)\b",
    r"\bthe\s+(?:fix|issue|bug|error)\s+(?:is|has\s+been)\s+(?:resolved|fixed|addressed)\b",
    r"\bnow\s+(?:it|the\s+code|the\s+system)\s+(?:works?|functions?|runs?)\b",
    # Success/completion claims
    r"\bno\s+(?:errors?|issues?|problems?|bugs?)\s+(?:remain|left|found|detected)\b",
    r"\b(?:everything|it)\s+(?:works?|is\s+working|should\s+work|looks?\s+good)\b",
    r"\b(?:i'm|I'm)\s+(?:confident|certain|sure)\s+(?:that\s+)?(?:this|it)\b",
    r"\bcorrectly\s+handles?\b",
    r"\bproperly\s+(?:implements?|handles?|manages?|processes?)\b",
    r"\bfully\s+(?:functional|implemented|working|tested)\b",
    r"\bcomprehensive\s+(?:test|coverage|solution)\b",
    r"\bwell[\s-]structured\b",
    r"\bproduction[\s-]ready\b",
    r"\bcompletely\s+(?:fixes?|resolves?|handles?)\b",
    r"\bshould\s+(?:now|work|function|run)\s+(?:correctly|properly|as\s+expected)\b",
    # Structural/architectural claims without tools
    r"\bthe\s+(?:codebase|project|repository|repo)\s+(?:has|contains?|includes?)\s+\d+\b",
    r"\bthere\s+(?:are|is)\s+\d+\s+(?:files?|classes?|functions?|methods?|modules?)\b",
    r"\bthe\s+(?:project|codebase)\s+(?:uses?|relies?\s+on|is\s+built\s+(?:with|on))\b",
    r"\bbased\s+on\s+(?:my\s+)?(?:analysis|review|inspection)\s+of\b",
    r"\bafter\s+(?:analyzing|reviewing|inspecting|examining)\b",
    r"\b(?:looking|looking)\s+at\s+the\s+(?:code|implementation|structure)\b",
    r"\bfrom\s+what\s+(?:i|we)\s+(?:can\s+see|see|found)\b",
    # Coverage/quality metrics without measurement
    r"\btest\s+coverage\s+(?:is|shows?|indicates?)\s+\d+%\b",
    r"\b\d+%\s+test\s+coverage\b",
    r"\bno\s+security\s+(?:vulnerabilities?|issues?|risks?)\b",
    r"\b(?:all|every)\s+(?:edge\s+cases?|corner\s+cases?)\s+(?:are|is)\s+handled\b",
    # Recommendation claims without evidence
    r"\bi\s+(?:recommend|suggest|advise)\s+(?:that\s+)?(?:you|we)\s+(?:should|could|can)\b",
    r"\bthe\s+(?:best|optimal|recommended)\s+(?:approach|solution|way)\s+(?:is|would\s+be)\b",
    r"\bthis\s+(?:is|will\s+be)\s+(?:more|less|better|worse|faster|slower)\s+efficient\b",
]

# Code block language patterns for multi-language syntax checking
_CODE_BLOCK_LANGS = {
    "python": ("py",),
    "javascript": ("js",),
    "typescript": ("ts", "tsx", "jsx"),
    "go": ("go",),
    "rust": ("rs",),
    "java": ("java",),
    "c": ("c",),
    "cpp": ("cpp", "c++", "cxx"),
    "csharp": ("cs",),
    "ruby": ("rb",),
    "php": ("php",),
    "kotlin": ("kt", "kts"),
    "swift": ("swift",),
    "scala": ("scala",),
    "dart": ("dart",),
    "bash": ("sh",),
    "shell": ("sh",),
    "zsh": ("zsh",),
}

# Known standard library + common third-party modules per language
_KNOWN_MODULES_PYTHON = {
    "os",
    "sys",
    "re",
    "json",
    "ast",
    "pathlib",
    "typing",
    "collections",
    "datetime",
    "time",
    "math",
    "random",
    "subprocess",
    "threading",
    "unittest",
    "pytest",
    "asyncio",
    "io",
    "copy",
    "functools",
    "itertools",
    "hashlib",
    "base64",
    "textwrap",
    "string",
    "struct",
    "socket",
    "http",
    "urllib",
    "email",
    "html",
    "xml",
    "csv",
    "sqlite3",
    "logging",
    "argparse",
    "dataclasses",
    "enum",
    "abc",
    "contextlib",
    "operator",
    "decimal",
    "fractions",
    "traceback",
    "inspect",
    "dis",
    "token",
    "tokenize",
    "code",
    "codeop",
    "compile",
    "compileall",
    "py_compile",
    "types",
    "warnings",
    "weakref",
    "codecs",
    "locale",
    "gettext",
    "unicodedata",
    "stringprep",
    "readline",
    "rlcompleter",
    "pdb",
    "profile",
    "timeit",
    "trace",
    "gc",
    "zipfile",
    "gzip",
    "bz2",
    "lzma",
    "tarfile",
    "shutil",
    "tempfile",
    "fnmatch",
    "linecache",
    "glob",
    "numpy",
    "pandas",
    "requests",
    "httpx",
    "aiohttp",
    "pydantic",
    "fastapi",
    "flask",
    "django",
    "click",
    "rich",
    "textual",
    "yaml",
    "toml",
    "dotenv",
    "sago",
    "google",
    "openai",
    "anthropic",
    "crewai",
    "langchain",
    "langgraph",
    "celery",
    "redis",
    "sqlalchemy",
    "alembic",
    "psycopg",
    "pymongo",
    "boto3",
    "botocore",
    "google/cloud",
    "uvicorn",
    "gunicorn",
    "starlette",
    "jinja2",
    "mako",
    "chameleon",
    "pillow",
    "opencv",
    "matplotlib",
    "seaborn",
    "scipy",
    "sklearn",
    "statsmodels",
    "torch",
    "tensorflow",
    "transformers",
    "paramiko",
    "fabric",
    "invoke",
    "docker",
    "kubernetes",
    "prometheus",
    "structlog",
    "loguru",
}


def _detect_code_hallucinations(content: str, tool_history: list) -> list[str]:
    """Detect hallucinated code, paths, imports, and fabrication signals in the response."""
    issues: list[str] = []
    if not content:
        return issues

    # 0. Detect fabrication phrases (LLM claiming verification without tool evidence)
    tools_called = {tc.get("tool", "") for tc in tool_history}
    has_shell = "execute_shell" in tools_called
    has_read = any(t in tools_called for t in ("read_file", "grep_content", "grep", "ast_grep"))
    has_edit = any(t in tools_called for t in ("write_file", "edit_file"))

    for phrase_pattern in _FABRICATION_PHRASES:
        for match in re.finditer(phrase_pattern, content, re.IGNORECASE):
            phrase = match.group(0)
            # Only flag if no relevant tool was called to back the claim
            if "pass" in phrase.lower() or "test" in phrase.lower():
                if not has_shell:
                    issues.append(f"Fabrication: '{phrase}' — no execute_shell tool was called")
            elif (
                "read" in phrase.lower()
                or "verified" in phrase.lower()
                or "checked" in phrase.lower()
            ):
                if not has_read:
                    issues.append(f"Fabrication: '{phrase}' — no read/search tool was called")
            elif "fix" in phrase.lower() or "resolved" in phrase.lower():
                if not has_edit:
                    issues.append(f"Fabrication: '{phrase}' — no edit/write tool was called")

    # 1. Check code blocks for syntax validity (multi-language)
    for lang, extensions in _CODE_BLOCK_LANGS.items():
        alt_pattern = "|".join(re.escape(ext) for ext in extensions)
        code_block_pattern = rf"```(?:{re.escape(lang)}|{alt_pattern})\s*\n(.*?)```"
        for match in re.finditer(code_block_pattern, content, re.DOTALL):
            code_block = match.group(1).strip()
            if not code_block:
                continue
            if lang == "python":
                try:
                    ast.parse(code_block)
                except SyntaxError as e:
                    issues.append(f"Python code block has syntax error: {e}")
            elif lang == "go":
                # Basic brace matching for Go
                depth = 0
                for ch in code_block:
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                    if depth < 0:
                        issues.append("Go code block has unbalanced braces")
                        break
                if depth > 0:
                    issues.append(f"Go code block has {depth} unclosed brace(s)")
            elif lang == "rust":
                depth = 0
                for ch in code_block:
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                    if depth < 0:
                        issues.append("Rust code block has unbalanced braces")
                        break
                if depth > 0:
                    issues.append(f"Rust code block has {depth} unclosed brace(s)")
            elif lang in ("javascript", "typescript"):
                depth = 0
                for ch in code_block:
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                    if depth < 0:
                        issues.append(f"{lang.title()} code block has unbalanced braces")
                        break
                if depth > 0:
                    issues.append(f"{lang.title()} code block has {depth} unclosed brace(s)")

    # 2. Check for hallucinated file paths
    # Broad patterns: backtick-quoted, plain text with extensions, and dotted names
    _FILE_EXTS = (
        ".py",
        ".js",
        ".ts",
        ".go",
        ".rs",
        ".java",
        ".c",
        ".cpp",
        ".tsx",
        ".jsx",
        ".pyc",
        ".pyd",
    )
    file_path_patterns = [
        r"(?:`|\"|')((?:\./|\.\./|\w+/)*[\w\-]+\.\w+)(?:`|\"|')",  # quoted paths
        r"\b([\w\-/]+\.(?:py|js|ts|go|rs|java|c|cpp|tsx|jsx|pyc))\b",  # plain text file refs
        r"\b([\w\-]+\.cpython-\d+\.\w+)\b",  # compiled Python files like analyze.cpython-311.pyc
    ]
    actual_files: set[str] = set()
    for tc in tool_history:
        args = tc.get("args", {})
        fp = (
            args.get("file_path", "")
            or args.get("path", "")
            or args.get("target_file", "")
            or args.get("directory", "")
        )
        if fp:
            actual_files.add(fp)
            # Also add basename for partial matches
            actual_files.add(os.path.basename(fp))

    for pat in file_path_patterns:
        for match in re.finditer(pat, content):
            path = match.group(1)
            if path.endswith(_FILE_EXTS) or "/" in path:
                if not os.path.exists(path) and not path.startswith("./"):
                    if path not in actual_files and os.path.basename(path) not in actual_files:
                        issues.append(
                            f"Referenced file '{path}' may not exist and was not accessed via tools"
                        )

    # 3. Check for hallucinated imports in code blocks
    import_pattern = r"```(?:python|py)\s*\n(.*?)```"
    for match in re.finditer(import_pattern, content, re.DOTALL):
        code_block = match.group(1).strip()
        for line in code_block.splitlines():
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                if stripped.startswith("from "):
                    module = stripped.split()[1].split(".")[0]
                else:
                    module = stripped.split()[1].split(".")[0]
                if module not in _KNOWN_MODULES_PYTHON and not module.startswith("_"):
                    tools_content = " ".join(str(tc.get("result", "")) for tc in tool_history)
                    if module not in tools_content.lower():
                        issues.append(f"Potentially hallucinated import: '{module}'")

    # 4. Check for hallucinated function/class names referenced in text
    # Look for patterns like "the foo() function" or "class Bar" that reference things not in tool results
    if tool_history:
        all_tool_content = " ".join(str(tc.get("result", "")) for tc in tool_history).lower()
        # Detect "the X() function" or "class X" references
        func_ref_pattern = r"(?:the\s+)?(\w+)\(\)\s+(?:function|method|class)"
        for match in re.finditer(func_ref_pattern, content, re.IGNORECASE):
            name = match.group(1)
            # Skip common English words
            if name not in {
                "the",
                "this",
                "that",
                "which",
                "what",
                "where",
                "when",
                "your",
                "our",
                "my",
                "its",
            }:
                if name.lower() not in all_tool_content and len(name) > 2:
                    issues.append(f"Referenced symbol '{name}()' not found in tool results")

    # 5. Detect overconfidence without evidence
    if not tool_history:
        overconfidence_patterns = [
            r"\b(?:definitely|certainly|absolutely|guaranteed)\b",
            r"\bworks?\s+(?:perfectly|flawlessly|correctly)\b",
            r"\bno\s+(?:doubt|question|issue|problem)\b",
        ]
        for pat in overconfidence_patterns:
            if re.search(pat, content, re.IGNORECASE):
                issues.append("Overconfidence signal: making strong claims without any tool usage")
                break

    return issues


def _verify_claims_against_history(content: str, tool_history: list) -> list[str]:
    """Cross-reference claims in response against actual tool call history."""
    issues: list[str] = []
    if not content:
        return issues

    content_lower = content.lower()
    tools_called = {tc.get("tool", "") for tc in tool_history}
    shell_calls = [tc for tc in tool_history if tc.get("tool") == "execute_shell"]
    read_calls = [
        tc
        for tc in tool_history
        if tc.get("tool") in ("read_file", "grep_content", "grep", "ast_grep")
    ]
    write_calls = [tc for tc in tool_history if tc.get("tool") in ("write_file", "edit_file")]

    # Collect all file paths touched by tools (from args AND results)
    all_tool_files: set[str] = set()
    for tc in tool_history:
        args = tc.get("args", {})
        for key in ("file_path", "path", "target_file", "directory"):
            val = args.get(key, "")
            if val:
                all_tool_files.add(val.lower())
                all_tool_files.add(os.path.basename(val).lower())
        # Also scan tool results for file names (e.g. glob_files returns file lists)
        result = str(tc.get("result", ""))
        for file_match in re.finditer(r"[\w\-/]+\.\w+", result):
            fname = file_match.group(0)
            all_tool_files.add(fname.lower())

    # 1. Check "I read X" claims
    read_claims = re.findall(
        r"(?:i\s+read|reading|examined?|inspected?|looked\s+at|checked|reviewed)\s+(?:the\s+)?(?:file\s+)?[`\"']?([^\s`\"'.]+\.\w+)",
        content_lower,
    )
    for claimed_file in read_claims:
        if not read_calls:
            issues.append(
                f"Claims to have read '{claimed_file}' but no read/search tool was called"
            )
        else:
            file_found = any(claimed_file in str(tc.get("args", "")) for tc in read_calls)
            if not file_found:
                issues.append(
                    f"Claims to have read '{claimed_file}' but it wasn't in read/search tool arguments"
                )

    # 2. Check "I created/wrote X" claims
    write_claims = re.findall(
        r"(?:i\s+(?:created|wrote|saved|added|generated|built|produced)|(?:created|wrote|saved|added|generated|built)\s+the\s+file)[\s]+[`\"']?([^\s`\"'.]+\.\w+)",
        content_lower,
    )
    for claimed_file in write_claims:
        if not write_calls:
            issues.append(
                f"Claims to have created '{claimed_file}' but no write_file/edit_file tool was called"
            )

    # 3. Check "tests pass" claims (expanded patterns)
    test_claims = [
        "all tests pass",
        "tests pass",
        "test passes",
        "all tests passed",
        "tests passed",
        "test passed",
        "all tests are passing",
        "tests are passing",
        "every test passes",
        "all unit tests pass",
        "test suite passes",
        "tests run successfully",
        "test results show",
        "all assertions pass",
    ]
    if any(claim in content_lower for claim in test_claims):
        if not shell_calls:
            issues.append("Claims tests pass but no execute_shell tool was called")
        else:
            last_shell_result = shell_calls[-1].get("result", "").lower()
            if "fail" in last_shell_result or "error" in last_shell_result:
                issues.append("Claims tests pass but last shell execution shows failures")

    # 4. Check "I fixed X" claims without edit_file
    fix_claims = [
        "fixed the",
        "resolved the",
        "patched the",
        "corrected the",
        "i fixed",
        "i resolved",
        "i patched",
        "i corrected",
        "the fix resolves",
        "this fixes",
        "this resolves",
        "the issue is fixed",
        "the bug is fixed",
        "the error is fixed",
    ]
    if any(claim in content_lower for claim in fix_claims):
        if not write_calls:
            issues.append("Claims to have fixed something but no edit_file/write_file was called")

    # 5. Check "I analyzed/inspected" claims without read tools
    analyze_claims = [
        "i analyzed",
        "i examined",
        "i inspected",
        "i reviewed",
        "after analyzing",
        "upon inspection",
        "looking at the code",
        "examining the",
        "reviewing the",
    ]
    if any(claim in content_lower for claim in analyze_claims):
        if not read_calls:
            issues.append("Claims to have analyzed/inspected but no read/search tool was called")

    # 6. Check "I ran/executed" claims without execute_shell
    exec_claims = [
        "i ran the",
        "i executed the",
        "i ran a",
        "i executed a",
        "running the tests",
        "executing the tests",
        "i ran pytest",
        "i ran npm",
        "i ran cargo",
        "the command succeeded",
        "the output shows",
    ]
    if any(claim in content_lower for claim in exec_claims):
        if not shell_calls:
            issues.append(
                "Claims to have run/executed something but no execute_shell tool was called"
            )

    # 7. Check "I searched/found" claims without grep/search tools
    search_claims = [
        "i searched for",
        "i found that",
        "searching revealed",
        "grepping showed",
        "grep shows",
        "rg shows",
        "i located",
        "the search found",
    ]
    if any(claim in content_lower for claim in search_claims):
        search_tools = {"grep_content", "grep", "rg", "ast_grep", "search_symbol"}
        if not (search_tools & tools_called) and not read_calls:
            issues.append("Claims to have searched/found something but no search tool was called")

    # 8. Check file path claims against actual tool-touched files
    path_claims = re.findall(
        r"(?:in|from|at|to|into)\s+(?:the\s+)?(?:file\s+)?[`\"']?([^\s`\"'.]+\.(?:py|js|ts|go|rs|java|c|cpp|tsx|jsx))",
        content_lower,
    )
    for claimed_path in path_claims:
        if claimed_path not in all_tool_files and not os.path.exists(claimed_path):
            # Only flag if it looks like a real file reference, not a common word
            if "/" in claimed_path or len(claimed_path) > 10:
                issues.append(f"References file '{claimed_path}' that was not accessed via tools")

    # 9. Detect "the files you mentioned" / "you mentioned X" fabrication
    #    when the user never actually mentioned specific files
    user_mention_patterns = [
        r"(?:the\s+)?(?:specific\s+)?files?\s+(?:you\s+)?(?:mentioned|said|referred\s+to|talked\s+about)",
        r"you\s+(?:mentioned|said)\s+(?:the\s+)?(?:files?\s+)?[`\"']?([^\s`\"'.]+\.\w+)",
        r"(?:files?\s+)?[`\"']([^\s`\"'.]+\.\w+)[`\"']\s+(?:and|that|you)",
        r"(?:mentioned|said)\s+(?:the\s+)?(?:files?\s+)?[`\"']?([^\s`\"'.]+\.\w+)",
    ]
    for pat in user_mention_patterns:
        for match in re.finditer(pat, content, re.IGNORECASE):
            claimed_files = [match.group(1)] if match.lastindex and match.group(1) else []
            # Extract snippet to the end of the sentence (look for period followed by space/newline/end)
            sentence_end = -1
            search_from = match.end()
            while True:
                dot_pos = content.find(".", search_from)
                if dot_pos == -1:
                    break
                # Check if this is a sentence-ending period (followed by space, newline, or end)
                after_dot = dot_pos + 1
                if after_dot >= len(content) or content[after_dot] in (" ", "\n", "\r", "\t", ")"):
                    sentence_end = dot_pos + 1
                    break
                search_from = dot_pos + 1
            if sentence_end == -1:
                sentence_end = min(match.end() + 200, len(content))
            snippet = content[match.start() : sentence_end]
            quoted_files = re.findall(r"[`\"']([^\s`\"'.]+\.\w+)[`\"']", snippet)
            all_claimed = set(claimed_files) | set(quoted_files)
            # Check if any of these files were found by tools
            for cf in all_claimed:
                if cf not in all_tool_files and not os.path.exists(cf):
                    issue_msg = (
                        f"Claims user mentioned '{cf}' but this file was not found via any tool"
                    )
                    if issue_msg not in issues:
                        issues.append(issue_msg)

    # 10. Detect listing specific files without using search/glob/read tools
    #     Pattern: numbered list of .py/.js/etc files or bullet points with filenames
    search_tools = {
        "grep_content",
        "grep",
        "rg",
        "ast_grep",
        "search_symbol",
        "glob_files",
        "file_search",
        "directory_scanner",
    }
    has_search = bool(search_tools & tools_called)
    has_read = any(t in tools_called for t in ("read_file", "grep_content"))
    if not has_search and not has_read:
        # Look for patterns like "1. foo.py" or "- bar.js" or lists of filenames
        file_listing_pattern = r"(?:^|\n)\s*(?:\d+\.\s*|[-*]\s*)[`\"']?([\w\-/]+\.\w+)[`\"']?"
        file_listings = re.findall(file_listing_pattern, content)
        if len(file_listings) >= 2:  # Listing 2+ specific files without tools is suspicious
            issues.append(
                f"Lists specific files ({', '.join(file_listings[:3])}) without using search/glob/read tools"
            )

    return issues


def _strip_hallucinated_sentences(content: str, issues: list[str]) -> str:
    """Remove sentences from content that contain hallucinated claims."""
    if not content or not issues:
        return content

    # Extract file names mentioned in issues
    hallucinated_files = set()
    for issue in issues:
        for match in re.finditer(r"'([^']+)'", issue):
            val = match.group(1)
            if "." in val:  # Likely a file name
                hallucinated_files.add(val.lower())

    # Split content into sentences
    # Handle both . and newline as sentence boundaries
    sentences = re.split(r"(?<=[.!?])\s+|\n{2,}", content)
    cleaned = []
    for sentence in sentences:
        sentence_lower = sentence.lower()
        is_hallucinated = False

        # Check if sentence references hallucinated files
        for hf in hallucinated_files:
            if hf in sentence_lower:
                is_hallucinated = True
                break

        # Check if sentence matches known fabrication patterns
        _FAB_STRIP_PATTERNS = [
            r"\bthe\s+(?:files?|code)\s+(?:you\s+)?(?:mentioned|said)\b",
            r"\byou\s+(?:mentioned|said)\s+(?:the\s+)?(?:files?)\b",
            r"\bthe\s+available\s+files?\s+(?:are|is|related)\b",
            r"\brelated\s+files?\s+(?:are|is)\b",
            r"\bthere\s+(?:are|is)\s+\d+\s+(?:files?|classes?|functions?|methods?)\b",
            r"\bthe\s+(?:codebase|project|repo)\s+(?:has|contains?|includes?)\b",
            r"\bbased\s+on\s+(?:my\s+)?(?:analysis|review)\b",
            r"\bafter\s+(?:analyzing|reviewing|inspecting)\b",
        ]
        for pat in _FAB_STRIP_PATTERNS:
            if re.search(pat, sentence_lower):
                is_hallucinated = True
                break

        if not is_hallucinated:
            cleaned.append(sentence)

    return " ".join(cleaned)


def _compute_confidence_score(
    content: str,
    tool_history: list,
    files_created: list,
    fabrication_issues: list,
    code_issues: list,
    claim_issues: list,
) -> int:
    """Compute a confidence score (0-100) for the response quality."""
    score = 100

    # Deductions for hallucination indicators
    score -= len(fabrication_issues) * 15
    score -= len(code_issues) * 10
    score -= len(claim_issues) * 12

    # Deductions for missing tool usage
    if not tool_history:
        score -= 20

    # Deductions for very short responses (but not for simple chat)
    if content and len(content.strip()) < 50:
        score -= 15
    elif content and len(content.strip()) < 100:
        score -= 5

    # Deductions for suspiciously long responses without tool evidence (overconfident rambling)
    if content and len(content) > 5000 and not tool_history:
        score -= 20

    # Bonus for proper tool usage
    if tool_history:
        successful = sum(1 for t in tool_history if t.get("success", True))
        total = len(tool_history)
        if total > 0:
            success_rate = successful / total
            if success_rate >= 0.8:
                score += 5
            elif success_rate < 0.5:
                score -= 10

    # Bonus for file creation when appropriate
    if files_created:
        score += 5

    # Bonus for tool diversity (used multiple different tools = better evidence)
    if tool_history:
        unique_tools = len(set(tc.get("tool", "") for tc in tool_history))
        if unique_tools >= 3:
            score += 5
        elif unique_tools == 1 and len(tool_history) > 3:
            score -= 5  # Repeated same tool without diversity is suspicious

    # Deduction for excessive fabrication phrases
    fabrication_count = sum(1 for issue in fabrication_issues if "Fabrication:" in issue)
    if fabrication_count >= 3:
        score -= 10  # Heavy penalty for multiple fabrication signals

    return max(0, min(100, score))


def _detect_overthinking_loop(
    tool_history: list[dict],
    messages: list[dict[str, Any]],
    iteration: int,
) -> str | None:
    """Self-realization brake: detect repeating loops and prompt a reflection.

    Returns a guidance string to inject as a user message if a loop is detected,
    else None. This is the anti-overthinking mechanism — it forces the agent to
    pause, summarize, and choose to conclude or try a different path instead of
    spinning on the same tool/args or same reasoning.
    """
    # 1) Same tool+args repeated 3+ times (classic loop)
    if len(tool_history) >= 3:
        last_three = tool_history[-3:]
        keys = [f"{t.get('tool')}:{t.get('args', {})}" for t in last_three]
        # Use JSON dump for stable comparison
        try:
            import json as _json

            keys = [
                f"{t.get('tool')}:{_json.dumps(t.get('args', {}), sort_keys=True)}"
                for t in last_three
            ]
        except Exception:
            pass
        if len(set(keys)) == 1:
            return (
                "SELF-REALIZATION: You have called the same tool with identical arguments 3 times. "
                "You are looping. Pause and reflect: what have you actually learned from those calls? "
                "Summarize progress so far in 1-2 sentences, then either provide a concise answer with what you have, "
                "or try a *different* tool/approach. Do NOT call the same tool again with the same args."
            )

    # 2) Same assistant content repeating ( difflib >0.85 ) over last 3 turns
    if len(messages) >= 4:
        recent_assistants = [
            m.get("content", "") or "" for m in messages[-6:] if m.get("role") == "assistant"
        ]
        if len(recent_assistants) >= 3:
            import difflib as _difflib

            a, b, c = recent_assistants[-3], recent_assistants[-2], recent_assistants[-1]
            if (
                a
                and b
                and _difflib.SequenceMatcher(None, a, b).ratio() > 0.85
                and _difflib.SequenceMatcher(None, b, c).ratio() > 0.85
            ):
                return (
                    "SELF-REALIZATION: Your last 3 reasoning turns were nearly identical. You are overthinking. "
                    "Summarize what you have verified with tools, state what remains, and either conclude concisely "
                    "or pivot to a new strategy. Do NOT repeat the same reasoning."
                )

    # 3) High iteration with no progress (no files created, no successful tools, >6 iterations)
    if iteration >= 6 and len(tool_history) >= 4:
        successes = sum(1 for t in tool_history if t.get("success", True))
        if successes == 0:
            return (
                "SELF-REALIZATION: You have made 4+ tool calls with no successes and are at iteration "
                f"{iteration + 1}. Reflect: is this the right approach? Consider a simpler alternative or ask for clarification. "
                "Do not keep trying the same failing pattern."
            )

    return None


def execute_agent_task(
    task: str,
    agent_role: str = "Sago Orchestrator",
    system_prompt: str = "",
    model: str = "openrouter/free",
    api_key: str = "",
    base_url: str | None = None,
    max_tokens: int = 50000,
    max_iterations: int = 45,
    cwd: str | None = None,
    on_tool_call: Callable | None = None,
    on_tool_result: Callable | None = None,
    on_thinking: Callable | None = None,
    on_todo_created: Callable | None = None,
    on_todo_update: Callable | None = None,
    on_request_input: Callable | None = None,
    pause_event: Any = None,
    session_id: str = "default",
    wall_timeout: float = 300.0,
) -> dict[str, Any]:
    """Execute a task with LLM, tools, and todo tracking.

    Args:
        on_request_input: Called when a todo needs user input. Signature: (question: str) -> str
        pause_event: threading.Event to pause/resume execution. If provided and set, executor pauses.
    """
    logger.info(
        "execute_agent_task start: agent=%s, model=%s, task=%r", agent_role, model, task[:200]
    )

    # Resolve callbacks: explicit args > contextvars > None
    ctx = get_execution_callbacks()
    on_tool_call = on_tool_call or ctx["on_tool_call"]
    on_tool_result = on_tool_result or ctx["on_tool_result"]
    on_thinking = on_thinking or ctx["on_thinking"]
    on_todo_created = on_todo_created or ctx["on_todo_created"]
    on_todo_update = on_todo_update or ctx["on_todo_update"]
    on_request_input = on_request_input or ctx["on_request_input"]

    # Wrap callbacks to inject per-agent distinction so TUI can show
    # "● {agent} — Technical Reasoning" and "Tool: ... by @agent" and preserve
    # sequential order thinking→tool→thinking per agent. Internal code still calls
    # with single arg, wrapper forwards with agent_role for per-agent dedupe.
    _orig_thinking = on_thinking
    _orig_tool_call = on_tool_call
    _orig_tool_result = on_tool_result

    def _wrap_thinking(text: str, agent_name: str | None = None) -> None:
        if _orig_thinking is None:
            return
        _ag = agent_name or agent_role
        try:
            _orig_thinking(text, _ag)  # type: ignore[call-arg]
        except TypeError:
            try:
                _orig_thinking(text)  # type: ignore[call-arg]
            except Exception:
                pass
        except Exception:
            pass

    def _wrap_tool_call(name: str, args: dict, agent_name: str | None = None) -> None:
        if _orig_tool_call is None:
            return
        _ag = agent_name or agent_role
        try:
            _orig_tool_call(name, args, _ag)  # type: ignore[call-arg]
        except TypeError:
            try:
                _orig_tool_call(name, args)  # type: ignore[call-arg]
            except Exception:
                pass
        except Exception:
            pass

    def _wrap_tool_result(
        name: str, args: dict, result: str, success: bool, agent_name: str | None = None
    ) -> None:
        if _orig_tool_result is None:
            return
        _ag = agent_name or agent_role
        try:
            _orig_tool_result(name, args, result, success, _ag)  # type: ignore[call-arg]
        except TypeError:
            try:
                _orig_tool_result(name, args, result, success)  # type: ignore[call-arg]
            except Exception:
                pass
        except Exception:
            pass

    # Replace with wrapped versions for internal use
    on_thinking = _wrap_thinking if _orig_thinking else None  # type: ignore[assignment]
    on_tool_call = _wrap_tool_call if _orig_tool_call else None  # type: ignore[assignment]
    on_tool_result = _wrap_tool_result if _orig_tool_result else None  # type: ignore[assignment]

    tools = _discover_tools()

    # --- Plugin: on_init hook (once per execution lifecycle) ---
    try:
        from sago.plugins.base import get_plugin_manager

        _plugin_ctx = {
            "task": task,
            "model": model,
            "agent_role": agent_role,
            "cwd": cwd,
            "session_id": session_id,
            "tools": list(tools.keys()),
        }
        for plugin in get_plugin_manager().discover_plugins():
            if plugin.meta.enabled:
                try:
                    plugin.on_init(_plugin_ctx)
                except Exception as e:
                    log_exception(e, f"Plugin on_init failed for {plugin.meta.name}")
    except Exception as e:
        log_exception(e, "Failed to discover and initialize plugins")

    # --- Skill: discover matching skills for this task ---
    matched_skills = []
    custom_skills_context = ""
    try:
        from sago.skills.loader import SkillLoader
        from sago.skills.registry import get_skill_registry

        registry = get_skill_registry()
        matched_skills = registry.find_skills_for_task(task)

        # Also discover custom skills from disk
        custom_skills = SkillLoader.discover_skills()
        # Match custom skills by keyword overlap with task
        task_words = set(task.lower().split())
        for cs in custom_skills.values():
            cs_words = set(cs.description.lower().split())
            name_words = set(cs.name.lower().replace("-", " ").replace("_", " ").split())
            if task_words & cs_words or task_words & name_words:
                matched_skills_custom = cs
                custom_skills_context += f"\n\n{matched_skills_custom.to_prompt_context()}"
            elif not task_words.isdisjoint(cs_words | name_words):
                custom_skills_context += f"\n\n{cs.to_prompt_context()}"
    except Exception as e:
        log_exception(e, "Failed to discover and match skills")

    # --- Plugin: hook_user_message (transform/enrich the prompt) ---
    try:
        from sago.plugins.base import get_plugin_manager

        _hook_ctx = {
            "task_type": _detect_task_type(task),
            "model": model,
            "agent_role": agent_role,
            "cwd": cwd,
            "matched_skills": [s.name for s in matched_skills],
        }
        task = get_plugin_manager().hook_user_message(task, _hook_ctx)
        enhanced_task = task  # re-sync after plugin transformation
    except Exception as e:
        log_exception(e, "Plugin hook_user_message failed")

    # Always resolve active model, key, base_url, and provider from config
    try:
        from sago.llm.tui_providers import resolve_active_llm_config

        # Pass through caller's values if provided; resolve_active_llm_config
        # merges them with saved settings/env vars and applies fallback logic.
        active_cfg = resolve_active_llm_config(
            model=None if model in ("openrouter/free", "") else model,
            api_key=api_key or None,
            base_url=base_url,
        )
        if not api_key:
            api_key = active_cfg["api_key"]
        if model in ("openrouter/free", "") and active_cfg["model"]:
            model = active_cfg["model"]
        if base_url is None:
            base_url = active_cfg["base_url"]
        provider = active_cfg["provider"]
    except Exception as e:
        log_exception(e, "Failed to resolve active LLM configuration")
        provider = "openrouter"

    # Use the correct client for the selected provider
    from sago.llm.tui_providers import get_tui_client

    client, api_model = get_tui_client(provider, model)
    start_time = time.time()

    # 1. Automatically enhance prompt with intent, clarity, constraints, and criteria
    from sago.engine.prompt_enhancer import enhance_prompt

    enhancement = enhance_prompt(
        task=task,
        agent_role=agent_role,
        cwd=cwd,
    )
    enhanced_task = enhancement.enhanced_prompt

    if on_thinking and enhancement.improvements:
        on_thinking(
            f"✨ Enhanced Prompt: {enhancement.intent_summary} ({', '.join(enhancement.improvements[:3])})"
        )

    # Assemble rich tri-partite context (AST symbols, hybrid search, learning patterns, previous sessions)
    task_type = _detect_task_type(task)
    logger.info(
        "Execution context assembled: task_type=%s, agent=%s, model=%s",
        task_type,
        agent_role,
        model,
    )
    # --- Simple analyze caps: tiny codebases (≤5 files) must be ≤15 tools / 8 iter / 8k tokens ---
    _file_count_probe = _detect_file_count(task, cwd)
    _is_simple_analyze_flag = _is_simple_analyze(task_type, _file_count_probe)
    logger.debug(
        "File count probe: %s, is_simple_analyze=%s", _file_count_probe, _is_simple_analyze_flag
    )
    if _is_simple_analyze_flag:
        # Cap budgets per spec (file_count <=5 → 15 tool calls, 8 iterations, 8k tokens)
        max_iterations = min(max_iterations, _SIMPLE_ANALYZE_CAPS["max_iterations"])
        max_tokens = min(max_tokens, _SIMPLE_ANALYZE_CAPS["max_tokens"])
        logger.info(
            "Simple analyze detected (file_count=%s) — capping max_iterations=%s max_tokens=%s",
            _file_count_probe,
            max_iterations,
            max_tokens,
        )
    try:
        from sago.engine.context_assembler import get_context_assembler

        assembler = get_context_assembler(cwd)
        agent_name_slug = agent_role.lower().replace(" ", "-") if agent_role else None
        assembled = assembler.assemble(
            task=enhanced_task,
            task_type=task_type,
            agent_name=agent_name_slug,
            available_tools=list(tools.keys()),
            session_id=session_id,
        )
    except Exception as e:
        log_exception(e, "Failed to assemble context")
        assembled = None

    # Detect existing project context (languages, frameworks, structure)
    project_ctx = _get_context(cwd)
    project_context = _detect_project_context(cwd)

    # Enrich project context with detected info
    if project_context["languages"]:
        project_ctx += f"\nDetected languages: {', '.join(project_context['languages'])}"
    if project_context["frameworks"]:
        project_ctx += f"\nDetected frameworks: {', '.join(project_context['frameworks'])}"
    if project_context["test_frameworks"]:
        project_ctx += f"\nTest frameworks: {', '.join(project_context['test_frameworks'])}"
    if project_context["package_managers"]:
        project_ctx += f"\nPackage managers: {', '.join(project_context['package_managers'])}"

    # Auto-create todo list for complex tasks
    task_plan = None
    if _is_complex_task(task) and api_key:
        try:
            from sago.tasks import TaskStatus, get_task_manager

            tm = get_task_manager()
            steps = _generate_plan_with_llm(task, client, model, _TOOL_DESCRIPTIONS)
            # Mark steps that sound like they need confirmation
            confirm_keywords = ["confirm", "approve", "review", "check", "verify", "validate"]
            todos_with_flags = []
            for step in steps:
                needs_confirm = any(kw in step.lower() for kw in confirm_keywords)
                todos_with_flags.append((step, needs_confirm))
            task_plan = tm.create_plan(goal=task, todos=[s for s, _ in todos_with_flags])
            # Mark todos that need confirmation
            for i, (_, needs_confirm) in enumerate(todos_with_flags):
                if needs_confirm and i < len(task_plan.todos):
                    task_plan.todos[i].requires_confirmation = True
                    task_plan.todos[
                        i
                    ].confirmation_message = f"Please confirm: {task_plan.todos[i].description}"
            if on_todo_created:
                on_todo_created(task_plan)
        except Exception as e:
            log_exception(e, "Failed to create task plan")
            task_plan = None

    # Auto-resolve specialist agent if default or generic agent was supplied
    if agent_role in ("python-engineer", "developer", "general-assistant", "assistant", "agent"):
        try:
            from sago.agents.registry import resolve_specialist_agent

            resolved = resolve_specialist_agent(task=task, cwd=cwd, default_agent=agent_role)
            if resolved and resolved != "general-assistant":
                agent_role = resolved
        except Exception as e:
            log_exception(e, "Failed to resolve specialist agent")

    # Load agent profile metadata
    profile = _load_agent_profile(agent_role)

    # Use profile metadata if available
    if profile:
        if not system_prompt and task_type != "chat":
            system_prompt = profile.get("system_prompt", "")
        if profile.get("model_preference"):
            model = profile["model_preference"]
        if profile.get("temperature"):
            pass  # temperature is used in API call below
        if profile.get("max_iterations") and max_iterations == 30:
            max_iterations = min(profile["max_iterations"], 50)
        # Filter tools to only those the agent knows about
        if profile.get("tools") and task_type != "chat":
            agent_tools = {t: tools[t] for t in profile["tools"] if t in tools}
            if agent_tools:
                tools = agent_tools
        # Simple analyze: disable sub-agent spawning (no spawn_agent for ≤5 files)
        if _is_simple_analyze_flag and "spawn_agent" in tools:
            tools.pop("spawn_agent", None)
            logger.info("Simple analyze — removed spawn_agent from toolset")

    # Auto-detect task type and use appropriate prompt
    if not system_prompt:
        template = PROMPTS.get(task_type, PROMPTS["create"])
        system_prompt = template.format(
            agent_role=agent_role,
            project_ctx="",  # Context goes in user message
        )

    # ── Simple analyze tight prompt: require glob_files first, cap budget ──
    if _is_simple_analyze_flag:
        system_prompt += (
            "\n\n=== SIMPLE ANALYZE MODE (≤5 files) ===\n"
            "BUDGET: max 15 tool calls total, max 8 iterations. You MUST finish within budget.\n"
            "WORKFLOW: glob_files FIRST to list files → code_analyzer on each file → summarize. Do NOT probe with read_file on directories or repeated execute_shell.\n"
            "TOOL RULE: If read_file fails with 'Not a file: is a directory', IMMEDIATELY use glob_files instead. Do NOT retry read_file on same path.\n"
            "EARLY EXIT: If glob_files shows ≤5 files and code_analyzer succeeds on all of them, STOP and summarize — do not keep looping with execute_shell probes.\n"
            "NO SPAWN: Do NOT use spawn_agent or delegate to sub-agents for this tiny codebase.\n"
        )
    # ── Always-on reasoning: append calibrated protocol even for chat/query ──
    # Previously lightweight tasks skipped heavy reasoning and produced shallow
    # answers. This ensures every turn does a brief think + self-realization
    # check without overthinking.
    system_prompt += REASONING_PROTOCOL

    # --- Skill: inject matched skill context into system prompt ---
    # Skip heavy skill injection for lightweight tasks (chat, query)
    _needs_heavy_context = task_type not in ("chat", "query")
    if matched_skills and _needs_heavy_context:
        skill_sections = []
        for skill in matched_skills[:3]:  # Top 3 matching skills
            skill_sections.append(f"### Active Skill: {skill.name}\n{skill.description}")
            if skill.tools:
                skill_sections.append(f"Recommended tools: {', '.join(skill.tools)}")
            if skill.steps:
                steps_text = "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(skill.steps))
                skill_sections.append(f"Suggested workflow:\n{steps_text}")
        skill_block = "\n\n".join(skill_sections)
        system_prompt += (
            f"\n\n=== MATCHED SKILL(S) FOR THIS TASK ===\n"
            f"{skill_block}\n"
            f"Follow the skill workflow where appropriate, but adapt to the specific context."
        )

    # --- Custom skill: inject SKILL.md instructions ---
    if custom_skills_context and _needs_heavy_context:
        system_prompt += f"\n\n=== CUSTOM SKILL INSTRUCTIONS ===\n{custom_skills_context}"

    # --- Skill-based tool filtering: restrict tools to skill-defined subset ---
    if matched_skills and _needs_heavy_context:
        # Union of all tools from matched skills
        skill_tool_names: set[str] = set()
        for skill in matched_skills:
            skill_tool_names.update(skill.tools)
        # Only filter if skill specifies tools and they exist in available tools
        if skill_tool_names:
            filtered = {t: tools[t] for t in skill_tool_names if t in tools}
            if filtered:
                # Always keep core tools available
                core_tools = {
                    "read_file",
                    "write_file",
                    "edit_file",
                    "execute_shell",
                    "grep_content",
                    "glob_files",
                    "ast_grep",
                    "code_analyzer",
                }
                filtered.update({t: tools[t] for t in core_tools if t in tools})
                tools = filtered
        # Ensure spawn_agent stripped for simple analyze even after skill filtering
        if _is_simple_analyze_flag and "spawn_agent" in tools:
            tools.pop("spawn_agent", None)

    # Inject system-level enhancements (learning approach, known fixes, project instructions)
    if assembled and _needs_heavy_context:
        system_enhancements = assembled.format_system_enhancements()
        if system_enhancements:
            system_prompt += f"\n\n{system_enhancements}"
    elif _needs_heavy_context:
        # Fallback to direct instructions / learning store lookup
        try:
            from sago.learning import get_learning_store

            ls = get_learning_store()
            suggestion = ls.suggest_approach(task_type, list(tools.keys()))
            if suggestion:
                system_prompt += (
                    f"\n\n=== PAST SUCCESSFUL APPROACH ===\n"
                    f"Based on past similar tasks, this approach worked:\n"
                    f"{suggestion}\n"
                    f"Consider using a similar approach, but adapt to the current context."
                )
        except Exception as e:
            log_exception(e, "Failed to load learning store suggestions")

        try:
            from sago.memory.project_instructions import get_project_instructions

            pi = get_project_instructions(cwd)
            instructions_prompt = pi.get_for_prompt()
            if instructions_prompt:
                system_prompt += instructions_prompt
        except Exception as e:
            log_exception(e, "Failed to load project instructions")

    # State tracking
    tool_history: list[dict] = []
    tool_call_counts: dict[str, int] = {}
    failed_calls: set[str] = set()
    total_tokens_in = 0
    total_tokens_out = 0
    total_cache_hit = 0
    total_cache_miss = 0
    files_created: list[str] = []
    current_todo_index = 0
    todo_tool_counts: dict[str, int] = {}  # track tools per todo

    # Initialize single ToolUsageStore instance for task lifecycle
    # Use real session_id when available so per-agent grouping works (fixes summary bug)
    tool_usage_store = None
    try:
        from sago.database import ToolUsageStore

        _tus_sid = (
            session_id
            if session_id and session_id not in ("default", "simple_executor")
            else "simple_executor"
        )
        # Ensure session row exists for FK (simple_executor is dummy)
        try:
            from sago.database import Session as _Session

            _s = _Session(_tus_sid)
            if not _s.get():
                _s.create(title="simple_executor auto")
                _s.close()
        except Exception:
            pass
        tool_usage_store = ToolUsageStore(_tus_sid)
    except Exception as e:
        log_exception(e, "Failed to initialize ToolUsageStore")
        tool_usage_store = None

    # Build user message with rich reference data context (read-only)
    # Skip heavy context for chat and lightweight query tasks
    if task_type in ("chat", "query"):
        user_content = task
    elif assembled:
        context_block = assembled.format_user_context_block()
        user_content = (
            f"## Reference Context (read-only workspace data)\n{context_block}\n\n## Task & Plan\n{enhanced_task}"
            if context_block
            else enhanced_task
        )
    else:
        user_content = (
            f"## Project Context (read-only reference data)\n{project_ctx}\n\n## Task & Plan\n{enhanced_task}"
            if project_ctx
            else enhanced_task
        )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    logger.info(
        "Execution loop starting: max_iterations=%d, max_tokens=%d, tools=%d",
        max_iterations,
        max_tokens,
        len(tools),
    )

    # Build OpenAI function calling tool definitions
    # Skip tools for chat tasks to avoid Google API rate limits on tool-use quotas
    # Auto-filter for reasoning-heavy models (e.g. stealth/ox-alpha) that choke on
    # 70+ tool schemas — verified live: 73 tools -> empty response, 7 tools -> tool_calls OK
    if "stealth/ox-alpha" in model and len(tools) > 20:
        keep = {
            "read_file",
            "write_file",
            "execute_shell",
            "edit_file",
            "multi_replace_file",
            "ast_edit",
            "ast_grep",
            "search_symbols",
            "hybrid_code_search",
            "code_analyzer",
            "list_directory",
            "glob_files",
            "grep_content",
            "diff_tool",
            "git_operations",
            "review_changes",
        }
        tools = {k: v for k, v in tools.items() if k in keep}
        logger.info("Filtered tools for %s: %d -> %d", model, 73, len(tools))
    if task_type == "chat":
        openai_tools = []
    else:
        openai_tools = _build_openai_tools(tools)

    content = ""

    def _compact_messages_if_needed(
        msgs: list[dict[str, Any]], max_tokens: int | None = None
    ) -> list[dict[str, Any]]:
        """Compact messages if total content exceeds token limit using semantic distillation."""
        effective_max_tokens = (
            max_tokens
            if max_tokens is not None
            else int(os.environ.get("SAGO_MAX_TOKENS", str(_get_executor_config().max_tokens)))
        )
        total_chars = sum(len(str(m.get("content", "") or "")) for m in msgs)
        estimated_tokens = total_chars // 4
        logger.debug(
            "Message compaction check: estimated_tokens=%d, max=%d, messages=%d",
            estimated_tokens,
            effective_max_tokens,
            len(msgs),
        )
        if estimated_tokens <= effective_max_tokens:
            return msgs

        # Distill older tool messages first to preserve conversation history and system instructions
        distilled: list[dict[str, Any]] = []
        recent_threshold = max(2, len(msgs) - 6)

        for idx, m in enumerate(msgs):
            if idx == 0 or idx >= recent_threshold:
                # Keep system prompt and recent 6 messages intact
                distilled.append(m)
                continue

            role = m.get("role")
            content = m.get("content")

            if role == "tool" and isinstance(content, str) and len(content) > 300:
                # Distill large tool output
                prefix = content[:150]
                suffix = content[-100:]
                short_content = (
                    f"{prefix}\n... [Output pruned ({len(content)} chars)] ...\n{suffix}"
                )
                new_m = dict(m)
                new_m["content"] = short_content
                distilled.append(new_m)
            elif role == "assistant" and isinstance(content, str) and len(content) > 800:
                short_content = content[:400] + "\n... [Assistant reasoning summary] ..."
                new_m = dict(m)
                new_m["content"] = short_content
                distilled.append(new_m)
            else:
                distilled.append(m)

        # Re-check
        new_total_chars = sum(len(str(m.get("content", "") or "")) for m in distilled)
        if new_total_chars // 4 <= max_tokens:
            return distilled

        # Fallback to session compactor if available
        try:
            from sago.memory.compaction import SessionCompactor

            compactor = SessionCompactor(max_context_tokens=max_tokens)
            return compactor.build_context_window(distilled, max_tokens=max_tokens)
        except Exception:
            return distilled

    # ---- Post-execution quality review ----
    def _review_output_quality(output: str, files_created: list, tool_history: list) -> list[str]:
        """Review output quality and return list of issues found."""
        issues = []
        if not output or len(output.strip()) < 50:
            issues.append(f"Output too short ({len(output or '')} chars) — likely incomplete")
        output_lower = (output or "").lower()
        failure_indicators = ["i cannot", "i'm unable", "i don't have", "not possible"]
        for fi in failure_indicators:
            if fi in output_lower:
                issues.append(f"Output contains failure indicator: '{fi}'")
        if tool_history and not files_created:
            write_calls = [t for t in tool_history if t.get("tool") in ("write_file", "edit_file")]
            if write_calls:
                issues.append("write_file/edit_file called but no files tracked as created")
        return issues

    # ---- Pre-validate tool arguments to catch hallucinated/empty args ----
    def _validate_tool_args(tool_name: str, tool_args: dict) -> str | None:
        """Return an error message if tool args are invalid, else None."""
        if tool_name == "spawn_agent":
            task_val = tool_args.get("task", "")
            if not task_val or not task_val.strip() or len(task_val.strip()) < 5:
                return None
        elif tool_name == "write_file":
            content_val = tool_args.get("content", "")
            path_val = tool_args.get("file_path", "")
            if not path_val or not path_val.strip():
                return "REJECTED: write_file requires a non-empty file_path."
            if not content_val or not content_val.strip():
                return f"REJECTED: write_file requires non-empty content for '{path_val}'."
        elif tool_name == "execute_shell":
            cmd_val = tool_args.get("command", "")
            if not cmd_val or not cmd_val.strip():
                return "REJECTED: execute_shell requires a non-empty command."
        elif tool_name == "edit_file":
            path_val = tool_args.get("file_path", "") or tool_args.get("target_file", "")
            if not path_val or not path_val.strip():
                return "REJECTED: edit_file requires a non-empty file_path."
        elif tool_name == "read_file":
            path_val = tool_args.get("file_path", "") or tool_args.get("path", "")
            if not path_val or not path_val.strip():
                return "REJECTED: read_file requires a non-empty file_path."
        elif tool_name == "http_client":
            url_val = tool_args.get("url", "")
            if not url_val or not url_val.strip():
                return "REJECTED: http_client requires a non-empty URL."
        return None

    for i in range(max_iterations):
        # --- Wall-clock timeout check ---
        if wall_timeout > 0 and (time.time() - start_time) > wall_timeout:
            logger.warning(
                "Agent '%s' exceeded wall-clock timeout (%.0fs), stopping after %d iterations",
                agent_role,
                wall_timeout,
                i,
            )
            if on_thinking:
                on_thinking(f"Timed out after {wall_timeout:.0f}s ({i} iterations completed)")
            break

        # --- Simple analyze hard budget: stop if 15 tool calls already made ---
        if _is_simple_analyze_flag and len(tool_history) >= _SIMPLE_ANALYZE_CAPS["max_tool_calls"]:
            logger.warning(
                "Simple analyze hard cap: %d tool calls reached, forcing exit at iteration %d",
                len(tool_history),
                i,
            )
            break

        # --- OPT-IN observability (no-op unless a trace was started) ---
        # To capture a full per-step span tree around each LLM+tool iteration,
        # uncomment the following block (control flow is unchanged):
        #
        #     from sago.observability.tracing import span as _trace_span
        #     _step_ctx = _trace_span(f"step:{i}")
        #     _step_ctx.__enter__()
        #     try:
        #         ... existing loop body ...
        #     finally:
        #         _step_ctx.__exit__(None, None, None)
        #
        # For now we record a lightweight step marker so the trace still shows
        # each agent turn without restructuring the large loop body.
        try:
            from sago.observability.tracing import record_marker

            record_marker("step", str(i), model=model)
        except Exception as e:
            log_exception(e, "Failed to record observability trace marker")
        if pause_event and pause_event.is_set():
            if on_thinking:
                on_thinking("Paused - waiting for user input...")
            pause_event.wait()  # Block until user provides input

        # Get current todo info for LLM context
        _todo_context = ""
        if task_plan and current_todo_index < len(task_plan.todos):
            current_todo = task_plan.todos[current_todo_index]
            _todo_context = (
                f"\n\n[CURRENT TASK STEP {current_todo_index + 1}/{len(task_plan.todos)}: {current_todo.description}]\n"
                f"Complete this specific step, then use finish_step tool or indicate you're done with this step."
            )

        phase = "Planning" if i == 0 else "Working"
        todo_info = f" | Step {current_todo_index + 1}/{len(task_plan.todos)}" if task_plan else ""
        files_info = f" ({len(files_created)} files created)" if files_created else ""
        # Spinner only - not real thinking. Real thinking is extracted from LLM <thinking> tags below.
        if on_thinking:
            on_thinking(f"{phase}... (step {i + 1}/{max_iterations}{todo_info}{files_info})")

        # Native tool calls extracted from the model response (OpenAI or Gemini).
        # The gemini branch populates this so the shared execution loop below runs.
        native_tool_calls: list[dict[str, Any]] = []

        # Enforce rate limits if configured
        try:
            from sago.tracking.token_tracker import get_token_tracker

            provider_name = "gemini" if model.startswith("gemini") else "openai"
            allowed, wait_sec = get_token_tracker().check_rate_limit(provider_name)
            if not allowed and wait_sec > 0:
                if on_thinking:
                    on_thinking(
                        f"Rate limit hit for {provider_name}, backing off for {wait_sec:.1f}s..."
                    )
                time.sleep(min(wait_sec, 60))
        except Exception as e:
            log_exception(e, "Failed to check token rate limit")

        try:
            temp = profile.get("temperature", 0.3) if profile else 0.3
            # Clamp temperature: max 0.4 for tool tasks, 0.6 for chat
            # Lower temperature = less hallucination
            temp = min(temp, 0.4) if task_type != "chat" else min(temp, 0.6)

            _raw_gemini_parts = []  # Preserve thought_signature across turns

            # Use Google native SDK for google/gemini providers
            if provider == "google":
                try:
                    from google.genai import types as google_types

                    # client is already a Google GenAI client from get_tui_client
                    google_client = client
                    sys_msg = ""
                    contents = []
                    for msg in messages:
                        if msg["role"] == "system":
                            sys_msg = msg["content"]
                            continue
                        if msg["role"] == "user":
                            contents.append(
                                google_types.Content(
                                    role="user",
                                    parts=[google_types.Part(text=msg["content"])],
                                )
                            )
                        elif msg["role"] == "assistant":
                            # Use raw parts if available (preserves thought_signature)
                            if msg.get("_google_parts"):
                                contents.append(
                                    google_types.Content(
                                        role="model",
                                        parts=list(msg["_google_parts"]),
                                    )
                                )
                            else:
                                parts = []
                                if msg.get("content"):
                                    parts.append(google_types.Part(text=msg["content"]))
                                for tc in msg.get("tool_calls", []):
                                    fn = tc["function"]
                                    try:
                                        args = (
                                            json.loads(fn["arguments"])
                                            if fn.get("arguments")
                                            else {}
                                        )
                                    except json.JSONDecodeError:
                                        args = {}
                                    parts.append(
                                        google_types.Part(
                                            function_call=google_types.FunctionCall(
                                                name=fn["name"], args=args
                                            )
                                        )
                                    )
                                if parts:
                                    contents.append(google_types.Content(role="model", parts=parts))
                        elif msg["role"] == "tool":
                            # Gemini receives tool results as function responses.
                            contents.append(
                                google_types.Content(
                                    role="user",
                                    parts=[
                                        google_types.Part(
                                            function_response=google_types.FunctionResponse(
                                                name=msg.get("name", "tool"),
                                                response={"result": msg["content"]},
                                            )
                                        )
                                    ],
                                )
                            )
                    if not contents:
                        contents = [
                            google_types.Content(
                                role="user", parts=[google_types.Part(text="Hello")]
                            )
                        ]

                    # Convert OpenAI tools to Google format
                    # ``google.genai.types.Type`` has grown over SDK versions.
                    # Resolve optional values defensively so an older SDK can
                    # still execute tools whose schemas use those JSON types.
                    gemini_type = google_types.Type
                    _JSON_TO_GEMINI_TYPE = {
                        "string": gemini_type.STRING,
                        "integer": getattr(gemini_type, "INTEGER", gemini_type.STRING),
                        "number": getattr(gemini_type, "NUMBER", gemini_type.STRING),
                        "boolean": getattr(gemini_type, "BOOLEAN", gemini_type.STRING),
                        "array": getattr(gemini_type, "ARRAY", gemini_type.STRING),
                        "object": gemini_type.OBJECT,
                    }
                    google_tools = []
                    for tool in openai_tools:
                        func = tool["function"]
                        params = func.get("parameters", {})
                        properties = {}
                        for k, v in params.get("properties", {}).items():
                            prop_type_str = v.get("type", "string")
                            prop_type = _JSON_TO_GEMINI_TYPE.get(
                                prop_type_str, google_types.Type.STRING
                            )
                            schema_kwargs: dict[str, Any] = {
                                "type": prop_type,
                                "description": v.get("description", ""),
                            }
                            # Handle enum for Literal types
                            if "enum" in v:
                                schema_kwargs["enum"] = v["enum"]
                            # Handle array item type
                            if prop_type == _JSON_TO_GEMINI_TYPE["array"] and "items" in v:
                                item_type_str = v["items"].get("type", "string")
                                schema_kwargs["items"] = google_types.Schema(
                                    type=_JSON_TO_GEMINI_TYPE.get(
                                        item_type_str, google_types.Type.STRING
                                    )
                                )
                            properties[k] = google_types.Schema(**schema_kwargs)
                        google_tools.append(
                            google_types.FunctionDeclaration(
                                name=func["name"],
                                description=func.get("description", ""),
                                parameters=google_types.Schema(
                                    type=google_types.Type.OBJECT,
                                    properties=properties,
                                    required=params.get("required", []),
                                ),
                            )
                        )

                    google_config = google_types.GenerateContentConfig(
                        system_instruction=sys_msg or None,
                        max_output_tokens=max_tokens,
                        temperature=temp,
                    )
                    if google_tools:
                        google_config.tools = [
                            google_types.Tool(function_declarations=google_tools)
                        ]
                    # Enable native Gemini thinking so part.thought is populated (gemini-2.5-flash)
                    try:
                        if hasattr(google_types, "ThinkingConfig"):
                            _tc_kwargs: dict[str, Any] = {}
                            # thinking_budget enables thought; include_thoughts ensures parts have thought=True
                            try:
                                _tc_kwargs["thinking_budget"] = 1024
                            except Exception:
                                pass
                            _tcfg = google_types.ThinkingConfig(**_tc_kwargs)  # type: ignore[attr-defined]
                            if hasattr(_tcfg, "include_thoughts"):
                                try:
                                    _tcfg.include_thoughts = True  # type: ignore[attr-defined]
                                except Exception:
                                    pass
                            google_config.thinking_config = _tcfg  # type: ignore[attr-defined]
                    except Exception:
                        pass

                    # Retry with exponential backoff for rate limits
                    max_retries = 3
                    response = None
                    for attempt in range(max_retries):
                        try:
                            response = google_client.models.generate_content(
                                model=model,
                                contents=contents,
                                config=google_config,
                            )
                            break
                        except Exception as api_err:
                            err_str = str(api_err).lower()
                            if (
                                "rate" in err_str
                                and "limit" in err_str
                                and attempt < max_retries - 1
                            ):
                                wait_sec = (2**attempt) * 2  # 2s, 4s, 8s
                                logger.warning(
                                    "Gemini rate limit, retrying in %ds (attempt %d/%d)",
                                    wait_sec,
                                    attempt + 1,
                                    max_retries,
                                )
                                time.sleep(wait_sec)
                            else:
                                raise

                    if response is None:
                        raise RuntimeError("Gemini API call failed after retries")

                    # Extract tool calls from Gemini response
                    gemini_tool_calls = []
                    _raw_gemini_parts = []  # Store raw parts for thought_signature preservation
                    # response.text raises if the response only contains function
                    # calls, so guard against that.
                    try:
                        content = response.text or ""
                    except Exception as e:
                        log_exception(e, "Failed to extract Gemini response text")
                        content = ""
                    if response.candidates:
                        _raw_gemini_parts = list(response.candidates[0].content.parts or [])
                        for part in _raw_gemini_parts:
                            if part.function_call:
                                gemini_tool_calls.append(
                                    {
                                        "id": f"gemini_{len(gemini_tool_calls)}",
                                        "name": part.function_call.name,
                                        "args": dict(part.function_call.args)
                                        if part.function_call.args
                                        else {},
                                    }
                                )

                    # Mirror the OpenAI path: feed the Gemini tool calls into the
                    # shared execution loop below (which runs them via the same
                    # tool registry and appends results for the next turn) instead
                    # of returning early.
                    if gemini_tool_calls:
                        native_tool_calls = gemini_tool_calls

                except ImportError:
                    logger.error("google-genai SDK not installed")
                    return {
                        "success": False,
                        "error": "google-genai not installed. Run: pip install google-genai",
                        "output": content or "Google SDK not available",
                        "tool_calls": tool_history,
                        "iterations": i + 1,
                        "tokens": {"input": 0, "output": 0},
                    }
            else:
                # OpenAI-compatible API with native function calling
                api_kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temp,
                }
                if openai_tools:
                    api_kwargs["tools"] = openai_tools
                    api_kwargs["tool_choice"] = "auto"

                # Retry with exponential backoff for rate limits
                max_retries = 3
                response = None
                for attempt in range(max_retries):
                    try:
                        response = client.chat.completions.create(**api_kwargs)
                        break
                    except Exception as api_err:
                        err_str = str(api_err).lower()
                        if ("429" in err_str or "rate" in err_str) and attempt < max_retries - 1:
                            wait_sec = (2**attempt) * 2  # 2s, 4s, 8s
                            logger.warning(
                                "Rate limit, retrying in %ds (attempt %d/%d)",
                                wait_sec,
                                attempt + 1,
                                max_retries,
                            )
                            time.sleep(wait_sec)
                        else:
                            raise

                if response is None:
                    raise RuntimeError("API call failed after retries")

        except Exception as e:
            error_msg = str(e)
            # Provide helpful error messages for common failures
            if "429" in error_msg or "rate" in error_msg.lower():
                if model.startswith("gemini"):
                    error_msg = (
                        f"Rate limit exceeded for model '{model}'.\n"
                        f"Try: 1) Wait a moment and retry, 2) Use a different model, "
                        f"3) Check your Google Cloud billing"
                    )
                else:
                    error_msg = (
                        f"Rate limit exceeded for model '{model}'.\n"
                        f"Try: 1) Wait a moment and retry, 2) Use a different model, "
                        f"3) Add credits at https://openrouter.ai/settings/credits"
                    )
            elif "401" in error_msg or "auth" in error_msg.lower():
                error_msg = f"Authentication failed. Check your API key for {model}."
            elif "404" in error_msg or "not found" in error_msg.lower():
                error_msg = (
                    f"Model '{model}' not found. Try 'openrouter/free' or check available models."
                )
            elif "insufficient" in error_msg.lower() or "credit" in error_msg.lower():
                error_msg = (
                    f"Insufficient credits for model '{model}'. Add credits or use 'openrouter'."
                )

            logger.error(
                "execute_agent_task failed at iteration %d: %s",
                i + 1,
                error_msg[:300],
            )
            return {
                "success": False,
                "error": error_msg,
                "output": content or f"API error: {error_msg}",
                "tool_calls": tool_history,
                "iterations": i + 1,
                "tokens": {
                    "input": total_tokens_in,
                    "output": total_tokens_out,
                    "cache_hit": total_cache_hit,
                    "cache_miss": total_cache_miss,
                },
                "elapsed": time.time() - start_time,
                "files_created": files_created,
                "task_plan": task_plan.to_dict() if task_plan else None,
            }

        # Parse response content and extract native tool calls
        message_obj = None

        if not model.startswith("gemini"):
            choice = response.choices[0]
            message_obj = choice.message
            content = message_obj.content or ""
            if not content and hasattr(message_obj, "reasoning") and message_obj.reasoning:
                content = message_obj.reasoning

            # Extract native tool_calls from OpenAI response
            if message_obj.tool_calls:
                for tc in message_obj.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except json.JSONDecodeError:
                        args = {}
                    native_tool_calls.append(
                        {
                            "id": tc.id,
                            "name": tc.function.name,
                            "args": args,
                        }
                    )

        # Handle empty or None content with no tool calls
        if not content or content.strip() == "":
            if not native_tool_calls:
                if i < max_iterations - 1:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "You returned an empty response. Please use the available tools to complete the task."
                            ),
                        }
                    )
                    continue
                else:
                    content = (
                        "Error: Model returned empty response. Try again or use a different model."
                    )

        if hasattr(response, "usage") and response.usage:
            total_tokens_in += response.usage.prompt_tokens or 0
            total_tokens_out += response.usage.completion_tokens or 0
            # Track cache hit/miss (OpenAI/OpenRouter compatible)
            if hasattr(response.usage, "prompt_tokens_details"):
                details = response.usage.prompt_tokens_details
                if hasattr(details, "cached_tokens"):
                    total_cache_hit += details.cached_tokens or 0
                    total_cache_miss += (response.usage.prompt_tokens or 0) - (
                        details.cached_tokens or 0
                    )
            # OPT-IN observability: record LLM token usage into the active trace
            # (no-op when no trace is active; never changes control flow).
            try:
                from sago.observability.tracing import record_token_usage

                record_token_usage(
                    prompt_tokens=response.usage.prompt_tokens or 0,
                    completion_tokens=response.usage.completion_tokens or 0,
                    model=model,
                )
            except Exception as e:
                log_exception(e, "Failed to record token usage in observability trace")
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": content or None}
        if native_tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["args"]),
                    },
                }
                for tc in native_tool_calls
            ]
        # Preserve raw Gemini parts for thought_signature across turns
        if _raw_gemini_parts:
            assistant_msg["_google_parts"] = _raw_gemini_parts
        messages.append(assistant_msg)

        # ── Always-on reasoning visibility: extract <thinking> or synthesize ──
        # Ensures dev telemetry Thinking tab never shows 0 even when LLM skips tags.
        _llm_thinking = ""
        try:
            # Gemini native thought parts
            if _raw_gemini_parts:
                _gem_think = ""
                for _part in _raw_gemini_parts:
                    if getattr(_part, "thought", None):
                        _t = getattr(_part, "text", "") or ""
                        if _t:
                            _gem_think += _t + "\n"
                if _gem_think.strip():
                    _llm_thinking = _gem_think.strip()
            if not _llm_thinking:
                _thm = re.search(
                    r"<(?:thinking|thought)>(.*?)</(?:thinking|thought)>",
                    content or "",
                    re.DOTALL,
                )
                if _thm:
                    _llm_thinking = _thm.group(1).strip()
            if not _llm_thinking and message_obj is not None:
                for _rf in (
                    "reasoning",
                    "reasoning_content",
                    "thinking",
                    "thought",
                    "reasoning_details",
                ):
                    if hasattr(message_obj, _rf):
                        _mr = getattr(message_obj, _rf, None)
                        if _mr:
                            if isinstance(_mr, list):
                                _mr = " ".join(
                                    str(v.get("text", "") if isinstance(v, dict) else str(v))
                                    for v in _mr
                                )
                            _llm_thinking = str(_mr).strip()
                            if _llm_thinking:
                                break
        except Exception:
            _llm_thinking = ""
        # No synthetic TUI — only real thinking shown (prevents BS). Fallback recorded to tracer only.
        _is_synthetic = False
        if not _llm_thinking and i == 0:
            _is_synthetic = True
            _llm_thinking = f"Considering: {task[:120].replace(chr(10), ' ').strip()[:100]} — planning next step."
        elif not _llm_thinking:
            _llm_thinking = ""  # No fallback for subsequent steps — keep 1 per turn
        if _llm_thinking:
            try:
                from sago.tracking.dev_tracer import get_dev_tracer as _gdt_think

                _tracer_think = _gdt_think()
                _tracer_think.record_thinking(
                    source=f"agent.{agent_role}", model=model, thinking_content=_llm_thinking
                )
            except Exception:
                pass
            # Only mount real thinking to TUI; synthetic stays in tracer (no BS card)
            if on_thinking and not _is_synthetic:
                try:
                    on_thinking(_llm_thinking)
                except Exception:
                    pass
        # Always record LLM response trace (thinking may be empty)
        try:
            from sago.tracking.dev_tracer import get_dev_tracer as _gdt_resp

            _tracer_resp = _gdt_resp()
            _tracer_resp.record_llm_response(
                source=f"agent.{agent_role}",
                model=model,
                response_content=content or "",
                thinking=_llm_thinking,
                tool_calls=[{"name": tc["name"], "args": tc["args"]} for tc in native_tool_calls],
                usage={
                    "tokens_in": total_tokens_in,
                    "tokens_out": total_tokens_out,
                },
            )
        except Exception:
            pass

        # If no tool calls at all, check for hallucination or completion
        if not native_tool_calls:
            # Detect fabrication (claims to have done things without tool calls)
            fabrication_phrases = [
                # File content claims
                "the file contains",
                "the contents are",
                "i read the file",
                "the file has",
                "i can see that",
                "looking at the file",
                "the code shows",
                "i opened the file",
                "the file shows",
                "after reading the file",
                "examining the file",
                "reviewing the file",
                "inspecting the file",
                "checking the file",
                "the file at",
                "opening the file",
                # File creation/modification claims
                "successfully created",
                "i saved the file",
                "the file was created",
                "i have created",
                "i've created",
                "done! the file",
                "i've updated",
                "i have updated",
                "i've added",
                "i have added",
                "i've removed",
                "i have removed",
                "i've deleted",
                "i have deleted",
                "i've modified",
                "i have modified",
                "the updated file",
                "the modified file",
                "i've written",
                "i have written",
                "i went ahead and",
                "i've gone ahead",
                "just finished",
                "i've already",
                # Code content claims
                "the code below",
                "here's the code",
                "here is the code",
                "as shown in",
                "as we can see",
                "based on the file",
                "after reviewing",
                "the function returns",
                "the class implements",
                "the module provides",
                "the implementation uses",
                "the logic handles",
                # Fix/analysis claims without tools
                "the fix involves",
                "the issue is",
                "the problem is",
                "the solution is",
                "here's the fix",
                "here is the fix",
                "the error occurs because",
                "the bug is in",
                "fixed by",
                "resolved by",
                # Test/result claims
                "i've tested",
                "i have tested",
                "all tests pass",
                "the test passes",
                "everything works",
                "it's working",
                "it works now",
                "verified that",
                "confirmed that",
                "tested and",
                "all checks pass",
                "all linting passes",
                "no test failures",
                "every assertion passed",
                "test coverage is",
                # Structural/architectural claims without tools
                "the codebase has",
                "the project has",
                "the repository has",
                "the codebase uses",
                "the project uses",
                "the repository uses",
                "there are",
                "there is",
                "based on my analysis",
                "based on the analysis",
                "after analyzing",
                "after reviewing",
                "after inspecting",
                "looking at the code",
                "looking at the implementation",
                "from what i can see",
                "from what we can see",
                "the available files",
                "the related files",
                "the files you mentioned",
                "the files in this",
                # Recommendation/quality claims without tools
                "i recommend",
                "i suggest",
                "the best approach",
                "the optimal solution",
                "this is more efficient",
                "this is less efficient",
                "no security vulnerabilities",
                "all edge cases are handled",
                # Action claims without tools
                "let me walk you through",
                "here's a summary",
                "to summarize",
                "in summary",
                "i've analyzed",
                "i have analyzed",
                "i've inspected",
                "i have inspected",
                "i've reviewed",
                "i have reviewed",
                # Structural claims
                "the project structure",
                "the codebase has",
                "the repository contains",
                "there are \\d+ files",
                "there are multiple",
                # Hedging/subtle claims
                "this should work",
                "that should work",
                "this will fix",
                "this is the right approach",
                "this is the correct",
                "this looks correct",
                "this looks good",
                "works as expected",
                "no breaking changes",
                "trust me",
                "rest assured",
                "i'm confident",
                "i'm sure that",
                "no further issues",
            ]
            content_lower = content.lower() if content else ""

            # Detect fabrication:
            # 1. No tool calls at all + claims to have done things
            # 2. Tool calls exist but response claims MORE than was actually done
            is_fabrication = False
            if not tool_history:
                # No tools called at all - any fabrication phrase is suspicious
                is_fabrication = any(phrase in content_lower for phrase in fabrication_phrases)
            else:
                # Tools were called - check if response claims actions beyond what tools did
                tools_called = {tc.get("tool", "") for tc in tool_history}
                # If agent claims file operations but no write/edit tool was called
                file_claim_phrases = [
                    "successfully created",
                    "i saved the file",
                    "the file was created",
                    "i've created",
                    "i have created",
                    "i've updated",
                    "i have updated",
                    "i've modified",
                    "i have modified",
                    "done! the file",
                    "i've written",
                    "i have written",
                ]
                claims_file_ops = any(phrase in content_lower for phrase in file_claim_phrases)
                made_file_ops = any(
                    t in tools_called for t in ("write_file", "edit_file", "create_file")
                )
                if claims_file_ops and not made_file_ops:
                    is_fabrication = True

            # ---- Code-level hallucination detection ----
            code_issues = _detect_code_hallucinations(content or "", tool_history)
            claim_issues = _verify_claims_against_history(content or "", tool_history)

            # Treat code-level issues as fabrication indicators
            if code_issues or claim_issues:
                is_fabrication = True

            if is_fabrication and i < max_iterations - 1:
                logger.info("Fabrication detected at iteration %d, triggering retry", i + 1)
                # Build specific guidance based on what was claimed
                guidance = []
                if any(
                    p in content_lower
                    for p in ["file contains", "i read", "the code shows", "i can see"]
                ):
                    guidance.append("Use read_file tool to actually read the file first.")
                if any(
                    p in content_lower
                    for p in ["created", "saved", "written", "updated", "modified"]
                ):
                    guidance.append(
                        "Use write_file or edit_file tool to actually create/modify the file."
                    )
                if any(p in content_lower for p in ["tested", "tests pass", "works"]):
                    guidance.append("Use execute_shell tool to actually run the tests.")
                if any(
                    p in content_lower for p in ["files you mentioned", "you mentioned", "you said"]
                ):
                    guidance.append(
                        "Do NOT claim the user mentioned specific files unless they literally said the names. "
                        "Use glob_files or grep_content to discover files."
                    )
                if any(p in content_lower for p in ["the available files", "related files are"]):
                    guidance.append(
                        "Use glob_files or file_search tool to discover files before listing them."
                    )
                if code_issues:
                    guidance.append(f"Code validation issues: {'; '.join(code_issues[:3])}")
                if claim_issues:
                    guidance.append(f"Claim verification issues: {'; '.join(claim_issues[:3])}")

                guidance_text = (
                    " ".join(guidance)
                    if guidance
                    else "Use the available tools to complete the task."
                )

                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "STOP. You are fabricating results without actually using tools. "
                            f"{guidance_text} "
                            "Do NOT claim file contents, file creation, or test results "
                            "without actually calling the corresponding tool. Do it NOW."
                        ),
                    }
                )
                continue

            # No tool calls - LLM is done with current step
            if task_plan and current_todo_index < len(task_plan.todos):
                from sago.tasks import TaskStatus, get_task_manager

                tm = get_task_manager()
                current_todo = task_plan.todos[current_todo_index]
                if current_todo.status == TaskStatus.IN_PROGRESS:
                    tm.complete_todo(
                        task_plan.id, current_todo.id, result=content[:200] if content else ""
                    )
                    if on_todo_update:
                        on_todo_update(task_plan, current_todo_index, "completed")
                    current_todo_index += 1
                    # Continue to next todo if there are more
                    if current_todo_index < len(task_plan.todos):
                        next_todo = task_plan.todos[current_todo_index]
                        tm.start_todo(task_plan.id, next_todo.id)
                        if on_todo_update:
                            on_todo_update(task_plan, current_todo_index, "started")
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    f"Moving to next step: {next_todo.description}\n"
                                    f"Execute this step now. Use the appropriate tools."
                                ),
                            }
                        )
                        continue
            # --- Plugin: hook_response (transform final response) ---
            try:
                from sago.plugins.base import get_plugin_manager

                content = get_plugin_manager().hook_response(
                    content, {"task": task, "model": model}
                )
            except Exception as e:
                log_exception(e, "Plugin hook_response failed")

            # ---- Post-execution quality review ----
            quality_issues = _review_output_quality(content, files_created, tool_history)

            # ---- Run hallucination detection on final response ----
            final_fabrication_issues = _detect_code_hallucinations(content or "", tool_history)
            final_claim_issues = _verify_claims_against_history(content or "", tool_history)

            # Hedging/subtle claim detection
            hedging_issues = []
            try:
                from sago.engine.hallucination_verifier import _detect_hedging_phrases

                hedging_issues = _detect_hedging_phrases(content or "", tool_history)
            except Exception as e:
                log_exception(e, "Failed to detect hedging phrases")

            # Tool result integrity check
            integrity_issues = []
            try:
                from sago.engine.hallucination_verifier import get_tool_integrity

                ti = get_tool_integrity()
                for tc in tool_history:
                    tc_issues = ti.check_after_plugin(
                        tc.get("tool", ""), tc.get("args", {}), tc.get("result", "")
                    )
                    integrity_issues.extend(tc_issues)
            except Exception as e:
                log_exception(e, "Failed to run tool integrity check")

            all_hallucination_issues = (
                final_fabrication_issues + final_claim_issues + hedging_issues + integrity_issues
            )

            # If hallucinations detected in final response, try to get a corrected response
            if all_hallucination_issues and i < max_iterations - 1:
                logger.info(
                    "Final hallucination check found %d issues at iteration %d, retrying",
                    len(all_hallucination_issues),
                    i + 1,
                )
                guidance_items = []
                if any("user mentioned" in issue for issue in all_hallucination_issues):
                    guidance_items.append(
                        "Do NOT claim the user mentioned specific files unless they literally said the file names. "
                        "If you're unsure what files exist, use glob_files or grep_content to search."
                    )
                if any("Lists specific files" in issue for issue in all_hallucination_issues):
                    guidance_items.append(
                        "Use glob_files or file_search tool to discover files before listing them."
                    )
                if any("Referenced file" in issue for issue in all_hallucination_issues):
                    guidance_items.append(
                        "Use read_file or glob_files to verify files exist before referencing them."
                    )
                guidance_text = (
                    " ".join(guidance_items) if guidance_items else "Fix hallucination issues."
                )

                messages.append(
                    {
                        "role": "assistant",
                        "content": content,
                    }
                )
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "STOP. Your response contains hallucinated claims:\n"
                            + "\n".join(f"- {issue}" for issue in all_hallucination_issues[:5])
                            + f"\n\n{guidance_text}\n"
                            "Revise your response to only state what you actually verified with tools."
                        ),
                    }
                )
                continue

            # ---- Confidence scoring ----
            confidence = _compute_confidence_score(
                content or "",
                tool_history,
                files_created,
                fabrication_issues=final_fabrication_issues,
                code_issues=[],
                claim_issues=final_claim_issues,
            )
            logger.debug(
                "Hallucination verification: confidence=%d, fabrication=%d, claims=%d",
                confidence,
                len(final_fabrication_issues),
                len(final_claim_issues),
            )

            # Determine if response should be flagged or rejected
            has_hallucinations = bool(all_hallucination_issues)
            low_confidence = confidence < 50

            # Build warning message for user if hallucinations detected
            hallucination_warning = ""
            if has_hallucinations:
                warning_lines = [
                    "WARNING: This response may contain hallucinated claims:",
                ]
                for issue in all_hallucination_issues[:5]:
                    warning_lines.append(f"  - {issue}")
                warning_lines.append("Treat these claims with skepticism. Verify independently.")
                hallucination_warning = "\n".join(warning_lines)

            # If hallucinations detected on final iteration, strip them from output
            if has_hallucinations and content:
                # Remove sentences that contain hallucinated claims
                cleaned_content = _strip_hallucinated_sentences(content, all_hallucination_issues)
                if cleaned_content.strip():
                    content = cleaned_content

            return {
                "success": not (low_confidence and has_hallucinations),
                "output": content,
                "tool_calls": tool_history,
                "iterations": i + 1,
                "tokens": {
                    "input": total_tokens_in,
                    "output": total_tokens_out,
                    "cache_hit": total_cache_hit,
                    "cache_miss": total_cache_miss,
                },
                "elapsed": time.time() - start_time,
                "files_created": files_created,
                "task_plan": task_plan.to_dict() if task_plan else None,
                "quality_issues": quality_issues,
                "confidence": confidence,
                "hallucination_issues": all_hallucination_issues,
                "hallucination_warning": hallucination_warning,
            }

        # ---- Execute native tool calls and return results as role:tool messages ----
        tools_used_in_iteration = []

        # Tools safe to run in parallel (read-only, no side effects)
        _PARALLEL_SAFE = {
            "grep",
            "glob",
            "read_file",
            "list_directory",
            "search_files",
            "count_lines",
        }

        def _exec_single_tool(tc: dict) -> dict:
            """Execute a single tool call and return the result message."""
            tc_id = tc["id"]
            name = tc["name"]
            args = tc["args"]
            call_key = f"{name}:{json.dumps(args, sort_keys=True)}"

            if call_key in failed_calls:
                return {
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "name": name,
                    "content": f"[SKIP] Already failed: {name} with same args",
                }

            if name not in tools:
                avail = ", ".join(sorted(tools.keys()))
                return {
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "name": name,
                    "content": f"Unknown tool '{name}'. Available: {avail}",
                }

            from sago.permissions import RiskLevel, get_permission_manager

            pm = get_permission_manager()
            risk = pm.get_risk_level(name)
            allowed, reason = pm.check_permission(name, args, session_id=session_id)

            if not allowed:
                if on_request_input and risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                    user_approval = on_request_input(
                        f"Allow tool '{name}'? (risk: {risk.value}) [y/N]: "
                    )
                    if user_approval and user_approval.strip().lower() in (
                        "y",
                        "yes",
                        "allow",
                        "approve",
                    ):
                        pm.approve_tool(name, session_id=session_id)
                        allowed = True

                if not allowed:
                    return {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "name": name,
                        "content": f"Permission denied: {name} requires approval"
                        if risk in (RiskLevel.HIGH, RiskLevel.CRITICAL)
                        else f"Permission denied: {reason}",
                    }

            tool_call_counts[name] = tool_call_counts.get(name, 0) + 1

            recent_calls = [
                f"{c['tool']}:{json.dumps(c['args'], sort_keys=True)[:50]}"
                for c in tool_history[-5:]
            ]
            circular_thresh = int(
                os.environ.get(
                    "SAGO_CIRCULAR_DETECTION_THRESHOLD",
                    str(_get_executor_config().circular_detection_threshold),
                )
            )
            if len(recent_calls) >= circular_thresh:
                unique_recent = set(recent_calls[-circular_thresh:])
                if len(unique_recent) == 1:
                    return {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "name": name,
                        "content": f"[HINT] You've called {name} with similar args {circular_thresh} times in a row.",
                    }

            # --- Plugin: hook_tool_call (intercept/modify args before execution) ---
            try:
                from sago.plugins.base import get_plugin_manager

                args = get_plugin_manager().hook_tool_call(name, args)
            except Exception as e:
                log_exception(e, "Plugin hook_tool_call failed")

            if on_tool_call:
                on_tool_call(name, args)
            logger.debug("Tool call: %s, args=%s", name, {k: str(v)[:100] for k, v in args.items()})

            validation_error = _validate_tool_args(name, args)
            if validation_error:
                failed_calls.add(call_key)
                return {
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "name": name,
                    "content": validation_error,
                }

            # --- Execute tool with full error resilience ---
            tool_start_time = time.time()
            try:
                tool_instance = tools[name]()
                result = tool_instance.run(**args)
                result_str = str(result)
            except TypeError as te:
                if "NoneType" in str(te):
                    logger.error("Tool '%s' returned None instance: %s", name, te)
                    result_str = f"Error: Tool '{name}' failed to instantiate."
                else:
                    logger.error("Tool '%s' type error: %s", name, te)
                    result_str = f"Error executing {name}: {te}"
            except Exception as tool_err:
                logger.error("Tool '%s' execution failed: %s", name, tool_err)
                result_str = f"Error executing {name}: {tool_err}"

            is_error = result_str.lower().startswith("error") or "traceback" in result_str.lower()
            if is_error:
                failed_calls.add(call_key)
            # --- Simple analyze: directory hint (read_file on dir → glob_files) ---
            if is_error and name in ("read_file", "code_analyzer"):
                low = result_str.lower()
                if "not a file" in low or "is a directory" in low:
                    hint = "\n[HINT] read_file on directory → use glob_files (pattern='**/*', path='<dir>') to list files, then read_file/code_analyzer individual files. Do NOT retry read_file on same directory."
                    result_str += hint
                    # Surface as thinking so UI shows learning
                    if on_thinking:
                        try:
                            on_thinking(
                                "Hint: read_file failed on directory — use glob_files instead"
                            )
                        except Exception:
                            pass
            logger.debug("Tool result: %s, success=%s, len=%d", name, not is_error, len(result_str))

            if name in ("write_file", "edit_file", "file_operations") and not is_error:
                fp = (
                    args.get("file_path", "") or args.get("target_file", "") or args.get("path", "")
                )
                if fp and fp not in files_created:
                    files_created.append(fp)
                try:
                    from sago.engine.verifier import get_continuous_verifier

                    get_continuous_verifier().enqueue_files([fp] if fp else [])
                except Exception as e:
                    log_exception(e, "Failed to enqueue file for continuous verification")
                if fp and any(
                    fp.endswith(ext)
                    for ext in (
                        ".py",
                        ".js",
                        ".ts",
                        ".tsx",
                        ".jsx",
                        ".go",
                        ".rs",
                        ".java",
                        ".c",
                        ".cpp",
                    )
                ):
                    try:
                        from sago.engine.verifier import ProjectVerifier

                        report = ProjectVerifier(root_dir=os.getcwd()).verify_files([fp])
                        if not report.passed and report.issues:
                            feedback = report.to_prompt_feedback()
                            result_str = (result_str + "\n\n" + feedback)[:4000]
                    except Exception as e:
                        log_exception(e, "Failed to run project verification on modified file")

            tool_history.append(
                {"tool": name, "args": args, "result": result_str[:2000], "success": not is_error}
            )
            tools_used_in_iteration.append(name)

            # Record TOOL_DISPATCH event for dev tracer (event graph visibility)
            try:
                from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer

                tool_dur_ms = (time.time() - tool_start_time) * 1000
                get_dev_tracer().record(
                    event_type=TraceEventType.TOOL_DISPATCH,
                    source=f"agent.{agent_role}",
                    action=f"run({name})",
                    data={"tool_name": name, "arguments": args, "result_preview": result_str[:300]},
                    status="FAILED" if is_error else "OK",
                    duration_ms=tool_dur_ms,
                )
            except Exception as e:
                log_exception(e, "Failed to record TOOL_DISPATCH event")

            if tool_usage_store is not None:
                try:
                    tool_usage_store.log(
                        tool_name=name,
                        arguments=args,
                        result=result_str[:1000],
                        success=not is_error,
                        agent=agent_role,
                    )
                except Exception as e:
                    log_exception(e, "Failed to log tool usage to store")

            # Always fire on_tool_result callback (not gated behind tool_usage_store)
            if on_tool_result:
                on_tool_result(name, args, result_str, not is_error)

            # --- Plugin: hook_tool_result (transform result after execution) ---
            try:
                from sago.plugins.base import get_plugin_manager

                result_str = str(get_plugin_manager().hook_tool_result(name, result_str))
            except Exception as e:
                log_exception(e, "Plugin hook_tool_result failed")

            # --- Tool result integrity check (plugin tamper detection) ---
            try:
                from sago.engine.hallucination_verifier import get_tool_integrity

                integrity = get_tool_integrity()
                integrity.record_original(name, args, result_str)
            except Exception as e:
                log_exception(e, "Failed to record tool result for integrity check")

            # Proactive context protection: clip excessively large tool outputs to prevent context blowup
            MAX_TOOL_RESULT_CHARS = 12000
            if len(result_str) > MAX_TOOL_RESULT_CHARS:
                lines = result_str.splitlines()
                if len(lines) > 100:
                    head = "\n".join(lines[:60])
                    tail = "\n".join(lines[-30:])
                    omitted = len(lines) - 90
                    result_str = (
                        f"{head}\n\n[... {omitted} lines truncated ({len(result_str):,} total chars) "
                        f"— use specific offset/limit or pattern search to view remaining parts ...]\n\n{tail}"
                    )
                else:
                    result_str = (
                        result_str[:8000]
                        + f"\n\n[... output truncated from {len(result_str):,} chars to protect context window ...]\n\n"
                        + result_str[-3000:]
                    )

            content = (
                f"[ERROR] {name}:\n{result_str}\nTry a different approach."
                if is_error
                else result_str
            )
            return {"role": "tool", "tool_call_id": tc_id, "name": name, "content": content}

        # Group tool calls: parallel-safe tools run concurrently, others run sequentially
        i = 0
        while i < len(native_tool_calls):
            tc = native_tool_calls[i]
            if tc["name"] in _PARALLEL_SAFE:
                # Collect batch of parallel-safe calls
                batch = []
                while i < len(native_tool_calls) and native_tool_calls[i]["name"] in _PARALLEL_SAFE:
                    batch.append(native_tool_calls[i])
                    i += 1

                if len(batch) == 1:
                    messages.append(_exec_single_tool(batch[0]))
                else:
                    # Execute parallel batch
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor(
                        max_workers=min(len(batch), 6)
                    ) as pool:
                        futures = {pool.submit(_exec_single_tool, tc): tc for tc in batch}
                        for future in concurrent.futures.as_completed(futures):
                            messages.append(future.result())
            else:
                messages.append(_exec_single_tool(tc))
                i += 1

        # --- Simple analyze caps & early exit (tiny codebase guard) ---
        if _is_simple_analyze_flag:
            # Hard cap 15 tool calls for simple analyze (spec)
            if len(tool_history) >= _SIMPLE_ANALYZE_CAPS["max_tool_calls"]:
                logger.info(
                    "Simple analyze tool budget exhausted (%d calls) — forcing summary",
                    len(tool_history),
                )
                messages.append(
                    {
                        "role": "user",
                        "content": "TOOL BUDGET EXHAUSTED (15 calls for simple analyze). Summarize now with file list (glob_files) and code_analyzer results. Do NOT call more tools.",
                    }
                )
            else:
                # Early exit: glob_files succeeded and code_analyzer covered all files → stop probing
                glob_success = [
                    c for c in tool_history if c["tool"] == "glob_files" and c["success"]
                ]
                analyzer_success = [
                    c for c in tool_history if c["tool"] == "code_analyzer" and c["success"]
                ]
                if glob_success and analyzer_success:
                    expected = _file_count_probe or 3
                    # If we have analyzer successes covering expected file count, nudge to summarize
                    if len(analyzer_success) >= min(expected, 3) and len(analyzer_success) >= 2:
                        # Avoid repeated nudge — only once
                        already_nudged = any(
                            "early exit" in str(m.get("content", "")).lower()
                            or "fully analyzed via glob_files" in str(m.get("content", ""))
                            for m in messages[-3:]
                        )
                        if not already_nudged:
                            logger.info(
                                "Simple analyze early exit: %d files via glob, %d analyzer successes",
                                expected,
                                len(analyzer_success),
                            )
                            messages.append(
                                {
                                    "role": "user",
                                    "content": "Early exit: tiny codebase fully covered via glob_files + code_analyzer. Summarize now — do NOT run further execute_shell probes.",
                                }
                            )

        # Update task plan progress based on actual work done
        if task_plan:
            try:
                from sago.tasks import TaskStatus, get_task_manager

                tm = get_task_manager()

                if current_todo_index < len(task_plan.todos):
                    current_todo = task_plan.todos[current_todo_index]

                    # Mark as in_progress if pending
                    if current_todo.status == TaskStatus.PENDING:
                        tm.start_todo(task_plan.id, current_todo.id)
                        if on_todo_update:
                            on_todo_update(task_plan, current_todo_index, "started")

                    # Track tools used for this todo
                    if current_todo.id not in todo_tool_counts:
                        todo_tool_counts[current_todo.id] = 0
                    todo_tool_counts[current_todo.id] += len(tools_used_in_iteration)

                    # Check if todo needs confirmation before proceeding
                    if (
                        current_todo.requires_confirmation
                        and current_todo.status == TaskStatus.IN_PROGRESS
                    ):
                        # Ask user for confirmation
                        if on_request_input:
                            question = (
                                current_todo.confirmation_message
                                or f"Confirm step: {current_todo.description}"
                            )
                            user_response = on_request_input(question)
                            if user_response and user_response.lower() in (
                                "no",
                                "deny",
                                "skip",
                                "n",
                            ):
                                tm.skip_todo(task_plan.id, current_todo.id)
                                if on_todo_update:
                                    on_todo_update(task_plan, current_todo_index, "skipped")
                                current_todo_index += 1
                                continue
                            else:
                                tm.provide_input(
                                    plan_id=task_plan.id,
                                    todo_id=current_todo.id,
                                    user_input=user_response,
                                )

                    # Auto-complete todo after sufficient work based on configurable thresholds
                    successful_tools = [
                        t["tool"]
                        for t in tool_history
                        if t.get("success") and t["tool"] in tools_used_in_iteration
                    ]
                    tools_for_this_todo = todo_tool_counts.get(current_todo.id, 0)
                    cfg = _get_executor_config()
                    min_tools = int(
                        os.environ.get(
                            "SAGO_AUTOCOMPLETE_MIN_TOOLS", str(cfg.auto_complete_min_tools)
                        )
                    )
                    min_success = int(
                        os.environ.get(
                            "SAGO_AUTOCOMPLETE_MIN_SUCCESS", str(cfg.auto_complete_min_success)
                        )
                    )
                    min_iters = int(
                        os.environ.get(
                            "SAGO_AUTOCOMPLETE_MIN_ITERATIONS",
                            str(cfg.auto_complete_min_iterations),
                        )
                    )

                    if (
                        tools_for_this_todo >= min_tools and len(successful_tools) >= min_success
                    ) or (i > 2 and tools_for_this_todo >= min_iters):
                        tm.complete_todo(
                            task_plan.id,
                            current_todo.id,
                            result=f"Completed: {', '.join(successful_tools[:3])}",
                        )
                        if on_todo_update:
                            on_todo_update(task_plan, current_todo_index, "completed")
                        current_todo_index += 1

                        # If more todos, tell LLM about next step
                        if current_todo_index < len(task_plan.todos):
                            next_todo = task_plan.todos[current_todo_index]
                            tm.start_todo(task_plan.id, next_todo.id)
                            if on_todo_update:
                                on_todo_update(task_plan, current_todo_index, "started")
                            messages.append(
                                {
                                    "role": "user",
                                    "content": (
                                        f"[PROGRESS] Step completed. Next step: {next_todo.description}\n"
                                        f"Execute this step now."
                                    ),
                                }
                            )
                        else:
                            messages.append(
                                {
                                    "role": "user",
                                    "content": "[PROGRESS] All steps completed. Provide final summary.",
                                }
                            )
            except Exception as e:
                log_exception(e, "Failed to update task plan progress")

        # ── Self-realization anti-loop brake ──
        # This is the "thinking and reasoning" guard the user asked for:
        # it fires when the agent repeats the same tool/args or same reasoning
        # and forces a brief reflection instead of looping. Always enabled.
        loop_guidance = _detect_overthinking_loop(tool_history, messages, i)
        if loop_guidance and i < max_iterations - 1:
            logger.info("Self-realization triggered at iteration %d", i + 1)
            if on_thinking:
                on_thinking("Self-check: possible loop detected — reflecting...")
            messages.append({"role": "user", "content": loop_guidance})
            # Also surface to TUI as a thinking event so user sees the brake
            try:
                from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer

                get_dev_tracer().record(
                    event_type=TraceEventType.LLM_THINKING,
                    source=f"agent.{agent_role}",
                    action="self_realization",
                    data={"iteration": i + 1, "guidance": loop_guidance[:300]},
                )
            except Exception:
                pass
            continue

        # Auto-compact if messages are getting too large — 175k context guard
        # Triggers at 175k tokens (~700k chars) to prevent bloat/hallucination.
        # Shows compact summary to user when it happens (manual /compact also works).
        if len(messages) > 30:
            # Check actual token estimate, not just message count
            est_tokens = sum(len(str(m.get("content", "")) or "") // 4 for m in messages)
            if est_tokens > 175000 or len(messages) > 50:
                old_len = len(messages)
                old_tokens = est_tokens
                messages = _compact_messages_if_needed(messages, max_tokens=80000)
                # Show compact summary to user so they see what was summarized
                try:
                    compact_info = f"📦 Auto-compact: {old_len} msgs (~{old_tokens:,} tokens) → {len(messages)} msgs | 175k guard tripped"
                    if on_thinking:
                        on_thinking(compact_info)
                    # Also add as system message so it's visible in chat
                    messages.append(
                        {
                            "role": "system",
                            "content": f"[COMPACTED] {compact_info}. Recent context preserved, older history summarized.",
                        }
                    )
                except Exception:
                    pass

        logger.debug(
            "Iteration %d complete: tools_used=%s, files_created=%d, messages=%d",
            i + 1,
            tools_used_in_iteration,
            len(files_created),
            len(messages),
        )

    # Mark final todo as complete if plan exists
    if task_plan:
        try:
            from sago.tasks import TaskStatus, get_task_manager

            tm = get_task_manager()
            # Complete any remaining todos
            for idx in range(current_todo_index, len(task_plan.todos)):
                todo = task_plan.todos[idx]
                if todo.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS):
                    tm.complete_todo(task_plan.id, todo.id, result="Task completed")
            if on_todo_update:
                on_todo_update(task_plan, current_todo_index, "completed")
        except Exception as e:
            log_exception(e, "Failed to mark remaining todos as complete")

        # === POST-EXECUTION: Test → Fix → Retry loop ===
    if files_created and on_thinking:
        on_thinking("Running tests and checking for errors...")

    test_fix_attempts = 0
    max_test_fix_attempts = 3

    while test_fix_attempts < max_test_fix_attempts:
        # Auto-detect and install dependencies if needed
        _auto_install_deps(files_created, on_thinking)

        # Try to run tests if test files exist
        test_result = _run_tests_if_exist(files_created, tools)
        if test_result is None:
            break  # No tests found, skip

        test_passed, test_output = test_result
        if test_passed:
            if on_thinking:
                on_thinking("All tests passed!")
            break

        # Tests failed - try to fix
        test_fix_attempts += 1
        if test_fix_attempts >= max_test_fix_attempts:
            if on_thinking:
                on_thinking(f"Tests still failing after {max_test_fix_attempts} attempts")
            break

        if on_thinking:
            on_thinking(
                f"Tests failed (attempt {test_fix_attempts}/{max_test_fix_attempts}), fixing..."
            )

        # Feed test errors back to LLM for fixing using native function calling
        try:
            fix_messages = messages + [
                {
                    "role": "user",
                    "content": (
                        f"The tests are failing. Fix the failing tests.\n\n"
                        f"Test output:\n{test_output[:3000]}\n\n"
                        f"Files you created: {', '.join(files_created)}\n"
                        f"Fix the issues and make the tests pass. Use edit_file or write_file to fix."
                    ),
                },
            ]
            fix_api_kwargs: dict[str, Any] = {
                "model": model,
                "messages": fix_messages,
                "max_tokens": max_tokens,
                "temperature": 0.3,
            }
            if openai_tools:
                fix_api_kwargs["tools"] = openai_tools
                fix_api_kwargs["tool_choice"] = "auto"

            fix_response = client.chat.completions.create(**fix_api_kwargs)
            fix_message = fix_response.choices[0].message
            fix_content = fix_message.content or ""
            if not fix_content and hasattr(fix_message, "reasoning") and fix_message.reasoning:
                fix_content = fix_message.reasoning or ""

            # Run hallucination detection on fix response
            if fix_content:
                fix_fab_issues = _detect_code_hallucinations(fix_content, tool_history)
                fix_claim_issues = _verify_claims_against_history(fix_content, tool_history)
                if fix_fab_issues or fix_claim_issues:
                    # Add correction prompt if fix response contains hallucinations
                    messages.append(
                        {
                            "role": "assistant",
                            "content": fix_content,
                        }
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "STOP. Your fix response contains hallucinated claims:\n"
                                + "\n".join(
                                    f"- {issue}"
                                    for issue in (fix_fab_issues + fix_claim_issues)[:3]
                                )
                                + "\n\nUse actual tools (read_file, edit_file, execute_shell) to fix the tests. "
                                "Do NOT claim tests pass without running them."
                            ),
                        }
                    )
                    continue

            if fix_message.tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": fix_content or None,
                        "tool_calls": [
                            {
                                "id": ftc.id,
                                "type": "function",
                                "function": {
                                    "name": ftc.function.name,
                                    "arguments": ftc.function.arguments,
                                },
                            }
                            for ftc in fix_message.tool_calls
                        ],
                    }
                )
                for ftc in fix_message.tool_calls:
                    try:
                        fix_args = (
                            json.loads(ftc.function.arguments) if ftc.function.arguments else {}
                        )
                    except json.JSONDecodeError:
                        fix_args = {}
                    fix_name = ftc.function.name
                    fix_call_key = f"{fix_name}:{json.dumps(fix_args, sort_keys=True)}"
                    if fix_call_key in failed_calls:
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": ftc.id,
                                "content": f"[SKIP] Already failed: {fix_name} with same args",
                            }
                        )
                        continue
                    if fix_name in tools:
                        tool_instance = tools[fix_name]()
                        result = tool_instance.run(**fix_args)
                        result_str = str(result)
                        is_error_result = (
                            result_str.lower().startswith("error")
                            or "traceback" in result_str.lower()
                        )
                        if is_error_result:
                            failed_calls.add(fix_call_key)
                        tool_history.append(
                            {
                                "tool": fix_name,
                                "args": fix_args,
                                "result": result_str[:2000],
                                "success": not is_error_result,
                            }
                        )
                        if fix_name == "write_file" and not is_error_result:
                            fp = fix_args.get("file_path", "")
                            if fp and fp not in files_created:
                                files_created.append(fp)
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": ftc.id,
                                "content": result_str,
                            }
                        )
            elif fix_content:
                messages.append({"role": "assistant", "content": fix_content})
        except Exception as e:
            if on_thinking:
                on_thinking(f"Fix attempt error: {type(e).__name__}: {e}")
            break

    # Record learning from this execution (ONLY if no hallucinations and confidence is high)
    try:
        from sago.learning import get_learning_store

        ls = get_learning_store()
        task_type = _detect_task_type(task)

        # Only record success if the response was hallucination-free and confident
        final_confidence = _compute_confidence_score(
            content or "",
            tool_history,
            files_created,
            fabrication_issues=[],
            code_issues=[],
            claim_issues=[],
        )
        final_hallucination_check = _detect_code_hallucinations(content or "", tool_history)
        final_claim_check = _verify_claims_against_history(content or "", tool_history)
        has_hallucinations = bool(final_hallucination_check or final_claim_check)

        if final_confidence >= 70 and not has_hallucinations:
            # Record success
            successful_tools = [t["tool"] for t in tool_history if t.get("success")]
            if successful_tools:
                ls.record_success(
                    task_type, successful_tools, f"Used {', '.join(set(successful_tools[:5]))}"
                )

            # Record tool effectiveness
            for tool_record in tool_history:
                ls.record_tool_effectiveness(tool_record["tool"], tool_record.get("success", False))

            # Record language patterns if files were created
            if files_created and project_context["languages"]:
                for lang in project_context["languages"]:
                    ls.record_language_pattern(
                        lang, "file_creation", f"Created {len(files_created)} files"
                    )

            # Record error fixes if test fixes were applied
            if test_fix_attempts > 0:
                ls.record_success(
                    "test_fix",
                    ["edit_file", "write_file"],
                    f"Fixed tests in {test_fix_attempts} attempts",
                )
    except Exception as e:
        log_exception(e, "Failed to record learning from execution")

    # --- Plugin: hook_response (transform final response at end of execution) ---
    try:
        from sago.plugins.base import get_plugin_manager

        content = get_plugin_manager().hook_response(content, {"task": task, "model": model})
    except Exception as e:
        log_exception(e, "Plugin hook_response failed on final response")

    # Get change summary
    change_summary = None
    try:
        from sago.memory.change_tracker import get_change_tracker

        tracker = get_change_tracker()
        change_summary = tracker.get_summary()
    except Exception as e:
        log_exception(e, "Failed to get change summary from tracker")

    # Record token usage
    if total_tokens_in > 0 or total_tokens_out > 0:
        try:
            from sago.tracking.token_tracker import get_token_tracker

            tracker = get_token_tracker()
            tracker.record(
                provider="openai",
                model=model,
                input_tokens=total_tokens_in,
                output_tokens=total_tokens_out,
                latency_ms=(time.time() - start_time) * 1000,
                metadata={"session_id": "simple_executor"},
            )
            tracker.save()
        except Exception as e:
            log_exception(e, "Failed to save token tracker")

    if tool_usage_store is not None:
        try:
            tool_usage_store.flush()
        except Exception as e:
            log_exception(e, "Failed to flush tool usage store")

    logger.info(
        "execute_agent_task complete: iterations=%d, tokens_in=%d, tokens_out=%d, files=%d, elapsed=%.1fs",
        max_iterations + test_fix_attempts,
        total_tokens_in,
        total_tokens_out,
        len(files_created),
        time.time() - start_time,
    )

    return {
        "success": True,
        "output": content,
        "tool_calls": tool_history,
        "iterations": max_iterations + test_fix_attempts,
        "tokens": {
            "input": total_tokens_in,
            "output": total_tokens_out,
            "cache_hit": total_cache_hit,
            "cache_miss": total_cache_miss,
        },
        "elapsed": time.time() - start_time,
        "files_created": files_created,
        "task_plan": task_plan.to_dict() if task_plan else None,
        "test_fixes_applied": test_fix_attempts,
        "change_summary": change_summary,
        "confidence": _compute_confidence_score(
            content or "",
            tool_history,
            files_created,
            fabrication_issues=[],
            code_issues=[],
            claim_issues=[],
        ),
    }
