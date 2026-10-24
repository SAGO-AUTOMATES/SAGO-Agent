"""Exhaustive tests for sago/tui/smart_suggest.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

from sago.tui import smart_suggest


def test_fuzzy_score_all_tiers() -> None:
    # 0. Empty query
    assert smart_suggest.fuzzy_score("", "anything") == 1.0

    # 1. Exact match
    assert smart_suggest.fuzzy_score("coder", "coder") == 100.0

    # 2. Prefix match
    assert smart_suggest.fuzzy_score("code", "coder-agent") >= 80.0

    # 3. Substring match
    assert smart_suggest.fuzzy_score("agent", "my-agent-specialist") >= 60.0

    # 4. Subsequence match ('pythn' in 'python-engineer')
    assert smart_suggest.fuzzy_score("pythn", "python-engineer") >= 40.0

    # 5. Approximate ratio match
    assert smart_suggest.fuzzy_score("refactr", "refactor") >= 20.0

    # 6. No match
    assert smart_suggest.fuzzy_score("zzzzz", "python") == 0.0


def test_get_git_modified_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(smart_suggest, "_GIT_CACHE", {})

    # Mock successful git status
    mock_run = MagicMock(
        return_value=subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="MM sago/tui/app.py\n?? tests/new_test.py\nAA docs/index.md\n",
            stderr="",
        )
    )
    monkeypatch.setattr("subprocess.run", mock_run)

    mods = smart_suggest.get_git_modified_files(tmp_path)
    assert "sago/tui/app.py" in mods
    assert "app.py" in mods
    assert "new_test.py" in mods

    # Test cache hit within 3 seconds
    mods_cached = smart_suggest.get_git_modified_files(tmp_path)
    assert mods_cached == mods
    assert mock_run.call_count == 1

    # Test failure branch
    smart_suggest._GIT_CACHE.clear()
    monkeypatch.setattr("subprocess.run", MagicMock(side_effect=Exception("Git not installed")))
    mods_failed = smart_suggest.get_git_modified_files(tmp_path)
    assert mods_failed == set()


def test_rank_agents_fuzzy() -> None:
    sample_agents = [
        {
            "name": "sago-orchestrator",
            "category": "meta",
            "description": "Orchestrates multi-agent tasks",
        },
        {
            "name": "coder",
            "category": "development",
            "description": "Expert in python and backend systems",
        },
        {
            "name": "researcher",
            "category": "analysis",
            "description": "Deep codebase search and exploration",
        },
        {
            "name": "tester",
            "category": "quality",
            "description": "Unit and integration test generator",
        },
    ]

    # Empty query returns featured / all agents
    ranked_default = smart_suggest.rank_agents_fuzzy(sample_agents, "")
    assert len(ranked_default) == len(sample_agents)

    # Search by name
    ranked_coder = smart_suggest.rank_agents_fuzzy(sample_agents, "coder")
    assert ranked_coder[0]["name"] == "coder"

    # Search by category
    ranked_dev = smart_suggest.rank_agents_fuzzy(sample_agents, "development")
    assert ranked_dev[0]["name"] == "coder"

    # Search by description keyword
    ranked_test = smart_suggest.rank_agents_fuzzy(sample_agents, "integration")
    assert ranked_test[0]["name"] == "tester"


def test_get_workspace_files_and_rank_files_smart(tmp_path, monkeypatch) -> None:
    # Setup test directory tree
    sub_dir = tmp_path / "pkg"
    sub_dir.mkdir()
    (sub_dir / "mod.py").write_text("print('hello')")
    (tmp_path / "README.md").write_text("# Project")

    # Git directory to skip
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("config")

    # Get workspace files
    entries = smart_suggest.get_workspace_files(tmp_path)
    paths = [e[0] for e in entries]
    assert any("README.md" in p for p in paths)
    assert any("mod.py" in p for p in paths)
    assert not any(".git" in p for p in paths)

    # Rank files smart
    monkeypatch.setattr(
        smart_suggest, "get_git_modified_files", lambda root: {"pkg/mod.py", "mod.py"}
    )
    items, vals = smart_suggest.rank_files_smart("mod", base_dir=tmp_path)
    assert len(items) >= 1
    assert any("mod.py" in v for v in vals)

    # Home directory rank mode
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    home_items, home_vals = smart_suggest.rank_files_smart("", home=True)
    assert len(home_items) >= 1


def test_get_subcommand_completions_all_branches() -> None:
    # Unknown command
    assert smart_suggest.get_subcommand_completions("/unknown_cmd arg") is None

    # Supported commands
    commands_to_test = [
        "/plan",
        "/plan my new feature",
        "/graph",
        "/project_graph arch",
        "/map",
        "/map routes",
        "/perms",
        "/perms allow",
        "/todo",
        "/todo done",
        "/buttons",
        "/tasks",
        "/tasks cancel",
        "/mcp",
        "/skills",
        "/agent",
        "/agents list",
        "/git",
        "/git status",
        "/pr",
        "/session",
        "/session switch",
        "/checkpoint",
        "/checkpoint restore",
        "/chain",
        "/chain coder,tester",
        "/delegate",
        "/parallel",
        "/model",
        "/model gpt",
        "/provider",
    ]

    for raw_cmd in commands_to_test:
        result = smart_suggest.get_subcommand_completions(raw_cmd)
        assert result is not None
        items, values = result
        assert isinstance(items, list)
        assert isinstance(values, list)
