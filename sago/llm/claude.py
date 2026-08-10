"""Claude (Anthropic) LLM Provider."""

from __future__ import annotations

import os
from typing import Any

from sago.llm.base import BaseLLMProvider


class ClaudeProvider(BaseLLMProvider):
    """Anthropic Claude LLM provider."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.api_key_env = config.get("api_key_env", "ANTHROPIC_API_KEY")
        self.api_key = os.environ.get(self.api_key_env, "")

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate response using Claude API."""
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)
        messages = [{"role": "user", "content": prompt}]

        response = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_prompt or "",
            messages=messages,
            temperature=self.temperature,
        )
        return response.content[0].text

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ):
        """Generate streaming response using Claude API."""
        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)
        messages = [{"role": "user", "content": prompt}]

        with client.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_prompt or "",
            messages=messages,
            temperature=self.temperature,
        ) as stream:
            yield from stream.text_stream

    def is_available(self) -> bool:
        """Check if Claude API key is available."""
        return bool(self.api_key)

    def get_langchain_llm(self) -> Any:
        """Get LangChain ChatAnthropic instance."""
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=self.model,
            anthropic_api_key=self.api_key,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
