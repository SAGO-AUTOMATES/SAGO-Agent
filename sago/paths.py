"""Cross-platform path management for Sago.

Handles ~/.sago/ directory across Linux, macOS, and Windows.
"""

from __future__ import annotations

import logging
import os
import platform
from pathlib import Path

logger = logging.getLogger("sago.paths")


def get_sago_home() -> Path:
    """Get the Sago home directory based on OS and environment.

    Supports:
    - SAGO_HOME environment variable override (any OS)
    - Linux/macOS: ~/.sago/
    - Windows: %USERPROFILE%/.sago/ or %LOCALAPPDATA%/sago

    Returns:
        Path to the Sago home directory.
    """
    if "SAGO_HOME" in os.environ:
        sago_home = Path(os.environ["SAGO_HOME"]).expanduser().resolve()
        logger.debug("Resolved SAGO_HOME from environment: %s", sago_home)
    elif platform.system() == "Windows":
        base = Path(os.environ.get("USERPROFILE", Path.home()))
        sago_home = (base / ".sago").resolve()
        logger.debug("Resolved Sago home on Windows: %s", sago_home)
    else:
        base = Path.home()
        sago_home = (base / ".sago").resolve()
        logger.debug("Resolved Sago home on Unix: %s", sago_home)

    try:
        sago_home.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error("Failed to create Sago home directory %s: %s", sago_home, e)
        raise
    return sago_home


def get_data_dir() -> Path:
    """Get the Sago data directory for databases and persistent data.

    Returns:
        Path to the data directory.
    """
    data_dir = get_sago_home() / "data"
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error("Failed to create data directory %s: %s", data_dir, e)
        raise
    return data_dir


def get_sessions_dir() -> Path:
    """Get the sessions directory.

    Returns:
        Path to the sessions directory.
    """
    sessions_dir = get_sago_home() / "sessions"
    try:
        sessions_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error("Failed to create sessions directory %s: %s", sessions_dir, e)
        raise
    return sessions_dir


def get_logs_dir() -> Path:
    """Get the logs directory.

    Returns:
        Path to the logs directory.
    """
    logs_dir = get_sago_home() / "logs"
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error("Failed to create logs directory %s: %s", logs_dir, e)
        raise
    return logs_dir


def get_config_dir() -> Path:
    """Get the user config directory.

    Returns:
        Path to the config directory.
    """
    config_dir = get_sago_home() / "config"
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error("Failed to create config directory %s: %s", config_dir, e)
        raise
    return config_dir


def get_db_path() -> Path:
    """Get the SQLite database path.

    Returns:
        Path to sago.db.
    """
    return get_data_dir() / "sago.db"


def ensure_sago_dirs() -> None:
    """Create all Sago directories if they don't exist."""
    logger.debug("Ensuring all Sago directories exist")
    get_sago_home()
    get_data_dir()
    get_sessions_dir()
    get_logs_dir()
    get_config_dir()

    # Additional directories used by various features
    sago_home = get_sago_home()
    try:
        (sago_home / "backups").mkdir(parents=True, exist_ok=True)
        (sago_home / "cache").mkdir(parents=True, exist_ok=True)
        (sago_home / "prompts").mkdir(parents=True, exist_ok=True)
        logger.debug("All Sago directories verified")
    except Exception as e:
        logger.error("Failed to create additional Sago directories in %s: %s", sago_home, e)
        raise
