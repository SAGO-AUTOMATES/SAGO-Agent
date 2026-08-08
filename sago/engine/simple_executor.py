"""Simple Agent Executor - Direct LLM + tool execution with full project context."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from openai import OpenAI

from sago.tools.file.read_file import ReadFileTool
from sago.tools.file.write_file import WriteFileTool
from sago.tools.file.edit_file import EditFileTool
from sago.tools.file.glob_files import GlobFilesTool
from sago.tools.file.grep_content import GrepContentTool
from sago.tools.file.spawn_agent import SpawnAgentTool
from sago.tools.shell.execute import ExecuteShellTool
from sago.tools.system.git_ops import GitOps


TOOL_MAP = {
    "read_file": ReadFileTool,
    "write_file": WriteFileTool,
    "edit_file": EditFileTool,
    "glob_files": GlobFilesTool,
    "grep_content": GrepContentTool,
    "spawn_agent": SpawnAgentTool,
    "execute_shell": ExecuteShellTool,
    "git_ops": GitOps,
}


def _get_project_context(cwd: str | None = None) -> str:
    """Gather project context: files, README, structure."""
    work_dir = Path(cwd) if cwd else Path.cwd()
    lines = [f"Working directory: {work_dir}"]

    # Read README
    for name in ["README.md", "readme.md", "README.txt", "readme.txt"]:
        readme_path = work_dir / name
        if readme_path.exists():
            try:
                content = readme_path.read_text(encoding="utf-8")[:4000]
                lines.append(f"\n--- {name} ---\n{content}")
            except Exception:
                pass
            break

    # List project files
    file_list = []
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "env", ".tox", ".mypy_cache", ".pytest_cache", "dist", "build", ".eggs"}

    try:
        for item in sorted(work_dir.iterdir()):
            if item.name.startswith(".") or item.name in skip_dirs:
                continue
            if item.is_dir():
                try:
                    child_count = sum(1 for _ in item.iterdir())
                    file_list.append(f"  {item.name}/ ({child_count} items)")
                except Exception:
                    file_list.append(f"  {item.name}/")
            else:
                try:
                    size = item.stat().st_size
                    file_list.append(f"  {item.name} ({size} bytes)" if size < 100_000 else f"  {item.name} ({size // 1024}KB)")
                except Exception:
                    file_list.append(f"  {item.name}")
    except PermissionError:
        pass

    if file_list:
        lines.append(f"\nProject files ({work_dir.name}/):")
        lines.extend(file_list[:60])

    # Git info
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
) -> dict[str, Any]:
    """Execute a task using direct LLM + tool calls with full project context."""
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=90.0, max_retries=2)

    project_ctx = _get_project_context(cwd)

    default_prompt = (
        f"You are {agent_role}. You are working on the user's actual machine with real files.\n\n"
        f"PROJECT CONTEXT:\n{project_ctx}\n\n"
        "=== TOOLS YOU CAN USE ===\n\n"
        "1. read_file(file_path, offset?, limit?)\n"
        "   Read any file. Use relative paths.\n"
        '   Example: {"name": "read_file", "args": {"file_path": "README.md"}}\n\n'
        "2. write_file(file_path, content)\n"
        "   Write content to a file. Creates dirs automatically.\n"
        '   Example: {"name": "write_file", "args": {"file_path": "output.py", "content": "print(42)"}}\n\n'
        "3. edit_file(file_path, old_string, new_string)\n"
        "   Edit a file by finding and replacing exact text.\n"
        '   Example: {"name": "edit_file", "args": {"file_path": "app.py", "old_string": "old", "new_string": "new"}}\n\n'
        "4. glob_files(pattern, path?)\n"
        "   Find files matching patterns like **/*.py or src/**/*.ts\n"
        '   Example: {"name": "glob_files", "args": {"pattern": "**/*.py"}}\n\n'
        "5. grep_content(pattern, path?, include?)\n"
        "   Search file contents with regex. Returns matching lines.\n"
        '   Example: {"name": "grep_content", "args": {"pattern": "def main", "include": "*.py"}}\n\n'
        "6. execute_shell(command, cwd?)\n"
        "   Run ANY shell command: ls, cat, grep, find, git, python, npm, etc.\n"
        '   Example: {"name": "execute_shell", "args": {"command": "ls -la"}}\n'
        '   Example: {"name": "execute_shell", "args": {"command": "python -c \"print(1+1)\""}}\n\n'
        "7. git_ops(operation, args?, cwd?)\n"
        "   Git operations: status, log, diff, add, commit, push, pull, branch, checkout\n"
        '   Example: {"name": "git_ops", "args": {"operation": "status"}}\n'
        '   Example: {"name": "git_ops", "args": {"operation": "log", "args": "--oneline -10"}}\n\n'
        "8. spawn_agent(task, agent_name, context?)\n"
        "   Delegate work to a specialist agent. Available agents:\n"
        "   python-engineer, javascript-engineer, java-engineer, go-engineer,\n"
        "   rust-engineer, cpp-engineer, frontend-engineer, backend-engineer,\n"
        "   fullstack-engineer, devops, security-engineer, qa-engineer,\n"
        "   debugger, code-reviewer, data-engineer, ml-engineer,\n"
        "   database-engineer, technical-writer, system-architect, mobile-engineer,\n"
        "   ios-engineer, android-engineer, flutter-engineer, kubernetes-engineer,\n"
        "   docker-engineer, cloud-engineer, performance-engineer, api-engineer,\n"
        "   ui-engineer, ux-engineer, css-engineer, software-engineer\n"
        '   Example: {"name": "spawn_agent", "args": {"task": "fix the bug", "agent_name": "debugger"}}\n'
        '   Example: {"name": "spawn_agent", "args": {"task": "write tests", "agent_name": "qa-engineer", "context": "module does X"}}\n\n'
        "=== RULES ===\n"
        "- You HAVE tools. USE THEM. Never say you can't read files or run commands.\n"
        "- Always use tools to explore before answering questions about the project.\n"
        "- Use relative paths (relative to working directory shown above).\n"
        "- Output EXACTLY one JSON object per tool call, on its own line.\n"
        "- After getting tool results, provide a clear summary.\n"
        "- If you need to read a file, USE read_file. If you need to run a command, USE execute_shell.\n"
    )

    messages = [
        {"role": "system", "content": system_prompt or default_prompt},
        {"role": "user", "content": task},
    ]

    tools_used = []
    content = ""

    for i in range(max_iterations):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.3,
        )

        choice = response.choices[0]
        content = choice.message.content or ""
        if not content and hasattr(choice.message, "reasoning") and choice.message.reasoning:
            content = choice.message.reasoning

        messages.append({"role": "assistant", "content": content})

        tool_matches = _extract_tool_calls(content)

        if not tool_matches:
            return {
                "success": True,
                "output": content,
                "tool_calls": tools_used,
                "iterations": i + 1,
            }

        for match in tool_matches:
            try:
                tool_data = json.loads(match) if isinstance(match, str) else match
                tool_name = tool_data.get("name", "")
                tool_args = tool_data.get("args", {})

                tool_class = TOOL_MAP.get(tool_name)
                if tool_class:
                    tool_instance = tool_class()
                    result = tool_instance.run(**tool_args)
                    result_str = str(result)[:2000]
                    tools_used.append({"tool": tool_name, "args": tool_args, "result": result_str[:500]})
                    messages.append({"role": "user", "content": f"[Tool: {tool_name}]\n{result_str}"})
                else:
                    available = ", ".join(TOOL_MAP.keys())
                    messages.append({"role": "user", "content": f"Unknown tool '{tool_name}'. Available: {available}"})
            except json.JSONDecodeError:
                messages.append({"role": "user", "content": "Invalid JSON format. Output exactly: {\"name\": \"tool\", \"args\": {...}}"})
            except Exception as e:
                messages.append({"role": "user", "content": f"Tool error: {e}. Try a different approach."})

    return {
        "success": True,
        "output": content,
        "tool_calls": tools_used,
        "iterations": max_iterations,
    }


def _extract_tool_calls(content: str) -> list[str]:
    """Extract tool calls from LLM output in various formats."""
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
