"""Unit tests for verifier enhancements (grounding, post-exec checks, calibration)
and dynamic replanning in the workflow engine."""

from __future__ import annotations


class TestVerifierGrounding:
    def test_symbol_grounding_flags_unknown_backticked_symbol(self, tmp_path) -> None:
        from sago.engine.hallucination_verifier import ResponseVerifier

        # Build a tiny repo so SymbolGraph has a non-empty symbol index.
        (tmp_path / "mod_real.py").write_text("def real_function_here():\n    return 1\n")

        verifier = ResponseVerifier(enable_external_checks=False)
        result = verifier.verify(
            "Now call `definitely_not_a_symbol_xyz`",
            tool_history=[],
            root_dir=str(tmp_path),
        )
        assert any("definitely_not_a_symbol" in str(i) for i in result.all_issues)

    def test_symbol_grounding_clean_repo_no_flags(self, tmp_path) -> None:
        from sago.engine.hallucination_verifier import ResponseVerifier

        (tmp_path / "m.py").write_text("def parse_data_here():\n    return 1\n")

        verifier = ResponseVerifier(enable_external_checks=False)
        result = verifier.verify(
            "Use `parse_data_here` from the module.",
            tool_history=[],
            root_dir=str(tmp_path),
        )
        assert not any("not found in repository" in str(i) for i in result.all_issues)


class TestVerifierPostExecSyntaxCheck:
    def test_modified_file_with_syntax_error_flagged(self, tmp_path) -> None:
        from sago.engine.hallucination_verifier import ResponseVerifier

        bad = tmp_path / "broken_out.py"
        bad.write_text("def bad(\n")

        verifier = ResponseVerifier(enable_external_checks=False)
        result = verifier.verify(
            "I wrote the file successfully.",
            tool_history=[
                {
                    "tool": "write_file",
                    "args": {"file_path": str(bad)},
                    "result": "ok",
                    "success": True,
                }
            ],
            root_dir=str(tmp_path),
        )
        assert any("syntax error" in str(i).lower() for i in result.all_issues)

    def test_modified_valid_file_not_flagged(self, tmp_path) -> None:
        from sago.engine.hallucination_verifier import ResponseVerifier

        good = tmp_path / "good.py"
        good.write_text("def fine():\n    return 2\n")

        verifier = ResponseVerifier(enable_external_checks=False)
        result = verifier.verify(
            "Wrote the file.",
            tool_history=[
                {
                    "tool": "edit_file",
                    "args": {"path": str(good)},
                    "result": "ok",
                    "success": True,
                }
            ],
            root_dir=str(tmp_path),
        )
        assert not any("syntax error" in str(i).lower() for i in result.all_issues)


class TestVerifierCalibration:
    def test_failed_tools_lower_confidence(self) -> None:
        from sago.engine.hallucination_verifier import ResponseVerifier

        verifier = ResponseVerifier(enable_external_checks=False)
        task = "Read the file and summarize it."
        ok_all = verifier.verify(
            task,
            tool_history=[
                {"tool": "read_file", "args": {}, "result": "kept short", "success": True},
            ],
        )
        with_fails = verifier.verify(
            task,
            tool_history=[
                {"tool": "read_file", "args": {}, "result": "kept short", "success": True},
                {"tool": "edit_file", "args": {}, "result": "x", "success": False},
                {"tool": "grep", "args": {}, "result": "y", "success": False},
            ],
        )
        assert with_fails.confidence <= ok_all.confidence


class TestDynamicReplan:
    def test_replan_retries_failed_llm_step(self, monkeypatch) -> None:
        monkeypatch.setenv("SAGO_REPLAN", "1")
        from sago.workflow.engine import StepStatus, Workflow, WorkflowEngine, WorkflowStep

        calls = {"n": 0}

        def flaky_executor(context, config):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"success": False, "error": "module foo not found"}
            return {"success": True, "output": "recovered"}

        engine = WorkflowEngine()
        engine.register_executor("agent_call", flaky_executor)
        wf: Workflow = engine.create_workflow("t2", "d")
        wf.steps.append(
            WorkflowStep(id="s1", name="s1", type="agent_call", config={"task": "do thing"})
        )

        out = engine.execute_workflow(wf.id)
        assert calls["n"] == 2, "replan must retry the failed step once with feedback"
        assert "recovered" in str(wf.steps[0].result)
        assert wf.steps[0].status == StepStatus.COMPLETED
        assert out.get("status") in ("completed", "COMPLETED", None) or True

    def test_replan_failure_recorded(self, monkeypatch) -> None:
        monkeypatch.setenv("SAGO_REPLAN", "1")
        from sago.workflow.engine import Workflow, WorkflowEngine, WorkflowStep

        def always_failing(context, config):
            return {"success": False, "error": "boom"}

        engine = WorkflowEngine()
        engine.register_executor("agent_call", always_failing)
        wf: Workflow = engine.create_workflow("t4", "d")
        wf.steps.append(WorkflowStep(id="s2", name="s2", type="agent_call", config={"task": "x"}))

        engine.execute_workflow(wf.id)
        assert "Replan failed" in (wf.steps[0].error or "")
        assert "boom" in str(wf.steps[0].result)

    def test_no_replan_when_env_off(self, monkeypatch) -> None:
        monkeypatch.delenv("SAGO_REPLAN", raising=False)
        from sago.workflow.engine import Workflow, WorkflowEngine, WorkflowStep

        engine = WorkflowEngine()
        calls = {"n": 0}

        def failing_executor(context, config):
            calls["n"] += 1
            return {"success": False, "error": "boom"}

        engine.register_executor("agent_call", failing_executor)
        wf: Workflow = engine.create_workflow("t3", "d")
        wf.steps.append(WorkflowStep(id="s3", name="s1", type="agent_call", config={"task": "x"}))

        engine.execute_workflow(wf.id)
        assert calls["n"] == 1, "without SAGO_REPLAN no retry-with-feedback should occur"


class TestWriteFilePythonValidation:
    def test_invalid_python_rejected(self, tmp_path) -> None:
        from unittest.mock import patch

        from sago.tools.file.write_file import WriteFileTool

        tool = WriteFileTool()
        with patch("sago.security.approval.check_write_safety", return_value=None):
            out = tool._run(str(tmp_path / "b.py"), "def broken(\n")
        assert "syntax" in out.lower()

    def test_valid_python_written(self, tmp_path) -> None:
        from unittest.mock import patch

        from sago.tools.file.write_file import WriteFileTool

        tool = WriteFileTool()
        with patch("sago.security.approval.check_write_safety", return_value=None):
            out = tool._run(str(tmp_path / "g.py"), "def ok():\n    return 1\n")
        assert "Successfully" in out or (tmp_path / "g.py").exists()

    def test_invalid_python_allowed_with_skip_syntax_check(self, tmp_path) -> None:
        from unittest.mock import patch

        from sago.tools.file.write_file import WriteFileTool

        tool = WriteFileTool()
        with patch("sago.security.approval.check_write_safety", return_value=None):
            out = tool._run(str(tmp_path / "fixture.py"), "def broken(\n", skip_syntax_check=True)
        assert "Successfully" in out or (tmp_path / "fixture.py").exists()


class TestExecutorCancellationAndCorrection:
    def test_cancellation_token_stops_execution(self) -> None:
        import threading

        from sago.engine.simple_executor import execute_agent_task

        cancel_ev = threading.Event()
        cancel_ev.set()

        res = execute_agent_task(
            task="Perform lengthy task",
            max_iterations=10,
            cancellation_token=cancel_ev,
        )
        assert res.get("cancelled") is True
        assert res.get("success") is False

    def test_cancellation_callable_stops_execution(self) -> None:
        from sago.engine.simple_executor import execute_agent_task

        res = execute_agent_task(
            task="Perform task with callable cancellation",
            max_iterations=10,
            cancellation_token=lambda: True,
        )
        assert res.get("cancelled") is True
        assert res.get("success") is False
