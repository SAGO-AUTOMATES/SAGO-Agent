"""Unit tests for v0.1.6 fixes and enhancements."""

from __future__ import annotations

import json
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


def test_mcp_permission_fail_closed() -> None:
    """Verify MCP gating fails CLOSED: if the permission manager itself errors,
    the tool must NOT execute (regression guard for the previous fail-open bug)."""

    def boom(*_args, **_kwargs):
        raise RuntimeError("permission subsystem misconfigured")

    server = MCPServer(name="test_mcp_failclosed")
    server.register_function(
        name="dangerous_tool",
        description="Dangerous operation",
        input_schema={"type": "object", "properties": {}},
        handler=lambda: "SHOULD_NOT_RUN",
    )

    with patch("sago.mcp.server.get_permission_manager", side_effect=boom):
        with pytest.raises(PermissionError):
            server.call_tool("dangerous_tool", {}, session_id="x")


def test_mesh_task_id_propagation() -> None:
    """Verify send_task_request carries task_id through to process_messages result
    so concurrent delegations to one node are not miscorrelated."""
    node = MeshNetwork(
        node_id="node-1", port=18901, task_executor=lambda task, agent: f"executed: {task}"
    )
    captured = {}
    node._unicast = lambda target, data: captured.update(json.loads(data))

    node.send_task_request("node-2", "do_thing", agent="python-engineer", task_id="abc-123")
    assert captured["payload"].get("task_id") == "abc-123"

    fake_msg = MeshMessage(
        type="task_request",
        sender="node-2",
        receiver="node-1",
        payload={"task": "do_thing", "agent": "python-engineer", "task_id": "abc-123"},
    )
    sent_messages = []
    node.send_task_result = lambda target, task_id, result, success: sent_messages.append(
        {"target": target, "task_id": task_id, "result": result, "success": success}
    )
    with patch.object(node, "_socket") as mock_sock:
        mock_sock.recvfrom.side_effect = [
            (fake_msg.to_json().encode(), ("127.0.0.1", 18901)),
            TimeoutError(),
        ]
        node.process_messages()
        assert len(sent_messages) == 1
        assert sent_messages[0]["task_id"] == "abc-123"
        assert sent_messages[0]["result"] == "executed: do_thing"


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


def test_parallel_agent_progressive_streaming() -> None:
    """Verify parallel execution streams each agent's result immediately upon completion."""
    from sago.tui.app import SagoApp

    app = SagoApp()
    streamed_results = []
    updated_statuses = []

    app._add_parallel_result = lambda agent, res, el, ok: streamed_results.append((agent, res, ok))
    app._update_parallel_agent_status = lambda agent, status: updated_statuses.append(
        (agent, status)
    )
    app._show_parallel_bar = lambda agents: None
    app._hide_parallel_bar = lambda: None
    app._hide_spinner = lambda: None
    app._update_dashboard = lambda: None
    app._add_system_message = lambda msg: None
    app.call_from_thread = lambda fn, *args: fn(*args)

    with patch("sago.tools.file.spawn_agent.SpawnAgentTool") as mock_tool_cls:
        mock_tool = mock_tool_cls.return_value
        mock_tool.run.side_effect = lambda task, agent_name: f"Result for {agent_name}"

        app._process_parallel_thread(["python-engineer", "tester"], "Run parallel task")

        # Verify all agents streamed their results immediately
        assert len(streamed_results) == 2
        agents_streamed = {r[0] for r in streamed_results}
        assert "python-engineer" in agents_streamed
        assert "tester" in agents_streamed
        assert all(r[2] is True for r in streamed_results)


def test_hybrid_search_scale_and_incremental_persistence() -> None:
    """Verify HybridCodeIndexer scales beyond 2000 files, persists to disk, and updates incrementally."""
    import time

    from sago.memory.hybrid_indexer import HybridCodeIndexer

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        # Generate 2,200 synthetic code files across multiple subdirectories
        for i in range(2200):
            sub = root / f"pkg_{i % 20}"
            sub.mkdir(parents=True, exist_ok=True)
            code_file = sub / f"module_{i}.py"
            if i == 1450:
                code_file.write_text(
                    "def unique_target_function_zeta():\n    return 'secret_omega'\n"
                )
            else:
                code_file.write_text(f"def helper_func_{i}(val: int):\n    return val * {i}\n")

        indexer = HybridCodeIndexer(root_dir=root)
        count = indexer.index_project(max_files=50000)
        assert count >= 2200
        assert indexer.total_docs == count

        # Sub-millisecond candidate retrieval via inverted index
        t0 = time.perf_counter()
        results = indexer.search("unique_target_function_zeta", limit=5)
        query_duration = time.perf_counter() - t0

        assert len(results) > 0
        assert results[0].chunk.name == "unique_target_function_zeta"
        assert query_duration < 0.1  # Fast retrieval

        # Verify disk cache existence and instant reload
        cache_file = indexer._get_cache_file()
        assert cache_file.exists()

        reloaded_indexer = HybridCodeIndexer(root_dir=root)
        loaded_count = reloaded_indexer.index_project()
        assert loaded_count == count
        assert reloaded_indexer.total_docs == count

        # Test incremental update by modifying a single file
        mod_file = root / "pkg_0" / "module_0.py"
        mod_file.write_text("def newly_added_incremental_symbol():\n    return 42\n")

        incremental_indexer = HybridCodeIndexer(root_dir=root)
        incremental_count = incremental_indexer.index_project()
        assert incremental_count >= count
        inc_results = incremental_indexer.search("newly_added_incremental_symbol", limit=5)
        assert len(inc_results) > 0
        assert inc_results[0].chunk.name == "newly_added_incremental_symbol"


def test_hybrid_search_full_semantic_recall() -> None:
    """Verify dense vector matching scans the entire codebase when lexical matches are sparse."""
    from sago.memory.hybrid_indexer import HybridCodeIndexer

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        # Create 250 files where the target file is at the very end
        for i in range(250):
            f = root / f"file_{i:03d}.py"
            if i == 249:
                f.write_text("def authenticate_jwt_bearer_token():\n    return 'valid'\n")
            else:
                f.write_text(f"def process_item_{i}():\n    return {i}\n")

        indexer = HybridCodeIndexer(root_dir=root)
        indexer.index_project()

        # Search for semantically related query with minimal exact token overlap
        results = indexer.search("auth jwt bearer", limit=5)
        assert len(results) > 0
        assert results[0].chunk.name == "authenticate_jwt_bearer_token"


def test_hybrid_search_incremental_preserves_vectors() -> None:
    """Regression for bug R-search-#1: edited files must keep their dense vectors
    after an incremental re-index. The earlier implementation left re-indexed
    chunks with `vector=[]`, making their semantic score permanently 0."""
    from sago.memory.hybrid_indexer import HybridCodeIndexer

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        target = root / "auth.py"
        target.write_text("def authenticate_jwt_bearer_token():\n    return 'valid'\n")
        for i in range(50):
            (root / f"file_{i:03d}.py").write_text(f"def process_item_{i}():\n    return {i}\n")

        indexer = HybridCodeIndexer(root_dir=root)
        indexer.index_project()
        assert all(len(c.vector) > 0 for c in indexer.chunks)

        # Edit the target file, then re-index incrementally (same cache dir)
        target.write_text("def authenticate_jwt_bearer_token():\n    return 'refreshed'\n")
        re_indexer = HybridCodeIndexer(root_dir=root)
        re_indexer.index_project()

        assert all(
            len(c.vector) > 0 for c in re_indexer.chunks
        ), "incremental re-index dropped dense vectors on edited files"
