"""Hierarchical exceptions for SAGO subsystems.

Provides typed exception classes matching the error hierarchy documented in
docs/ERRORS.md for tools, agents, LLM providers, and system storage.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("sago.errors.exceptions")


class SagoError(Exception):
    """Base class for all SAGO exceptions."""

    def __init__(self, message: str = "", details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} (details={self.details})"
        return self.message


# ---------------------------------------------------------------------------
# Tool Exceptions
# ---------------------------------------------------------------------------


class ToolError(SagoError):
    """Base exception for tool-related errors."""


class ToolNotFoundError(ToolError):
    """Raised when a requested tool is not found in the registry."""


class ToolExecutionError(ToolError):
    """Raised when a tool execution fails."""


class ToolTimeoutError(ToolError):
    """Raised when a tool operation exceeds its timeout."""


class ToolPermissionError(ToolError):
    """Raised when a tool operation is denied by the permission manager."""


# ---------------------------------------------------------------------------
# Agent Exceptions
# ---------------------------------------------------------------------------


class AgentError(SagoError):
    """Base exception for agent-related errors."""


class AgentNotFoundError(AgentError):
    """Raised when a requested agent profile cannot be found."""


class AgentExecutionError(AgentError):
    """Raised when an agent fails during autonomous task execution."""


class AgentTimeoutError(AgentError):
    """Raised when an agent task execution times out."""


class AgentDelegationError(AgentError):
    """Raised when dynamic delegation or handoff fails."""


class RecursionLimitError(AgentError):
    """Raised when maximum agent delegation depth is reached."""


class CycleDetectedError(AgentError):
    """Raised when an illegal cycle is detected in an agent delegation chain."""


class SameAgentLimitError(AgentError):
    """Raised when an agent is invoked consecutively too many times."""


# ---------------------------------------------------------------------------
# LLM Exceptions
# ---------------------------------------------------------------------------


class LLMError(SagoError):
    """Base exception for LLM provider errors."""


class ProviderNotFoundError(LLMError):
    """Raised when an unsupported or unregistered LLM provider is requested."""


class APIKeyError(LLMError):
    """Raised when an API key is missing or invalid for a provider."""


class RateLimitError(LLMError):
    """Raised when rate limits are exceeded."""


class ModelNotFoundError(LLMError):
    """Raised when the requested model is not available."""


# ---------------------------------------------------------------------------
# System & Persistence Exceptions
# ---------------------------------------------------------------------------


class SystemError(SagoError):
    """Base exception for system-level errors."""


class DatabaseError(SystemError):
    """Raised when SQLite database operations fail."""


class CacheError(SystemError):
    """Raised when cache operations fail."""


class ConfigError(SystemError):
    """Raised when configuration parsing or validation fails."""
