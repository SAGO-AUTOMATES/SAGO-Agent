import sys
from unittest.mock import MagicMock, patch

from sago.agents.handoff import FeedbackRequest, HandoffContext
from sago.agents.spawner import AgentSpawner


def test_spawner_init():
    spawner = AgentSpawner()
    assert spawner.config is not None
    assert spawner._crew_agents == {}


def test_spawner_spawn_unknown_agent():
    spawner = AgentSpawner()
    mock_crewai = MagicMock()
    with patch.dict(sys.modules, {"crewai": mock_crewai}):
        assert spawner.spawn("nonexistent-agent-xyz") is None


def test_spawner_spawn_valid_agent():
    spawner = AgentSpawner()
    mock_crewai = MagicMock()
    mock_agent_instance = MagicMock()
    mock_crewai.Agent.return_value = mock_agent_instance

    with (
        patch.dict(sys.modules, {"crewai": mock_crewai}),
        patch.object(spawner, "_resolve_tools", return_value=[]),
        patch.object(spawner, "_get_llm", return_value=MagicMock()),
    ):
        ctx = HandoffContext(original_task="Build feature")
        agent = spawner.spawn("python-engineer", context=ctx, model_override="gemini-flash")
        assert agent is not None
        assert "python-engineer" in spawner._crew_agents


def test_spawner_spawn_with_dict_context():
    spawner = AgentSpawner()
    mock_crewai = MagicMock()
    mock_crewai.Agent.return_value = MagicMock()

    with (
        patch.dict(sys.modules, {"crewai": mock_crewai}),
        patch.object(spawner, "_resolve_tools", return_value=[]),
        patch.object(spawner, "_get_llm", return_value=MagicMock()),
    ):
        agent = spawner.spawn("python-engineer", context={"info": "prior step output"})
        assert agent is not None


def test_spawner_execute_with_agent(tmp_path):
    spawner = AgentSpawner()
    mock_crewai = MagicMock()
    mock_crew = MagicMock()
    mock_crew.kickoff.return_value = "Agent executed successfully"
    mock_crewai.Crew.return_value = mock_crew
    mock_crewai.Task = MagicMock()

    with (
        patch.dict(sys.modules, {"crewai": mock_crewai}),
        patch.object(spawner, "spawn") as mock_spawn,
        patch("sago.database.Session") as mock_session_cls,
        patch("sago.database.MessageStore"),
    ):
        mock_spawn.return_value = MagicMock()
        mock_sess = MagicMock()
        mock_sess.id = "sess_123"
        mock_session_cls.return_value = mock_sess

        res = spawner.execute_with_agent("python-engineer", "Implement parser")
        assert res == "Agent executed successfully"

        # Spawn failure
        mock_spawn.return_value = None
        res_fail = spawner.execute_with_agent("python-engineer", "Implement parser")
        assert "Error: Could not spawn" in res_fail


def test_spawner_orchestrate():
    spawner = AgentSpawner()
    with (
        patch.object(
            spawner,
            "execute_with_agent",
            side_effect=["Step 1 output", "Step 2 output"],
        ),
        patch("sago.database.Session") as mock_session_cls,
    ):
        mock_sess = MagicMock()
        mock_sess.id = "orch_sess"
        mock_session_cls.return_value = mock_sess

        res = spawner.orchestrate(
            "Test multi-step task",
            agent_chain=["python-engineer", "qa-engineer"],
            enable_feedback=False,
        )
        assert res == "Step 2 output"


def test_spawner_orchestrate_error_break():
    spawner = AgentSpawner()
    with (
        patch.object(
            spawner,
            "execute_with_agent",
            return_value="Error: execution failed",
        ),
        patch("sago.database.Session") as mock_session_cls,
    ):
        mock_sess = MagicMock()
        mock_sess.id = "orch_sess"
        mock_session_cls.return_value = mock_sess

        res = spawner.orchestrate(
            "Test fail task",
            agent_chain=["python-engineer", "qa-engineer"],
        )
        assert res.startswith("Error:")


def test_spawner_feedback_loop():
    spawner = AgentSpawner()
    ctx = HandoffContext(original_task="Build API")
    ctx.completed_agents = ["python-engineer"]
    req = FeedbackRequest(
        from_agent="qa-engineer",
        to_agent="python-engineer",
        question="What is the port?",
    )
    ctx.feedback_requests = [req]

    with patch.object(spawner, "execute_with_agent", return_value="Port is 8000"):
        result = spawner._handle_feedback_loop(ctx, "qa-engineer", "Initial result", "sess1")
        assert "Feedback from python-engineer" in result
        assert req.answered is True


def test_spawner_plan_chain():
    spawner = AgentSpawner()
    chain = spawner._plan_chain("Please optimize our database slow queries")
    assert len(chain) >= 1
    assert any("engineer" in c for c in chain)


def test_spawner_orchestrate_parallel():
    spawner = AgentSpawner()
    with (
        patch("sago.database.Session"),
        patch("sago.engine.simple_executor.execute_agent_task") as mock_exec_task,
    ):
        mock_exec_task.return_value = {
            "success": True,
            "output": "Task result",
            "tool_calls": [],
            "files_created": [],
        }

        subtasks = [
            {"agent": "python-engineer", "task": "Task 1"},
            {"agent": "qa-engineer", "task": "Task 2"},
        ]
        results = spawner.orchestrate_parallel(subtasks, max_workers=2)
        assert len(results) == 2
        assert all(r["success"] is True for r in results)


def test_spawner_resolve_tools():
    spawner = AgentSpawner()
    with patch(
        "sago.tools.crewai_wrappers.get_crewai_tool",
        side_effect=lambda name: MagicMock() if name == "read_file" else None,
    ):
        resolved = spawner._resolve_tools(["read_file", "unknown_xyz"])
        assert len(resolved) == 1


def test_spawner_get_llm(monkeypatch):
    spawner = AgentSpawner()
    mock_crewai = MagicMock()
    with patch.dict(sys.modules, {"crewai": mock_crewai}):
        # Unknown provider returns None
        assert spawner._get_llm(provider_override="nonexistent_provider") is None

        # With API key
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-mock-key")
        mock_crewai.LLM.return_value = MagicMock()
        llm = spawner._get_llm(provider_override="openrouter")
        assert llm is not None
