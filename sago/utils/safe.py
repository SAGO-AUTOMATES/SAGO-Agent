"""Safe exception handling utilities.

Provides logging-aware exception handling to replace silent 'except Exception: pass' patterns.
"""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

logger = logging.getLogger("sago")

F = TypeVar("F", bound=Callable[..., Any])


def safe_call(func: F, default: Any = None, log_level: int = logging.DEBUG) -> F:
    """Decorator that catches exceptions and logs them instead of crashing.

    Args:
        func: Function to wrap.
        default: Value to return on exception.
        log_level: Logging level for the exception.

    Returns:
        Wrapped function that returns default on exception.
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.log(log_level, f"Error in {func.__name__}: {type(e).__name__}: {e}")
            return default

    return wrapper  # type: ignore


def safe_import(module_name: str) -> Any:
    """Safely import a module, returning None on failure.

    Args:
        module_name: Full module path to import.

    Returns:
        Module or None if import fails.
    """
    import importlib

    try:
        return importlib.import_module(module_name)
    except Exception as e:
        logger.debug(f"Failed to import {module_name}: {e}")
        return None


def safe_file_read(path: str | Any, encoding: str = "utf-8") -> str:
    """Safely read a file, returning empty string on failure.

    Args:
        path: File path to read.
        encoding: File encoding.

    Returns:
        File contents or empty string.
    """
    from pathlib import Path

    try:
        return Path(path).read_text(encoding=encoding, errors="replace")
    except Exception as e:
        logger.debug(f"Failed to read {path}: {e}")
        return ""


def safe_json_loads(data: str, default: Any = None) -> Any:
    """Safely parse JSON, returning default on failure.

    Args:
        data: JSON string to parse.
        default: Value to return on parse failure.

    Returns:
        Parsed JSON or default.
    """
    import json

    try:
        return json.loads(data)
    except Exception as e:
        logger.debug(f"JSON parse error: {e}")
        return default


def log_exception(
    e: Exception,
    context: str = "",
    level: int = logging.DEBUG,
    include_traceback: bool = False,
) -> None:
    """Log an exception with context.

    Args:
        e: Exception to log.
        context: Additional context about what was happening.
        level: Logging level.
        include_traceback: Whether to include full traceback.
    """
    msg = f"{context}: {type(e).__name__}: {e}" if context else f"{type(e).__name__}: {e}"
    if include_traceback:
        msg += f"\n{traceback.format_exc()}"
    logger.log(level, msg)
