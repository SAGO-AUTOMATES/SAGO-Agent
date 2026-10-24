"""Deep exhaustive tests for sago/tui/orchestrator.py."""

from __future__ import annotations

import types
from unittest.mock import MagicMock

import pytest

from sago.tui.app import SagoApp
from sago.tui.orchestrator import (
    _detect_file_count_for_task,
    _direct_simple_analyze,
    _is_error_result,
    _is_simple_analyze_task,
)


def test_is_error_result_heuristics() -> None:
    # Empty or prose mentioning error
    assert _is_error_result("") is False
    assert _is_error_result("   ") is False
    assert _is_error_result("Successfully verified: 0 errors and all tests passed.") is False
    assert _is_error_result("No error detected in code review.") is False

    # Strong error starts
    assert _is_error_result("error: critical failure") is True
    assert _is_error_result("Exception: unhandled ValueError") is True
    assert _is_error_result("Traceback (most recent call last):") is True
    assert _is_error_result("fatal: unable to read tree") is True
    assert _is_error_result("rejected: tool call blocked") is True
    assert _is_error_result("cannot spawn subagent") is True
    assert _is_error_result("permission denied for /root") is True

    # Embedded error markers
    assert _is_error_result("The subagent could not be spawned due to limit") is True
    assert _is_error_result("Rate limit reached for openrouter model") is True


def test_detect_file_count_and_simple_analyze(tmp_path) -> None:
    # Non-path task
    assert _detect_file_count_for_task("Just general chat task") is None
    assert _is_simple_analyze_task("analyze general chat") is False

    # Single file
    f1 = tmp_path / "mod1.py"
    f1.write_text("print('mod1')")
    assert _detect_file_count_for_task(f"Read file '{f1}' please") == 1

    # Directory with 3 files
    f2 = tmp_path / "mod2.py"
    f2.write_text("print('mod2')")
    f3 = tmp_path / "mod3.py"
    f3.write_text("print('mod3')")

    cnt = _detect_file_count_for_task(f"Analyze directory '{tmp_path}'")
    assert cnt == 3
    assert _is_simple_analyze_task(f"analyze '{tmp_path}'") is True

    # Direct simple analyze execution
    res = _direct_simple_analyze(f"analyze '{tmp_path}'")
    assert res is not None
    assert "mod1.py" in res or "mod2.py" in res


@pytest.mark.asyncio
async def test_parallel_bar_and_summarization() -> None:
    app = SagoApp()
    async with app.run_test() as pilot:
        await pilot.pause()

        # Parallel bar operations
        app._show_parallel_bar(["coder", "tester", "researcher"])
        await pilot.pause()
        app._update_parallel_agent_status("coder", "Running code checks...")
        app._hide_parallel_bar()
        await pilot.pause()

        # Mock LLM client for summarization
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "Clean summarized response for user"
        mock_client.chat.completions.create.return_value.choices = [mock_choice]

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "sago.llm.tui_providers.get_tui_client",
                lambda prov, model: (mock_client, "gpt-4o"),
            )

            # Summarize agent result (standard OpenAI path)
            app.current_provider = "openrouter"
            app.current_model = "gpt-4o"
            ans = app._summarize_agent_result("Raw output 123", "User query", "coder")
            assert ans == "Clean summarized response for user"

            # Summarize chain results
            handoff_ctx = types.SimpleNamespace(
                agent_results={"coder": "Code written", "tester": "Tests passed"}
            )
            chain_ans = app._summarize_chain_results(
                handoff_ctx, "Build and test auth", ["coder", "tester"]
            )
            assert chain_ans == "Clean summarized response for user"

            # Exception fallback returns empty string
            mp.setattr(
                "sago.llm.tui_providers.get_tui_client",
                MagicMock(side_effect=Exception("LLM connection failed")),
            )
            fallback_ans = app._summarize_agent_result("Raw output 789", "User query", "coder")
            assert fallback_ans == ""


@pytest.mark.asyncio
async def test_delegation_and_chain_threads(monkeypatch) -> None:
    import threading

    app = SagoApp()
    async with app.run_test() as pilot:
        await pilot.pause()

        # Set user message so active exchange card is present
        app._add_user_message("Please build authentication")
        await pilot.pause()

        # Mock API key to succeed
        monkeypatch.setattr(app, "_get_provider_api_key", lambda: "fake-key")

        # Mock SpawnAgentTool
        mock_spawn = MagicMock()
        mock_spawn.return_value.run.return_value = "Feature implemented with 100% tests passing"
        monkeypatch.setattr("sago.tools.file.spawn_agent.SpawnAgentTool", mock_spawn)

        # Mock summarizer to return output
        monkeypatch.setattr(
            app, "_summarize_agent_result", lambda raw, task, agent: f"Summary of {raw}"
        )
        monkeypatch.setattr(
            app, "_summarize_chain_results", lambda ctx, task, agents: "Chain summary"
        )

        async def run_in_thread(target, *args):
            t = threading.Thread(target=target, args=args, daemon=True)
            t.start()
            for _ in range(50):
                if not t.is_alive():
                    break
                await pilot.pause(0.05)

        # 1. Delegation thread success
        await run_in_thread(app._process_delegation_thread, "coder", "Implement authentication")
        await pilot.pause()

        # 2. Delegation thread error
        mock_spawn.return_value.run.return_value = "error: agent could not be spawned"
        await run_in_thread(app._process_delegation_thread, "coder", "Implement broken task")
        await pilot.pause()

        # 3. Simple analyze branch in delegation thread
        monkeypatch.setattr("sago.tui.orchestrator._is_simple_analyze_task", lambda task: True)
        monkeypatch.setattr(
            "sago.tui.orchestrator._direct_simple_analyze",
            lambda task: "Analyzed 2 files cleanly",
        )
        await run_in_thread(app._process_delegation_thread, "coder", "analyze tiny files")
        await pilot.pause()

        # 4. Chain execution thread
        monkeypatch.setattr("sago.tui.orchestrator._is_simple_analyze_task", lambda task: False)
        mock_spawn.return_value.run.return_value = "Step output completed"
        await run_in_thread(app._process_chain_thread, [["coder"], ["tester"]], "Build and verify")
        await pilot.pause()

        # 5. Orchestration plan execution thread
        await run_in_thread(
            app._execute_orchestration_plan_thread,
            [
                {"agent": "coder", "task": "code step"},
                {"agent": "tester", "task": "test step"},
            ],
        )
        await pilot.pause()

        # 7. Orchestration planning and execution thread
        mock_planning_client = MagicMock()
        mock_planning_choice = MagicMock()
        mock_planning_choice.message.content = '[{"agent": "coder", "task": "build feature"}]'
        mock_planning_client.chat.completions.create.return_value.choices = [mock_planning_choice]
        monkeypatch.setattr(
            "sago.llm.tui_providers.get_tui_client",
            lambda prov, model: (mock_planning_client, "gpt-4o"),
        )

        await run_in_thread(app._process_orchestration_thread, "Analyze and plan architecture")
        await pilot.pause()

        # 8. Entry point methods that launch background threads
        app._process_delegation("coder", "quick delegation task")
        app._process_chain([["coder"], ["tester"]], "quick chain task")
        app._process_parallel([("coder", "task A"), ("tester", "task B")])
        app._execute_orchestration_plan([{"agent": "coder", "task": "plan step 1"}])
        app._process_orchestration("orchestrate whole task")

        for _ in range(30):
            await pilot.pause(0.05)
