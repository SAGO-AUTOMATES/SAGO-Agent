"""Smart Agent Executor - Thinks before acting, learns from results, no loops."""

from __future__ import annotations

import importlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI

from sago.tools.base import BaseTool


# Auto-discover all tools
_TOOL_CLASSES: dict[str, type[BaseTool]] = {}
_TOOL_DESCRIPTIONS = ""


def _discover_tools() -> dict[str, type[BaseTool]]:
    global _TOOL_CLASSES, _TOOL_DESCRIPTIONS
    if _TOOL_CLASSES:
        return _TOOL_CLASSES

    tools_dir = Path(__file__).parent.parent / "tools"
    for py_file in tools_dir.rglob("*.py"):
        if py_file.name.startswith("_") or py_file.name == "base.py":
            continue
        try:
            parts = py_file.relative_to(tools_dir).with_suffix("").as_posix().split("/")
            mod = importlib.import_module(f"sago.tools.{'.'.join(parts)}")
            for attr in dir(mod):
                obj = getattr(mod, attr)
                if isinstance(obj, type) and issubclass(obj, BaseTool) and obj is not BaseTool and getattr(obj, "name", None):
                    _TOOL_CLASSES[obj.name] = obj
        except Exception:
            pass

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

    for name in ["README.md", "readme.md"]:
        p = work_dir / name
        if p.exists():
            try:
                lines.append(f"\n--- {name} ---\n{p.read_text('utf-8')[:4000]}")
            except Exception:
                pass
            break

    skip = {".git", "node_modules", "__pycache__", ".venv", "venv", "env", ".tox", "dist", "build"}
    files = []
    try:
        for item in sorted(work_dir.iterdir()):
            if item.name.startswith(".") or item.name in skip:
                continue
            if item.is_dir():
                try:
                    files.append(f"  {item.name}/ ({sum(1 for _ in item.iterdir())} items)")
                except Exception:
                    files.append(f"  {item.name}/")
            else:
                try:
                    s = item.stat().st_size
                    files.append(f"  {item.name} ({s}B)" if s < 100_000 else f"  {item.name} ({s//1024}KB)")
                except Exception:
                    files.append(f"  {item.name}")
    except PermissionError:
        pass
    if files:
        lines.append(f"\nFiles ({work_dir.name}/):")
        lines.extend(files[:50])

    try:
        import subprocess
        r = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, timeout=5, cwd=str(work_dir))
        if r.returncode == 0 and r.stdout.strip():
            lines.append(f"\nGit changes:\n{r.stdout.strip()[:800]}")
    except Exception:
        pass

    return "\n".join(lines)


SYSTEM_PROMPT_TEMPLATE = """You are {agent_role}. You are a SMART agent that thinks before acting.

{project_ctx}

=== YOUR TOOLS ({tool_count} available) ===
{tool_descriptions}

=== HOW TO THINK ===

1. UNDERSTAND: Read the task carefully. What exactly is being asked?
2. PLAN: What steps do you need? Which tools in what order?
3. ACT: Execute ONE tool at a time. Wait for the result.
4. LEARN: What did the tool tell you? Does it match your expectation?
5. ADAPT: If it failed or wasn't what you expected, try a DIFFERENT approach.
6. ANSWER: Once you have enough info, give a clear final answer.

=== CRITICAL RULES ===

- NEVER repeat the exact same tool call. If it failed, try something different.
- NEVER use the same tool more than 3 times in a row.
- If a file read fails, try a different path or use glob_files to find it.
- If a command fails, read the error and fix your approach.
- STOP using tools once you have the answer. Don't over-explore.
- Your final response should be AFTER all tool calls, summarizing what you found/did.

=== TOOL FORMAT ===

Output EXACTLY one JSON per tool call on its own line:
{{"name": "tool_name", "args": {{"param": "value"}}}}

Examples:
{{"name": "execute_shell", "args": {{"command": "ls -la"}}}}
{{"name": "read_file", "args": {{"file_path": "README.md"}}}}
{{"name": "glob_files", "args": {{"pattern": "**/*.py"}}}}
{{"name": "grep_content", "args": {{"pattern": "class App", "include": "*.py"}}}}
{{"name": "spawn_agent", "args": {{"task": "write tests", "agent_name": "qa-engineer"}}}}
"""


def execute_agent_task(
    task: str,
    agent_role: str = "Sago Orchestrator",
    system_prompt: str = "",
    model: str = "openrouter/free",
    api_key: str = "",
    base_url: str = "https://openrouter.ai/api/v1",
    max_tokens: int = 4096,
    max_iterations: int = 5,
    cwd: str | None = None,
    on_tool_call: Callable | None = None,
    on_thinking: Callable | None = None,
) -> dict[str, Any]:
    tools = _discover_tools()
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=90.0, max_retries=2)
    project_ctx = _get_context(cwd)
    start_time = time.time()

    # Build smart system prompt
    if not system_prompt:
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            agent_role=agent_role,
            project_ctx=project_ctx,
            tool_count=len(tools),
            tool_descriptions=_TOOL_DESCRIPTIONS,
        )

    # State tracking
    tool_history: list[dict] = []  # [{name, args, result, success}]
    tool_call_counts: dict[str, int] = {}  # tool_name -> count
    failed_calls: set[str] = set()  # "tool:args_hash" for failed calls
    total_tokens_in = 0
    total_tokens_out = 0

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]

    content = ""

    for i in range(max_iterations):
        if on_thinking:
            on_thinking(f"Thinking... (step {i+1}/{max_iterations})")

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.3,
            )
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": content or f"API error: {e}",
                "tool_calls": tool_history,
                "iterations": i + 1,
                "tokens": {"input": total_tokens_in, "output": total_tokens_out},
                "elapsed": time.time() - start_time,
            }

        choice = response.choices[0]
        content = choice.message.content or ""
        if not content and hasattr(choice.message, "reasoning") and choice.message.reasoning:
            content = choice.message.reasoning

        if hasattr(response, "usage") and response.usage:
            total_tokens_in += response.usage.prompt_tokens or 0
            total_tokens_out += response.usage.completion_tokens or 0

        messages.append({"role": "assistant", "content": content})

        tool_calls = _extract_tool_calls(content)

        if not tool_calls:
            return {
                "success": True,
                "output": content,
                "tool_calls": tool_history,
                "iterations": i + 1,
                "tokens": {"input": total_tokens_in, "output": total_tokens_out},
                "elapsed": time.time() - start_time,
            }

        # Execute each tool call
        results_for_llm = []
        for call_str in tool_calls:
            try:
                call = json.loads(call_str) if isinstance(call_str, str) else call_str
                name = call.get("name", "")
                args = call.get("args", {})

                # Check if this exact call already failed
                call_key = f"{name}:{json.dumps(args, sort_keys=True)}"
                if call_key in failed_calls:
                    results_for_llm.append(f"[SKIP] Already failed: {name}")
                    continue

                # Check if tool exists
                if name not in tools:
                    avail = ", ".join(sorted(tools.keys()))
                    results_for_llm.append(f"Unknown tool '{name}'. Available: {avail}")
                    continue

                # Check if repeating same tool too much
                tool_call_counts[name] = tool_call_counts.get(name, 0) + 1
                if tool_call_counts[name] > 3:
                    results_for_llm.append(
                        f"[STOP] You've used {name} {tool_call_counts[name]} times. "
                        f"Try a different tool or give your final answer."
                    )
                    continue

                # Execute
                if on_tool_call:
                    on_tool_call(name, args)

                tool_instance = tools[name]()
                result = tool_instance.run(**args)
                result_str = str(result)[:3000]

                # Determine success
                is_error = result_str.lower().startswith("error") or "traceback" in result_str.lower()
                if is_error:
                    failed_calls.add(call_key)

                tool_history.append({
                    "tool": name,
                    "args": args,
                    "result": result_str[:500],
                    "success": not is_error,
                })

                # Format result with context
                if is_error:
                    results_for_llm.append(f"[ERROR] {name}:\n{result_str}\nHint: Fix your approach, don't retry the same thing.")
                else:
                    results_for_llm.append(f"[OK] {name}:\n{result_str}")

            except json.JSONDecodeError:
                results_for_llm.append("Invalid JSON format. Use: {\"name\": \"tool\", \"args\": {...}}")
            except Exception as e:
                results_for_llm.append(f"Tool crashed: {type(e).__name__}: {e}")

        # Send all results back to LLM
        combined = "\n\n".join(results_for_llm)
        messages.append({"role": "user", "content": combined})

    # Max iterations reached
    return {
        "success": True,
        "output": content,
        "tool_calls": tool_history,
        "iterations": max_iterations,
        "tokens": {"input": total_tokens_in, "output": total_tokens_out},
        "elapsed": time.time() - start_time,
    }


def _extract_tool_calls(content: str) -> list[str]:
    matches = []

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

    for pattern in [r'```json\s*\n(.*?)\n```', r'```\s*\n(\{.*?\})\n```']:
        for f in re.findall(pattern, content, re.DOTALL):
            try:
                data = json.loads(f.strip())
                if "name" in data and "args" in data:
                    matches.append(f.strip())
            except json.JSONDecodeError:
                pass

    if matches:
        return matches

    for tool_name, args_str in re.findall(r'<tool_call>(\w+)(.*?)</tool_call>', content, re.DOTALL):
        args = {}
        for m in re.finditer(r'<arg_key>(\w+)</arg_key><arg_value>(.*?)</arg_value>', args_str, re.DOTALL):
            args[m.group(1)] = m.group(2)
        if args:
            matches.append(json.dumps({"name": tool_name, "args": args}))

    return matches
