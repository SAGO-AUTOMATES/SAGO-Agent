"""Simple Agent Executor - Bypasses CrewAI's internal LLM handling."""

from __future__ import annotations

import json
import re
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


def execute_agent_task(
    task: str,
    agent_role: str = "Python Engineer",
    system_prompt: str = "",
    model: str = "openrouter/free",
    api_key: str = "",
    base_url: str = "https://openrouter.ai/api/v1",
    max_tokens: int = 2048,
    max_iterations: int = 5,
) -> dict[str, Any]:
    """Execute a task using direct LLM + tool calls.
    
    Returns dict with 'success', 'output', 'tool_calls', 'iterations'.
    """
    client = OpenAI(api_key=api_key, base_url=base_url, timeout=60.0, max_retries=2)
    
    tools_used = []
    iterations = 0
    content = ""
    
    messages = [
        {"role": "system", "content": system_prompt or (
            f"You are a {agent_role}. You have access to these tools:\n"
            "- write_file(file_path, content): Write content to a file\n"
            "- read_file(file_path): Read a file\n"
            "- execute_shell(command): Run a shell command\n\n"
            "To use a tool, output EXACTLY this format (no other text):\n"
            '{"name": "write_file", "args": {"file_path": "/path/to/file.py", "content": "code here"}}\n\n'
            "After using tools, output your final response.\n"
            "IMPORTANT: When writing Python code, put the code directly in the content field, no markdown."
        )},
        {"role": "user", "content": task},
    ]
    
    for i in range(max_iterations):
        iterations = i + 1
        
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.3,
        )
        
        content = response.choices[0].message.content or ""
        messages.append({"role": "assistant", "content": content})
        
        # Look for tool calls in various formats
        tool_matches = []
        
        # First, try to parse the entire content as JSON (most common case)
        try:
            data = json.loads(content)
            if "name" in data and "args" in data:
                tool_matches = [content]
        except json.JSONDecodeError:
            pass
        
        if not tool_matches:
            # Try ```tool blocks
            tool_pattern = r'```tool\s*\n(.*?)\n```'
            tool_matches = re.findall(tool_pattern, content, re.DOTALL)
        
        if not tool_matches:
            # Try ```json blocks
            json_pattern = r'```json\s*\n(.*?)\n```'
            tool_matches = re.findall(json_pattern, content, re.DOTALL)
        
        if not tool_matches:
            # Try <|tool_call>format
            tc_pattern = r'<\|tool_call\>.*?:([\w]+)\{([^}]+)\}<tool_call\|>'
            tc_matches = re.findall(tc_pattern, content, re.DOTALL)
            for tool_name, args_str in tc_matches:
                # Parse args like command: "..." or file_path: "...", content: "..."
                args = {}
                # Simple parsing for key: "value" pairs
                for match in re.finditer(r'(\w+):\s*"([^"]*)"', args_str):
                    args[match.group(1)] = match.group(2)
                if args:
                    tool_matches.append(json.dumps({"name": tool_name, "args": args}))
        
        if not tool_matches:
            # Try <tool_call>write_file<arg_key>...</arg_key><arg_value>...</arg_value></tool_call>
            tc_pattern = r'<tool_call>(\w+)(.*?)</tool_call>'
            tc_matches = re.findall(tc_pattern, content, re.DOTALL)
            for tool_name, args_str in tc_matches:
                args = {}
                # Parse <arg_key>name</arg_key><arg_value>value</arg_value> pairs
                # Also handle malformed tags like arg_key>name</arg_key>
                key_pattern = r'<arg_key>(\w+)</arg_key><arg_value>(.*?)</arg_value>'
                for match in re.finditer(key_pattern, args_str, re.DOTALL):
                    args[match.group(1)] = match.group(2)
                if not args:
                    # Try alternate format
                    key_pattern = r'arg_key>(\w+)</arg_key><arg_value>(.*?)</arg_value>'
                    for match in re.finditer(key_pattern, args_str, re.DOTALL):
                        args[match.group(1)] = match.group(2)
                if args:
                    tool_matches.append(json.dumps({"name": tool_name, "args": args}))
        
        if not tool_matches:
            # Try <|tool_call>call:toolname{args:{key:value, ...}}<tool_call|>
            tc_pattern = r'<\|tool_call\>call:(\w+)\{args:\{(.*?)\}\}<tool_call\|>'
            tc_matches = re.findall(tc_pattern, content, re.DOTALL)
            for tool_name, args_str in tc_matches:
                args = {}
                # Parse key:value pairs (values can be multi-line)
                for match in re.finditer(r'(\w+):(.*?)(?=,\s*\w+:|$)', args_str, re.DOTALL):
                    key = match.group(1)
                    value = match.group(2).strip().rstrip('}')
                    # Handle nested braces in content
                    if value.startswith('{'):
                        # Find matching closing brace
                        depth = 0
                        for i, c in enumerate(value):
                            if c == '{': depth += 1
                            elif c == '}':
                                depth -= 1
                                if depth == 0:
                                    value = value[:i+1]
                                    break
                    args[key] = value
                if args:
                    tool_matches.append(json.dumps({"name": tool_name, "args": args}))
        
        if not tool_matches:
            # No more tool calls, return final response
            return {
                "success": True,
                "output": content,
                "tool_calls": tools_used,
                "iterations": iterations,
            }
        
        # Execute tool calls
        for match in tool_matches:
            try:
                tool_data = json.loads(match) if isinstance(match, str) else match
                tool_name = tool_data.get("name", "")
                tool_args = tool_data.get("args", {})
                
                tool_class = TOOL_MAP.get(tool_name)
                if tool_class:
                    tool_instance = tool_class()
                    result = tool_instance.run(**tool_args)
                    tools_used.append({"tool": tool_name, "args": tool_args, "result": result})
                    messages.append({"role": "user", "content": f"Tool result: {result}"})
                else:
                    messages.append({"role": "user", "content": f"Unknown tool: {tool_name}"})
            except json.JSONDecodeError:
                messages.append({"role": "user", "content": f"Could not parse tool call: {match}"})
        
        # If we executed tools, continue to next iteration
        if tool_matches:
            continue
    
    return {
        "success": True,
        "output": content,
        "tool_calls": tools_used,
        "iterations": iterations,
    }
