"""Ollama LLM Provider (Local models)."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from sago.llm.base import BaseLLMProvider
from sago.llm.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class OllamaProvider(BaseLLMProvider):
    """Ollama local LLM provider."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.base_url = config.get("base_url", "http://localhost:11434")

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate response using Ollama API."""
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt

        def _call() -> str:
            response = httpx.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=120.0,
            )
            response.raise_for_status()
            return response.json().get("response", "")

        return retry_with_backoff(_call)

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ):
        """Generate streaming response using Ollama API."""
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            with httpx.stream(
                "POST",
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=120.0,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if "response" in data:
                                yield data["response"]
                        except json.JSONDecodeError as exc:
                            logger.warning("Ollama stream JSON decode error: %s", exc)
                            continue
        except Exception as exc:
            logger.error("Ollama streaming failed: %s", exc)
            raise

    def is_available(self) -> bool:
        """Check if Ollama server is reachable."""
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            return response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    def get_langchain_llm(self) -> Any:
        """Get LangChain Ollama instance."""
        from langchain_community.llms import Ollama

        return Ollama(
            model=self.model,
            base_url=self.base_url,
            temperature=self.temperature,
        )
