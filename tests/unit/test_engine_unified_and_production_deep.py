"""Deep unit test suite for sago/engine/unified.py and sago/engine/production.py.

Thoroughly exercises backends (simple, CrewAI, LangGraph), streaming loops,
tool execution, verification hooks, parallel pools, session lifecycle,
and multi-agent chains.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from sago.engine.production import EngineConfig, ProductionEngine
from sago.engine.unified import (
    UnifiedExecutor,
    execute_parallel,
    execute_task,
    stream_task,
)

# ==============================================================================
# UnifiedExecutor Tests
# ==============================================================================


def test_unified_executor_simple_backend() -> None:
    executor = UnifiedExecutor(api_key="test-key", model="mock-model")

    with patch("sago.engine.simple_executor.execute_agent_task") as mock_exec:
        mock_exec.return_value = {
            "success": True,
            "output": "Simple executed successfully",
            "iterations": 1,
            "tool_calls": [{"tool": "bash", "result": "ok"}],
            "tokens": {"input": 100, "output": 50},
        }

        # 1. Without auto_verify
        res = executor.execute(
            task="Write tests",
            agent_name="python-engineer",
            backend="simple",
            auto_verify=False,
        )
        assert res["success"] is True
        assert res["output"] == "Simple executed successfully"

        # 2. With auto_verify passed
        with patch("sago.engine.verifier.get_project_verifier") as mock_verifier_fn:
            mock_v = MagicMock()
            rep = MagicMock()
            rep.passed = True
            rep.linter_passed = True
            rep.typecheck_passed = True
            rep.tests_passed = True
            rep.issues = []
            mock_v.verify_all.return_value = rep
            mock_verifier_fn.return_value = mock_v

            res2 = executor.execute(
                task="Write tests",
                agent_name="python-engineer",
                backend="simple",
                auto_verify=True,
            )
            assert "verification" in res2
            assert res2["verification"]["passed"] is True


def test_unified_executor_crewai_backend() -> None:
    executor = UnifiedExecutor(api_key="test-key")

    with patch("sago.agents.spawner.AgentSpawner") as mock_spawner_cls:
        spawner = MagicMock()
        spawner.execute_with_agent.return_value = "CrewAI output"
        mock_spawner_cls.return_value = spawner

        # Success case
        res = executor.execute(task="Do task", backend="crewai")
        assert res["success"] is True
        assert res["output"] == "CrewAI output"

        # Failure string case
        spawner.execute_with_agent.return_value = "Error: Agent crashed"
        res_fail = executor.execute(task="Do task", backend="crewai")
        assert res_fail["success"] is False

        # Exception case
        spawner.execute_with_agent.side_effect = RuntimeError("CrewAI load failure")
        res_exc = executor.execute(task="Do task", backend="crewai")
        assert res_exc["success"] is False
        assert "CrewAI error" in res_exc["output"]


def test_unified_executor_langgraph_backend() -> None:
    executor = UnifiedExecutor(api_key="test-key")

    with patch("sago.workflow.langgraph_engine.SagoWorkflowEngine") as mock_engine_cls:
        eng = MagicMock()
        mock_res = MagicMock()
        mock_res.to_dict.return_value = {
            "success": True,
            "output": "LangGraph output",
            "tool_calls": [],
        }
        eng.run.return_value = mock_res
        mock_engine_cls.return_value = eng

        res = executor.execute(task="Stateful task", backend="langgraph")
        assert res["success"] is True
        assert res["output"] == "LangGraph output"

        # Exception case
        eng.run.side_effect = RuntimeError("LangGraph runtime error")
        res_exc = executor.execute(task="Stateful task", backend="langgraph")
        assert res_exc["success"] is False
        assert "LangGraph error" in res_exc["output"]


def test_unified_executor_stream() -> None:
    executor = UnifiedExecutor(api_key="test-key")

    with (
        patch("sago.engine.unified.OpenAI") as mock_openai_cls,
        patch("sago.engine.simple_executor._discover_tools") as mock_disc,
        patch("sago.permissions.get_permission_manager") as mock_pm_fn,
    ):
        pm = MagicMock()
        pm.check_permission.return_value = (True, "allowed")
        mock_pm_fn.return_value = pm
        mock_tool_cls = MagicMock()
        mock_tool_inst = MagicMock()
        mock_tool_inst.run.return_value = "tool ran ok"
        mock_tool_cls.return_value = mock_tool_inst
        mock_disc.return_value = {"custom_tool": mock_tool_cls}

        client = MagicMock()
        mock_openai_cls.return_value = client

        # Iteration 1: model returns tool call
        chunk1 = MagicMock()
        chunk1.usage = MagicMock(prompt_tokens=10, completion_tokens=20)
        tc_delta = MagicMock()
        tc_delta.index = 0
        tc_delta.id = "call_123"
        fn_mock = MagicMock()
        fn_mock.name = "custom_tool"
        fn_mock.arguments = '{"param": 1}'
        tc_delta.function = fn_mock
        chunk1.choices = [MagicMock(delta=MagicMock(content="", tool_calls=[tc_delta]))]

        # Iteration 2: model returns final text
        chunk2 = MagicMock()
        chunk2.usage = None
        chunk2.choices = [
            MagicMock(delta=MagicMock(content="Final response tokens", tool_calls=None))
        ]

        client.chat.completions.create.side_effect = [[chunk1], [chunk2]]

        tokens = []
        thinking = []
        tool_calls = []

        res = executor.stream(
            task="Sample stream task",
            agent_name="python-engineer",
            max_iterations=5,
            on_token=tokens.append,
            on_thinking=thinking.append,
            on_tool_call=lambda n, a: tool_calls.append((n, a)),
        )

        assert res["success"] is True
        assert "Final response tokens" in res["output"]
        assert len(tokens) >= 1
        assert len(thinking) >= 1
        assert len(tool_calls) == 1
        assert tool_calls[0][0] == "custom_tool"


def test_unified_convenience_functions() -> None:
    # 1. execute_task
    with patch("sago.engine.unified.UnifiedExecutor.execute") as mock_exec:
        mock_exec.return_value = {"success": True, "output": "Done"}
        r = execute_task("quick task")
        assert r["success"] is True

    # 2. stream_task
    with patch("sago.engine.unified.UnifiedExecutor.stream") as mock_stream:
        mock_stream.return_value = {"success": True, "output": "Streamed"}
        r = stream_task("quick stream")
        assert r["success"] is True

    # 3. execute_parallel
    with patch("sago.engine.unified.UnifiedExecutor.execute") as mock_exec:
        mock_exec.side_effect = [
            {"success": True, "output": "Task 1 finished"},
            {"success": True, "output": "Task 2 finished"},
        ]
        results = execute_parallel(
            [
                {"task": "task 1", "agent": "python-engineer"},
                {"task": "task 2", "agent": "code-reviewer"},
            ],
            max_workers=2,
        )
        assert len(results) == 2
        assert results[0]["output"] == "Task 1 finished"
        assert results[1]["output"] == "Task 2 finished"


# ==============================================================================
# ProductionEngine Tests
# ==============================================================================


def test_production_engine_init_and_callbacks() -> None:
    cfg = EngineConfig(max_workers=2, default_effort="low", show_thinking=False)
    engine = ProductionEngine(config=cfg)

    started = []
    completed = []
    errors = []

    engine.on_task_start(started.append)
    engine.on_task_complete(completed.append)
    engine.on_error(errors.append)

    assert len(engine._on_task_start) == 1
    assert len(engine._on_task_complete) == 1
    assert len(engine._on_error) == 1

    # Session creation & cleanup
    sess = engine.create_session("Unit Test Session")
    assert sess.id

    # Test _cleanup_sessions threshold (< 300s does nothing)
    engine._cleanup_sessions()

    # Simulate aged session cleanup (> 300s)
    engine._last_cleanup = time.time() - 350
    engine._session_ttl = 0  # all expire immediately
    engine._cleanup_sessions()


def test_production_engine_run_task_success() -> None:
    engine = ProductionEngine()

    with (
        patch("sago.agents.registry.get_agent") as mock_get_agent,
        patch("sago.engine.production.ProductionEngine._execute_agent") as mock_exec_ag,
        patch("sago.engine.hallucination_verifier.get_verifier") as mock_ver_fn,
    ):
        mock_agent = MagicMock()
        mock_agent.codename = "python-engineer"
        mock_get_agent.return_value = mock_agent
        mock_exec_ag.return_value = "Result from python engineer"

        # Hallucination verifier mock (with low confidence warning)
        verifier = MagicMock()
        rep = MagicMock()
        rep.has_hallucinations = True
        rep.cleaned_content = "Cleaned result without hallucinations"
        rep.confidence = 40  # triggers confidence warning
        verifier.verify.return_value = rep
        mock_ver_fn.return_value = verifier

        task_completed_cb = MagicMock()
        engine.on_task_complete(task_completed_cb)

        res = engine.run_task(
            task="Build feature",
            agent="python-engineer",
            effort="medium",
            stream=False,
        )

        assert res["success"] is True
        assert "Cleaned result without hallucinations" in res["content"]
        assert "Confidence Warning" in res["content"]
        assert task_completed_cb.called


def test_production_engine_run_task_fallbacks_and_errors() -> None:
    engine = ProductionEngine()

    # Fallback to first available agent
    with (
        patch("sago.agents.registry.get_agent") as mock_get_agent,
        patch("sago.agents.registry.list_agents") as mock_list_agents,
        patch("sago.engine.production.ProductionEngine._execute_agent") as mock_exec_ag,
    ):
        mock_get_agent.side_effect = [None, MagicMock(codename="first-agent")]
        mock_list_agents.return_value = [{"name": "first-agent"}]
        mock_exec_ag.return_value = "Fallback succeeded"

        res = engine.run_task("Fallback task", agent="nonexistent-agent", stream=False)
        assert res["success"] is True
        assert res["content"] == "Fallback succeeded"

    # Total failure / error callback
    err_cb = MagicMock()
    engine.on_error(err_cb)
    with patch("sago.sessions.manager.SessionManager.create_thread") as mock_ct:
        mock_ct.side_effect = RuntimeError("Thread pool exhausted")
        res_fail = engine.run_task("Crash task", stream=False)
        assert res_fail["success"] is False
        assert "Thread pool exhausted" in res_fail["error"]
        assert err_cb.called


def test_production_engine_run_chain() -> None:
    engine = ProductionEngine()

    with patch.object(engine, "run_task") as mock_rt:
        mock_rt.side_effect = [
            {"success": True, "content": "Architect plan output"},
            {"success": True, "content": "Developer code output"},
        ]

        chain_res = engine.run_chain(
            task="Build microservice",
            agent_chain=["system-architect", "python-engineer"],
            effort="high",
        )

        assert chain_res["success"] is True
        assert chain_res["content"] == "Developer code output"
        assert len(chain_res["chain_results"]) == 2

        # Test chain failure stopping early
        mock_rt.side_effect = [
            {"success": False, "error": "Architect failed syntax check"},
        ]
        fail_res = engine.run_chain(
            task="Broken task",
            agent_chain=["system-architect", "python-engineer"],
        )
        assert fail_res["success"] is False
        assert "Chain failed at step 1" in fail_res["error"]


def test_production_engine_run_parallel() -> None:
    engine = ProductionEngine()

    with patch.object(engine, "_execute_thread_task") as mock_ett:
        mock_ett.return_value = "Parallel output"

        res = engine.run_parallel(
            tasks=[
                {"task": "Analyze security", "agent": "security-engineer"},
                {"task": "Check styles", "agent": "code-reviewer"},
            ],
            effort="medium",
        )

        assert res["success"] is True
        assert len(res["results"]) == 2
