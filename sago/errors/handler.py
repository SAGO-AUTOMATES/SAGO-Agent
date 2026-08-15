"""Error Handling and Recovery System

Provides automatic error recovery, retry logic, and fallback strategies
for tool execution and agent operations.
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


_FALLBACK_TOOL_CACHE: dict[str, type] = {}
_FALLBACK_TOOL_LOCK = threading.Lock()


def _get_tool_class_by_name(target_name: str) -> type | None:
    """Find a tool class by name with thread-safe cached discovery."""
    with _FALLBACK_TOOL_LOCK:
        if target_name in _FALLBACK_TOOL_CACHE:
            return _FALLBACK_TOOL_CACHE[target_name]

        if not _FALLBACK_TOOL_CACHE:
            import importlib
            from pathlib import Path

            from sago.tools.base import BaseTool

            tools_dir = Path(__file__).parent.parent / "tools"
            for py_file in tools_dir.rglob("*.py"):
                if py_file.name.startswith("_") or py_file.name == "base.py":
                    continue
                parts = py_file.relative_to(tools_dir).with_suffix("").as_posix().split("/")
                module_name = ".".join(["sago", "tools"] + parts)
                try:
                    mod = importlib.import_module(module_name)
                    for attr_name in dir(mod):
                        obj = getattr(mod, attr_name)
                        if (
                            isinstance(obj, type)
                            and issubclass(obj, BaseTool)
                            and hasattr(obj, "name")
                            and obj.name
                        ):
                            _FALLBACK_TOOL_CACHE[obj.name] = obj
                except Exception:
                    continue

        return _FALLBACK_TOOL_CACHE.get(target_name)


class ErrorSeverity(StrEnum):
    """Error severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecoveryStrategy(StrEnum):
    """Recovery strategies."""

    RETRY = "retry"
    FALLBACK = "fallback"
    SKIP = "skip"
    ABORT = "abort"
    ASK_USER = "ask_user"


@dataclass
class ErrorContext:
    """Context information for an error."""

    tool_name: str
    error: Exception
    attempt: int
    max_attempts: int
    severity: ErrorSeverity
    traceback_str: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def should_retry(self) -> bool:
        return self.attempt < self.max_attempts

    @property
    def is_transient(self) -> bool:
        """Check if error is likely transient."""
        transient_types = (TimeoutError, ConnectionError, OSError)
        return isinstance(self.error, transient_types)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "error_type": type(self.error).__name__,
            "error_message": str(self.error),
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "severity": self.severity.value,
            "is_transient": self.is_transient,
        }


@dataclass
class RecoveryResult:
    """Result of a recovery attempt."""

    success: bool
    strategy_used: RecoveryStrategy
    result: Any = None
    error: Exception | None = None
    attempts_made: int = 0
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "strategy": self.strategy_used.value,
            "attempts_made": self.attempts_made,
            "duration_ms": round(self.duration_ms, 2),
        }


# Default retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 1.0  # seconds
DEFAULT_RETRY_BACKOFF = 2.0  # multiplier

# Transient error types that should be retried
TRANSIENT_ERRORS = (
    TimeoutError,
    ConnectionError,
    ConnectionRefusedError,
    ConnectionResetError,
    OSError,
    IOError,
)

# Permanent errors that should NOT be retried
PERMANENT_ERRORS = (
    FileNotFoundError,
    PermissionError,
    ValueError,
    TypeError,
    KeyError,
)


class ErrorHandler:
    """Central error handler for Sago."""

    def __init__(self) -> None:
        self.errors: list[ErrorContext] = []
        self.on_error: Callable[[ErrorContext], None] | None = None
        self.on_recovery: Callable[[RecoveryResult], None] | None = None

    def handle_error(
        self,
        tool_name: str,
        error: Exception,
        attempt: int = 1,
        max_attempts: int = DEFAULT_MAX_RETRIES,
    ) -> ErrorContext:
        """Handle and log an error."""
        severity = self._classify_severity(error)
        context = ErrorContext(
            tool_name=tool_name,
            error=error,
            attempt=attempt,
            max_attempts=max_attempts,
            severity=severity,
            traceback_str=traceback.format_exc(),
        )
        self.errors.append(context)
        if len(self.errors) > 5000:
            self.errors = self.errors[-5000:]

        log_msg = (
            "Error in tool '%s' (attempt %d/%d, severity=%s): %s",
            context.tool_name,
            context.attempt,
            context.max_attempts,
            context.severity.value,
            context.error,
        )
        if context.severity in (ErrorSeverity.HIGH, ErrorSeverity.CRITICAL):
            logger.error(*log_msg)
        else:
            logger.warning(*log_msg)

        if self.on_error:
            self.on_error(context)

        return context

    def _classify_severity(self, error: Exception) -> ErrorSeverity:
        """Classify error severity."""
        if isinstance(error, PERMANENT_ERRORS):
            return ErrorSeverity.HIGH
        if isinstance(error, TRANSIENT_ERRORS):
            return ErrorSeverity.MEDIUM
        if isinstance(error, (RuntimeError, SystemError)):
            return ErrorSeverity.CRITICAL
        return ErrorSeverity.LOW

    def get_recent_errors(self, limit: int = 10) -> list[ErrorContext]:
        """Get recent errors."""
        return self.errors[-limit:]

    def clear_errors(self) -> None:
        """Clear error history."""
        self.errors.clear()


class RecoveryManager:
    """Manages automatic error recovery."""

    def __init__(
        self,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY,
        backoff: float = DEFAULT_RETRY_BACKOFF,
    ) -> None:
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.backoff = backoff
        self.error_handler = ErrorHandler()
        self._fallback_tools: dict[str, list[str]] = {}

    def set_fallbacks(self, tool_name: str, fallbacks: list[str]) -> None:
        """Set fallback tools for a tool."""
        self._fallback_tools[tool_name] = fallbacks

    def execute_with_recovery(
        self,
        tool_name: str,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> RecoveryResult:
        """Execute a function with automatic recovery."""
        start_time = time.time()
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                result = func(*args, **kwargs)
                duration = (time.time() - start_time) * 1000
                return RecoveryResult(
                    success=True,
                    strategy_used=RecoveryStrategy.RETRY if attempt > 1 else RecoveryStrategy.SKIP,
                    result=result,
                    attempts_made=attempt,
                    duration_ms=duration,
                )
            except Exception as e:
                last_error = e
                context = self.error_handler.handle_error(
                    tool_name=tool_name,
                    error=e,
                    attempt=attempt,
                    max_attempts=self.max_retries,
                )

                # Check if we should retry
                if not context.should_retry:
                    break

                # Check if error is transient
                if not context.is_transient:
                    break

                # Wait before retry
                delay = self.retry_delay * (self.backoff ** (attempt - 1))
                time.sleep(delay)

        # All retries failed, try fallback
        if last_error and tool_name in self._fallback_tools:
            for fallback_name in self._fallback_tools[tool_name]:
                tool_cls = _get_tool_class_by_name(fallback_name)
                if tool_cls:
                    try:
                        fallback_instance = tool_cls()
                        result = fallback_instance.run(**kwargs)
                        duration = (time.time() - start_time) * 1000
                        return RecoveryResult(
                            success=True,
                            strategy_used=RecoveryStrategy.FALLBACK,
                            result=result,
                            attempts_made=self.max_retries,
                            duration_ms=duration,
                        )
                    except Exception:
                        continue

        duration = (time.time() - start_time) * 1000
        return RecoveryResult(
            success=False,
            strategy_used=RecoveryStrategy.ABORT,
            error=last_error,
            attempts_made=self.max_retries,
            duration_ms=duration,
        )

    def execute_with_fallbacks(
        self,
        primary_tool: str,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> RecoveryResult:
        """Execute with fallback tools."""
        # Try primary
        result = self.execute_with_recovery(primary_tool, func, *args, **kwargs)
        if result.success:
            return result

        # Try fallbacks
        for fallback_name in self._fallback_tools.get(primary_tool, []):
            try:
                import importlib
                from pathlib import Path

                from sago.tools.base import BaseTool

                tools_dir = Path(__file__).parent.parent / "tools"
                for py_file in tools_dir.rglob("*.py"):
                    if py_file.name.startswith("_") or py_file.name == "base.py":
                        continue
                    parts = py_file.relative_to(tools_dir).with_suffix("").as_posix().split("/")
                    module_name = ".".join(["sago", "tools"] + parts)
                    try:
                        mod = importlib.import_module(module_name)
                        for attr_name in dir(mod):
                            obj = getattr(mod, attr_name)
                            if (
                                isinstance(obj, type)
                                and hasattr(obj, "name")
                                and obj.name == fallback_name
                            ):
                                if issubclass(obj, BaseTool):
                                    fallback_instance = obj()
                                    result = fallback_instance.run(*args, **kwargs)
                                    return RecoveryResult(
                                        success=True,
                                        strategy_used=RecoveryStrategy.FALLBACK,
                                        result=result,
                                        attempts_made=1,
                                        duration_ms=0,
                                    )
                    except Exception:
                        continue
            except Exception:
                continue

        return result


# Global instances
_error_handler: ErrorHandler | None = None
_recovery_manager: RecoveryManager | None = None
_error_handler_lock = threading.Lock()
_recovery_manager_lock = threading.Lock()


def get_error_handler() -> ErrorHandler:
    """Get global error handler."""
    global _error_handler
    if _error_handler is None:
        with _error_handler_lock:
            if _error_handler is None:
                _error_handler = ErrorHandler()
    return _error_handler


def get_recovery_manager() -> RecoveryManager:
    """Get global recovery manager."""
    global _recovery_manager
    if _recovery_manager is None:
        with _recovery_manager_lock:
            if _recovery_manager is None:
                _recovery_manager = RecoveryManager()
    return _recovery_manager
