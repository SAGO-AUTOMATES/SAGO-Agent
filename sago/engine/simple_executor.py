"""Simple Agent Executor - Auto-discovers all tools, prevents loops, provides progress."""

from __future__ import annotations

import importlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from openai import OpenAI

from sago.tools.base import BaseTool


# Auto-discover all tools from sago/tools/
_TOOL_CLASSES: dict[str, type[BaseTool]] = {}
_TOOL_DESCRIPTIONS: str = ""


def _discover_tools() -> dict[str, type[BaseTool]]:
    """Auto-discover all BaseTool subclasses from sago/tools/."""
    global _TOOL_CLASSES, _TOOL_DESCRIPTIONS
    if _TOOL_CLASSES:
        return _TOOL_CLASSES

    tools_dir = Path(__file__).parent.parent / "tools"
    skip = {"base.py", "__init__.py"}

    for py_file in tools_dir.rglob("*.py"):
        if py_file.name.startswith("_") or py_file.name in skip:
            continue
        try:
            parts = py_file.relative_to(tools_dir).with_suffix("").as_posix().split("/")
            mod_name = f"sago.tools.{'.'.join(parts)}"
            mod = importlib.import_module(mod_name)
            for attr_name in dir(mod):
                obj = getattr(mod, attr_name)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, BaseTool)
                    and obj is not BaseTool
                    and hasattr(obj, "name")
                    and obj.name
                ):
                    _TOOL_CLASSES[obj.name] = obj
        except Exception:
            pass

    # Build description string
    lines = []
    for name, cls in sorted(_TOOL_CLASSES.items()):
        desc = cls.description or name
        args = ""
        if cls.args_model:
            fields = cls.args_model.model_fields
            arg_parts = []
            for fname, finfo in fields.items():
                req = "required" if finfo.is_required() else f"default={finfo.default}"
                arg_parts.append(f"{fname} ({req})")
            args = ", ".join(arg_parts)
        lines.append(f"- {name}({args}): {desc}")
    _TOOL_DESCRIPTIONS = "\n".join(lines)

    return _TOOL_CLASSES


def _get_project_context(cwd: str | None = None) -> str:
    """Gather project context."""
    work_dir = Path(cwd) if cwd else Path.cwd()
    lines = [f"Working directory: {work_dir}"]

    # README
    for name in ["README.md", "readme.md"]:
        p = work_dir / name
        if p.exists():
            try:
                lines.append(f"\n--- {name} ---\n{p.read_text('utf-8')[:4000]}")
            except Exception:
                pass
            break

    # Files
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "env", ".tox", ".mypy_cache", "dist", "build"}
    file_list = []
    try:
        for item in sorted(work_dir.iterdir()):
            if item.name.startswith(".") or item.name in skip_dirs:
                continue
            if item.is_dir():
                try:
                    file_list.append(f"  {item.name}/ ({sum(1 for _ in item.iterdir())} items)")
                except Exception:
                    file_list.append(f"  {item.name}/")
            else:
                try:
                    s = item.stat().st_size
                    file_list.append(f"  {item.name} ({s}B)" if s < 100_000 else f"  {item.name} ({s//1024}KB)")
                except Exception:
                    file_list.append(f"  {item.name}")
    except PermissionError:
        pass

    if file_list:
        lines.append(f"\nFiles ({work_dir.name}/):")
        lines.extend(file_list[:50])

    # Git
    try:
        import subprocess
        r = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, timeout=5, cwd=str(work_dir))
        if r.returncode == 0 and r.stdout.strip():
            lines.append(f"\nGit changes:\n{r.stdout.strip()[:1000]}")
    except Exception:
        pass

    return "\n".join(lines)


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
    on_tool_call: Any = None,
    on_thinking: Any = None,
) -> dict[str, Any]:
    """Execute a task with auto-discovered tools, loop protection, and progress callbacks."""
    tools = _discover_tools()
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=90.0, max_retries=2)
    project_ctx = _get_project_context(cwd)
    start_time = time.time()

    # Track state to prevent loops
    seen_tool_results: set[str] = set()
    consecutive_same_tool = 0
    last_tool_call = ""
    total_input_tokens = 0
    total_output_tokens = 0

    default_prompt = (
        f"You are {agent_role}. Working on the user's real machine.\n\n"
        f"PROJECT CONTEXT:\n{project_ctx}\n\n"
        f"TOOLS ({len(tools)} available):\n{_TOOL_DESCRIPTIONS}\n\n"
        "RULES:\n"
        "- Output ONE JSON per tool call on its own line: {\"name\": \"tool\", \"args\": {...}}\n"
        "- Use relative paths (relative to working directory).\n"
        "- Never say you can't - you have full tool access.\n"
        "- After tool results, provide a clear summary.\n"
        "- If a tool fails, try a different approach.\n"
        "- Do NOT repeat the same tool call with the same arguments.\n"
    )

    messages = [
        {"role": "system", "content": system_prompt or default_prompt},
        {"role": "user", "content": task},
    ]

    tools_used = []
    content = ""

    for i in range(max_iterations):
        iteration_start = time.time()

        if on_thinking:
            on_thinking(f"Iteration {i+1}/{max_iterations}...")

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
                "output": content,
                "tool_calls": tools_used,
                "iterations": i + 1,
                "tokens": {"input": total_input_tokens, "output": total_output_tokens},
                "elapsed": time.time() - start_time,
            }

        choice = response.choices[0]
        content = choice.message.content or ""
        if not content and hasattr(choice.message, "reasoning") and choice.message.reasoning:
            content = choice.message.reasoning

        # Track tokens
        if hasattr(response, "usage") and response.usage:
            total_input_tokens += response.usage.prompt_tokens or 0
            total_output_tokens += response.usage.completion_tokens or 0

        messages.append({"role": "assistant", "content": content})

        tool_matches = _extract_tool_calls(content)

        if not tool_matches:
            return {
                "success": True,
                "output": content,
                "tool_calls": tools_used,
                "iterations": i + 1,
                "tokens": {"input": total_input_tokens, "output": total_output_tokens},
                "elapsed": time.time() - start_time,
            }

        for match in tool_matches:
            try:
                tool_data = json.loads(match) if isinstance(match, str) else match
                tool_name = tool_data.get("name", "")
                tool_args = tool_data.get("args", {})

                # Loop detection: same tool+args repeated
                call_sig = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
                if call_sig == last_tool_call:
                    consecutive_same_tool += 1
                    if consecutive_same_tool >= 2:
                        messages.append({"role": "user", "content": "You already tried this exact call and got a result. Do NOT repeat it. Use the result you have and provide your final answer."})
                        continue
                else:
                    consecutive_same_tool = 0
                last_tool_call = call_sig

                # Loop detection: same result seen
                result_key = call_sig[:100]
                if result_key in seen_tool_results:
                    messages.append({"role": "user", "content": "This tool call was already executed. Use existing results and move forward."})
                    continue

                # Execute tool
                if on_tool_call:
                    on_tool_call(tool_name, tool_args)

                tool_class = tools.get(tool_name)
                if tool_class:
                    tool_instance = tool_class()
                    result = tool_instance.run(**tool_args)
                    result_str = str(result)[:3000]
                    seen_tool_results.add(result_key)
                    tools_used.append({"tool": tool_name, "args": tool_args, "result": result_str[:500]})
                    messages.append({"role": "user", "content": f"[Tool: {tool_name}]\n{result_str}"})
                else:
                    available = ", ".join(sorted(tools.keys()))
                    messages.append({"role": "user", "content": f"Unknown tool '{tool_name}'. Available: {available}"})

            except json.JSONDecodeError:
                messages.append({"role": "user", "content": "Invalid JSON. Output exactly: {\"name\": \"tool\", \"args\": {...}}"})
            except Exception as e:
                messages.append({"role": "user", "content": f"Tool error: {type(e).__name__}: {e}. Try different approach."})

    return {
        "success": True,
        "output": content,
        "tool_calls": tools_used,
        "iterations": max_iterations,
        "tokens": {"input": total_input_tokens, "output": total_output_tokens},
        "elapsed": time.time() - start_time,
    }


def _extract_tool_calls(content: str) -> list[str]:
    """Extract tool calls from LLM output."""
    matches = []

    # JSON on its own line
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

    # ```json blocks
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

    # <tool_call>...</tool_call>
    for tool_name, args_str in re.findall(r'<tool_call>(\w+)(.*?)</tool_call>', content, re.DOTALL):
        args = {}
        for m in re.finditer(r'<arg_key>(\w+)</arg_key><arg_value>(.*?)</arg_value>', args_str, re.DOTALL):
            args[m.group(1)] = m.group(2)
        if args:
            matches.append(json.dumps({"name": tool_name, "args": args}))

    return matches
