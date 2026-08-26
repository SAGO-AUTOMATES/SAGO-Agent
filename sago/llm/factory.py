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
        logger.debug("Providers already registered, skipping")
        return

    logger.debug("Registering LLM providers")

    from sago.llm.claude import ClaudeProvider
    from sago.llm.mock import MockLLMProvider
    from sago.llm.ollama import OllamaProvider
    from sago.llm.openai_provider import OpenAIProvider
    from sago.llm.openrouter import OpenRouterProvider

    _PROVIDER_MAP = {
        "openai": OpenAIProvider,
        "claude": ClaudeProvider,
        "openrouter": OpenRouterProvider,
        "ollama": OllamaProvider,
        "mock": MockLLMProvider,
    }

    try:
        from sago.llm.gemini import GeminiProvider

        _PROVIDER_MAP["gemini"] = GeminiProvider
    except ImportError:
        logger.debug("Gemini provider not available (google-generativeai not installed)")

    logger.info("Registered LLM providers: %s", list(_PROVIDER_MAP.keys()))


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
    logger.debug("Creating provider: name=%s", provider_name)
    _register_providers()

    provider_class = _PROVIDER_MAP.get(provider_name)
    if provider_class is None:
        available = ", ".join(_PROVIDER_MAP.keys())
        logger.error("Unknown LLM provider requested: %r (available: %s)", provider_name, available)
        raise ValueError(
            f"Unknown LLM provider: {provider_name!r}. Available providers: {available}"
        )

    logger.debug(
        "Provider class found: %s, instantiating with config keys=%s",
        provider_class.__name__,
        list(config.keys()),
    )
    provider = provider_class(config)
    logger.info("Provider %r instantiated: %s", provider_name, provider_class.__name__)
    return provider


def get_available_providers() -> list[str]:
    """Get list of all registered provider names.

    Returns:
        List of available provider names.
    """
    _register_providers()
    providers = list(_PROVIDER_MAP.keys())
    logger.debug("Available providers: %s", providers)
    return providers


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
    logger.debug("Getting provider: name=%s", provider_name)
    try:
        provider = create_provider(provider_name, config)
        if provider.is_available():
            logger.info("Provider %r is available and ready", provider_name)
            return provider
        logger.warning(
            "Provider %r is not available (missing API key or unreachable), fallback may be needed",
            provider_name,
        )
        return None
    except ValueError as exc:
        logger.warning("Failed to create provider %r: %s", provider_name, exc)
        return None
