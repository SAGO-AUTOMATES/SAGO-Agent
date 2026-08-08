"""OpenRouter LLM Provider."""

from __future__ import annotations

import os
from typing import Any

from sago.llm.base import BaseLLMProvider


class OpenRouterProvider(BaseLLMProvider):
    """OpenRouter LLM provider - access multiple models via unified API."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.api_key_env = config.get("api_key_env", "OPENROUTER_API_KEY")
        self.api_key = os.environ.get(self.api_key_env, "")
        self.base_url = config.get("base_url", "https://openrouter.ai/api/v1")

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate response using OpenRouter API."""
        from openai import OpenAI

        client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        return response.choices[0].message.content or ""

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ):
        """Generate streaming response using OpenRouter API."""
        from openai import OpenAI

        client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        stream = client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stream=True,
        )
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def is_available(self) -> bool:
        """Check if OpenRouter API key is available."""
        return bool(self.api_key)

    def get_langchain_llm(self) -> Any:
        """Get LangChain ChatOpenAI instance configured for OpenRouter."""
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
