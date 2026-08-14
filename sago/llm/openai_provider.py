"""OpenAI LLM Provider (GPT models)."""

from __future__ import annotations

import logging
import os
from typing import Any

from sago.llm.base import BaseLLMProvider
from sago.llm.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI GPT LLM provider."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.api_key_env = config.get("api_key_env", "OPENAI_API_KEY")
        self.api_key = os.environ.get(self.api_key_env, "")
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
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
        """Generate response using OpenAI API."""
        client = self._get_client()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        def _call() -> str:
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            if not response.choices:
                logger.warning("OpenAI returned empty choices for prompt length=%d", len(prompt))
                return ""
            return response.choices[0].message.content or ""

        return retry_with_backoff(_call)

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ):
        """Generate streaming response using OpenAI API."""
        client = self._get_client()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            stream = client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                stream=True,
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as exc:
            logger.error("OpenAI streaming failed: %s", exc)
            raise

    def is_available(self) -> bool:
        """Check if OpenAI API key and library are available."""
        if not self.api_key:
            return False
        try:
            from openai import OpenAI
            return True
        except ImportError:
            return False

    def get_langchain_llm(self) -> Any:
        """Get LangChain ChatOpenAI instance."""
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=self.model,
            api_key=self.api_key,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
