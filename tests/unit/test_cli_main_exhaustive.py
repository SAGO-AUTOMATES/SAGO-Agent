"""Exhaustive test suite for sago/main.py (Click CLI entrypoint and commands).

Validates all subcommands, option flags, helper routines, and error handling.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from sago.cleanup import CleanResult
from sago.main import (
    _chat_gemini,
    _chat_openai_compatible,
    _get_configured_model,
    _mask_secret,
    _sanitize_error_message,
    cli,
    main,
)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_mask_secret_and_sanitizer(monkeypatch: pytest.MonkeyPatch) -> None:
    # _mask_secret
    assert _mask_secret("") == ""
    assert _mask_secret("short") == "****"
    assert _mask_secret("1234567890abcdef", show_chars=4) == "1234...cdef"

    # _sanitize_error_message
    monkeypatch.setenv("OPENAI_API_KEY", "sk-testsecret1234567890")
    sanitized = _sanitize_error_message("Request failed sk-testsecret1234567890 error")
    assert "sk-t...7890" in sanitized
    assert "sk-testsecret1234567890" not in sanitized

    # _get_configured_model
    from sago.config.loader import invalidate_config_cache

    try:
        with patch("sago.config.loader.load_config") as mock_cfg:
            cfg = MagicMock()
            cfg.model = "gemini-2.0-flash"
            mock_cfg.return_value = cfg
            m = _get_configured_model()
            assert isinstance(m, str)
    finally:
        invalidate_config_cache()


def test_cli_help_command(runner: CliRunner) -> None:
    # Master dashboard
    res = runner.invoke(cli, ["help"])
    assert res.exit_code == 0
    assert "Command Reference" in res.output or "SAGO" in res.output

    # Specific command help
    res2 = runner.invoke(cli, ["help", "run"])
    assert res2.exit_code == 0
    assert "run" in res2.output

    # Fuzzy/unknown command
    res3 = runner.invoke(cli, ["help", "unknown_cmd_xyz"])
    assert res3.exit_code == 0


def test_cli_run_command_variants(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-key")
    # 1. Basic run
    with patch("sago.engine.simple_executor.execute_agent_task") as mock_exec:
        mock_exec.return_value = {
            "output": "Task succeeded",
            "iterations": 1,
            "tool_calls": [{"tool": "bash", "result": "ok"}],
        }
        res = runner.invoke(cli, ["run", "hello world task", "--agent", "python-engineer"])
        assert res.exit_code == 0
        assert "Task succeeded" in res.output

    # 2. Detach mode
    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.pid = 99999
        mock_popen.return_value = mock_proc
        res = runner.invoke(cli, ["run", "background task", "--detach"])
        assert res.exit_code == 0
        assert "Background Mode Active" in res.output or "Detached" in res.output

    # 3. Chain mode
    with patch("sago.engine.simple_executor.execute_agent_task") as mock_exec:
        mock_exec.return_value = {"output": "Chain finished", "iterations": 1}
        res = runner.invoke(cli, ["run", "chained task", "--chain", "architect,coder"])
        assert res.exit_code == 0


def test_cli_smart_command(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-key")
    with (
        patch("sago.llm.tui_providers.get_tui_client") as mock_tui,
        patch("sago.engine.simple_executor.execute_agent_task") as mock_exec,
    ):
        client = MagicMock()
        resp = MagicMock()
        choice = MagicMock()
        choice.message.content = "python-engineer"
        resp.choices = [choice]
        client.chat.completions.create.return_value = resp
        mock_tui.return_value = (client, "dummy-model")

        mock_exec.return_value = {
            "output": "Smart execution output",
            "iterations": 2,
            "tool_calls": [{"tool": "read_file", "result": "done"}],
        }

        res = runner.invoke(cli, ["smart", "optimize database query", "--effort", "high"])
        assert res.exit_code == 0
        assert "Smart Execution" in res.output


def test_cli_chain_command(runner: CliRunner) -> None:
    with patch("sago.engine.production.ProductionEngine.run_chain") as mock_chain:
        mock_chain.return_value = {"output": "Pipeline completed", "steps": 2}
        res = runner.invoke(
            cli, ["chain", "build api", "--chain", "system-architect,python-engineer"]
        )
        assert res.exit_code == 0


def test_cli_workflows_suite(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. workflows list
    res = runner.invoke(cli, ["workflows"])
    assert res.exit_code == 0

    # 2. workflow-create
    res = runner.invoke(
        cli,
        [
            "workflow-create",
            "AutoDeploy",
            "-d",
            "Automatic deployment pipeline",
            "-t",
            "manual",
        ],
    )
    assert res.exit_code == 0
    assert "Workflow created" in res.output or "AutoDeploy" in res.output

    # 3. workflow-add-step
    res = runner.invoke(
        cli,
        [
            "workflow-add-step",
            "wf_test_123",
            "-n",
            "LintStep",
            "-t",
            "agent_call",
            "-a",
            "code-reviewer",
            "--task",
            "Review files",
        ],
    )
    assert res.exit_code == 0

    # 4. workflow-run
    with patch("sago.workflow.engine.WorkflowEngine.execute_workflow") as mock_wf_exec:
        mock_wf_exec.return_value = MagicMock(status="completed", step_results=[])
        res = runner.invoke(cli, ["workflow-run", "wf_test_123"])
        assert res.exit_code == 0

    # 5. workflow (dynamic loop)
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-key")
    with patch("sago.workflow.langgraph_engine.SagoWorkflowEngine") as mock_engine_cls:
        eng = MagicMock()
        mock_res = MagicMock()
        mock_res.plan = ["step1"]
        mock_res.output = "Workflow done"
        mock_res.tool_calls = []
        mock_res.files_created = []
        mock_res.iterations = 1
        mock_res.elapsed = 1.5
        mock_res.tokens = {"input": 120, "output": 45}
        eng.run.return_value = mock_res
        mock_engine_cls.return_value = eng
        res = runner.invoke(cli, ["workflow", "analyze codebase", "-i", "2"])
        assert res.exit_code == 0


def test_cli_chat_command(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    with patch("sago.llm.tui_providers.resolve_active_llm_config") as mock_res:
        mock_res.return_value = {
            "api_key": "sk-dummy",
            "provider": "openai",
            "model": "gpt-4o",
            "base_url": "https://api.openai.com/v1",
        }
        # Single-shot exit
        res = runner.invoke(cli, ["chat", "exit"])
        assert res.exit_code == 0

        # Help
        res = runner.invoke(cli, ["chat", "help"])
        assert res.exit_code == 0

        # Single shot with response
        with patch("sago.main._chat_openai_compatible") as mock_chat_openai:
            mock_chat_openai.return_value = "Hello from AI!"
            res = runner.invoke(cli, ["chat", "Hi there!"], input="exit\n")
            assert res.exit_code == 0
            assert "Hello from AI!" in res.output


def test_chat_backend_helpers() -> None:
    # 1. _chat_openai_compatible
    with patch("openai.OpenAI") as mock_cls:
        client = MagicMock()
        mock_cls.return_value = client
        resp = MagicMock()
        choice = MagicMock()
        choice.message.content = "OpenAI response"
        resp.choices = [choice]
        client.chat.completions.create.return_value = resp

        out = _chat_openai_compatible(
            "openai",
            "gpt-4o",
            "key",
            "https://api.openai.com/v1",
            "prompt",
            [{"role": "user", "content": "hi"}],
            "hello",
        )
        assert out == "OpenAI response"

    # 2. _chat_gemini
    mock_genai = types.ModuleType("google.genai")
    mock_types = types.ModuleType("google.genai.types")
    mock_genai.types = mock_types

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "Gemini response"
    mock_client.models.generate_content.return_value = mock_resp
    mock_genai.Client = MagicMock(return_value=mock_client)

    mock_types.Content = MagicMock()
    mock_types.Part = MagicMock()
    mock_types.GenerateContentConfig = MagicMock()

    with patch.dict(sys.modules, {"google.genai": mock_genai, "google.genai.types": mock_types}):
        out = _chat_gemini(
            "gemini-key",
            "gemini-2.0-flash",
            "prompt",
            [{"role": "user", "content": "hi"}],
            "hello",
        )
        assert out == "Gemini response"


def test_cli_tui_and_attach(runner: CliRunner) -> None:
    # tui command
    with patch("sago.tui.app.SagoApp.run") as mock_tui_run:
        res = runner.invoke(cli, ["tui", "--resume", "sess_xyz"])
        assert res.exit_code == 0
        assert mock_tui_run.called

    # attach command with no target (list sessions)
    with patch("sago.database.Session") as mock_session_cls, patch("sago.database.init_db"):
        s = MagicMock()
        s.list_all.return_value = [
            {"id": "sess_1", "created_at": "2026-01-01", "title": "Test Session", "status": "open"}
        ]
        mock_session_cls.return_value = s
        res = runner.invoke(cli, ["attach"])
        assert res.exit_code == 0

    # attach with specific target (TUI session)
    with patch("sago.tui.app.SagoApp.run") as mock_tui_run:
        res = runner.invoke(cli, ["attach", "sess_1"])
        assert res.exit_code == 0


def test_cli_server_and_daemon(runner: CliRunner) -> None:
    # 1. serve --daemon
    with patch("sago.server.daemon.get_daemon") as mock_daemon_fn:
        daemon = MagicMock()
        daemon.is_running.return_value = False
        mock_daemon_fn.return_value = daemon
        res = runner.invoke(cli, ["serve", "--daemon"])
        assert res.exit_code == 0
        daemon.start.assert_called_once()

    # 2. serve (web server)
    with patch("uvicorn.run") as mock_uvicorn:
        res = runner.invoke(cli, ["serve", "--port", "8888"])
        assert res.exit_code == 0
        assert mock_uvicorn.called

    # 3. web alias
    with patch("uvicorn.run") as mock_uvicorn:
        res = runner.invoke(cli, ["web", "--port", "8888"])
        assert res.exit_code == 0
        assert mock_uvicorn.called

    # 4. stop
    with patch("sago.server.daemon.get_daemon") as mock_daemon_fn:
        daemon = MagicMock()
        daemon.is_running.return_value = True
        daemon.get_pid.return_value = 1234
        daemon.stop.return_value = True
        mock_daemon_fn.return_value = daemon
        res = runner.invoke(cli, ["stop"])
        assert res.exit_code == 0

    # 5. daemon-status
    with patch("sago.server.daemon.get_daemon") as mock_daemon_fn:
        daemon = MagicMock()
        daemon.is_running.return_value = True
        daemon.get_pid.return_value = 1234
        daemon.status.return_value = "Daemon PID 1234 is running"
        mock_daemon_fn.return_value = daemon
        res = runner.invoke(cli, ["daemon-status"])
        assert res.exit_code == 0
        assert "1234" in res.output

    # 6. remote
    with patch("sago.server.daemon.get_client") as mock_get_client:
        client = MagicMock()
        client.ping.return_value = True
        client.execute.return_value = {"status": "completed", "result": "Remote task completed"}
        mock_get_client.return_value = client
        res = runner.invoke(cli, ["remote", "test remote task"])
        assert res.exit_code == 0
        assert "Remote task completed" in res.output


def test_cli_intel_and_graph(runner: CliRunner) -> None:
    # 1. map
    res = runner.invoke(cli, ["map", "-d", "sago/utils"])
    assert res.exit_code == 0

    # 2. project-graph
    with patch("sago.memory.project_graph.ProjectGraph.build_graph") as mock_bg:
        mock_bg.return_value = None
        res = runner.invoke(cli, ["project-graph", "--view", "arch"])
        assert res.exit_code == 0

    # 3. graph alias
    res = runner.invoke(cli, ["graph", "--view", "mermaid"])
    assert res.exit_code == 0

    # 4. verify
    with patch("sago.engine.verifier.ProjectVerifier.verify_project") as mock_ver:
        rep = MagicMock()
        rep.passed = True
        rep.summary = "All checks passed successfully."
        mock_ver.return_value = rep
        res = runner.invoke(cli, ["verify", "-d", "."])
        assert res.exit_code == 0
        assert "ALL CHECKS PASSED" in res.output


def test_cli_onboard_setup_doctor_init(runner: CliRunner, tmp_path: Path) -> None:
    # 1. init
    with patch("sago.config.project_config.create_config_file") as mock_cfg_create:
        res = runner.invoke(cli, ["init", "--name", "my-project"])
        assert res.exit_code == 0
        assert mock_cfg_create.called

    # 2. doctor
    res = runner.invoke(cli, ["doctor"])
    assert res.exit_code == 0

    # 3. update --check
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"info": {"version": "0.1.15"}}).encode("utf-8")
        mock_url.return_value.__enter__.return_value = mock_resp
        res = runner.invoke(cli, ["update", "--check"])
        assert res.exit_code == 0

    # 4. setup / onboard
    with patch("sago.main._run_interactive_setup") as mock_setup_fn:
        res = runner.invoke(cli, ["setup"])
        assert res.exit_code == 0
        assert mock_setup_fn.called

        res2 = runner.invoke(cli, ["onboard"])
        assert res2.exit_code == 0


def test_cli_logs_commands(runner: CliRunner, tmp_path: Path) -> None:
    # 1. logs
    res = runner.invoke(cli, ["logs", "--limit", "5"])
    assert res.exit_code == 0

    # 2. logs stats
    res = runner.invoke(cli, ["logs", "stats"])
    assert res.exit_code == 0

    # 3. logs sessions
    res = runner.invoke(cli, ["logs", "sessions"])
    assert res.exit_code == 0

    # 4. logs level
    res = runner.invoke(cli, ["logs", "level", "--set", "debug"])
    assert res.exit_code == 0

    # 5. logs clean --dry-run
    res = runner.invoke(cli, ["logs", "clean", "--dry-run"])
    assert res.exit_code == 0

    # 6. logs export
    out_file = tmp_path / "logs_exported.json"
    res = runner.invoke(cli, ["logs", "export", str(out_file)])
    assert res.exit_code == 0


def test_cli_clean_commands(runner: CliRunner) -> None:
    with patch("sago.cleanup.run_cleanup") as mock_cleanup:
        mock_cleanup.return_value = [
            CleanResult(
                category="cache",
                items_scanned=10,
                items_deleted=2,
                bytes_reclaimed=1024,
                details=["ok"],
            ),
            CleanResult(
                category="backups",
                items_scanned=5,
                items_deleted=1,
                bytes_reclaimed=512,
                details=["ok"],
            ),
        ]
        res = runner.invoke(cli, ["clean", "--dry-run"])
        assert res.exit_code == 0
        assert "Running in dry-run mode" in res.output

        res2 = runner.invoke(cli, ["clean", "--force", "--all"])
        assert res2.exit_code == 0


def test_cli_misc_and_git_features(runner: CliRunner, tmp_path: Path) -> None:
    # 1. search
    with patch("sago.memory.hybrid_indexer.get_hybrid_code_indexer") as mock_idx_fn:
        indexer = MagicMock()
        chunk = MagicMock()
        chunk.file_path = "sago/main.py"
        chunk.start_line = 10
        chunk.end_line = 20
        chunk.name = "cli"
        res_item = MagicMock()
        res_item.chunk = chunk
        res_item.to_dict.return_value = {"file": "sago/main.py", "score": 0.9}
        indexer.search.return_value = [res_item]
        mock_idx_fn.return_value = indexer

        res = runner.invoke(cli, ["search", "cli group", "--json-out"])
        assert res.exit_code == 0

    # 2. telemetry
    res = runner.invoke(cli, ["telemetry", "--export", "json"])
    assert res.exit_code == 0

    # 3. checkpoint
    with patch("sago.engine.checkpoint.CheckpointManager.create_checkpoint") as mock_cp:
        mock_meta = MagicMock()
        mock_meta.checkpoint_id = "snap_123"
        mock_meta.file_paths = ["file.py"]
        mock_cp.return_value = mock_meta
        res = runner.invoke(cli, ["checkpoint", "create", "test snapshot"])
        assert res.exit_code == 0

    res = runner.invoke(cli, ["checkpoint", "list"])
    assert res.exit_code == 0

    # 4. parse
    test_doc = tmp_path / "test.md"
    test_doc.write_text("# Test Document\nSample text", encoding="utf-8")
    res = runner.invoke(cli, ["parse", str(test_doc)])
    assert res.exit_code == 0

    # 5. pr create
    with patch("sago.tools.vcs.pr_workflow.create_pr_workflow") as mock_pr:
        mock_pr.return_value = {
            "success": True,
            "message": "PR created successfully",
            "pr_url": "https://github.com/test/repo/pull/1",
            "branch": "feature/test",
        }
        res = runner.invoke(cli, ["pr", "create", "Add new feature", "--draft"])
        assert res.exit_code == 0

    # 6. hook install & run
    git_dir = tmp_path / ".git" / "hooks"
    git_dir.mkdir(parents=True)
    res = runner.invoke(cli, ["hook", "install", "--repo", str(tmp_path)])
    assert res.exit_code == 0
    assert (git_dir / "pre-commit").exists()

    with patch("sago.engine.verifier.get_project_verifier") as mock_gpv:
        rep = MagicMock()
        rep.passed = True
        rep.issues = []
        mock_v = MagicMock()
        mock_v.verify_project.return_value = rep
        mock_gpv.return_value = mock_v
        res2 = runner.invoke(cli, ["hook", "run", "--dir", str(tmp_path)])
        assert res2.exit_code == 0


def test_main_entrypoint() -> None:
    with patch("sago.main.cli") as mock_cli, patch("sago.paths.ensure_sago_dirs"):
        main()
        assert mock_cli.called


def test_cli_agents_and_info(runner: CliRunner) -> None:
    # 1. agents category overview
    res = runner.invoke(cli, ["agents"])
    assert res.exit_code == 0

    # 2. agents --all
    res = runner.invoke(cli, ["agents", "--all"])
    assert res.exit_code == 0

    # 3. agents query
    res = runner.invoke(cli, ["agents", "python"])
    assert res.exit_code == 0

    # 4. info for existing agent
    res = runner.invoke(cli, ["info", "python-engineer"])
    assert res.exit_code == 0

    # 5. info for nonexistent agent
    res = runner.invoke(cli, ["info", "unknown-specialist-xyz"])
    assert res.exit_code == 0
    assert "Agent not found" in res.output


def test_cli_tools_and_skills_and_plugins(runner: CliRunner) -> None:
    # 1. tools overview
    res = runner.invoke(cli, ["tools"])
    assert res.exit_code == 0

    # 2. tools --all
    res = runner.invoke(cli, ["tools", "--all"])
    assert res.exit_code == 0

    # 3. tools query specific tool
    res = runner.invoke(cli, ["tools", "bash"])
    assert res.exit_code == 0

    # 4. tools --category
    res = runner.invoke(cli, ["tools", "--category", "coding"])
    assert res.exit_code == 0

    # 5. tools --reload
    res = runner.invoke(cli, ["tools", "--reload"])
    assert res.exit_code == 0

    # 6. skills
    res = runner.invoke(cli, ["skills", "-f", "python"])
    assert res.exit_code == 0

    # 7. plugins
    res = runner.invoke(cli, ["plugins"])
    assert res.exit_code == 0


def test_cli_sessions_history_status_usage(runner: CliRunner) -> None:
    # 1. status
    res = runner.invoke(cli, ["status"])
    assert res.exit_code == 0

    # 2. usage
    res = runner.invoke(cli, ["usage"])
    assert res.exit_code == 0

    # 3. sessions
    res = runner.invoke(cli, ["sessions", "--limit", "5"])
    assert res.exit_code == 0

    # 4. history
    res = runner.invoke(cli, ["history", "nonexistent_session"])
    assert res.exit_code == 0

    # 5. checkpoint restore & prune
    with (
        patch("sago.engine.checkpoint.CheckpointManager.restore_checkpoint") as mock_res,
        patch("sago.engine.checkpoint.CheckpointManager.prune_checkpoints") as mock_prune,
    ):
        mock_res.return_value = {"success": True, "restored_count": 2}
        mock_prune.return_value = ["snap_old"]
        res = runner.invoke(cli, ["checkpoint", "restore", "snap_123"])
        assert res.exit_code == 0

        res2 = runner.invoke(cli, ["checkpoint", "prune", "2"])
        assert res2.exit_code == 0


def test_run_interactive_setup_wizard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sago.main import _run_interactive_setup

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    with (
        patch(
            "rich.prompt.Prompt.ask", side_effect=["1", "dummy_openrouter_key", "openrouter/free"]
        ),
        patch("rich.prompt.Confirm.ask", return_value=False),
    ):
        _run_interactive_setup()
        cfg_file = tmp_path / ".sago" / "config.yaml"
        assert cfg_file.exists()

    # Also test Ollama with base URL
    with (
        patch(
            "rich.prompt.Prompt.ask", side_effect=["7", "http://localhost:11434/v1", "deepseek-r1"]
        ),
        patch("rich.prompt.Confirm.ask", return_value=False),
    ):
        _run_interactive_setup()
        assert cfg_file.exists()
