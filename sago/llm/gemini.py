"""Gemini LLM Provider."""

from __future__ import annotations

import os
from typing import Any

from sago.llm.base import BaseLLMProvider


class GeminiProvider(BaseLLMProvider):
    """Google Gemini LLM provider."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.api_key_env = config.get("api_key_env", "GEMINI_API_KEY")
        self.api_key = os.environ.get(self.api_key_env, "")

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate response using Gemini API."""
        import google.generativeai as genai

        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(self.model)

        content = prompt
        if system_prompt:
            content = f"{system_prompt}\n\n{prompt}"

        response = model.generate_content(
            content,
            generation_config=genai.GenerationConfig(
                max_output_tokens=self.max_tokens,
                temperature=self.temperature,
            ),
        )
        return response.text

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ):
        """Generate streaming response using Gemini API."""
        import google.generativeai as genai

        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(self.model)

        content = prompt
        if system_prompt:
            content = f"{system_prompt}\n\n{prompt}"

        response = model.generate_content(
            content,
            generation_config=genai.GenerationConfig(
                max_output_tokens=self.max_tokens,
                temperature=self.temperature,
            ),
            stream=True,
        )
        for chunk in response:
            if chunk.text:
                yield chunk.text

    def is_available(self) -> bool:
        """Check if Gemini API key is available."""
        return bool(self.api_key)

    def get_langchain_llm(self) -> Any:
        """Get LangChain ChatGoogleGenerativeAI instance."""
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=self.model,
            google_api_key=self.api_key,
            max_output_tokens=self.max_tokens,
            temperature=self.temperature,
        )
