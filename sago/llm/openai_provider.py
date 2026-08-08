"""OpenAI LLM Provider (GPT models)."""

from __future__ import annotations

import os
from typing import Any

from sago.llm.base import BaseLLMProvider


class OpenAIProvider(BaseLLMProvider):
    """OpenAI GPT LLM provider."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.api_key_env = config.get("api_key_env", "OPENAI_API_KEY")
        self.api_key = os.environ.get(self.api_key_env, "")

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate response using OpenAI API."""
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key)
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
        """Generate streaming response using OpenAI API."""
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key)
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
        """Check if OpenAI API key is available."""
        return bool(self.api_key)

    def get_langchain_llm(self) -> Any:
        """Get LangChain ChatOpenAI instance."""
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=self.model,
            api_key=self.api_key,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
