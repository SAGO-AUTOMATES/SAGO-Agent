"""LLM Provider abstraction layer for Sago.

Supports: Gemini, OpenAI, Claude, OpenRouter, Ollama
All providers implement a common interface for easy switching.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseLLMProvider(ABC):
    """Abstract base class for all LLM providers."""

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the provider with configuration.

        Args:
            config: Provider-specific configuration dictionary.
        """
        self.config = config
        self.model = config.get("model", "")
        self.max_tokens = config.get("max_tokens", 4096)
        self.temperature = config.get("temperature", 0.7)

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate a response from the LLM.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system prompt for context.
            **kwargs: Additional provider-specific parameters.

        Returns:
            The generated text response.
        """
        ...

    @abstractmethod
    def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ):
        """Generate a streaming response from the LLM.

        Args:
            prompt: The user prompt.
            system_prompt: Optional system prompt for context.
            **kwargs: Additional provider-specific parameters.

        Yields:
            Chunks of the generated response.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available and configured.

        Returns:
            True if the provider can be used.
        """
        ...

    def get_langchain_llm(self) -> Any:
        """Get a LangChain-compatible LLM instance.

        Returns:
            A LangChain LLM instance for use with CrewAI.
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not implement get_langchain_llm")
