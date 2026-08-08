"""Ollama LLM Provider (Local models)."""

from __future__ import annotations

from typing import Any

from sago.llm.base import BaseLLMProvider


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
        import httpx

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

        response = httpx.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=120.0,
        )
        response.raise_for_status()
        return response.json().get("response", "")

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ):
        """Generate streaming response using Ollama API."""
        import json

        import httpx

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

        with httpx.stream(
            "POST",
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=120.0,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    if "response" in data:
                        yield data["response"]

    def is_available(self) -> bool:
        """Check if Ollama server is reachable."""
        import httpx

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
