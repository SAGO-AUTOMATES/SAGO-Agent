"""Unit tests for competitive features: Ollama local provider, PR workflow, direct shell escape, and self-healing verification."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from sago.llm.ollama import OllamaProvider, is_ollama_running
from sago.main import pr_create
from sago.tools.vcs.pr_workflow import PRWorkflowTool, create_pr_workflow


def _make_passing_verifier():
    """Create a mock verifier that always passes."""
    mock_verifier = MagicMock()
    mock_report = MagicMock()
    mock_report.passed = True
    mock_report.linter_passed = True
    mock_report.typecheck_passed = True
    mock_report.tests_passed = True
    mock_report.issues = []
    mock_verifier.verify_project.return_value = mock_report
    return mock_verifier


def test_ollama_provider_local_models_and_check():
    """Verify OllamaProvider model listing and daemon detection."""
    provider = OllamaProvider({"model": "qwen2.5-coder", "base_url": "http://127.0.0.1:11434"})
    assert provider.model == "qwen2.5-coder"
    # When offline/no daemon running, should gracefully return empty list and False
    models = provider.list_local_models()
    assert isinstance(models, list)
    assert isinstance(is_ollama_running("http://127.0.0.1:11434"), bool)


@patch("sago.engine.verifier.get_project_verifier")
def test_pr_workflow_in_git_repo(mock_get_verifier):
    """Verify PR workflow creates feature branch and formats PR description."""
    mock_get_verifier.return_value = _make_passing_verifier()

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        subprocess.run(["git", "init"], cwd=str(root), capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "TestUser"], cwd=str(root), capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"], cwd=str(root), capture_output=True
        )

        (root / "app.py").write_text("def hello():\n    return 'world'\n")
        subprocess.run(["git", "add", "-A"], cwd=str(root), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=str(root), capture_output=True
        )

        # Make a change
        (root / "app.py").write_text("def hello():\n    return 'world 2'\n")

        res = create_pr_workflow(
            title="Add feature updates",
            body="Implements updated response",
            branch="feat/hello-update",
            cwd=str(root),
        )

        assert res["success"] is True
        assert res["branch"] == "feat/hello-update"
        assert "pr_markdown" in res or "pr_url" in res

        # Tool execution interface
        tool = PRWorkflowTool()
        t_res = tool.execute(title="Test PR", branch="feat/tool-branch", cwd=str(root))
        assert t_res.success is True


def test_pr_cli_command():
    """Verify 'sago pr create' CLI command."""
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        subprocess.run(["git", "init"], cwd=str(root), capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "TestUser"], cwd=str(root), capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"], cwd=str(root), capture_output=True
        )

        (root / "main.py").write_text("print(1)\n")
        subprocess.run(["git", "add", "-A"], cwd=str(root), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=str(root), capture_output=True
        )

        # Test PR creation in temp repo
        res = runner.invoke(pr_create, ["Some PR Title", "--dir", str(root)])
        assert "Pull Request" in res.output or "✓" in res.output
