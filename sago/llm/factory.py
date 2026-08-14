"""LLM Provider Factory.

Creates and manages LLM provider instances based on configuration.
"""

from __future__ import annotations

import logging
from typing import Any

from sago.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

_PROVIDER_MAP: dict[str, type[BaseLLMProvider]] = {}


def _register_providers() -> None:
    """Register all available providers."""
    global _PROVIDER_MAP
    if _PROVIDER_MAP:
        return

    from sago.llm.claude import ClaudeProvider
    from sago.llm.ollama import OllamaProvider
    from sago.llm.openai_provider import OpenAIProvider
    from sago.llm.openrouter import OpenRouterProvider

    _PROVIDER_MAP = {
        "openai": OpenAIProvider,
        "claude": ClaudeProvider,
        "openrouter": OpenRouterProvider,
        "ollama": OllamaProvider,
    }

    try:
        from sago.llm.gemini import GeminiProvider

        _PROVIDER_MAP["gemini"] = GeminiProvider
    except ImportError:
        logger.debug("Gemini provider not available (google-generativeai not installed)")


def create_provider(
    provider_name: str,
    config: dict[str, Any],
) -> BaseLLMProvider:
    """Create an LLM provider instance.

    Args:
        provider_name: Name of the provider (gemini, openai, claude, etc.).
        config: Provider-specific configuration.

    Returns:
        An initialized LLM provider instance.

    Raises:
        ValueError: If the provider name is not recognized.
    """
    _register_providers()

    provider_class = _PROVIDER_MAP.get(provider_name)
    if provider_class is None:
        available = ", ".join(_PROVIDER_MAP.keys())
        raise ValueError(
            f"Unknown LLM provider: {provider_name!r}. Available providers: {available}"
        )

    return provider_class(config)


def get_available_providers() -> list[str]:
    """Get list of all registered provider names.

    Returns:
        List of available provider names.
    """
    _register_providers()
    return list(_PROVIDER_MAP.keys())


def get_provider(
    provider_name: str,
    config: dict[str, Any],
) -> BaseLLMProvider | None:
    """Get a provider instance, returning None if not available.

    Args:
        provider_name: Name of the provider.
        config: Provider-specific configuration.

    Returns:
        Provider instance or None if unavailable.
    """
    try:
        provider = create_provider(provider_name, config)
        if provider.is_available():
            return provider
        logger.warning(
            "Provider %r is not available (missing API key or unreachable)", provider_name
        )
        return None
    except ValueError as exc:
        logger.warning("Failed to create provider %r: %s", provider_name, exc)
        return None
