"""Unit tests for context assembler, exceptions hierarchy, and MCP client."""

from __future__ import annotations

import tempfile
from pathlib import Path

from sago.engine.context_assembler import ContextAssembler
from sago.errors import (
    AgentNotFoundError,
    APIKeyError,
    DatabaseError,
    RateLimitError,
    SagoError,
    ToolExecutionError,
)
from sago.errors.exceptions import (
    CycleDetectedError,
    ModelNotFoundError,
    RecursionLimitError,
)
from sago.mcp.client import MCPClient, MCPRemoteTool
from sago.memory.compaction import HierarchicalMemoryPyramid
from sago.memory.learning_store import get_learning_store


def test_exception_hierarchy():
    """Verify standard error classes inherit from SagoError and instantiate correctly."""
    err = ToolExecutionError("File not writeable", details={"path": "/var/log/syslog"})
    assert isinstance(err, SagoError)
    assert "File not writeable" in str(err)
    assert err.details["path"] == "/var/log/syslog"

    agent_err = AgentNotFoundError("missing-agent")
    assert isinstance(agent_err, SagoError)

    cycle_err = CycleDetectedError("Cycle A->B->A")
    assert isinstance(cycle_err, SagoError)

    rec_err = RecursionLimitError("Depth 6 exceeded")
    assert isinstance(rec_err, SagoError)

    llm_err = RateLimitError("429 Too Many Requests")
    assert isinstance(llm_err, SagoError)

    model_err = ModelNotFoundError("gpt-5")
    assert isinstance(model_err, SagoError)

    api_err = APIKeyError("Missing OPENAI_API_KEY")
    assert isinstance(api_err, SagoError)

    db_err = DatabaseError("Disk full")
    assert isinstance(db_err, SagoError)


def test_mcp_client_tools_and_call():
    """Verify MCPClient registers remote tools and executes tool calls."""
    client = MCPClient(server_url="local://mock")
    assert client.connect() is True

    tool = client.register_remote_tool(
        name="remote_calculator",
        description="Calculate math expression",
        input_schema={
            "type": "object",
            "properties": {"expr": {"type": "string"}},
            "required": ["expr"],
        },
    )
    assert isinstance(tool, MCPRemoteTool)
    tools = client.list_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "remote_calculator"

    # Tool execution
    res = client.call_tool("remote_calculator", {"expr": "2 + 2"})
    assert "content" in res or "result" in res


def test_learning_store_forwarder():
    """Verify sago.memory.learning_store imports and functions as expected."""
    ls = get_learning_store()
    assert ls is not None
    ls.record_error_fix("ConnectionRefusedError: port 8000", "Start backend server first")
    fix = ls.get_known_fixes("Got ConnectionRefusedError: port 8000 on startup")
    assert fix is not None
    assert "Start backend server first" in fix


def test_context_assembler_pipeline():
    """Verify ContextAssembler builds full multi-tiered context and smart prompt enhancements."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "main.py").write_text("class Server:\n    def start(self):\n        pass\n")
        (root / "pyproject.toml").write_text("[project]\nname = 'demo'\n")

        assembler = ContextAssembler(cwd=str(root))
        pyramid = HierarchicalMemoryPyramid(
            architectural_goals=["Build microservice with JWT auth"],
            architectural_decisions=["Use FastAPI and SQLite WAL"],
            modified_files=["main.py", "auth.py"],
        )

        assembled = assembler.assemble(
            task="Fix authentication bug in Server class",
            task_type="fix",
            agent_name="python-engineer",
            available_tools=["read_file", "edit_file"],
            pyramid=pyramid,
            session_id="test_session",
        )

        user_block = assembled.format_user_context_block()
        sys_block = assembled.format_system_enhancements()

        assert "Project Structure" in user_block
        assert "main.py" in user_block
        assert "HIERARCHICAL MEMORY PYRAMID" in sys_block
        assert "Build microservice with JWT auth" in sys_block
        assert "Use FastAPI and SQLite WAL" in sys_block
        assert "AUTHORIZED AGENT HANDOFF TARGETS" in sys_block
        assert len(assembled.handoff_targets) > 0
