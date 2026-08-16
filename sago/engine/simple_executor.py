"""Smart Executor - Handles complex multi-step tasks using native function calling."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sago.tools.base import BaseTool

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
        # Compact single-line description to save tokens
        first_line = raw_desc.split("\n", 1)[0].strip()
        if len(first_line) > 160:
            first_line = first_line[:157] + "..."
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
                # Trim overly verbose parameter descriptions
                if "description" in prop and isinstance(prop["description"], str):
                    pdesc = prop["description"].split("\n", 1)[0].strip()
                    if len(pdesc) > 100:
                        pdesc = pdesc[:97] + "..."
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
            pass
        # Regex fallback: find first complete JSON array
        match = re.search(r"\[(?:[^\[\]]*(?:\"[^\"]*\")[^\[\]]*)*\]", content, re.DOTALL)
        if match:
            try:
                steps = json.loads(match.group())
                if isinstance(steps, list) and all(isinstance(s, str) for s in steps):
                    return steps
            except (json.JSONDecodeError, ValueError):
                pass
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

    with _tool_discovery_lock:
        if _TOOL_CLASSES and _TOOL_DESCRIPTIONS:
            return _TOOL_CLASSES

        from sago.tools.registry import discover_tools

        discovered = discover_tools()
        _TOOL_CLASSES = {name: tdef.tool_class for name, tdef in discovered.items()}

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
                except Exception:
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
    except PermissionError:
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
    except Exception:
        pass

    return "\n".join(lines)


# Task-specific system prompts (tools are now passed via API, not in text)
PROMPTS = {
    "chat": """You are {agent_role}, a helpful, knowledgeable, and friendly AI assistant.

{project_ctx}

- Answer questions, conversation, weather inquiries, greetings, explanations, and general requests naturally and accurately.
- Respond conversationally without imposing unsolicited engineering templates or code scaffolding.
- Only invoke tools if the user explicitly requests inspecting files, executing commands, or performing workspace operations.
- Never hallucinate tool results or file contents.""",
    "create": """You are {agent_role}. The user wants you to create, implement, or modify code and files.

{project_ctx}

- Inspect existing code with tools first if needed.
- Write or edit files cleanly with exact code.
- Verify work and report results honestly without fabricating output.
- Reply directly without calling tools for simple conversational queries.""",
    "fix": """You are {agent_role}. The user wants you to fix an issue, bug, or error.

{project_ctx}

- Identify root cause and inspect relevant files before modifying.
- Make precise, minimal fixes and verify changes.
- Never guess file contents or pretend tool executions succeeded.""",
    "analyze": """You are {agent_role}. The user wants you to analyze code or architecture.

{project_ctx}

- Inspect files thoroughly and provide structured, actionable analysis and insights.
- Do not fabricate findings or tool outputs.""",
}


def _detect_task_type(task: str) -> str:
    """Detect task type using semantic IntentClassifier with micro-LLM and fast-path cache."""
    from sago.engine.intent_classifier import get_intent_classifier

    try:
        return get_intent_classifier().classify(task).task_type
    except Exception:
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
    session_id: str = "default",
) -> dict[str, Any]:
    """Execute a task with LLM, tools, and todo tracking.

    Args:
        on_request_input: Called when a todo needs user input. Signature: (question: str) -> str
        pause_event: threading.Event to pause/resume execution. If provided and set, executor pauses.
    """
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
                except Exception:
                    pass
    except Exception:
        pass

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
    except Exception:
        pass

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
    except Exception:
        pass

    # Auto-resolve active model, key, and base_url if defaults or empty
    if not api_key or model == "openrouter/free":
        try:
            from sago.llm.tui_providers import resolve_active_llm_config

            active_cfg = resolve_active_llm_config(
                model=None if model == "openrouter/free" else model,
                api_key=api_key or None,
                base_url=base_url,
            )
            if not api_key:
                api_key = active_cfg["api_key"]
            if model == "openrouter/free" and active_cfg["model"]:
                model = active_cfg["model"]
            if base_url is None:
                base_url = active_cfg["base_url"]
        except Exception:
            pass

    # Auto-detect base_url from model/provider if not provided
    if base_url is None:
        if model.startswith("gemini"):
            base_url = None  # Will be handled by google-genai SDK
        elif model.startswith("gpt") or model.startswith("o1") or model.startswith("o3"):
            base_url = "https://api.openai.com/v1"
        else:
            base_url = "https://openrouter.ai/api/v1"

    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=90.0, max_retries=2)
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
            f"✨ Enhanced Prompt: {enhancement.intent_summary} [dim]({', '.join(enhancement.improvements[:3])})[/dim]"
        )

    # Assemble rich tri-partite context (AST symbols, hybrid search, learning patterns, previous sessions)
    task_type = _detect_task_type(task)
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
    except Exception:
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
        except Exception:
            task_plan = None

    # Auto-resolve specialist agent if default or generic agent was supplied
    if agent_role in ("python-engineer", "developer", "general-assistant", "assistant", "agent"):
        try:
            from sago.agents.registry import resolve_specialist_agent

            resolved = resolve_specialist_agent(task=task, cwd=cwd, default_agent=agent_role)
            if resolved and resolved != "general-assistant":
                agent_role = resolved
        except Exception:
            pass

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

    # Auto-detect task type and use appropriate prompt
    if not system_prompt:
        template = PROMPTS.get(task_type, PROMPTS["create"])
        system_prompt = template.format(
            agent_role=agent_role,
            project_ctx="",  # Context goes in user message
        )

    # --- Skill: inject matched skill context into system prompt ---
    if matched_skills and task_type != "chat":
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
    if custom_skills_context and task_type != "chat":
        system_prompt += f"\n\n=== CUSTOM SKILL INSTRUCTIONS ===\n{custom_skills_context}"

    # --- Skill-based tool filtering: restrict tools to skill-defined subset ---
    if matched_skills and task_type != "chat":
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
                }
                filtered.update({t: tools[t] for t in core_tools if t in tools})
                tools = filtered

    # Inject system-level enhancements (learning approach, known fixes, project instructions)
    if assembled and task_type != "chat":
        system_enhancements = assembled.format_system_enhancements()
        if system_enhancements:
            system_prompt += f"\n\n{system_enhancements}"
    elif task_type != "chat":
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
        except Exception:
            pass

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

    # Initialize single ToolUsageStore instance for task lifecycle
    tool_usage_store = None
    try:
        from sago.database import ToolUsageStore

        tool_usage_store = ToolUsageStore("simple_executor")
    except Exception:
        tool_usage_store = None

    # Build user message with rich reference data context (read-only)
    if task_type == "chat":
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

    # Build OpenAI function calling tool definitions
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
        except Exception:
            pass

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
        except Exception:
            pass

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
                            continue
                        if msg["role"] == "user":
                            contents.append(
                                google_types.Content(
                                    role="user",
                                    parts=[google_types.Part(text=msg["content"])],
                                )
                            )
                        elif msg["role"] == "assistant":
                            parts = []
                            if msg.get("content"):
                                parts.append(google_types.Part(text=msg["content"]))
                            for tc in msg.get("tool_calls", []):
                                fn = tc["function"]
                                try:
                                    args = (
                                        json.loads(fn["arguments"]) if fn.get("arguments") else {}
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

                    response = google_client.models.generate_content(
                        model=model,
                        contents=contents,
                        config=google_config,
                    )

                    # Extract tool calls from Gemini response
                    gemini_tool_calls = []
                    # response.text raises if the response only contains function
                    # calls, so guard against that.
                    try:
                        content = response.text or ""
                    except Exception:
                        content = ""
                    if response.candidates:
                        for part in response.candidates[0].content.parts:
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
            except Exception:
                pass

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
            # --- Plugin: hook_response (transform final response) ---
            try:
                from sago.plugins.base import get_plugin_manager

                content = get_plugin_manager().hook_response(
                    content, {"task": task, "model": model}
                )
            except Exception:
                pass

            # ---- Post-execution quality review ----
            quality_issues = _review_output_quality(content, files_created, tool_history)

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
                "quality_issues": quality_issues,
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
            except Exception:
                pass

            if on_tool_call:
                on_tool_call(name, args)

            validation_error = _validate_tool_args(name, args)
            if validation_error:
                failed_calls.add(call_key)
                return {
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "name": name,
                    "content": validation_error,
                }

            tool_instance = tools[name]()
            result = tool_instance.run(**args)
            result_str = str(result)

            is_error = result_str.lower().startswith("error") or "traceback" in result_str.lower()
            if is_error:
                failed_calls.add(call_key)

            if name in ("write_file", "edit_file", "file_operations") and not is_error:
                fp = (
                    args.get("file_path", "") or args.get("target_file", "") or args.get("path", "")
                )
                if fp and fp not in files_created:
                    files_created.append(fp)
                try:
                    from sago.engine.verifier import get_continuous_verifier

                    get_continuous_verifier().enqueue_files([fp] if fp else [])
                except Exception:
                    pass
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
                    except Exception:
                        pass

            tool_history.append(
                {"tool": name, "args": args, "result": result_str[:2000], "success": not is_error}
            )
            tools_used_in_iteration.append(name)

            if tool_usage_store is not None:
                try:
                    tool_usage_store.log(
                        tool_name=name,
                        arguments=args,
                        result=result_str[:1000],
                        success=not is_error,
                    )
                except Exception:
                    pass

            if on_tool_result:
                on_tool_result(name, args, result_str, not is_error)

            # --- Plugin: hook_tool_result (transform result after execution) ---
            try:
                from sago.plugins.base import get_plugin_manager

                result_str = str(get_plugin_manager().hook_tool_result(name, result_str))
            except Exception:
                pass

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

    # --- Plugin: hook_response (transform final response at end of execution) ---
    try:
        from sago.plugins.base import get_plugin_manager

        content = get_plugin_manager().hook_response(content, {"task": task, "model": model})
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
        except Exception:
            pass

    if tool_usage_store is not None:
        try:
            tool_usage_store.flush()
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
