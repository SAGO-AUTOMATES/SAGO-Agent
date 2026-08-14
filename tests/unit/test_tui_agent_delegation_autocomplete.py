"""Unit tests for @ and /delegate agent autocompletion in TUI."""

from __future__ import annotations

from unittest.mock import MagicMock

from sago.tui.app import SagoApp


def _create_mock_app():
    app = MagicMock(spec=SagoApp)
    app._rank_agent_matches = lambda agents, query: SagoApp._rank_agent_matches(app, agents, query)
    return app


def test_show_agent_suggestions_empty_prefix():
    """Typing @ alone should suggest available specialist agents with descriptions."""
    app = _create_mock_app()
    shown_items = []
    shown_values = []
    app._show_suggestions = lambda items, values: (
        shown_items.extend(items),
        shown_values.extend(values),
    )

    SagoApp._show_agent_suggestions(app, "")

    assert len(shown_values) > 0
    assert any("python" in v.lower() for v in shown_values)
    assert any("bold magenta" in item for item in shown_items)


def test_show_agent_suggestions_filtered():
    """Typing @py should filter agent list, placing name matches first."""
    app = _create_mock_app()
    shown_items = []
    shown_values = []
    app._show_suggestions = lambda items, values: (
        shown_items.extend(items),
        shown_values.extend(values),
    )

    SagoApp._show_agent_suggestions(app, "py")

    assert len(shown_values) > 0
    assert any("python-engineer" in val for val in shown_values[:5])
    assert all(val.startswith("@") for val in shown_values)


def test_show_cmd_suggestions_delegate():
    """Typing /delegate or @delegate should suggest agents."""
    app = _create_mock_app()
    shown_items = []
    shown_values = []
    app._show_suggestions = lambda items, values: (
        shown_items.extend(items),
        shown_values.extend(values),
    )

    SagoApp._show_cmd_suggestions(app, "/delegate py")

    assert len(shown_values) > 0
    assert all(v.startswith("/delegate ") for v in shown_values)

    shown_items.clear()
    shown_values.clear()
    SagoApp._show_cmd_suggestions(app, "@delegate py")
    assert len(shown_values) > 0
    assert all(v.startswith("@delegate ") for v in shown_values)


def test_show_cmd_suggestions_chain():
    """Typing /chain should suggest agents."""
    app = _create_mock_app()
    shown_items = []
    shown_values = []
    app._show_suggestions = lambda items, values: (
        shown_items.extend(items),
        shown_values.extend(values),
    )

    SagoApp._show_cmd_suggestions(app, "/chain ")
    assert len(shown_values) > 0
    assert all(v.startswith("/chain ") for v in shown_values)
