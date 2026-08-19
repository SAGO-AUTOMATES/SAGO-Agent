"""Centralized logging configuration for Sago.

Sets up file + console logging with daily rotation.
Call setup_logging() once at app startup.

Log files: ~/.sago/logs/sago.log (rotated daily, 7 days retention)
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

_INITIALIZED = False


def setup_logging(
    level: int = logging.DEBUG,
    log_dir: Path | None = None,
    console_level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB per file
    backup_count: int = 7,  # keep 7 days
) -> None:
    """Initialize Sago logging with file and console handlers.

    Args:
        level: Root log level for file output.
        log_dir: Directory for log files. Defaults to ~/.sago/logs/.
        console_level: Log level for console (stderr) output.
        max_bytes: Max size per log file before rotation.
        backup_count: Number of rotated log files to keep.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return
    _INITIALIZED = True

    if log_dir is None:
        from sago.paths import get_logs_dir

        log_dir = get_logs_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "sago.log"

    # Root logger
    root = logging.getLogger()
    root.setLevel(level)

    # Prevent duplicate handlers on re-init
    root.handlers.clear()

    # ---- File handler (daily rotation, detailed format) ----
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=str(log_file),
        when="midnight",
        interval=1,
        backupCount=backup_count,
        encoding="utf-8",
        delay=True,
    )
    file_handler.setLevel(level)
    file_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)-40s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    root.addHandler(file_handler)

    # ---- Console handler (cleaner format, higher threshold) ----
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(console_level)
    console_formatter = logging.Formatter(
        fmt="%(levelname)s | %(name)s | %(message)s",
    )
    console_handler.setFormatter(console_formatter)
    root.addHandler(console_handler)

    # Log startup
    logger = logging.getLogger("sago.logging")
    logger.info("Logging initialized -> %s (level=%s)", log_file, logging.getLevelName(level))
