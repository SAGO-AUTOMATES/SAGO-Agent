"""Persistent settings — global (~/.sago/settings.json) + project-level (.sago/settings.json)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import RootModel, ValidationError

from sago.paths import get_sago_home

logger = logging.getLogger(__name__)

GLOBAL_SETTINGS = get_sago_home() / "settings.json"

# Validates that a settings document is a JSON object (free-form otherwise).
SettingsData = RootModel[dict[str, Any]]


def _find_project_root() -> Path | None:
    """Walk up from cwd looking for a git root or pyproject.toml."""
    cwd = Path.cwd()
    for p in [cwd, *cwd.parents]:
        if (p / ".git").exists() or (p / "pyproject.toml").exists():
            logger.debug("Project root found: %s", p)
            return p
    logger.debug("No project root found from %s", cwd)
    return None


def _project_settings_path() -> Path | None:
    root = _find_project_root()
    if root:
        return root / ".sago" / "settings.json"
    return None


def _load_settings_file(path: Path) -> dict[str, Any]:
    """Read and validate a single settings JSON file.

    Raises ValueError with a clear message when the file is malformed or is not
    a JSON object, instead of silently ignoring the error.
    """
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse settings file %s: %s", path, exc)
        raise ValueError(f"Malformed settings JSON in {path}: {exc}") from exc

    try:
        validated = SettingsData.model_validate(raw)
    except ValidationError as exc:
        logger.error("Invalid settings structure in %s", path)
        raise ValueError(f"Invalid settings in {path}: {exc}") from exc

    if not isinstance(validated.root, dict):
        logger.error("Settings file %s is not a JSON object", path)
        raise ValueError(f"Settings in {path} must be a JSON object")

    return validated.root


def load_settings() -> dict[str, Any]:
    """Load merged settings: global base + project overrides."""
    settings: dict[str, Any] = {}
    # Global base
    if GLOBAL_SETTINGS.exists():
        logger.debug("Loading global settings from %s", GLOBAL_SETTINGS)
        settings.update(_load_settings_file(GLOBAL_SETTINGS))
    # Project overrides
    proj = _project_settings_path()
    if proj and proj.exists():
        logger.debug("Loading project settings from %s", proj)
        settings.update(_load_settings_file(proj))
    logger.debug("Settings loaded: %d keys", len(settings))
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
            SettingsData.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning(
                "Existing settings file %s is malformed (%s); it will be overwritten",
                path,
                exc,
            )
    data[key] = value
    path.write_text(json.dumps(data, indent=2))
    logger.debug("Setting saved: key=%s, scope=%s, path=%s", key, scope, path)


def load_setting(key: str, default: Any = None) -> Any:
    """Get a setting (project > global > default)."""
    # Project wins
    proj = _project_settings_path()
    if proj and proj.exists():
        data = _load_settings_file(proj)
        if key in data:
            logger.debug("Setting '%s' found in project settings", key)
            return data[key]
    # Then global
    if GLOBAL_SETTINGS.exists():
        data = _load_settings_file(GLOBAL_SETTINGS)
        if key in data:
            logger.debug("Setting '%s' found in global settings", key)
            return data[key]
    logger.debug("Setting '%s' not found, using default=%s", key, default)
    return default
