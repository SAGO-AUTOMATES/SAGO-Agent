"""TUI Provider Registry — auto-discovers providers, returns correct client.

To add a new provider, just create a file in sago/llm/ like:
    sago/llm/my_provider.py

with a class inheriting BaseLLMProvider and register it in factory.py.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def resolve_active_llm_config(
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Resolve active LLM configuration (provider, model, api_key, base_url).

    Inherits settings from persistent user choices (e.g. from TUI or CLI),
    environment variables, project configs, and falls back gracefully.
    """
    from sago.settings import load_setting

    # 1. Resolve Provider
    resolved_provider = provider
    if not resolved_provider:
        resolved_provider = os.environ.get("SAGO_PROVIDER") or load_setting("provider")
    if not resolved_provider:
        try:
            from sago.config.loader import get_config

            cfg = get_config()
            resolved_provider = getattr(cfg.llm_providers, "default", None) or "openrouter"
        except Exception:
            resolved_provider = "openrouter"

    # 2. Resolve Model
    resolved_model = model
    if not resolved_model:
        resolved_model = os.environ.get("SAGO_MODEL") or load_setting("model")
    if not resolved_model:
        try:
            from sago.config.loader import get_config

            cfg = get_config()
            if hasattr(cfg, "orchestrator") and getattr(cfg.orchestrator, "model", None):
                resolved_model = cfg.orchestrator.model
        except Exception:
            pass
    if not resolved_model:
        provider_defaults = {
            "google": "gemini-2.5-pro",
            "openai": "gpt-4o",
            "openrouter": "openrouter/free",
            "claude": "claude-3-5-sonnet-20241022",
            "anthropic": "claude-3-5-sonnet-20241022",
        }
        resolved_model = provider_defaults.get(resolved_provider, "openrouter/free")

    # 3. Resolve API Key
    resolved_key = api_key
    if not resolved_key:
        if resolved_provider == "google" or "gemini" in resolved_model:
            resolved_key = os.environ.get("GEMINI_API_KEY", "")
        elif resolved_provider == "openai" or any(
            resolved_model.startswith(p) for p in ("gpt", "o1", "o3")
        ):
            resolved_key = os.environ.get("OPENAI_API_KEY", "")
        elif resolved_provider in ("claude", "anthropic") or "claude" in resolved_model:
            resolved_key = os.environ.get("ANTHROPIC_API_KEY", "")
        elif resolved_provider == "openrouter":
            resolved_key = os.environ.get("OPENROUTER_API_KEY", "")

        if not resolved_key:
            resolved_key = (
                os.environ.get("OPENROUTER_API_KEY")
                or os.environ.get("OPENAI_API_KEY")
                or os.environ.get("GEMINI_API_KEY")
                or os.environ.get("ANTHROPIC_API_KEY")
                or ""
            )

    # 4. Resolve Base URL
    resolved_base_url = base_url
    if resolved_base_url is None:
        if resolved_provider == "google":
            resolved_base_url = None
        elif resolved_provider == "openai":
            resolved_base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        elif resolved_provider == "openrouter":
            resolved_base_url = os.environ.get(
                "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
            )

    return {
        "provider": resolved_provider,
        "model": resolved_model,
        "api_key": resolved_key,
        "base_url": resolved_base_url,
    }


def get_tui_client(provider: str, model: str) -> tuple[Any, str]:
    """Get (client, api_model) for the TUI.

    Returns:
        (client, model_name_for_api) — client is OpenAI or native SDK
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")

    if provider == "google":
        return _get_google_client(model)
    elif provider == "openai":
        return _get_openai_client(model)
    elif provider == "ollama" or model.startswith("ollama/"):
        return _get_ollama_client(model)
    else:
        return _get_openrouter_client(model, api_key), model


def _get_ollama_client(model: str) -> tuple[Any, str]:
    """Local Ollama client via OpenAI-compatible endpoint."""
    try:
        from openai import OpenAI
    except ImportError as err:
        raise ImportError(
            "The 'openai' package is required to use Ollama via standard endpoint. "
            "Install it via: pip install openai"
        ) from err

    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    api_model = model.replace("ollama/", "", 1) if model.startswith("ollama/") else model
    return OpenAI(api_key="ollama", base_url=base_url, timeout=180.0), api_model


def _get_google_client(model: str) -> tuple[Any, str]:
    """Google Gemini via native google-genai SDK."""
    from google import genai as google_genai

    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise ValueError("GEMINI_API_KEY not set. Get one at: https://aistudio.google.com/apikey")
    client = google_genai.Client(api_key=key)
    api_model = model.replace("google/", "", 1) if model.startswith("google/") else model
    return client, api_model


def _get_openai_client(model: str) -> tuple[Any, str]:
    """OpenAI direct."""
    try:
        from openai import OpenAI
    except ImportError as err:
        raise ImportError(
            "The 'openai' package is required to use OpenAI models. "
            "Install it via: pip install openai or pip install langchain-openai"
        ) from err

    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise ValueError("OPENAI_API_KEY not set.")
    api_model = model.replace("openai/", "", 1) if model.startswith("openai/") else model
    return OpenAI(api_key=key, timeout=90.0), api_model


def _get_openrouter_client(model: str, api_key: str) -> Any:
    """OpenRouter — routes to any provider."""
    try:
        from openai import OpenAI
    except ImportError as err:
        raise ImportError(
            "The 'openai' package is required to use OpenRouter. "
            "Install it via: pip install openai or pip install langchain-openai"
        ) from err

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
