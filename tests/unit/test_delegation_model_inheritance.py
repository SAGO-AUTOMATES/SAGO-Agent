"""Tests for LLM model and provider inheritance across delegation and subagents."""

from __future__ import annotations

from unittest.mock import patch

from sago.llm.tui_providers import resolve_active_llm_config
from sago.tools.file.agent_delegator import AgentDelegator
from sago.tools.file.spawn_agent import SpawnAgentTool


def test_resolve_active_llm_config_with_custom_env(monkeypatch):
    monkeypatch.setenv("SAGO_PROVIDER", "openai")
    monkeypatch.setenv("SAGO_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai-12345")

    cfg = resolve_active_llm_config()
    assert cfg["provider"] == "openai"
    assert cfg["model"] == "gpt-4o"
    assert cfg["api_key"] == "sk-test-openai-12345"
    assert "api.openai.com" in cfg["base_url"]


def test_resolve_active_llm_config_google_gemini(monkeypatch):
    monkeypatch.setenv("SAGO_PROVIDER", "google")
    monkeypatch.setenv("SAGO_MODEL", "gemini-2.5-pro")
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyTestKey123")

    cfg = resolve_active_llm_config()
    assert cfg["provider"] == "google"
    assert cfg["model"] == "gemini-2.5-pro"
    assert cfg["api_key"] == "AIzaSyTestKey123"
    assert cfg["base_url"] is None


@patch("sago.engine.simple_executor.execute_agent_task")
def test_agent_delegator_inherits_model(mock_exec, monkeypatch):
    monkeypatch.setenv("SAGO_PROVIDER", "openai")
    monkeypatch.setenv("SAGO_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-mock-key")

    mock_exec.return_value = {
        "output": "Delegation task completed successfully by specialist.",
        "tool_calls": [],
    }

    delegator = AgentDelegator()
    res = delegator.execute_delegated("Write a fast sorting function in python")

    assert res["success"] is True
    assert mock_exec.called
    call_kwargs = mock_exec.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o-mini"
    assert call_kwargs["api_key"] == "sk-mock-key"


@patch("sago.engine.simple_executor.execute_agent_task")
def test_spawn_agent_inherits_model(mock_exec, monkeypatch):
    monkeypatch.setenv("SAGO_PROVIDER", "google")
    monkeypatch.setenv("SAGO_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-gemini-test")

    mock_exec.return_value = {
        "output": "Code written by python engineer specialist.",
        "tool_calls": [],
    }

    tool = SpawnAgentTool()
    res = tool.run(task="Refactor codebase", agent_name="python-engineer")

    assert "python-engineer" in res or "Code written" in res
    assert mock_exec.called
    call_kwargs = mock_exec.call_args.kwargs
    assert call_kwargs["model"] == "gemini-2.5-flash"
    assert call_kwargs["api_key"] == "AIza-gemini-test"
