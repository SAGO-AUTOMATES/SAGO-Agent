"""Persistent settings — global (~/.sago/settings.json) + project-level (.sago/settings.json)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sago.paths import get_sago_home

GLOBAL_SETTINGS = get_sago_home() / "settings.json"


def _find_project_root() -> Path | None:
    """Walk up from cwd looking for a git root or pyproject.toml."""
    cwd = Path.cwd()
    for p in [cwd, *cwd.parents]:
        if (p / ".git").exists() or (p / "pyproject.toml").exists():
            return p
    return None


def _project_settings_path() -> Path | None:
    root = _find_project_root()
    if root:
        return root / ".sago" / "settings.json"
    return None


def load_settings() -> dict[str, Any]:
    """Load merged settings: global base + project overrides."""
    settings: dict[str, Any] = {}
    # Global base
    if GLOBAL_SETTINGS.exists():
        try:
            settings.update(json.loads(GLOBAL_SETTINGS.read_text()))
        except Exception:
            pass
    # Project overrides
    proj = _project_settings_path()
    if proj and proj.exists():
        try:
            settings.update(json.loads(proj.read_text()))
        except Exception:
            pass
    return settings


def save_setting(key: str, value: Any, scope: str = "global") -> None:
    """Save a single setting. scope='global' or 'project'."""
    if scope == "project":
        path = _project_settings_path()
        if path is None:
            # Create in current dir if no project root found
            path = Path.cwd() / ".sago" / "settings.json"
    else:
        path = GLOBAL_SETTINGS

    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except Exception:
            pass
    data[key] = value
    path.write_text(json.dumps(data, indent=2))


def load_setting(key: str, default: Any = None) -> Any:
    """Get a setting (project > global > default)."""
    # Project wins
    proj = _project_settings_path()
    if proj and proj.exists():
        try:
            data = json.loads(proj.read_text())
            if key in data:
                return data[key]
        except Exception:
            pass
    # Then global
    if GLOBAL_SETTINGS.exists():
        try:
            data = json.loads(GLOBAL_SETTINGS.read_text())
            if key in data:
                return data[key]
        except Exception:
            pass
    return default
