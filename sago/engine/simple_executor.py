"""Simple Agent Executor - Direct LLM + tool execution with project context."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from openai import OpenAI

from sago.tools.file.write_file import WriteFileTool
from sago.tools.file.read_file import ReadFileTool
from sago.tools.shell.execute import ExecuteShellTool


TOOL_MAP = {
    "write_file": WriteFileTool,
    "read_file": ReadFileTool,
    "execute_shell": ExecuteShellTool,
}


def _get_project_context(cwd: str | None = None) -> str:
    """Gather project context: files, README, structure."""
    work_dir = Path(cwd) if cwd else Path.cwd()
    lines = [f"Working directory: {work_dir}"]

    readme_content = ""
    for name in ["README.md", "readme.md", "README.txt", "readme.txt"]:
        readme_path = work_dir / name
        if readme_path.exists():
            try:
                readme_content = readme_path.read_text(encoding="utf-8")[:3000]
                lines.append(f"\n--- {name} ---\n{readme_content}")
            except Exception:
                pass
            break

    file_list = []
    skip_dirs = {
        ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
        ".env", ".tox", ".mypy_cache", ".pytest_cache", "dist", "build",
        ".eggs", "*.egg-info",
    }
    skip_files = {".pyc", ".pyo", ".so", ".o", ".a", ".dylib"}

    try:
        for item in sorted(work_dir.iterdir()):
            if item.name.startswith("."):
                continue
            if item.name in skip_dirs:
                continue
            if item.is_dir():
                try:
                    child_count = sum(1 for _ in item.iterdir())
                    file_list.append(f"  {item.name}/ ({child_count} items)")
                except Exception:
                    file_list.append(f"  {item.name}/")
            elif item.suffix not in skip_files:
                try:
                    size = item.stat().st_size
                    if size < 100_000:
                        file_list.append(f"  {item.name} ({size} bytes)")
                    else:
                        file_list.append(f"  {item.name} ({size // 1024}KB)")
                except Exception:
                    file_list.append(f"  {item.name}")
    except PermissionError:
        lines.append("  (permission denied)")

    if file_list:
        lines.append(f"\nFiles in {work_dir.name}/:")
        lines.extend(file_list[:50])

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
    """Execute a task using direct LLM + tool calls with project context."""
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=90.0, max_retries=2)

    project_ctx = _get_project_context(cwd)

    default_prompt = (
        f"You are {agent_role}. You are working in a real project on the user's machine.\n\n"
        f"PROJECT CONTEXT:\n{project_ctx}\n\n"
        "TOOLS AVAILABLE:\n"
        "1. read_file(file_path) - Read any file. Use relative paths from the working directory.\n"
        "2. write_file(file_path, content) - Write content to a file.\n"
        "3. execute_shell(command) - Run any shell command (ls, cat, grep, git, python, etc.).\n\n"
        "HOW TO USE TOOLS:\n"
        "Output a JSON object on its OWN line (no other text before or after):\n"
        '{"name": "read_file", "args": {"file_path": "README.md"}}\n'
        '{"name": "execute_shell", "args": {"command": "ls -la"}}\n'
        '{"name": "write_file", "args": {"file_path": "output.txt", "content": "hello"}}\n\n'
        "RULES:\n"
        "- Always use tools to read files, list directories, or run commands.\n"
        "- Do NOT guess file contents - read them first.\n"
        "- Use relative paths (relative to the working directory shown above).\n"
        "- After using tools and getting results, provide a clear summary.\n"
        "- If the user asks to read a file, USE the read_file tool immediately.\n"
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

        content = response.choices[0].message.content or ""
        if not content and response.choices[0].message.reasoning:
            content = response.choices[0].message.reasoning

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
                    tools_used.append({"tool": tool_name, "args": tool_args, "result": str(result)[:500]})
                    messages.append({"role": "user", "content": f"Tool [{tool_name}] result:\n{result}"})
                else:
                    messages.append({"role": "user", "content": f"Unknown tool: {tool_name}. Use read_file, write_file, or execute_shell."})
            except json.JSONDecodeError:
                messages.append({"role": "user", "content": f"Invalid tool format. Use JSON: {{\"name\": \"tool\", \"args\": {{...}}}}"})

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
        found = re.findall(pattern, content, re.DOTALL)
        for f in found:
            try:
                data = json.loads(f.strip())
                if "name" in data and "args" in data:
                    matches.append(f.strip())
            except json.JSONDecodeError:
                pass

    if matches:
        return matches

    # <tool_call>name<arg_key>key</arg_key><arg_value>val</arg_value></tool_call>
    tc_pattern = r'<tool_call>(\w+)(.*?)</tool_call>'
    for tool_name, args_str in re.findall(tc_pattern, content, re.DOTALL):
        args = {}
        for m in re.finditer(r'<arg_key>(\w+)</arg_key><arg_value>(.*?)</arg_value>', args_str, re.DOTALL):
            args[m.group(1)] = m.group(2)
        if args:
            matches.append(json.dumps({"name": tool_name, "args": args}))

    return matches
