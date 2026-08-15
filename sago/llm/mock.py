"""Mock LLM Provider for offline integration testing, CI, and deterministic validation."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from sago.llm.base import BaseLLMProvider


class MockLLMProvider(BaseLLMProvider):
    """Mock LLM provider for tests and offline execution."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config or {})
        self.model = (config or {}).get("model", "mock-model")
        self.canned_responses: list[str] = (config or {}).get("responses", [])
        self.call_history: list[dict[str, Any]] = []

    def is_available(self) -> bool:
        return True

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        self.call_history.append(
            {"prompt": prompt, "system_prompt": system_prompt, "kwargs": kwargs}
        )
        if self.canned_responses:
            return self.canned_responses.pop(0)
        return f"Mock response for task: {prompt[:80]}"

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> Generator[str, None, None]:
        full_text = self.generate(prompt, system_prompt, **kwargs)
        tokens = full_text.split(" ")
        for i, tok in enumerate(tokens):
            yield tok + (" " if i < len(tokens) - 1 else "")
