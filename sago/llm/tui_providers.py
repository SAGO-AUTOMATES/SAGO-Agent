"""TUI Provider Registry — auto-discovers providers, returns correct client.

To add a new provider, just create a file in sago/llm/ like:
    sago/llm/my_provider.py

with a class inheriting BaseLLMProvider and register it in factory.py.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from openai import OpenAI

logger = logging.getLogger(__name__)


def get_tui_client(provider: str, model: str) -> tuple[OpenAI | Any, str]:
    """Get (client, api_model) for the TUI.

    Returns:
        (client, model_name_for_api) — client is OpenAI or native SDK
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")

    if provider == "google":
        return _get_google_client(model)
    elif provider == "openai":
        return _get_openai_client(model)
    else:
        return _get_openrouter_client(model, api_key), model


def _get_google_client(model: str) -> tuple[Any, str]:
    """Google Gemini via native google-genai SDK."""
    from google import genai as google_genai

    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ValueError("GEMINI_API_KEY not set. Get one at: https://aistudio.google.com/apikey")
    client = google_genai.Client(api_key=key)
    api_model = model.replace("google/", "", 1) if model.startswith("google/") else model
    return client, api_model


def _get_openai_client(model: str) -> tuple[OpenAI, str]:
    """OpenAI direct."""
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise ValueError("OPENAI_API_KEY not set.")
    api_model = model.replace("openai/", "", 1) if model.startswith("openai/") else model
    return OpenAI(api_key=key, timeout=90.0), api_model


def _get_openrouter_client(model: str, api_key: str) -> OpenAI:
    """OpenRouter — routes to any provider."""
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set.")
    return OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1", timeout=90.0)


def generate_with_provider(
    provider: str,
    model: str,
    messages: list[dict],
    system_prompt: str = "",
    max_tokens: int = 16384,
    temperature: float = 0.3,
    stream: bool = False,
) -> Any:
    """Unified generation call — works with any registered provider."""
    client, api_model = get_tui_client(provider, model)

    if provider == "google":
        from google.genai import types as google_types

        contents = []
        sys_msg = system_prompt
        for msg in messages:
            if msg["role"] == "system":
                sys_msg = msg["content"]
            elif msg["role"] in ("user", "assistant"):
                contents.append(msg["content"])
        if not contents:
            contents = ["Hello"]

        if stream:
            return client.models.generate_content_stream(
                model=api_model,
                contents=contents,
                config=google_types.GenerateContentConfig(
                    system_instruction=sys_msg or None,
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                ),
            )
        else:
            response = client.models.generate_content(
                model=api_model,
                contents=contents,
                config=google_types.GenerateContentConfig(
                    system_instruction=sys_msg or None,
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                ),
            )
            return response.text or ""

    if stream:
        return client.chat.completions.create(
            model=api_model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
            stream_options={"include_usage": True},
        )
    else:
        response = client.chat.completions.create(
            model=api_model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if not response.choices:
            logger.warning("Provider %s returned empty choices", provider)
            return ""
        return response.choices[0].message.content or ""
