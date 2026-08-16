"""Unit tests for TUI Smart Suggestions — fuzzy search, Git-aware files, and dynamic subcommands."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from sago.tui.smart_suggest import (
    fuzzy_score,
    get_subcommand_completions,
    rank_agents_fuzzy,
    rank_files_smart,
)


def test_fuzzy_score():
    """Verify fuzzy scoring ranks exact > prefix > substring > subsequence."""
    assert fuzzy_score("python", "python") == 100.0
    assert fuzzy_score("py", "python-engineer") > fuzzy_score("eng", "python-engineer")
    assert fuzzy_score("pythn", "python-engineer") > 0.0
    assert fuzzy_score("dockr", "docker-engineer") > 0.0
    assert fuzzy_score("xyz123", "python") == 0.0


def test_rank_agents_fuzzy():
    """Verify agent ranking prioritizes typo-tolerant matches."""
    agents = [
        {"name": "python-engineer", "category": "coding", "description": "Python expert"},
        {"name": "docker-engineer", "category": "devops", "description": "Container expert"},
        {"name": "rust-engineer", "category": "systems", "description": "Rust systems dev"},
    ]
    matches = rank_agents_fuzzy(agents, "pythn")
    assert len(matches) > 0
    assert matches[0]["name"] == "python-engineer"

    matches_doc = rank_agents_fuzzy(agents, "dockr")
    assert len(matches_doc) > 0
    assert matches_doc[0]["name"] == "docker-engineer"


def test_subcommand_completions():
    """Verify dynamic parameter autocomplete for slash commands."""
    res_git = get_subcommand_completions("/git")
    assert res_git is not None
    items, values = res_git
    assert any("status" in v for v in values)
    assert any("diff" in v for v in values)

    res_pr = get_subcommand_completions("/pr")
    assert res_pr is not None
    _, pr_vals = res_pr
    assert any("create" in v for v in pr_vals)

    res_chain = get_subcommand_completions("/chain")
    assert res_chain is not None
    _, chain_vals = res_chain
    assert any("architect -> python-engineer" in v for v in chain_vals)

    res_del = get_subcommand_completions("/delegate")
    assert res_del is not None
    _, del_vals = res_del
    assert any("python-engineer" in v for v in del_vals)

    res_model = get_subcommand_completions("/model")
    assert res_model is not None
    _, model_vals = res_model
    assert any("openrouter/free" in v for v in model_vals)

    res_prov = get_subcommand_completions("/provider")
    assert res_prov is not None
    _, prov_vals = res_prov
    assert any("openrouter" in v for v in prov_vals)


def test_rank_files_smart():
    """Verify file ranking with Git status, nested subfolders, and fuzzy search."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "app.py").write_text("print(1)")
        nested = root / "sago" / "tui"
        nested.mkdir(parents=True)
        (nested / "models.py").write_text("x = 1")
        (nested / "processor.py").write_text("y = 2")
        (root / "README.md").write_text("# Test")

        # Test nested file discovery from root without typing subpath
        items, values = rank_files_smart("proc", base_dir=root)
        assert len(items) > 0
        assert any("#sago/tui/processor.py" in v for v in values)

        # Test nested file discovery with exact name
        items_mod, values_mod = rank_files_smart("models", base_dir=root)
        assert len(items_mod) > 0
        assert any("#sago/tui/models.py" in v for v in values_mod)


def test_new_subcommand_completions():
    """Verify /graph, /map, /perms, /todo subcommands have clean suggestions."""
    res_graph = get_subcommand_completions("/graph")
    assert res_graph is not None
    _, graph_vals = res_graph
    assert any("/graph arch" in v for v in graph_vals)
    assert any("/graph models" in v for v in graph_vals)

    res_perms = get_subcommand_completions("/perms")
    assert res_perms is not None
    _, perms_vals = res_perms
    assert any("/perms allow" in v for v in perms_vals)
    assert any("/perms block" in v for v in perms_vals)

    res_plan = get_subcommand_completions("/plan")
    assert res_plan is not None
    _, plan_vals = res_plan
    assert any("/plan <task>" in v for v in plan_vals)
    assert any("/plan status" in v for v in plan_vals)

    res_todo = get_subcommand_completions("/todo")
    assert res_todo is not None
    _, todo_vals = res_todo
    assert any("/todo list" in v for v in todo_vals)
    assert any("/todo done" in v for v in todo_vals)


@pytest.mark.anyio
async def test_session_suggestions_and_routing():
    """Verify /session subcommands and suggestions work smoothly."""
    from sago.database import Session, init_db
    from sago.tui.app import SagoApp

    init_db()
    s = Session()
    s_info = s.create(title="Test Autocomplete Session")
    sid = str(s_info["id"])

    res = get_subcommand_completions("/session")
    assert res is not None
    items, values = res
    # Ensure active session appears in suggestions
    assert any(sid[:8] in v for v in values)

    # Verify /session list routes without 'Session not found: list' error
    app = SagoApp()
    async with app.run_test() as pilot:
        app._switch_session("list")  # Should not raise
        await pilot.pause()
        app._switch_session(sid[:8])
        await pilot.pause()
        assert app.current_session_id == sid
