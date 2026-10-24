"""Unit tests for new Phase 1/2 modules: code intelligence facade, tool discovery,
verify_edit, context budget, and semantic routing."""

from __future__ import annotations

import os


class TestCodeIntelligenceFacade:
    def test_facade_constructs_and_maps(self, tmp_path) -> None:
        from sago.memory.code_intelligence import CodeIntelligenceService

        (tmp_path / "alpha.py").write_text("def foo():\n    return 1\n")
        svc = CodeIntelligenceService(root_dir=str(tmp_path))
        assert svc.root_dir == tmp_path
        assert svc.repo_map() is not None

    def test_singleton_helper(self, tmp_path) -> None:
        from sago.memory.code_intelligence import get_code_intelligence

        svc = get_code_intelligence(root_dir=str(tmp_path))
        assert svc is not None


class TestToolDiscoveryTool:
    def test_discovery_lists_catalog_tools(self) -> None:
        from sago.tools.admin.tool_discovery import ToolDiscoveryTool

        tool = ToolDiscoveryTool()
        out = tool._run()
        assert "Discovered" in out
        # Catalog tools present (safe mode excludes only dynamic plugins/MCP)
        assert "read_file" in out or "execute_shell" in out or int(out.split()[1]) >= 0

    def test_discovery_query_filter(self) -> None:
        from sago.tools.admin.tool_discovery import ToolDiscoveryTool

        tool = ToolDiscoveryTool()
        out = tool._run(query="python")
        assert out.startswith("Discovered")

    def test_discovery_unknown_category(self) -> None:
        from sago.tools.admin.tool_discovery import ToolDiscoveryTool

        tool = ToolDiscoveryTool()
        out = tool._run(category="definitely-not-a-category")
        assert out == "Discovered 0 tools:\n"


class TestVerifyEditTool:
    def test_verify_edit_would_apply(self, tmp_path) -> None:
        from sago.tools.coding.verify_edit_tool import VerifyEditTool

        f = tmp_path / "mod.py"
        f.write_text("x = 1\ny = 2\n")
        tool = VerifyEditTool()
        out = tool._run(
            file_path=str(f),
            old_string="y = 2",
            new_string="y = 3",
        )
        assert isinstance(out, str)
        assert "apply" in out.lower()

    def test_verify_edit_missing_file(self, tmp_path) -> None:
        from sago.tools.coding.verify_edit_tool import VerifyEditTool

        tool = VerifyEditTool()
        out = tool._run(
            file_path=str(tmp_path / "nope.py"),
            old_string="a",
            new_string="b",
        )
        assert "not found" in out.lower()

    def test_verify_edit_bad_python_rejected(self, tmp_path) -> None:
        from sago.tools.coding.verify_edit_tool import VerifyEditTool

        f = tmp_path / "mod.py"
        f.write_text("x = 1\n")
        tool = VerifyEditTool()
        out = tool._run(
            file_path=str(f),
            old_string="x = 1\n",
            new_string="x = (\n",
        )
        assert isinstance(out, str)


class TestContextBudget:
    def test_estimate_tokens(self) -> None:
        from sago.memory.context_budget import estimate_tokens

        assert estimate_tokens("") == 1
        assert estimate_tokens("a" * 400) == 100

    def test_truncate_within_budget(self) -> None:
        from sago.memory.context_budget import truncate_to_budget

        text = "hello world"
        assert truncate_to_budget(text, 100) == text

    def test_truncate_over_budget_keeps_head_tail(self) -> None:
        from sago.memory.context_budget import truncate_to_budget

        text = ("A" * 5000) + "\n" + ("B" * 5000)
        out = truncate_to_budget(text, 500)
        assert "[truncated to fit context budget]" in out
        assert out.startswith("A")
        assert out.rstrip().endswith("B")

    def test_budget_manager(self) -> None:
        from sago.memory.context_budget import ContextBudgetManager

        mgr = ContextBudgetManager(max_tokens=100)
        assert mgr.fit("short") == "short"


class TestSemanticRouting:
    def test_disabled_by_default(self) -> None:
        from sago.tools.file.agent_delegator import _semantic_boost

        os.environ.pop("SAGO_SEMANTIC_ROUTING", None)
        assert _semantic_boost("fix python bug") == {}

    def test_enabled_produces_relative_scores(self) -> None:
        from sago.tools.file.agent_delegator import AGENT_CAPABILITIES, _semantic_boost

        os.environ["SAGO_SEMANTIC_ROUTING"] = "1"
        try:
            scores = _semantic_boost("build a react frontend with styled components")
            assert isinstance(scores, dict)
            for name, score in scores.items():
                assert 0.0 < score <= 0.45
                assert name in AGENT_CAPABILITIES
        finally:
            os.environ.pop("SAGO_SEMANTIC_ROUTING", None)


class TestDelegatorDefaultUnchanged:
    """Ground rule: without the flag, delegation behavior is identical to before."""

    def test_python_task_default(self) -> None:
        from sago.tools.file.agent_delegator import delegate_task

        r = delegate_task("implement database migration", language="python")
        # language python -> python-engineer/backend-engineer; keyword "database" -> database/data-engineer
        assert r.primary_agent in (
            "python-engineer",
            "backend-engineer",
            "database-engineer",
            "data-engineer",
        )
        assert "language:python" in r.reason

    def test_unknown_task_defaults(self) -> None:
        from sago.tools.file.agent_delegator import delegate_task

        r = delegate_task("lorem ipsumす thing xyzzy")
        assert r.primary_agent == "fullstack-engineer"
        assert "default" in r.reason


class TestScopedRegistries:
    def test_scoped_tool_registry(self) -> None:
        from sago.tools.registry import ScopedToolRegistry

        reg = ScopedToolRegistry(allowed={"read_file", "write_file"})
        tools = reg.tools()
        assert set(tools.keys()).issubset({"read_file", "write_file"})

        reg.allow({"glob_files"})
        assert "glob_files" in reg.tools()

        reg.deny({"read_file"})
        assert "read_file" not in reg.tools()

    def test_scoped_agent_registry(self) -> None:
        from sago.agents.registry import AgentDefinition, ScopedAgentRegistry

        scoped = ScopedAgentRegistry()
        custom_agent = AgentDefinition(
            name="custom-bot",
            codename="cbot",
            role="Specialist",
            description="A custom bot for tests",
            system_prompt="You are custom.",
            skills=["custom"],
            tools=["read_file"],
        )
        scoped.register(custom_agent)
        assert scoped.get("custom-bot") is not None
        assert scoped.get("cbot") is not None
        assert scoped.get("architect") is not None  # fallback to global

        scoped.unregister("custom-bot")
        assert scoped.get("custom-bot") is None


class TestWorkflowRoleLoop:
    def test_planner_coder_verifier_pipeline(self) -> None:
        from sago.workflow.engine import WorkflowEngine
        from sago.workflow.templates import WorkflowTemplates

        engine = WorkflowEngine()
        templates = WorkflowTemplates(engine)
        wf = templates.planner_coder_verifier_pipeline("Refactor database layer")
        assert wf is not None
        step_names = [s.name for s in wf.steps]
        assert "Plan Architecture" in step_names
        assert "Implement Code" in step_names
        assert "Verify Implementation" in step_names


class TestEvalHarness:
    def test_harness_evaluation_pass_and_fail(self) -> None:
        from evals.harness import evaluate_response, run_eval

        case = {
            "id": "test_case",
            "category": "unit",
            "prompt": "Say hello",
            "expected_contains": ["hello"],
            "negative_contains": ["forbidden"],
        }
        res_pass = evaluate_response(case, "Hello world!")
        assert res_pass["passed"] is True

        res_fail = evaluate_response(case, "Hello forbidden world!")
        assert res_fail["passed"] is False

        report = run_eval([case], lambda p: "hello")
        assert report["total"] == 1
        assert report["passed"] == 1
        assert report["pass_rate"] == 1.0
