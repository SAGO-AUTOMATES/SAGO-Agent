"""Centralized logging configuration for Sago.

Sets up file-only logging with daily rotation and smart cleanup.
No logs are printed to console/screen/TUI — only CRITICAL exceptions
surface in TUI status bar. All logs go to ~/.sago/logs/sago.log.

Log level is configurable via ~/.sago/settings.json ("log_level" key).
Valid values: debug, info, warning, error. Default: info.

Log files: ~/.sago/logs/sago.log (rotated daily, 14 days retention, 10MB max)
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import uuid
from contextvars import ContextVar
from pathlib import Path

_INITIALIZED = False

# Valid log levels
VALID_LOG_LEVELS = {"debug", "info", "warning", "error", "critical"}

# Session context — every log line includes this ID for filtering
_session_id: ContextVar[str] = ContextVar("sago_session_id", default="")


def get_session_id() -> str:
    """Get the current session ID for log correlation."""
    return _session_id.get()


def set_session_id(session_id: str | None = None) -> str:
    """Set or generate a new session ID. Returns the active session ID."""
    if session_id is None:
        session_id = uuid.uuid4().hex[:12]
    _session_id.set(session_id)
    return session_id


def get_log_level() -> str:
    """Get the configured log level from settings.json.

    Returns the level name in lowercase (e.g. 'info', 'debug').
    Falls back to 'info' if not configured or invalid.
    """
    from sago.settings import load_setting

    level = load_setting("log_level", "info")
    if isinstance(level, str) and level.lower() in VALID_LOG_LEVELS:
        return level.lower()
    return "info"


def set_log_level(level: str) -> None:
    """Save log level to settings.json and reconfigure the root logger.

    Args:
        level: One of 'debug', 'info', 'warning', 'error', 'critical'.
    """
    from sago.settings import save_setting

    level = level.lower()
    if level not in VALID_LOG_LEVELS:
        raise ValueError(
            f"Invalid log level: {level!r}. Must be one of: {', '.join(sorted(VALID_LOG_LEVELS))}"
        )

    save_setting("log_level", level)

    # Reconfigure root logger immediately
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(numeric_level)
    for handler in root.handlers:
        # Keep emergency handler at CRITICAL always — only surface fatal crashes
        if isinstance(handler, logging.StreamHandler) and handler.stream is sys.stderr:
            handler.setLevel(logging.CRITICAL)
        else:
            handler.setLevel(numeric_level)

    logger = logging.getLogger("sago.logging")
    logger.info("Log level changed to %s", level.upper())


def _level_from_name(name: str) -> int:
    """Convert level name string to logging constant."""
    return getattr(logging, name.upper(), logging.INFO)


class SessionFilter(logging.Filter):
    """Inject session_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.session_id = get_session_id()
        return True


class _MaxSizeRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """RotatingFileHandler that also caps total log directory size."""

    def __init__(self, filename: str, max_total_mb: float = 100, **kwargs: object) -> None:
        super().__init__(filename=filename, **kwargs)  # type: ignore[arg-type]
        self._max_total_bytes = int(max_total_mb * 1024 * 1024)

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self._enforce_total_size()

    def _enforce_total_size(self) -> None:
        """Delete oldest rotated files if total exceeds max_total_bytes."""
        try:
            log_dir = Path(self.baseFilename).parent
            log_files = sorted(log_dir.glob("*.log*"), key=lambda f: f.stat().st_mtime)
            total = sum(f.stat().st_size for f in log_files if f.is_file())
            while total > self._max_total_bytes and len(log_files) > 1:
                oldest = log_files.pop(0)
                sz = oldest.stat().st_size
                oldest.unlink(missing_ok=True)
                total -= sz
        except OSError:
            pass


def setup_logging(
    level: int | None = None,
    log_dir: Path | None = None,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 14,
    max_total_mb: float = 100.0,
) -> None:
    """Initialize Sago logging — file only, no console output.

    Args:
        level: Root log level. If None, reads from settings.json (default: INFO).
        log_dir: Directory for log files. Defaults to ~/.sago/logs/.
        max_bytes: Max size per log file before rotation.
        backup_count: Number of rotated log files to keep (days).
        max_total_mb: Max total size of log directory before pruning.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return
    _INITIALIZED = True

    # Read level from settings if not explicitly provided
    if level is None:
        level = _level_from_name(get_log_level())

    if log_dir is None:
        from sago.paths import get_logs_dir

        log_dir = get_logs_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "sago.log"

    # Generate session ID for this process
    set_session_id()

    # Root logger
    root = logging.getLogger()
    root.setLevel(level)

    # Prevent duplicate handlers on re-init
    root.handlers.clear()

    # Session filter — adds session_id to all records
    session_filter = SessionFilter()

    # ---- File handler (daily rotation + size cap, detailed format) ----
    file_handler = _MaxSizeRotatingFileHandler(
        filename=str(log_file),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
        delay=True,
        max_total_mb=max_total_mb,
    )
    file_handler.setLevel(level)
    file_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(session_id)-12s | %(name)-38s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    file_handler.addFilter(session_filter)
    root.addHandler(file_handler)

    # ---- Errors-only file (ERROR+ for quick triage) ----
    errors_file = log_dir / "errors.log"
    errors_handler = logging.handlers.RotatingFileHandler(
        filename=str(errors_file),
        maxBytes=max_bytes,
        backupCount=5,
        encoding="utf-8",
        delay=True,
    )
    errors_handler.setLevel(logging.ERROR)
    errors_handler.setFormatter(file_formatter)
    errors_handler.addFilter(session_filter)
    root.addHandler(errors_handler)

    # ---- Emergency handler — only CRITICAL to stderr (for TUI crash visibility) ----
    emergency_handler = logging.StreamHandler(sys.stderr)
    emergency_handler.setLevel(logging.CRITICAL)
    emergency_formatter = logging.Formatter(
        fmt="[CRITICAL] %(name)s | %(message)s",
    )
    emergency_handler.setFormatter(emergency_formatter)
    root.addHandler(emergency_handler)

    # Log startup
    logger = logging.getLogger("sago.logging")
    logger.info(
        "Logging initialized -> %s (level=%s, session=%s)",
        log_file,
        logging.getLevelName(level),
        get_session_id(),
    )
