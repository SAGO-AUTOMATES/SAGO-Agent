"""Smart Executor - Handles complex multi-step tasks like building projects."""

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
    if _TOOL_CLASSES:
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


# Task-specific system prompts
PROMPTS = {
    "create": """You are {agent_role}. The user wants you to CREATE something (file, project, feature).

{project_ctx}

=== YOUR CAPABILITIES ===
You have {tool_count} tools. For creation tasks, you'll typically:
1. Explore existing structure with glob_files, read_file
2. Create files with write_file (creates directories automatically)
3. Edit files with edit_file for modifications
4. Test with execute_shell (run tests, linting, etc.)

=== CREATION STRATEGY ===
- Start by understanding what exists (glob_files, read_file)
- Create files ONE AT A TIME using write_file
- After each file, verify it was created correctly
- For projects: create structure first, then implement
- Always verify your work (run tests, check syntax)

{tool_list}

=== FORMAT ===
One JSON per tool call on its own line:
{{"name": "write_file", "args": {{"file_path": "src/app.py", "content": "import os\\n\\nclass App:\\n    def run(self):\\n        print('Hello')"}}}}

IMPORTANT: When writing files, put the ACTUAL CODE in the content field. No markdown, no backticks, just the raw code.""",
    "fix": """You are {agent_role}. The user wants you to FIX something (bug, error, issue).

{project_ctx}

=== YOUR CAPABILITIES ===
You have {tool_count} tools. For fixing tasks:
1. Understand the error (read error messages, logs)
2. Find the relevant code (grep_content, read_file)
3. Fix the issue (edit_file or write_file)
4. Verify the fix (run tests, execute commands)

=== FIX STRATEGY ===
- Read the error message carefully
- Find the file and line causing the issue
- Understand the root cause before fixing
- Make minimal changes to fix
- Test that the fix works

{tool_list}

=== FORMAT ===
One JSON per tool call on its own line:
{{"name": "edit_file", "args": {{"file_path": "app.py", "old_string": "broken code", "new_string": "fixed code"}}}}""",
    "analyze": """You are {agent_role}. The user wants you to ANALYZE something (code, project, issue).

{project_ctx}

=== YOUR CAPABILITIES ===
You have {tool_count} tools. For analysis tasks:
1. Explore structure (glob_files, execute_shell with ls/find)
2. Read relevant files (read_file)
3. Search for patterns (grep_content)
4. Provide comprehensive analysis

=== ANALYSIS STRATEGY ===
- Be thorough but focused
- Read multiple files to understand the full picture
- Look for patterns, issues, improvements
- Provide actionable recommendations

{tool_list}

=== FORMAT ===
One JSON per tool call on its own line:
{{"name": "grep_content", "args": {{"pattern": "def ", "include": "*.py"}}}}""",
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
    base_url: str = "https://openrouter.ai/api/v1",
    max_tokens: int = 4096,
    max_iterations: int = 8,
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
        if profile.get("max_iterations") and max_iterations == 8:
            max_iterations = min(profile["max_iterations"], 15)
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
            tool_count=len(tools),
            tool_list=_TOOL_DESCRIPTIONS,
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

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]

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
        todo_context = ""
        if task_plan and current_todo_index < len(task_plan.todos):
            current_todo = task_plan.todos[current_todo_index]
            todo_context = (
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
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temp,
            )
        except Exception as e:
            error_msg = str(e)
            # Provide helpful error messages for common failures
            if "429" in error_msg or "rate" in error_msg.lower():
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

        choice = response.choices[0]
        content = choice.message.content or ""
        if not content and hasattr(choice.message, "reasoning") and choice.message.reasoning:
            content = choice.message.reasoning

        # Handle empty or None content - retry with clearer prompt
        if not content or content.strip() == "":
            if i < max_iterations - 1:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "You returned an empty response. Please use the available tools to complete the task. "
                            'Output a JSON tool call like: {"name": "tool_name", "args": {"param": "value"}}'
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

        messages.append({"role": "assistant", "content": content})

        tool_calls = _extract_tool_calls(content)

        if not tool_calls:
            # No tool calls - LLM is done with current step
            if task_plan and current_todo_index < len(task_plan.todos):
                from sago.tasks import TaskStatus, get_task_manager

                tm = get_task_manager()
                current_todo = task_plan.todos[current_todo_index]
                if current_todo.status == TaskStatus.IN_PROGRESS:
                    tm.complete_todo(task_plan.id, current_todo.id, result=content[:200])
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

        results_for_llm = []
        tools_used_in_iteration = []

        for call_str in tool_calls:
            try:
                call = json.loads(call_str) if isinstance(call_str, str) else call_str
                name = call.get("name", "")
                args = call.get("args", {})

                # Loop prevention
                call_key = f"{name}:{json.dumps(args, sort_keys=True)}"
                if call_key in failed_calls:
                    results_for_llm.append(f"[SKIP] Already failed: {name} with same args")
                    continue

                if name not in tools:
                    avail = ", ".join(sorted(tools.keys()))
                    results_for_llm.append(f"Unknown tool '{name}'. Available: {avail}")
                    continue

                # Check permissions before execution
                from sago.permissions import RiskLevel, get_permission_manager

                pm = get_permission_manager()
                risk = pm.get_risk_level(name)
                allowed, reason = pm.check_permission(name, args)

                if not allowed:
                    if risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                        results_for_llm.append(
                            f"Permission denied: {name} requires approval (risk: {risk.value})"
                        )
                    else:
                        results_for_llm.append(f"Permission denied: {reason}")
                    continue

                tool_call_counts[name] = tool_call_counts.get(name, 0) + 1
                # No hard limits - let the LLM self-regulate
                # But detect circular behavior and warn
                recent_calls = [
                    f"{c['tool']}:{json.dumps(c['args'], sort_keys=True)[:50]}"
                    for c in tool_history[-5:]
                ]
                if len(recent_calls) >= 3:
                    unique_recent = set(recent_calls[-3:])
                    if len(unique_recent) == 1:
                        results_for_llm.append(
                            f"[HINT] You've called {name} with similar args 3 times in a row. "
                            f"If this isn't working, try a completely different approach or finish the task."
                        )

                if on_tool_call:
                    on_tool_call(name, args)

                tool_instance = tools[name]()
                result = tool_instance.run(**args)
                result_str = str(result)[:4000]

                is_error = (
                    result_str.lower().startswith("error") or "traceback" in result_str.lower()
                )
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
                        "result": result_str[:500],
                        "success": not is_error,
                    }
                )

                tools_used_in_iteration.append(name)

                # Notify caller of tool result immediately
                if on_tool_result:
                    on_tool_result(name, args, result_str[:1000], not is_error)

                if is_error:
                    results_for_llm.append(
                        f"[ERROR] {name}:\n{result_str}\nTry a different approach."
                    )
                else:
                    # Truncate long results
                    display = result_str[:1500] + "..." if len(result_str) > 1500 else result_str
                    results_for_llm.append(f"[OK] {name}:\n{display}")

            except json.JSONDecodeError:
                results_for_llm.append('Invalid JSON. Use: {{"name": "tool", "args": {{...}}}}')
            except Exception as e:
                results_for_llm.append(f"Tool error: {type(e).__name__}: {e}")

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

                    # Auto-complete todo after sufficient work (3+ successful tools or 2+ iterations on same todo)
                    successful_tools = [
                        t["tool"]
                        for t in tool_history
                        if t.get("success") and t["tool"] in tools_used_in_iteration
                    ]
                    tools_for_this_todo = todo_tool_counts.get(current_todo.id, 0)
                    if (tools_for_this_todo >= 3 and len(successful_tools) >= 2) or (
                        i > 0 and tools_for_this_todo >= 2
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
                            results_for_llm.append(
                                f"\n[PROGRESS] Step completed. Next step: {next_todo.description}\n"
                                f"Execute this step now."
                            )
                        else:
                            results_for_llm.append(
                                "\n[PROGRESS] All steps completed. Provide final summary."
                            )
            except Exception:
                pass

        # Add context about progress
        progress_parts = [f"{len(tool_history)} tools used", f"{len(files_created)} files created"]
        if task_plan:
            progress_parts.append(f"Step {current_todo_index + 1}/{len(task_plan.todos)}")
        progress = f"\n[Progress: {', '.join(progress_parts)}]" + todo_context
        combined = "\n\n".join(results_for_llm) + progress
        messages.append({"role": "user", "content": combined})

        # Auto-compact if messages are getting too large
        if len(messages) > 15:
            messages = _compact_messages_if_needed(messages)

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

        # Feed test errors back to LLM for fixing
        try:
            fix_response = client.chat.completions.create(
                model=model,
                messages=messages
                + [
                    {
                        "role": "user",
                        "content": (
                            f"The tests are failing. Fix the failing tests.\n\n"
                            f"Test output:\n{test_output[:3000]}\n\n"
                            f"Files you created: {', '.join(files_created)}\n"
                            f"Fix the issues and make the tests pass. Use edit_file or write_file to fix."
                        ),
                    },
                ],
                max_tokens=max_tokens,
                temperature=0.3,
            )
            fix_content = fix_response.choices[0].message.content or ""
            if not fix_content and hasattr(fix_response.choices[0].message, "reasoning"):
                fix_content = fix_response.choices[0].message.reasoning or ""

            if fix_content:
                messages.append({"role": "assistant", "content": fix_content})
                fix_tool_calls = _extract_tool_calls(fix_content)
                for call_str in fix_tool_calls:
                    try:
                        call = json.loads(call_str)
                        name = call.get("name", "")
                        args = call.get("args", {})
                        if name in tools:
                            tool_instance = tools[name]()
                            result = tool_instance.run(**args)
                            result_str = str(result)[:4000]
                            is_error = result_str.lower().startswith("error")
                            tool_history.append(
                                {
                                    "tool": name,
                                    "args": args,
                                    "result": result_str[:500],
                                    "success": not is_error,
                                }
                            )
                            if name == "write_file" and not is_error:
                                fp = args.get("file_path", "")
                                if fp and fp not in files_created:
                                    files_created.append(fp)
                    except Exception:
                        pass
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
    # This handles cases where LLM wraps in markdown or adds extra text
    for m in re.finditer(
        r'\{[^{}]*"name"\s*:\s*"(\w+)"[^{}]*"args"\s*:\s*\{[^{}]*\}[^{}]*\}', content, re.DOTALL
    ):
        try:
            data = json.loads(m.group(0))
            if "name" in data and "args" in data:
                matches.append(m.group(0))
        except json.JSONDecodeError:
            pass

    return matches

    return matches
