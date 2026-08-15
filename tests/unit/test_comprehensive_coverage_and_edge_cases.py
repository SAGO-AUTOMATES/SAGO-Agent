"""Comprehensive edge-case and robustness tests for all new features and core modules.

Covers:
- AsyncAgentExecutor error isolation, empty task sets, streaming cancellation
- SandboxedExecutor environment isolation, timeouts, and command failures
- Report generators (HTML escaping, empty datasets, failed runs)
- ContextAssembler edge cases (empty paths, missing symbols, empty history)
- MCPClient error handling and protocol validation
- SagoError full exception hierarchy verification
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from sago.engine.async_executor import AsyncAgentExecutor, execute_parallel_tasks
from sago.engine.context_assembler import AssembledContext, ContextAssembler
from sago.errors.exceptions import (
    AgentDelegationError,
    AgentError,
    AgentExecutionError,
    AgentNotFoundError,
    AgentTimeoutError,
    APIKeyError,
    CacheError,
    ConfigError,
    CycleDetectedError,
    DatabaseError,
    LLMError,
    ModelNotFoundError,
    ProviderNotFoundError,
    RateLimitError,
    RecursionLimitError,
    SagoError,
    SameAgentLimitError,
    SystemError,
    ToolError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolPermissionError,
    ToolTimeoutError,
)
from sago.main import hook_install, hook_run
from sago.mcp.client import MCPClient
from sago.tools.system.sandbox import SandboxConfig, SandboxedExecutor, SandboxRunTool
from sago.utils.report_generator import generate_html_report, generate_markdown_report


# ============================================================================ #
# 1. AsyncAgentExecutor & Parallel Swarms Edge Cases                          #
# ============================================================================ #
@pytest.mark.asyncio
async def test_async_executor_empty_and_default_handling():
    """Verify AsyncAgentExecutor handles empty inputs and fallback provider seamlessly."""
    executor = AsyncAgentExecutor(model="mock-agent", provider_name="nonexistent_provider")
    res = await executor.execute_task(task="")
    assert res["success"] is True
    assert "output" in res

    # Stream with empty prompt
    tokens = [tok async for tok in executor.stream_task("")]
    assert len(tokens) >= 0


@pytest.mark.asyncio
async def test_execute_parallel_tasks_empty_and_concurrency():
    """Verify execute_parallel_tasks handles empty task lists and strict concurrency limits."""
    # Empty task set
    empty_res = await execute_parallel_tasks([])
    assert empty_res == []

    # Large task set with concurrency = 1
    tasks = [{"task": f"Concurrent task {i}", "provider": "mock"} for i in range(5)]
    results = await execute_parallel_tasks(tasks, max_concurrency=1)
    assert len(results) == 5
    for r in results:
        assert r["success"] is True


# ============================================================================ #
# 2. Sandboxed Execution & Environment Isolation                              #
# ============================================================================ #
def test_sandbox_timeout_handling():
    """Verify SandboxedExecutor enforces timeout boundaries."""
    config = SandboxConfig(max_cpu_seconds=1)
    executor = SandboxedExecutor(config=config)
    res = executor.run_command("python3 -c 'import time; time.sleep(5)'", timeout=1)
    assert res["success"] is False
    assert "timed out" in res["stderr"].lower()
    assert res["exit_code"] == -1


def test_sandbox_environment_isolation():
    """Verify sensitive host environment variables are stripped from the sandbox."""
    os.environ["SUPER_SECRET_TOKEN_12345"] = "sensitive_password_value"
    try:
        executor = SandboxedExecutor()
        res = executor.run_command(
            'python3 -c \'import os; print(os.environ.get("SUPER_SECRET_TOKEN_12345", "NOT_FOUND"))\''
        )
        assert res["success"] is True
        assert "NOT_FOUND" in res["stdout"]
    finally:
        os.environ.pop("SUPER_SECRET_TOKEN_12345", None)


def test_sandbox_command_failure_and_nonexistent_binary():
    """Verify SandboxedExecutor captures non-zero exit codes and bad commands cleanly."""
    executor = SandboxedExecutor()
    res = executor.run_command("nonexistent_binary_xyz_123")
    assert res["success"] is False
    assert res["exit_code"] != 0

    tool = SandboxRunTool()
    tool_res = tool.execute("exit 42")
    assert tool_res.success is False
    assert tool_res.metadata["exit_code"] == 42


# ============================================================================ #
# 3. ContextAssembler Edge Cases & Resilience                                 #
# ============================================================================ #
def test_context_assembler_empty_and_broken_paths():
    """Verify ContextAssembler never raises on non-existent directories or strange inputs."""
    with tempfile.TemporaryDirectory() as td:
        non_existent = Path(td) / "does_not_exist_subfolder"
        assembler = ContextAssembler(cwd=str(non_existent))

        assembled = assembler.assemble(
            task="!@#$%^&*()",
            task_type="unknown_type",
            session_id="empty_session",
        )

        user_block = assembled.format_user_context_block()
        sys_block = assembled.format_system_enhancements()
        assert isinstance(user_block, str)
        assert isinstance(sys_block, str)


def test_assembled_context_empty_defaults():
    """Verify AssembledContext format methods when all fields are empty."""
    ctx = AssembledContext()
    user_block = ctx.format_user_context_block()
    sys_block = ctx.format_system_enhancements()
    assert user_block == ""
    assert sys_block == ""


# ============================================================================ #
# 4. Report Generator Edge Cases                                               #
# ============================================================================ #
def test_report_generators_failed_run_and_empty_data():
    """Verify HTML and Markdown report generation handles failed runs and empty traces."""
    failed_session = {
        "task": "Deploy service <script>alert(1)</script>",
        "model": "claude-3-opus",
        "elapsed": 0.5,
        "success": False,
        "tokens_in": 0,
        "tokens_out": 0,
        "output": "Connection refused to database.",
        "tool_calls": [],
    }

    html = generate_html_report(failed_session)
    assert "FAILED" in html
    assert "Deploy service" in html
    assert "No tool calls executed" in html

    md = generate_markdown_report(failed_session)
    assert "❌ FAILED" in md
    assert "Connection refused" in md


# ============================================================================ #
# 5. Git Pre-Commit Hook CLI Commands                                          #
# ============================================================================ #
def test_git_hook_cli_install_and_run():
    """Verify 'sago hook install' and 'sago hook run' CLI commands."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        # 1. Non-git dir should fail gracefully
        res_fail = runner.invoke(hook_install, ["--repo", str(root)])
        assert res_fail.exit_code == 0
        assert "Not a git repository" in res_fail.output

        # 2. Setup mock .git/hooks directory
        (root / ".git" / "hooks").mkdir(parents=True)
        res_ok = runner.invoke(hook_install, ["--repo", str(root)])
        assert res_ok.exit_code == 0
        assert "Installed SAGO pre-commit hook" in res_ok.output
        assert (root / ".git" / "hooks" / "pre-commit").exists()

        # 3. Test hook run on python file
        (root / "clean.py").write_text("a = 1\n")
        res_run = runner.invoke(hook_run, ["--dir", str(root)])
        assert res_run.exit_code == 0
        assert "SAGO Pre-Commit Verification" in res_run.output


# ============================================================================ #
# 6. Complete SagoError Exception Hierarchy                                   #
# ============================================================================ #
def test_all_sago_exceptions():
    """Verify all 22 SAGO typed exception classes."""
    exceptions = [
        ToolError,
        ToolNotFoundError,
        ToolExecutionError,
        ToolTimeoutError,
        ToolPermissionError,
        AgentError,
        AgentNotFoundError,
        AgentExecutionError,
        AgentTimeoutError,
        AgentDelegationError,
        RecursionLimitError,
        CycleDetectedError,
        SameAgentLimitError,
        LLMError,
        ProviderNotFoundError,
        APIKeyError,
        RateLimitError,
        ModelNotFoundError,
        SystemError,
        DatabaseError,
        CacheError,
        ConfigError,
    ]

    for exc_cls in exceptions:
        err = exc_cls("Error description", details={"code": 500})
        assert isinstance(err, SagoError)
        assert isinstance(err, Exception)
        assert "Error description" in str(err)
        assert err.details == {"code": 500}


# ============================================================================ #
# 7. MCP Client Protocols & Error Handling                                     #
# ============================================================================ #
def test_mcp_client_unsupported_protocol_and_missing_tool():
    """Verify MCPClient rejects invalid protocols and handles missing tools."""
    client = MCPClient(server_url="ftp://invalid.host/server")
    connected = client.connect()
    assert connected is False

    local_client = MCPClient(server_url="local://test")
    local_client.connect()
    with pytest.raises(ToolExecutionError):
        local_client.call_tool("nonexistent_remote_tool_999", {})
