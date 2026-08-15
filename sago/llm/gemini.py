"""Gemini LLM Provider."""

from __future__ import annotations

import logging
import os
from typing import Any

from sago.llm.base import BaseLLMProvider
from sago.llm.retry import retry_with_backoff

logger = logging.getLogger(__name__)


class GeminiProvider(BaseLLMProvider):
    """Google Gemini LLM provider supporting both google.genai and legacy google.generativeai."""

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.api_key_env = config.get("api_key_env", "GEMINI_API_KEY")
        self.api_key = os.environ.get(self.api_key_env, "")
        self._client: Any = None

    def _get_genai_client(self) -> Any | None:
        try:
            from google import genai

            return genai.Client(api_key=self.api_key)
        except ImportError:
            return None

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate response using Gemini API."""
        client = self._get_genai_client()
        if client is not None:
            from google.genai import types as genai_types

            api_model = (
                self.model.replace("google/", "", 1)
                if self.model.startswith("google/")
                else self.model
            )
            config = genai_types.GenerateContentConfig(
                system_instruction=system_prompt or None,
                max_output_tokens=self.max_tokens,
                temperature=self.temperature,
            )

            def _call_genai() -> str:
                response = client.models.generate_content(
                    model=api_model,
                    contents=prompt,
                    config=config,
                )
                return response.text or ""

            return retry_with_backoff(_call_genai)

        # Fallback to legacy google.generativeai
        import google.generativeai as legacy_genai

        legacy_genai.configure(api_key=self.api_key)
        model = legacy_genai.GenerativeModel(self.model)

        gen_config = {
            "max_output_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if system_prompt:
            gen_config["system_instruction"] = system_prompt

        def _call_legacy() -> str:
            response = model.generate_content(
                prompt,
                generation_config=legacy_genai.GenerationConfig(**gen_config),
            )
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                logger.warning("Gemini response blocked: %s", response.prompt_feedback.block_reason)
                return f"[Response blocked: {response.prompt_feedback.block_reason}]"
            if not response.text:
                logger.warning("Gemini returned empty text for prompt length=%d", len(prompt))
                return ""
            return response.text

        return retry_with_backoff(_call_legacy)

    def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ):
        """Generate streaming response using Gemini API."""
        client = self._get_genai_client()
        if client is not None:
            from google.genai import types as genai_types

            api_model = (
                self.model.replace("google/", "", 1)
                if self.model.startswith("google/")
                else self.model
            )
            config = genai_types.GenerateContentConfig(
                system_instruction=system_prompt or None,
                max_output_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            response = client.models.generate_content_stream(
                model=api_model,
                contents=prompt,
                config=config,
            )
            for chunk in response:
                if chunk.text:
                    yield chunk.text
            return

        # Fallback to legacy google.generativeai
        import google.generativeai as legacy_genai

        legacy_genai.configure(api_key=self.api_key)
        model = legacy_genai.GenerativeModel(self.model)

        gen_config = {
            "max_output_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if system_prompt:
            gen_config["system_instruction"] = system_prompt

        try:
            response = model.generate_content(
                prompt,
                generation_config=legacy_genai.GenerationConfig(**gen_config),
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
            from google import genai  # noqa: F401

            return True
        except ImportError:
            try:
                import google.generativeai  # noqa: F401

                return True
            except ImportError:
                return False

    def get_langchain_llm(self) -> Any:
        """Get LangChain ChatGoogleGenerativeAI instance."""
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                model=self.model,
                google_api_key=self.api_key,
                max_output_tokens=self.max_tokens,
                temperature=self.temperature,
            )
        except ImportError as e:
            raise ImportError(
                "langchain-google-genai is required for LangChain integration with Gemini. "
                "Install it via: pip install langchain-google-genai"
            ) from e
