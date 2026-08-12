"""Smart Executor - Handles complex multi-step tasks using native function calling."""

from __future__ import annotations

import importlib
import json
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from openai import OpenAI

from sago.tools.base import BaseTool

# Auto-discover all tools
_TOOL_CLASSES: dict[str, type[BaseTool]] = {}
_TOOL_DESCRIPTIONS = ""


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
    """Convert tool classes to OpenAI function calling tool definitions.

    Returns a list of tool dicts in the format:
        [{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}]
    """
    openai_tools: list[dict[str, Any]] = []

    for name, cls in sorted(tool_classes.items()):
        description = cls.description or name
        parameters: dict[str, Any] = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        if cls.args_model:
            fields = cls.args_model.model_fields
            for field_name, field_info in fields.items():
                prop = _pydantic_field_to_schema(field_info)
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
    task_lower = task.lower()
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
        except Exception:
            pass


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


def _detect_project_context(cwd: str | None = None) -> dict[str, Any]:
    """Detect existing project language, framework, and structure from files.

    Returns a dict with detected info that helps the LLM understand the project.
    """
    import subprocess

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
        except Exception:
            pass

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
        except Exception:
            pass

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
    except Exception:
        pass

    return context


def _generate_plan_with_llm(
    task: str,
    client: OpenAI,
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
        # Extract JSON array from response
        match = re.search(r"\[.*\]", content, re.DOTALL)
        if match:
            steps = json.loads(match.group())
            if isinstance(steps, list) and all(isinstance(s, str) for s in steps):
                return steps
    except Exception:
        pass
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
        return _TOOL_CLASSES

    import logging

    _log = logging.getLogger("sago.tools")

    tools_dir = Path(__file__).parent.parent / "tools"
    for py_file in tools_dir.rglob("*.py"):
        if py_file.name.startswith("_") or py_file.name == "base.py":
            continue
        try:
            parts = py_file.relative_to(tools_dir).with_suffix("").as_posix().split("/")
            mod = importlib.import_module(f"sago.tools.{'.'.join(parts)}")
            for attr in dir(mod):
                obj = getattr(mod, attr)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, BaseTool)
                    and obj is not BaseTool
                    and getattr(obj, "name", None)
                ):
                    _TOOL_CLASSES[obj.name] = obj
        except Exception as e:
            _log.debug(f"Failed to load tool from {py_file.name}: {e}")

    lines = []
    for name, cls in sorted(_TOOL_CLASSES.items()):
        desc = cls.description or name
        args = ""
        if cls.args_model:
            fields = cls.args_model.model_fields
            parts = []
            for fn, fi in fields.items():
                req = "REQ" if fi.is_required() else f"={fi.default}"
                parts.append(f"{fn}({req})")
            args = ", ".join(parts)
        lines.append(f"- {name}({args}): {desc}")
    _TOOL_DESCRIPTIONS = "\n".join(lines)
    return _TOOL_CLASSES


def _get_context(cwd: str | None = None) -> str:
    work_dir = Path(cwd) if cwd else Path.cwd()
    lines = [f"Working directory: {work_dir}"]

    for name in [
        "README.md",
        "readme.md",
        "pyproject.toml",
        "package.json",
        "Cargo.toml",
        "go.mod",
    ]:
        p = work_dir / name
        if p.exists():
            try:
                lines.append(f"\n--- {name} ---\n{p.read_text('utf-8')[:3000]}")
            except Exception:
                pass

    skip = {".git", "node_modules", "__pycache__", ".venv", "venv", "env", ".tox", "dist", "build"}
    files = []
    dirs = []
    try:
        for item in sorted(work_dir.iterdir()):
            if item.name.startswith(".") or item.name in skip:
                continue
            if item.is_dir():
                try:
                    count = sum(1 for _ in item.iterdir())
                    dirs.append(f"  {item.name}/ ({count} items)")
                except Exception:
                    dirs.append(f"  {item.name}/")
            else:
                try:
                    s = item.stat().st_size
                    files.append(
                        f"  {item.name} ({s}B)" if s < 100_000 else f"  {item.name} ({s // 1024}KB)"
                    )
                except Exception:
                    files.append(f"  {item.name}")
    except PermissionError:
        pass
    if dirs:
        lines.append(f"\nDirectories ({work_dir.name}/):")
        lines.extend(dirs[:30])
    if files:
        lines.append(f"\nFiles ({work_dir.name}/):")
        lines.extend(files[:50])

    try:
        import subprocess

        r = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(work_dir),
        )
        if r.returncode == 0 and r.stdout.strip():
            lines.append(f"\nGit changes:\n{r.stdout.strip()[:800]}")
    except Exception:
        pass

    return "\n".join(lines)


# Task-specific system prompts (tools are now passed via API, not in text)
PROMPTS = {
    "create": """You are {agent_role}. The user wants you to CREATE something (file, project, feature).

{project_ctx}

=== CREATION STRATEGY ===
- Start by understanding what exists (glob_files, read_file)
- Create files ONE AT A TIME using write_file
- After each file, verify it was created correctly
- For projects: create structure first, then implement
- Always verify your work (run tests, check syntax)

=== CRITICAL RULES ===
- NEVER fabricate or hallucinate file contents. If you haven't read a file, use read_file first.
- NEVER claim to have done something you haven't actually done.
- ALWAYS use tools to interact with the filesystem. Do not guess or make up results.
- If a tool call fails, report the error honestly. Do not pretend it succeeded.
- When writing files, put the ACTUAL CODE in the content field. No markdown, no backticks, just the raw code.
- NEVER say "I cannot" or "I am unable" — you have tools, USE THEM.""",
    "fix": """You are {agent_role}. The user wants you to FIX something (bug, error, issue).

{project_ctx}

=== FIX STRATEGY ===
- Read the error message carefully
- Find the file and line causing the issue
- Understand the root cause before fixing
- Make minimal changes to fix
- Test that the fix works

=== CRITICAL RULES ===
- NEVER fabricate or hallucinate file contents. If you haven't read a file, use read_file first.
- NEVER claim to have done something you haven't actually done.
- ALWAYS use tools to interact with the filesystem. Do not guess or make up results.
- If a tool call fails, report the error honestly. Do not pretend it succeeded.
- NEVER say "I cannot" or "I am unable" — you have tools, USE THEM.""",
    "analyze": """You are {agent_role}. The user wants you to ANALYZE something (code, project, issue).

{project_ctx}

=== ANALYSIS STRATEGY ===
- Be thorough but focused
- Read multiple files to understand the full picture
- Look for patterns, issues, improvements
- Provide actionable recommendations

=== CRITICAL RULES ===
- NEVER fabricate or hallucinate file contents. If you haven't read a file, use read_file first.
- NEVER claim to have done something you haven't actually done.
- ALWAYS use tools to interact with the filesystem. Do not guess or make up results.
- If a tool call fails, report the error honestly. Do not pretend it succeeded.
- NEVER say "I cannot" or "I am unable" — you have tools, USE THEM.""",
}


def _detect_task_type(task: str) -> str:
    task_lower = task.lower()
    create_words = [
        "create",
        "build",
        "write",
        "implement",
        "make",
        "generate",
        "setup",
        "set up",
        "add",
        "new",
    ]
    fix_words = [
        "fix",
        "debug",
        "repair",
        "resolve",
        "patch",
        "correct",
        "solve",
        "issue",
        "error",
        "bug",
        "broken",
    ]
    analyze_words = [
        "analyze",
        "review",
        "explain",
        "describe",
        "show",
        "list",
        "find",
        "search",
        "what",
        "how",
        "why",
    ]

    if any(w in task_lower for w in fix_words):
        return "fix"
    if any(w in task_lower for w in create_words):
        return "create"
    if any(w in task_lower for w in analyze_words):
        return "analyze"
    return "create"


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
    except Exception:
        pass
    return None


def execute_agent_task(
    task: str,
    agent_role: str = "Sago Orchestrator",
    system_prompt: str = "",
    model: str = "openrouter/free",
    api_key: str = "",
    base_url: str | None = None,
    max_tokens: int = 50000,
    max_iterations: int = 30,
    cwd: str | None = None,
    on_tool_call: Callable | None = None,
    on_tool_result: Callable | None = None,
    on_thinking: Callable | None = None,
    on_todo_created: Callable | None = None,
    on_todo_update: Callable | None = None,
    on_request_input: Callable | None = None,
    pause_event: Any = None,
) -> dict[str, Any]:
    """Execute a task with LLM, tools, and todo tracking.

    Args:
        on_request_input: Called when a todo needs user input. Signature: (question: str) -> str
        pause_event: threading.Event to pause/resume execution. If provided and set, executor pauses.
    """
    tools = _discover_tools()

    # Auto-detect base_url from model/provider if not provided
    if base_url is None:
        if model.startswith("gemini"):
            base_url = None  # Will be handled by google-genai SDK
        elif model.startswith("gpt") or model.startswith("o1") or model.startswith("o3"):
            base_url = "https://api.openai.com/v1"
        else:
            base_url = "https://openrouter.ai/api/v1"

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=90.0, max_retries=2)
    start_time = time.time()

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

    # Load learning store for smart suggestions
    learning_suggestion = None
    try:
        from sago.learning import get_learning_store

        ls = get_learning_store()
        task_type = _detect_task_type(task)
        learning_suggestion = ls.suggest_approach(task_type, list(tools.keys()))
    except Exception:
        pass

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
        except Exception:
            task_plan = None

    # Load agent profile metadata
    profile = _load_agent_profile(agent_role)

    # Use profile metadata if available
    if profile:
        if not system_prompt:
            system_prompt = profile.get("system_prompt", "")
        if profile.get("model_preference"):
            model = profile["model_preference"]
        if profile.get("temperature"):
            pass  # temperature is used in API call below
        if profile.get("max_iterations") and max_iterations == 30:
            max_iterations = min(profile["max_iterations"], 50)
        # Filter tools to only those the agent knows about
        if profile.get("tools"):
            agent_tools = {t: tools[t] for t in profile["tools"] if t in tools}
            if agent_tools:
                tools = agent_tools

    # Auto-detect task type and use appropriate prompt
    if not system_prompt:
        task_type = _detect_task_type(task)
        template = PROMPTS.get(task_type, PROMPTS["create"])
        system_prompt = template.format(
            agent_role=agent_role,
            project_ctx=project_ctx,
        )

    # Add learning suggestion if available
    if learning_suggestion:
        system_prompt += (
            f"\n\n=== PAST SUCCESSFUL APPROACH ===\n"
            f"Based on past similar tasks, this approach worked:\n"
            f"{learning_suggestion}\n"
            f"Consider using a similar approach, but adapt to the current context."
        )

    # Add project context hints
    if project_context["frameworks"]:
        system_prompt += (
            f"\n\n=== EXISTING PROJECT DETECTED ===\n"
            f"This project uses: {', '.join(project_context['frameworks'])}\n"
            f"Match the existing style and conventions."
        )

    # Load project instructions (CLAUDE.md / .sago/instructions.md)
    try:
        from sago.memory.project_instructions import get_project_instructions

        pi = get_project_instructions(cwd)
        instructions_prompt = pi.get_for_prompt()
        if instructions_prompt:
            system_prompt += instructions_prompt
    except Exception:
        pass

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

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]

    # Build OpenAI function calling tool definitions
    openai_tools = _build_openai_tools(tools)

    content = ""

    def _compact_messages_if_needed(
        msgs: list[dict[str, Any]], max_tokens: int = 32000
    ) -> list[dict[str, Any]]:
        """Compact messages if total content exceeds token limit."""
        total_chars = sum(len(m.get("content", "")) for m in msgs)
        estimated_tokens = total_chars // 4
        if estimated_tokens <= max_tokens:
            return msgs
        try:
            from sago.memory.compaction import SessionCompactor

            compactor = SessionCompactor(max_context_tokens=max_tokens)
            compacted = compactor.build_context_window(msgs, max_tokens=max_tokens)
            return compacted
        except Exception:
            system_msgs = [m for m in msgs if m.get("role") == "system"]
            other_msgs = [m for m in msgs if m.get("role") != "system"]
            return system_msgs + other_msgs[-5:]

    for i in range(max_iterations):
        # Check if execution is paused (user input needed)
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

        if on_thinking:
            phase = "Planning" if i == 0 else "Working"
            todo_info = (
                f" | Step {current_todo_index + 1}/{len(task_plan.todos)}" if task_plan else ""
            )
            files_info = f" ({len(files_created)} files created)" if files_created else ""
            on_thinking(f"{phase}... (step {i + 1}/{max_iterations}{todo_info}{files_info})")

        try:
            temp = profile.get("temperature", 0.3) if profile else 0.3

            # Use Google native SDK for gemini models
            if model.startswith("gemini"):
                try:
                    from google import genai as google_genai
                    from google.genai import types as google_types

                    google_client = google_genai.Client(api_key=api_key)
                    sys_msg = ""
                    contents = []
                    for msg in messages:
                        if msg["role"] == "system":
                            sys_msg = msg["content"]
                        elif msg["role"] in ("user", "assistant"):
                            contents.append(msg["content"])
                    if not contents:
                        contents = ["Hello"]

                    # Convert OpenAI tools to Google format
                    google_tools = []
                    for tool in openai_tools:
                        func = tool["function"]
                        params = func.get("parameters", {})
                        properties = {
                            k: google_types.Schema(
                                type=google_types.Type.STRING,
                                description=v.get("description", ""),
                            )
                            for k, v in params.get("properties", {}).items()
                        }
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

                    response = google_client.models.generate_content(
                        model=model,
                        contents=contents,
                        config=google_config,
                    )

                    # Extract tool calls from Gemini response
                    gemini_tool_calls = []
                    content = response.text or ""
                    if response.candidates:
                        for part in response.candidates[0].content.parts:
                            if part.function_call:
                                gemini_tool_calls.append(
                                    {
                                        "name": part.function_call.name,
                                        "args": dict(part.function_call.args)
                                        if part.function_call.args
                                        else {},
                                    }
                                )

                    # If Gemini made tool calls, store them for processing
                    if gemini_tool_calls:
                        # Store as a special attribute on content for the loop below
                        # We'll process them after the API call
                        pass

                except ImportError:
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

                response = client.chat.completions.create(**api_kwargs)

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
                error_msg = f"Insufficient credits for model '{model}'. Add credits or use 'openrouter/free'."

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
        native_tool_calls: list[dict[str, Any]] = []
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

        # Append assistant message (with tool_calls if present)
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
        messages.append(assistant_msg)

        # If no tool calls at all, check for hallucination or completion
        if not native_tool_calls:
            # Detect fabrication (claims to have done things without tool calls)
            fabrication_phrases = [
                "the file contains",
                "the contents are",
                "i read the file",
                "the file has",
                "i can see that",
                "looking at the file",
                "the code shows",
                "i opened the file",
                "the file shows",
                "successfully created",
                "i saved the file",
                "the file was created",
                "i have created",
                "i've created",
                "done! the file",
            ]
            content_lower = content.lower() if content else ""
            is_fabrication = not tool_history and any(
                phrase in content_lower for phrase in fabrication_phrases
            )

            if is_fabrication and i < max_iterations - 1:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "STOP. You are fabricating results without calling tools. "
                            "You have NOT read any file. You have NOT created any file. "
                            "You MUST use a tool to interact with the system. "
                            "Do it NOW."
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
            return {
                "success": True,
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
            }

        # ---- Execute native tool calls and return results as role:tool messages ----
        tools_used_in_iteration = []

        for tc in native_tool_calls:
            tc_id = tc["id"]
            name = tc["name"]
            args = tc["args"]

            # Loop prevention
            call_key = f"{name}:{json.dumps(args, sort_keys=True)}"
            if call_key in failed_calls:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": f"[SKIP] Already failed: {name} with same args",
                    }
                )
                continue

            if name not in tools:
                avail = ", ".join(sorted(tools.keys()))
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": f"Unknown tool '{name}'. Available: {avail}",
                    }
                )
                continue

            # Check permissions before execution
            from sago.permissions import RiskLevel, get_permission_manager

            pm = get_permission_manager()
            risk = pm.get_risk_level(name)
            allowed, reason = pm.check_permission(name, args)

            if not allowed:
                if risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": f"Permission denied: {name} requires approval (risk: {risk.value})",
                        }
                    )
                else:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": f"Permission denied: {reason}",
                        }
                    )
                continue

            tool_call_counts[name] = tool_call_counts.get(name, 0) + 1

            # Detect circular behavior
            recent_calls = [
                f"{c['tool']}:{json.dumps(c['args'], sort_keys=True)[:50]}"
                for c in tool_history[-5:]
            ]
            if len(recent_calls) >= 3:
                unique_recent = set(recent_calls[-3:])
                if len(unique_recent) == 1:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": (
                                f"[HINT] You've called {name} with similar args 3 times in a row. "
                                f"If this isn't working, try a completely different approach or finish the task."
                            ),
                        }
                    )
                    continue

            if on_tool_call:
                on_tool_call(name, args)

            tool_instance = tools[name]()
            result = tool_instance.run(**args)
            result_str = str(result)

            is_error = result_str.lower().startswith("error") or "traceback" in result_str.lower()
            if is_error:
                failed_calls.add(call_key)

            # Track created files
            if name == "write_file" and not is_error:
                fp = args.get("file_path", "")
                if fp and fp not in files_created:
                    files_created.append(fp)

            tool_history.append(
                {
                    "tool": name,
                    "args": args,
                    "result": result_str[:2000],
                    "success": not is_error,
                }
            )

            tools_used_in_iteration.append(name)

            # Notify caller of tool result immediately
            if on_tool_result:
                on_tool_result(name, args, result_str, not is_error)

            # Send result back as role:tool message with tool_call_id
            if is_error:
                tool_result_content = f"[ERROR] {name}:\n{result_str}\nTry a different approach."
            else:
                tool_result_content = result_str

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": tool_result_content,
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

                    # Auto-complete todo after sufficient work (5+ successful tools or 4+ iterations on same todo)
                    successful_tools = [
                        t["tool"]
                        for t in tool_history
                        if t.get("success") and t["tool"] in tools_used_in_iteration
                    ]
                    tools_for_this_todo = todo_tool_counts.get(current_todo.id, 0)
                    if (tools_for_this_todo >= 5 and len(successful_tools) >= 3) or (
                        i > 2 and tools_for_this_todo >= 4
                    ):
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
            except Exception:
                pass

        # Auto-compact if messages are getting too large
        if len(messages) > 40:
            messages = _compact_messages_if_needed(messages, max_tokens=80000)

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
        except Exception:
            pass

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
                    if fix_name in tools:
                        tool_instance = tools[fix_name]()
                        result = tool_instance.run(**fix_args)
                        result_str = str(result)
                        is_error_result = result_str.lower().startswith("error")
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
        except Exception:
            break

    # Record learning from this execution
    try:
        from sago.learning import get_learning_store

        ls = get_learning_store()
        task_type = _detect_task_type(task)

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
    except Exception:
        pass

    # Get change summary
    change_summary = None
    try:
        from sago.memory.change_tracker import get_change_tracker

        tracker = get_change_tracker()
        change_summary = tracker.get_summary()
    except Exception:
        pass

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
    }


def _extract_tool_calls(content: str) -> list[str]:
    """DEPRECATED: Extract tool calls from LLM text output.

    This is kept for backward compatibility with the TUI and tests.
    The main executor now uses native OpenAI function calling instead.
    """
    matches = []

    # Format 1: Single JSON object on its own line
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                data = json.loads(line)
                if "name" in data and "args" in data:
                    matches.append(line)
            except json.JSONDecodeError:
                pass

    if matches:
        return matches

    # Format 2: Inside code blocks
    for pattern in [r"```json\s*\n(.*?)\n```", r"```\s*\n(\{.*?\})\n```"]:
        for f in re.findall(pattern, content, re.DOTALL):
            try:
                data = json.loads(f.strip())
                if "name" in data and "args" in data:
                    matches.append(f.strip())
            except json.JSONDecodeError:
                pass

    if matches:
        return matches

    # Format 3: XML-style tags
    for tool_name, args_str in re.findall(r"<tool_call>(\w+)(.*?)</tool_call>", content, re.DOTALL):
        args = {}
        for m in re.finditer(
            r"<arg_key>(\w+)</arg_key><arg_value>(.*?)</arg_value>", args_str, re.DOTALL
        ):
            args[m.group(1)] = m.group(2)
        if args:
            matches.append(json.dumps({"name": tool_name, "args": args}))

    if matches:
        return matches

    # Format 4: Try to find any JSON-like structure with tool call patterns
    for m in re.finditer(
        r'\{[^{}]*"name"\s*:\s*"(\w+)"[^{}]*"args"\s*:\s*\{[^{}]*\}[^{}]*\}', content, re.DOTALL
    ):
        try:
            data = json.loads(m.group(0))
            if "name" in data and "args" in data:
                matches.append(m.group(0))
        except json.JSONDecodeError:
            pass

    if matches:
        return matches

    # Format 5: Free model format — <|tool_call>call:tool_name{arg: val, ...}<tool_call|>
    for m in re.finditer(r"<\|tool_call\>call:(\w+)\{(.*?)\}<tool_call\|>", content, re.DOTALL):
        tool_name = m.group(1)
        kwargs_str = m.group(2)
        args = {}
        for kv in re.finditer(r"(\w+):\s*\"([^\"]*)\"", kwargs_str):
            args[kv.group(1)] = kv.group(2)
        for kv in re.finditer(r"(\w+):\s*([^,\}]+)", kwargs_str):
            if kv.group(1) not in args:
                val = kv.group(2).strip()
                if val.lower() == "true":
                    args[kv.group(1)] = True
                elif val.lower() == "false":
                    args[kv.group(1)] = False
                else:
                    try:
                        args[kv.group(1)] = int(val)
                    except ValueError:
                        try:
                            args[kv.group(1)] = float(val)
                        except ValueError:
                            args[kv.group(1)] = val
        if args:
            matches.append(json.dumps({"name": tool_name, "args": args}))

    return matches
