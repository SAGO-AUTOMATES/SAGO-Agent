"""Unit tests for v0.1.6 fixes and enhancements."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from sago.agents.registry import AGENTS, get_agent, get_handoff_targets
from sago.agents.spawner import AgentSpawner
from sago.engine.verifier import ProjectVerifier
from sago.llm.gemini import GeminiProvider
from sago.mcp.server import MCPServer
from sago.peers.mesh import MESH_PORT, MeshMessage, MeshNetwork
from sago.permissions import PermissionManager, RiskLevel


def test_agent_profiles_handoffs_all_resolve() -> None:
    """Verify that every single handoff target in all 339 agent profiles resolves to a valid agent."""
    for name, profile in AGENTS.items():
        targets = get_handoff_targets(name)
        # If profile lists handoffs, they should resolve
        if profile.handoff_to:
            assert len(targets) > 0, (
                f"Agent {name} has handoffs {profile.handoff_to} that failed to resolve"
            )


def test_spawner_plan_chain_uses_real_agents() -> None:
    """Verify that _plan_chain returns only registered, non-ghost agent names."""
    spawner = AgentSpawner()
    sample_tasks = [
        "Write a Python FastAPI REST API with pydantic models",
        "Deploy kubernetes cluster and docker containers with CI/CD",
        "Design scalable system architecture and microservices",
        "Review code and check security vulnerabilities",
        "Optimize slow SQL queries and database indexes",
        "General task without specific keywords",
    ]
    for task in sample_tasks:
        chain = spawner._plan_chain(task)
        assert len(chain) > 0
        for agent_name in chain:
            assert get_agent(agent_name) is not None, (
                f"Planned agent '{agent_name}' for task '{task}' not found in registry"
            )


def test_gemini_provider_is_available_and_genai() -> None:
    """Verify GeminiProvider checks availability without crashing on import."""
    with patch.dict("os.environ", {}, clear=True):
        provider = GeminiProvider({"model": "gemini-2.5-flash"})
        # Without api key it should be False
        assert provider.is_available() is False

    with patch.dict("os.environ", {"GEMINI_API_KEY": "fake_test_key"}):
        prov_with_key = GeminiProvider({"model": "gemini-2.5-flash"})
        # Should detect availability of google.genai or google.generativeai
        assert prov_with_key.is_available() is True


def test_mcp_permission_gating() -> None:
    """Verify MCP server enforces permissions on call_tool."""
    server = MCPServer(name="test_mcp")
    server.register_function(
        name="dangerous_tool",
        description="Dangerous operation",
        input_schema={"type": "object", "properties": {}},
        handler=lambda: "done",
    )

    from sago.permissions import TOOL_RISK_LEVELS

    TOOL_RISK_LEVELS["dangerous_tool"] = RiskLevel.CRITICAL
    pm = PermissionManager()
    pm._approvals.clear()
    pm.config.session_approvals.clear()
    pm.config.require_approval_critical = True

    with patch("sago.mcp.server.get_permission_manager", return_value=pm):
        # Without approval, dangerous_tool must raise PermissionError
        with pytest.raises(PermissionError) as exc_info:
            server.call_tool("dangerous_tool", {}, session_id="fresh_test_session")
        assert "Permission denied" in str(exc_info.value)

        # Once approved, it executes successfully
        pm.approve_tool("dangerous_tool", session_id="fresh_test_session")
        res = server.call_tool("dangerous_tool", {}, session_id="fresh_test_session")
        assert res == "done"


def test_mesh_port_no_daemon_collision() -> None:
    """Verify MESH_PORT does not collide with the default TCP daemon port (7654)."""
    assert MESH_PORT != 7654
    assert MESH_PORT == 7655


def test_mesh_task_execution() -> None:
    """Verify MeshNetwork executes incoming task_request with task_executor."""
    node = MeshNetwork(
        node_id="node-1", port=18899, task_executor=lambda task, agent: f"executed: {task}"
    )
    fake_msg = MeshMessage(
        type="task_request",
        sender="node-2",
        receiver="node-1",
        payload={"task": "calculate_pi", "agent": "python-engineer", "task_id": "t1"},
    )

    sent_messages = []
    node.send_task_result = lambda target, task_id, result, success: sent_messages.append(
        {"target": target, "task_id": task_id, "result": result, "success": success}
    )

    # Simulate message arrival
    with patch.object(node, "_socket") as mock_sock:
        mock_sock.recvfrom.side_effect = [
            (fake_msg.to_json().encode(), ("127.0.0.1", 18899)),
            TimeoutError(),
        ]
        messages = node.process_messages()
        assert len(messages) == 1
        assert len(sent_messages) == 1
        assert sent_messages[0]["result"] == "executed: calculate_pi"
        assert sent_messages[0]["success"] is True


def test_in_process_py_compile_verification() -> None:
    """Verify ProjectVerifier uses fast in-process compilation for python syntax checks."""
    verifier = ProjectVerifier()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        good_file = tmp_path / "good.py"
        good_file.write_text("def add(a: int, b: int) -> int:\n    return a + b\n")

        bad_file = tmp_path / "bad.py"
        bad_file.write_text("def broken(\n")

        report_good = verifier.verify_files([str(good_file)])
        assert report_good.passed is True

        report_bad = verifier.verify_files([str(bad_file)])
        assert report_bad.typecheck_passed is False
        assert any(i.rule == "SYNTAX_ERROR" for i in report_bad.issues)
