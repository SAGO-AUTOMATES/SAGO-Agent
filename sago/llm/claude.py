"""Claude (Anthropic) LLM Provider."""

from __future__ import annotations

import logging
import os
from typing import Any

from sago.llm.base import BaseLLMProvider
from sago.llm.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class ClaudeProvider(BaseLLMProvider):
    """Anthropic Claude LLM provider."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.api_key_env = config.get("api_key_env", "ANTHROPIC_API_KEY")
        self.api_key = os.environ.get(self.api_key_env, "")
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(
                api_key=self.api_key,
                timeout=90.0,
                max_retries=0,
            )
        return self._client

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate response using Claude API."""
        client = self._get_client()
        messages = [{"role": "user", "content": prompt}]

        def _call() -> str:
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt or None,
                messages=messages,
                temperature=self.temperature,
            )
            if not response.content:
                logger.warning("Claude returned empty content for prompt length=%d", len(prompt))
                return ""
            return response.content[0].text

        return retry_with_backoff(_call)

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ):
        """Generate streaming response using Claude API."""
        client = self._get_client()
        messages = [{"role": "user", "content": prompt}]

        try:
            with client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt or None,
                messages=messages,
                temperature=self.temperature,
            ) as stream:
                yield from stream.text_stream
        except Exception as exc:
            logger.error("Claude streaming failed: %s", exc)
            raise

    def is_available(self) -> bool:
        """Check if Claude API key and library are available."""
        if not self.api_key:
            return False
        try:
            import anthropic  # noqa: F401

            return True
        except ImportError:
            return False

    def get_langchain_llm(self) -> Any:
        """Get LangChain ChatAnthropic instance."""
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=self.model,
            anthropic_api_key=self.api_key,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
