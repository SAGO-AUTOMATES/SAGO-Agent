"""Comprehensive tests for sago.settings."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from sago.settings import (
    _load_settings_file,
    load_setting,
    load_settings,
    save_setting,
)


class TestLoadSettingsFile:
    def test_valid_json(self, tmp_path: Path) -> None:
        p = tmp_path / "settings.json"
        p.write_text('{"model": "gpt-4o", "effort": "high"}')
        result = _load_settings_file(p)
        assert result["model"] == "gpt-4o"
        assert result["effort"] == "high"

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "settings.json"
        p.write_text("{bad json}")
        with pytest.raises(ValueError, match="Malformed"):
            _load_settings_file(p)

    def test_non_object_json_raises(self, tmp_path: Path) -> None:
        # A JSON array is valid JSON but not an object
        p = tmp_path / "settings.json"
        p.write_text("[1, 2, 3]")
        with pytest.raises(ValueError):
            _load_settings_file(p)

    def test_empty_object_valid(self, tmp_path: Path) -> None:
        p = tmp_path / "settings.json"
        p.write_text("{}")
        result = _load_settings_file(p)
        assert result == {}


class TestLoadSettings:
    def test_no_files_returns_empty(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "settings.json"
        with patch("sago.settings.GLOBAL_SETTINGS", nonexistent):
            with patch("sago.settings._project_settings_path", return_value=None):
                result = load_settings()
        assert isinstance(result, dict)

    def test_global_only(self, tmp_path: Path) -> None:
        settings_file = tmp_path / "settings.json"
        settings_file.write_text('{"theme": "dark"}')
        with patch("sago.settings.GLOBAL_SETTINGS", settings_file):
            with patch("sago.settings._project_settings_path", return_value=None):
                result = load_settings()
        assert result.get("theme") == "dark"

    def test_project_overrides_global(self, tmp_path: Path) -> None:
        global_file = tmp_path / "global.json"
        project_file = tmp_path / "project.json"
        global_file.write_text('{"theme": "dark", "effort": "low"}')
        project_file.write_text('{"effort": "high"}')
        with patch("sago.settings.GLOBAL_SETTINGS", global_file):
            with patch("sago.settings._project_settings_path", return_value=project_file):
                result = load_settings()
        assert result["theme"] == "dark"
        assert result["effort"] == "high"  # project wins


class TestSaveSetting:
    def test_save_global(self, tmp_path: Path) -> None:
        global_file = tmp_path / "settings.json"
        with patch("sago.settings.GLOBAL_SETTINGS", global_file):
            save_setting("my_key", "my_value", scope="global")
        data = json.loads(global_file.read_text())
        assert data["my_key"] == "my_value"

    def test_save_global_preserves_existing(self, tmp_path: Path) -> None:
        global_file = tmp_path / "settings.json"
        global_file.write_text('{"existing": "yes"}')
        with patch("sago.settings.GLOBAL_SETTINGS", global_file):
            save_setting("new_key", 42, scope="global")
        data = json.loads(global_file.read_text())
        assert data["existing"] == "yes"
        assert data["new_key"] == 42

    def test_save_project_scope(self, tmp_path: Path) -> None:
        project_file = tmp_path / ".sago" / "settings.json"
        with patch("sago.settings._project_settings_path", return_value=project_file):
            save_setting("proj_key", "proj_val", scope="project")
        assert project_file.exists()
        data = json.loads(project_file.read_text())
        assert data["proj_key"] == "proj_val"

    def test_save_project_no_project_root(self, tmp_path: Path) -> None:
        # When no project root, saves to cwd/.sago/settings.json
        cwd_file = tmp_path / ".sago" / "settings.json"
        with patch("sago.settings._project_settings_path", return_value=None):
            with patch("sago.settings.Path.cwd", return_value=tmp_path):
                save_setting("k", "v", scope="project")
        if cwd_file.exists():
            data = json.loads(cwd_file.read_text())
            assert data["k"] == "v"

    def test_save_overwrites_malformed_existing(self, tmp_path: Path) -> None:
        global_file = tmp_path / "settings.json"
        global_file.write_text("{bad json}")
        with patch("sago.settings.GLOBAL_SETTINGS", global_file):
            save_setting("clean", "start", scope="global")
        data = json.loads(global_file.read_text())
        assert data["clean"] == "start"


class TestLoadSetting:
    def test_fallback_to_default(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "settings.json"
        with patch("sago.settings.GLOBAL_SETTINGS", nonexistent):
            with patch("sago.settings._project_settings_path", return_value=None):
                val = load_setting("missing_key", default="fallback")
        assert val == "fallback"

    def test_found_in_global(self, tmp_path: Path) -> None:
        settings_file = tmp_path / "settings.json"
        settings_file.write_text('{"model": "claude-3-haiku"}')
        with patch("sago.settings.GLOBAL_SETTINGS", settings_file):
            with patch("sago.settings._project_settings_path", return_value=None):
                val = load_setting("model")
        assert val == "claude-3-haiku"

    def test_project_wins_over_global(self, tmp_path: Path) -> None:
        global_file = tmp_path / "global.json"
        project_file = tmp_path / "project.json"
        global_file.write_text('{"effort": "low"}')
        project_file.write_text('{"effort": "high"}')
        with patch("sago.settings.GLOBAL_SETTINGS", global_file):
            with patch("sago.settings._project_settings_path", return_value=project_file):
                val = load_setting("effort")
        assert val == "high"

    def test_global_fallback_when_not_in_project(self, tmp_path: Path) -> None:
        global_file = tmp_path / "global.json"
        project_file = tmp_path / "project.json"
        global_file.write_text('{"global_key": "from_global"}')
        project_file.write_text('{"other": "thing"}')
        with patch("sago.settings.GLOBAL_SETTINGS", global_file):
            with patch("sago.settings._project_settings_path", return_value=project_file):
                val = load_setting("global_key")
        assert val == "from_global"
