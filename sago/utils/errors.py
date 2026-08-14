"""Central error-handling and structured-logging utilities for SAGO.

Provides a module-level structured logger plus helpers to replace silent
``except Exception: pass`` patterns with proper logging.

A structured logger (stdlib :mod:`logging`) is used. When the
``SAGO_LOG_JSON`` environment variable is set to a truthy value the records
are emitted as single-line JSON; otherwise human-readable text is emitted.
"""

from __future__ import annotations

import json
import logging
import os
import traceback
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

logger = logging.getLogger("sago")

_JSON_ENABLED = os.environ.get("SAGO_LOG_JSON", "0") in ("1", "true", "yes", "on")


def log_error(
    message: str,
    exc: Exception | None = None,
    *,
    level: int = logging.ERROR,
    context: dict | None = None,
) -> None:
    """Log an error message with optional exception info and structured context.

    Args:
        message: Human-readable description of what failed.
        exc: Optional exception instance associated with the failure.
        level: Logging level (defaults to ``logging.ERROR``).
        context: Optional structured context dict attached to the record.
    """
    ctx: dict[str, Any] = dict(context or {})
    if exc is not None:
        ctx.setdefault("error_type", type(exc).__name__)
        ctx.setdefault("error", str(exc))

    if _JSON_ENABLED:
        payload: dict[str, Any] = {
            "message": message,
            "level": logging.getLevelName(level),
            "context": ctx,
        }
        if exc is not None:
            payload["traceback"] = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )
        logger.log(level, json.dumps(payload, default=str))
    else:
        suffix = ""
        if ctx:
            suffix = " | " + ", ".join(f"{k}={v}" for k, v in ctx.items())
        if exc is not None:
            logger.log(level, f"{message}{suffix}", exc_info=exc)
        else:
            logger.log(level, f"{message}{suffix}")


F = TypeVar("F", bound=Callable[..., Any])


def handle_errors(
    default: Any = None,
    reraise: bool = False,
    log_level: int = logging.ERROR,
) -> Callable[[F], F]:
    """Wrap a function so exceptions are logged instead of crashing.

    On exception the failure is logged via :func:`log_error`. If ``reraise``
    is ``True`` the exception is re-raised after logging; otherwise ``default``
    is returned.

    Args:
        default: Value returned on exception when not re-raising.
        reraise: When ``True``, re-raise the caught exception after logging.
        log_level: Logging level used for the error record.
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                log_error(
                    f"Unhandled exception in {func.__name__}",
                    e,
                    level=log_level,
                    context={"function": func.__name__},
                )
                if reraise:
                    raise
                return default

        return wrapper  # type: ignore

    return decorator
