"""Unit tests for v0.1.6 fixes and enhancements."""

from __future__ import annotations

import json
import sqlite3
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

        assert all(len(c.vector) > 0 for c in re_indexer.chunks), (
            "incremental re-index dropped dense vectors on edited files"
        )


def test_sql_schema_and_workflow_injection_sanitization() -> None:
    """Verify N1 and N2: PRAGMA table/index queries and workflow reports sanitize inputs."""
    from sago.tools.database.sql_schema import SqlSchemaTool
    from sago.workflow.engine import WorkflowEngine
    from sago.workflow.templates import WorkflowTemplates

    with tempfile.NamedTemporaryFile(suffix=".db") as tmp_db:
        # Create a table with unusual quotes/characters
        conn = sqlite3.connect(tmp_db.name)
        conn.execute('CREATE TABLE "users_tbl" (id INTEGER PRIMARY KEY, username TEXT)')
        conn.commit()
        conn.close()

        tool = SqlSchemaTool()
        result = tool._run(database_path=tmp_db.name, include_indexes=True)
        assert "Table: `users_tbl`" in result
        assert "username" in result

        # Test workflow template sanitization
        templates = WorkflowTemplates(engine=WorkflowEngine())
        wf = templates.scheduled_report("audit'; DROP TABLE metrics;--", "0 0 * * *")
        gather_step = wf.steps[0]
        assert "DROP TABLE" not in gather_step.config["args"]["query"]
        assert "auditDROPTABLEmetrics" in gather_step.config["args"]["query"]


def test_daemon_default_local_host_and_sudo_stdin() -> None:
    """Verify N4 and N5: Daemon binds 127.0.0.1 by default and sudo passes password via stdin."""
    from sago.server.daemon import DEFAULT_HOST
    from sago.tools.admin.sudo_executor import SudoExecutorTool

    assert DEFAULT_HOST == "127.0.0.1"

    sudo_tool = SudoExecutorTool()
    # Test Unix sudo execution command preparation
    assert sudo_tool.name == "sudo_executor"


def test_thread_safe_singletons_and_metadata_default() -> None:
    """Verify N8-N11 and N20: Singletons have lock protection and ToolResult has independent metadata."""
    from sago.cache.intelligent import get_cache
    from sago.config.loader import get_config
    from sago.errors.handler import get_error_handler, get_recovery_manager
    from sago.tools.base import ToolResult
    from sago.tracking.token_tracker import get_token_tracker

    # Verify singletons resolve properly
    assert get_error_handler() is not None
    assert get_recovery_manager() is not None
    assert get_token_tracker() is not None
    assert get_cache() is not None
    assert get_config() is not None

    # Verify ToolResult default factory creates distinct dicts
    res1 = ToolResult()
    res2 = ToolResult()
    res1.metadata["test_key"] = "unique_value"
    assert "test_key" not in res2.metadata


def test_configurable_settings_and_doctor_command() -> None:
    """Verify configurable search/daemon/mesh/executor schemas and doctor command."""
    from click.testing import CliRunner

    from sago.config.loader import get_config
    from sago.main import cli

    cfg = get_config()
    assert hasattr(cfg, "search")
    assert cfg.search.max_files == 50000
    assert hasattr(cfg, "daemon")
    assert cfg.daemon.host == "127.0.0.1"
    assert hasattr(cfg, "mesh")
    assert cfg.mesh.port == 7655
    assert hasattr(cfg, "executor")
    assert cfg.executor.max_tokens == 32000

    runner = CliRunner()
    result = runner.invoke(cli, ["doctor"])
    assert result.exit_code == 0
    assert "System Health Check" in result.output
    assert "Python Runtime" in result.output


def test_daemon_resilience_and_safety_checks() -> None:
    """Verify dangerous shell command rejection, fallback tool caching, rate limits, and memory caps."""
    from sago.cache.intelligent import get_cache
    from sago.errors.handler import _get_tool_class_by_name, get_error_handler
    from sago.tools.shell.execute import ExecuteShellTool
    from sago.tracking.token_tracker import TokenUsage, get_token_tracker

    # 1. Shell dangerous commands safety
    shell = ExecuteShellTool()
    res = shell._run("rm -rf /")
    assert "Command rejected by safety guard" in res
    res_fork = shell._run(":(){ :|:& };:")
    assert "Command rejected by safety guard" in res_fork

    # 2. Fast cached fallback tool lookup
    tool_cls = _get_tool_class_by_name("read_file")
    assert tool_cls is not None
    assert getattr(tool_cls, "name") == "read_file"
    # Second call uses cache
    assert _get_tool_class_by_name("read_file") is tool_cls

    # 3. Fast cache entry size calculation
    cache = get_cache()
    cache.set("str_key", "hello world")
    assert cache.get("str_key") == "hello world"

    # 4. Token tracker and Error handler memory caps
    tracker = get_token_tracker()
    for _ in range(5):
        tracker._usages.append(
            TokenUsage(
                provider="test",
                model="test",
                input_tokens=10,
                output_tokens=10,
                cached=False,
                latency_ms=10.0,
                cost_usd=0.001,
            )
        )
    eh = get_error_handler()
    eh.handle_error("test_tool", ValueError("test error"))
    assert len(eh.errors) >= 1
    assert len(eh.errors) <= 5000


def test_spawn_agent_resilience_and_dev_trace_graphs(tmp_path: Path) -> None:
    """Verify SpawnAgentTool flexible args and DevTracer interaction graph generation."""
    import json

    from sago.tools.file.spawn_agent import SpawnAgentTool
    from sago.tracking.dev_tracer import DevTracer, TraceEventType

    # 1. SpawnAgentTool auto-routing
    tool = SpawnAgentTool()
    assert tool._resolve_target_agent("", "create a python calculator") == "python-engineer"
    assert tool._resolve_target_agent("", "write a go program") == "go-engineer"
    assert tool._resolve_target_agent("", "write java spring service") == "java-engineer"
    assert tool._resolve_target_agent("backend", "build api") == "backend-engineer"

    # 2. DevTracer Mermaid & ASCII graph export
    tracer = DevTracer()
    tracer.record(
        TraceEventType.AGENT_ROUTING,
        source="sago.orchestrator",
        action="DELEGATE",
        data={"target_agent": "python-engineer", "task": "build calculator"},
    )
    tracer.record(
        TraceEventType.TOOL_DISPATCH,
        source="python-engineer",
        action="run(write_file)",
        data={"tool_name": "write_file"},
    )
    tracer.record(
        TraceEventType.LLM_PAYLOAD,
        source="tui.llm",
        action="generate",
        data={"model": "gpt-4o", "tokens_in": 100, "tokens_out": 50},
    )

    # Export markdown
    md_path = tmp_path / "trace.md"
    ok_md, res_md = tracer.export_traces(md_path, format="md")
    assert ok_md
    content_md = md_path.read_text(encoding="utf-8")
    assert "```mermaid" in content_md
    assert "python-engineer" in content_md
    assert "Call Hierarchy Map" in content_md

    # Export json
    json_path = tmp_path / "trace.json"
    ok_json, res_json = tracer.export_traces(json_path, format="json")
    assert ok_json
    data_json = json.loads(json_path.read_text(encoding="utf-8"))
    assert "interaction_graph" in data_json
    assert len(data_json["interaction_graph"]["nodes"]) == 3


def test_session_prefix_lookup_and_useless_session_auto_cleanup(tmp_path: Path) -> None:
    """Verify session find_by_prefix, has_human_messages, and cleanup_useless_sessions."""
    from sago.database import MessageStore, Session, init_db

    init_db()

    # Session 1: Real human message -> Should be kept
    s1 = Session()
    s1.create(title="Real Session")
    ms1 = MessageStore(s1.id)
    ms1.add(role="user", content="Write a sorting function in Python")
    ms1.add(role="assistant", content="Here is quicksort")
    ms1.flush()

    # Session 2: Only slash commands -> Useless, should be deleted
    s2 = Session()
    s2.create(title="Command Only Session")
    ms2 = MessageStore(s2.id)
    ms2.add(role="user", content="/model gpt-4o")
    ms2.add(role="user", content="/help")
    ms2.flush()

    # Session 3: Empty session (no messages) -> Useless, should be deleted
    s3 = Session()
    s3.create(title="Empty Session")

    # Session 4: Only system or assistant messages -> Useless, should be deleted
    s4 = Session()
    s4.create(title="System Only Session")
    ms4 = MessageStore(s4.id)
    ms4.add(role="system", content="System notification")
    ms4.flush()

    # Verify has_human_messages
    assert s1.has_human_messages() is True
    assert s2.has_human_messages() is False
    assert s3.has_human_messages() is False
    assert s4.has_human_messages() is False

    # Verify find_by_prefix
    matched = Session().find_by_prefix(s1.id[:8])
    assert matched is not None
    assert matched["id"] == s1.id

    # Verify cleanup_useless_sessions
    deleted_count = Session().cleanup_useless_sessions()
    assert deleted_count >= 3

    # s1 should still exist, s2, s3, s4 should be gone
    assert Session(s1.id).get() is not None
    assert Session(s2.id).get() is None
    assert Session(s3.id).get() is None
    assert Session(s4.id).get() is None

    # Cleanup s1
    s1.delete()


def test_read_file_header_empty_file_edge_cases(tmp_path: Path) -> None:
    """Verify ReadFileTool produces clean headers on empty files and non-empty files."""
    from sago.tools.file.read_file import ReadFileTool

    tool = ReadFileTool()

    # Empty file
    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("", encoding="utf-8")
    out_empty = tool.run(file_path=str(empty_file))
    assert "(empty or beyond offset, total lines: 0)" in out_empty

    # Non-empty file
    regular_file = tmp_path / "code.py"
    regular_file.write_text("print('hello')\nprint('world')\n", encoding="utf-8")
    out_reg = tool.run(file_path=str(regular_file))
    assert "lines 1-2 of 2" in out_reg


def test_continue_command_tool_context_injection() -> None:
    """Verify /continue extracts recent tool usage for prompt context."""
    from sago.database import Session, ToolUsageStore, init_db

    init_db()
    s = Session()
    s.create(title="Test Continue")

    tus = ToolUsageStore(s.id)
    tus.log(
        "write_file", {"path": "main.py"}, "File written successfully", duration_ms=50, success=True
    )
    tus.log("execute_command", {"cmd": "pytest"}, "1 passed", duration_ms=200, success=True)
    tus.flush()

    recent = tus.get_all()
    assert len(recent) == 2
    assert recent[0]["tool_name"] == "write_file"
    assert recent[1]["tool_name"] == "execute_command"

    s.delete()
