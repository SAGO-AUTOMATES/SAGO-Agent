"""Unit tests for next-gen features: AsyncExecutor, Sandboxed execution, and HTML/Markdown reports."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from sago.engine.async_executor import AsyncAgentExecutor, execute_parallel_tasks
from sago.tools.system.sandbox import SandboxedExecutor, SandboxRunTool
from sago.utils.report_generator import generate_html_report, generate_markdown_report


@pytest.mark.asyncio
async def test_async_agent_executor():
    """Verify AsyncAgentExecutor completes tasks and streams tokens asynchronously."""
    executor = AsyncAgentExecutor(model="mock/test", provider_name="mock")
    tokens = []
    res = await executor.execute_task(
        task="Write a python function to add two numbers",
        on_token=lambda tok: tokens.append(tok),
    )
    assert res["success"] is True
    assert len(res["output"]) > 0
    assert len(tokens) > 0

    stream_tokens = []
    async for tok in executor.stream_task("Say hello"):
        stream_tokens.append(tok)
    assert len(stream_tokens) > 0


@pytest.mark.asyncio
async def test_execute_parallel_tasks():
    """Verify execute_parallel_tasks runs concurrent agent tasks with bounded concurrency."""
    tasks = [
        {"task": "Task 1: Generate schema", "provider": "mock"},
        {"task": "Task 2: Generate endpoints", "provider": "mock"},
        {"task": "Task 3: Write tests", "provider": "mock"},
    ]
    results = await execute_parallel_tasks(tasks, max_concurrency=2)
    assert len(results) == 3
    for r in results:
        assert r["success"] is True


def test_sandboxed_executor():
    """Verify SandboxedExecutor executes commands in an isolated temp directory."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "sample.txt").write_text("Hello Sandbox")

        executor = SandboxedExecutor(workspace_root=str(root))
        res = executor.run_command("cat sample.txt")
        assert res["success"] is True
        assert "Hello Sandbox" in res["stdout"]

        # Tool interface
        tool = SandboxRunTool()
        t_res = tool.execute(command="echo 'Sandboxed safe run'")
        assert t_res.success is True
        assert "Sandboxed safe run" in t_res.output


def test_report_generators():
    """Verify HTML and Markdown report generation from session traces."""
    session_data = {
        "task": "Build REST API with JWT",
        "model": "gpt-4o",
        "elapsed": 2.45,
        "success": True,
        "tokens_in": 1200,
        "tokens_out": 450,
        "output": "API created successfully in server.py",
        "tool_calls": [
            {
                "tool": "write_file",
                "args": {"file_path": "server.py"},
                "result": "File written",
            }
        ],
    }

    html = generate_html_report(session_data)
    assert "<!DOCTYPE html>" in html
    assert "Build REST API with JWT" in html
    assert "server.py" in html
    assert "PASSED" in html

    md = generate_markdown_report(session_data)
    assert "# ⚡ SAGO Execution Report" in md
    assert "Build REST API with JWT" in md
    assert "server.py" in md
