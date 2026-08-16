"""Unit tests for competitive features: Ollama local provider, PR workflow, direct shell escape, and self-healing verification."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from sago.engine.verifier import VerificationReport
from sago.llm.ollama import OllamaProvider, is_ollama_running
from sago.main import pr_create
from sago.tools.vcs.pr_workflow import PRWorkflowTool, create_pr_workflow


def test_ollama_provider_local_models_and_check():
    """Verify OllamaProvider model listing and daemon detection."""
    provider = OllamaProvider({"model": "qwen2.5-coder", "base_url": "http://127.0.0.1:11434"})
    assert provider.model == "qwen2.5-coder"
    # When offline/no daemon running, should gracefully return empty list and False
    models = provider.list_local_models()
    assert isinstance(models, list)
    assert isinstance(is_ollama_running("http://127.0.0.1:11434"), bool)


def test_pr_workflow_in_git_repo():
    """Verify PR workflow creates feature branch and formats PR description."""
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

        # Mock verifier to always pass (unit test for PR workflow, not verifier)
        mock_report = VerificationReport(
            passed=True, linter_passed=True, typecheck_passed=True, tests_passed=True
        )
        with patch("sago.engine.verifier.get_project_verifier") as mock_verifier:
            mock_verifier.return_value.verify_project.return_value = mock_report
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
        with patch("sago.engine.verifier.get_project_verifier") as mock_verifier:
            mock_verifier.return_value.verify_project.return_value = mock_report
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
