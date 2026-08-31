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


def safe_call(
    func: F | None = None,
    *,
    default: Any = None,
    log_level: int = logging.DEBUG,
) -> Any:
    """Decorator that catches exceptions and logs them instead of crashing.

    Supports both `@safe_call` and `@safe_call(default=...)`.

    Args:
        func: Function to wrap (when used as `@safe_call`).
        default: Value to return on exception.
        log_level: Logging level for the exception.

    Returns:
        Wrapped function that returns default on exception.
    """

    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                logger.log(log_level, f"Error in {fn.__name__}: {type(e).__name__}: {e}")
                return default

        return wrapper  # type: ignore

    if func is not None:
        return decorator(func)
    return decorator


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


def safe_json_dumps(
    data: Any,
    default: str = "",
    indent: int | None = None,
    log_level: int = logging.DEBUG,
) -> str:
    """Safely serialize to JSON string, returning default on failure.

    Args:
        data: Python object to serialize to JSON.
        default: Value to return on serialization failure.
        indent: Optional indentation for pretty printing.
        log_level: Logging level for the exception.

    Returns:
        JSON string or default.
    """
    import json

    try:
        return json.dumps(data, indent=indent, ensure_ascii=False)
    except Exception as e:
        logger.log(log_level, f"JSON serialize error: {e}")
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
