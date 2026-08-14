"""Tests for settings & project_config validation (sago/settings.py, sago/config/project_config.py)."""

from __future__ import annotations

import json

import pytest

import sago.config.project_config as project_config
import sago.paths
import sago.settings as settings
from sago.config.project_config import load_config
from sago.settings import load_setting, load_settings, save_setting

# ---------------------------------------------------------------------------
# settings.py
# ---------------------------------------------------------------------------


def test_load_settings_defaults_no_file(tmp_path, monkeypatch):
    """With no config files present, loading returns an empty dict (defaults)."""
    monkeypatch.setattr(settings, "GLOBAL_SETTINGS", tmp_path / "settings.json")
    monkeypatch.setattr(settings, "_project_settings_path", lambda: None)

    assert load_settings() == {}
    assert load_setting("model", "gemini") == "gemini"


def test_load_setting_defaults_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "GLOBAL_SETTINGS", tmp_path / "settings.json")
    monkeypatch.setattr(settings, "_project_settings_path", lambda: None)

    assert load_setting("provider", "openai") == "openai"
    assert load_setting("missing") is None


def test_load_settings_valid_file(tmp_path, monkeypatch):
    cfg = tmp_path / "settings.json"
    cfg.write_text(json.dumps({"model": "opus", "provider": "anthropic"}))
    monkeypatch.setattr(settings, "GLOBAL_SETTINGS", cfg)
    monkeypatch.setattr(settings, "_project_settings_path", lambda: None)

    data = load_settings()
    assert data["model"] == "opus"
    assert data["provider"] == "anthropic"
    assert load_setting("model", "x") == "opus"


def test_load_settings_invalid_file_raises(tmp_path, monkeypatch):
    cfg = tmp_path / "settings.json"
    cfg.write_text("{ this is not valid json ")
    monkeypatch.setattr(settings, "GLOBAL_SETTINGS", cfg)
    monkeypatch.setattr(settings, "_project_settings_path", lambda: None)

    with pytest.raises(ValueError):
        load_settings()
    with pytest.raises(ValueError):
        load_setting("model", "x")


def test_save_setting_roundtrip(tmp_path, monkeypatch):
    cfg = tmp_path / "settings.json"
    monkeypatch.setattr(settings, "GLOBAL_SETTINGS", cfg)
    monkeypatch.setattr(settings, "_project_settings_path", lambda: None)

    save_setting("model", "sonnet")
    assert load_setting("model") == "sonnet"
    # saving a malformed pre-existing file is logged, not silently dropped
    cfg.write_text("{ broken ")
    save_setting("model", "haiku")
    assert json.loads(cfg.read_text())["model"] == "haiku"


# ---------------------------------------------------------------------------
# project_config.py
# ---------------------------------------------------------------------------


def test_load_config_defaults_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(sago.paths, "get_sago_home", lambda: tmp_path / "home")
    data = load_config(tmp_path)
    assert data["orchestrator"]["max_iterations"] == 15
    assert data["orchestrator"]["default_provider"] == "gemini"
    assert data["permissions"]["blocked_paths"] == ["/etc", "/sys", "/proc"]


def test_create_and_load_valid_config(tmp_path):
    path = project_config.create_config_file(
        project_path=tmp_path,
        project_name="demo",
        languages=["python"],
        frameworks=["fastapi"],
        enable_ssh=True,
    )
    assert path.exists()
    data = load_config(tmp_path)
    assert data["project"]["name"] == "demo"
    assert data["permissions"]["allow_ssh"] is True
    # unknown agent keys are preserved
    assert data["agents"]


def test_load_config_invalid_file_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(sago.paths, "get_sago_home", lambda: tmp_path / "home")
    cfg = tmp_path / "config.sago.json"
    # orchestrator must be an object, not a string
    cfg.write_text(json.dumps({"version": "1.0.0", "orchestrator": "broken"}))
    with pytest.raises(ValueError):
        load_config(tmp_path)


def test_load_config_out_of_range_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(sago.paths, "get_sago_home", lambda: tmp_path / "home")
    cfg = tmp_path / "config.sago.json"
    cfg.write_text(
        json.dumps(
            {
                "version": "1.0.0",
                "orchestrator": {"max_iterations": 0, "temperature": 3.0},
            }
        )
    )
    with pytest.raises(ValueError):
        load_config(tmp_path)


def test_dead_functions_removed():
    """Dead/no-caller helpers were removed; public callers remain."""
    for name in ("get_agent_config", "is_agent_enabled", "is_tool_enabled"):
        assert not hasattr(project_config, name), f"{name} should have been removed"
    # Callers of the module still exist
    assert hasattr(project_config, "create_config_file")
    assert hasattr(project_config, "load_config")
    assert hasattr(project_config, "detect_project_languages")
    assert hasattr(project_config, "detect_project_frameworks")
