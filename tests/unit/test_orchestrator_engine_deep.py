import sys
from unittest.mock import MagicMock, patch

from sago.config.loader import get_config
from sago.orchestrator.engine import SagoOrchestrator


def test_orchestrator_init():
    cfg = get_config()
    orch = SagoOrchestrator(cfg)
    assert orch.config == cfg
    assert orch._crew is None
    assert orch._agents == {}
    assert orch._tools == {}


def test_orchestrator_load_tools():
    orch = SagoOrchestrator()
    orch._load_tools()
    assert len(orch._tools) > 0


def test_orchestrator_resolve_tools():
    orch = SagoOrchestrator()
    mock_tool = MagicMock()
    mock_tool.to_langchain_tool.return_value = "langchain_tool_instance"
    orch._tools = {"mock_tool": mock_tool}

    resolved = orch._resolve_tools(["mock_tool", "missing_tool"])
    assert len(resolved) == 1
    assert resolved[0] == "langchain_tool_instance"


def test_orchestrator_get_builtin_configs():
    orch = SagoOrchestrator()
    for agent in [
        "coder",
        "debugger",
        "architect",
        "devops",
        "reviewer",
        "researcher",
        "planner",
    ]:
        cfg = orch._get_builtin_agent_config(agent)
        assert cfg is not None
        assert "role" in cfg
        assert "tools" in cfg
    assert orch._get_builtin_agent_config("unknown_agent") is None


def test_orchestrator_get_agent_config_yaml(tmp_path):
    orch = SagoOrchestrator()
    with patch("sago.paths.get_sago_home", return_value=tmp_path):
        agents_yaml = tmp_path / "agents.yaml"
        agents_yaml.write_text("agents:\n  custom_coder:\n    role: Custom\n    tools: []\n")
        cfg = orch._get_agent_config("custom_coder")
        assert cfg is not None
        assert cfg["role"] == "Custom"

        # When yaml does not exist, uses builtin
        agents_yaml.unlink()
        builtin_cfg = orch._get_agent_config("coder")
        assert builtin_cfg is not None
        assert builtin_cfg["role"] == "Senior Software Engineer"


def test_orchestrator_routing():
    orch = SagoOrchestrator()
    assert orch._route_task("Please write a python function to add numbers") == "coder"
    orch.config.routing.triggers = {
        "debugger": ["fix", "bug", "crash"],
        "devops": ["docker", "deploy", "ci/cd"],
    }
    assert orch._route_task("We have a crash in the server") == "debugger"
    assert orch._route_task("Deploy the app to production") == "devops"
    assert orch._route_task("General inquiry without keywords") == "coder"


def test_orchestrator_validate_result():
    orch = SagoOrchestrator()
    issues_short = orch._validate_result("short", "A task to build a service")
    assert any("too short" in i for i in issues_short)

    issues_failure = orch._validate_result(
        "I cannot complete this request because I am unable to access files.",
        "A task to build a service",
    )
    assert any("failure indicator" in i for i in issues_failure)

    long_good = "This is a detailed and complete implementation of the requested service module with full documentation and tests."
    issues_good = orch._validate_result(long_good, "service module tests")
    assert not issues_good or not any("failure indicator" in i for i in issues_good)


def test_orchestrator_build():
    orch = SagoOrchestrator()
    mock_crewai = MagicMock()
    with patch.dict(sys.modules, {"crewai": mock_crewai}):
        orch.build()
        assert len(orch._agents) >= 1


def test_orchestrator_execute_success():
    orch = SagoOrchestrator()
    mock_crewai = MagicMock()
    mock_crew = MagicMock()
    mock_crew.kickoff.return_value = (
        "Here is the comprehensive python function implementation with documentation."
    )
    mock_crewai.Crew.return_value = mock_crew
    mock_crewai.Task = MagicMock()

    with (
        patch.dict(sys.modules, {"crewai": mock_crewai}),
        patch("sago.engine.hallucination_verifier.get_verifier") as mock_verifier_fn,
    ):
        orch._agents["coder"] = MagicMock()
        mock_v_inst = MagicMock()
        mock_v_inst.verify.return_value = MagicMock(
            has_hallucinations=False,
            confidence=95,
            cleaned_content="Here is the comprehensive python function implementation with documentation.",
        )
        mock_verifier_fn.return_value = mock_v_inst

        res = orch.execute("write a python function")
        assert "comprehensive" in res


def test_orchestrator_execute_hallucination_warning():
    orch = SagoOrchestrator()
    mock_crewai = MagicMock()
    mock_crew = MagicMock()
    mock_crew.kickoff.return_value = "Result with hallucination"
    mock_crewai.Crew.return_value = mock_crew
    mock_crewai.Task = MagicMock()

    with (
        patch.dict(sys.modules, {"crewai": mock_crewai}),
        patch("sago.engine.hallucination_verifier.get_verifier") as mock_verifier_fn,
    ):
        orch._agents["coder"] = MagicMock()
        mock_v_inst = MagicMock()
        mock_v_inst.verify.return_value = MagicMock(
            has_hallucinations=True,
            all_issues=["Invented function foo()"],
            confidence=40,
            cleaned_content="Cleaned result content here that is reasonably long enough to avoid being flagged.",
        )
        mock_verifier_fn.return_value = mock_v_inst

        res = orch.execute("write something")
        assert "[Confidence Warning]" in res


def test_orchestrator_execute_no_agent():
    orch = SagoOrchestrator()
    orch._agents = {}
    mock_crewai = MagicMock()
    with patch.dict(sys.modules, {"crewai": mock_crewai}):
        with patch.object(orch, "build"):
            orch._route_task = MagicMock(return_value="missing_agent")
            res = orch.execute("task")
            assert "Error: No agent found" in res
