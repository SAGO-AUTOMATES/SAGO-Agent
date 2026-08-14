"""Gemini LLM Provider."""

from __future__ import annotations

import logging
import os
from typing import Any

from sago.llm.base import BaseLLMProvider
from sago.llm.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class GeminiProvider(BaseLLMProvider):
    """Google Gemini LLM provider."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.api_key_env = config.get("api_key_env", "GEMINI_API_KEY")
        self.api_key = os.environ.get(self.api_key_env, "")
        self._client: Any = None

    def _get_model(self) -> Any:
        import google.generativeai as genai

        genai.configure(api_key=self.api_key)
        return genai.GenerativeModel(self.model)

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate response using Gemini API."""
        import google.generativeai as genai

        model = self._get_model()

        gen_config = {
            "max_output_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if system_prompt:
            gen_config["system_instruction"] = system_prompt

        def _call() -> str:
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(**gen_config),
            )
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                logger.warning(
                    "Gemini response blocked: %s", response.prompt_feedback.block_reason
                )
                return f"[Response blocked: {response.prompt_feedback.block_reason}]"
            if not response.text:
                logger.warning("Gemini returned empty text for prompt length=%d", len(prompt))
                return ""
            return response.text

        return retry_with_backoff(_call)

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ):
        """Generate streaming response using Gemini API."""
        model = self._get_model()

        gen_config = {
            "max_output_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if system_prompt:
            gen_config["system_instruction"] = system_prompt

        import google.generativeai as genai

        try:
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(**gen_config),
                stream=True,
            )
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as exc:
            logger.error("Gemini streaming failed: %s", exc)
            raise

    def is_available(self) -> bool:
        """Check if Gemini API key and library are available."""
        if not self.api_key:
            return False
        try:
            import google.generativeai
            return True
        except ImportError:
            return False

    def get_langchain_llm(self) -> Any:
        """Get LangChain ChatGoogleGenerativeAI instance."""
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=self.model,
            google_api_key=self.api_key,
            max_output_tokens=self.max_tokens,
            temperature=self.temperature,
        )
