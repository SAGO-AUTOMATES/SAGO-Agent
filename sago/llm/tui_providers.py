"""TUI Provider Registry — auto-discovers providers, returns correct client.

To add a new provider, register a ProviderSpec in sago/llm/registry.py
(one declarative entry) and optionally add a client builder below.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from sago.llm.registry import (
    fallback_order,
    get_provider_spec,
    known_providers,
    normalize_provider,
    resolve_api_key,
    resolve_base_url,
)

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
    resolved_provider = normalize_provider(provider)
    if not resolved_provider:
        resolved_provider = normalize_provider(
            os.environ.get("SAGO_PROVIDER") or load_setting("provider")
        )
    if not resolved_provider:
        try:
            from sago.config.loader import get_config

            cfg = get_config()
            raw = getattr(cfg.llm_providers, "default", None) or "openrouter"
            resolved_provider = normalize_provider(raw)
        except Exception:
            resolved_provider = "openrouter"

    # Auto-fallback: if configured provider has no API key, pick one that does
    _original_provider = resolved_provider
    spec = get_provider_spec(resolved_provider)
    needs_key = bool(spec and spec.api_key_env) if spec else True
    if needs_key:
        has_key = resolve_api_key(resolved_provider) != ""
        if not has_key:
            for fallback in fallback_order():
                fspec = get_provider_spec(fallback)
                if fspec is None or fspec.local or not fspec.api_key_env:
                    continue
                if resolve_api_key(fallback):
                    logger.info(
                        "No API key for %r, falling back to %r", resolved_provider, fallback
                    )
                    resolved_provider = fallback
                    break

    # 2. Resolve Model
    resolved_model = model
    if not resolved_model:
        resolved_model = (
            os.environ.get("SAGO_MODEL") or load_setting("model") or load_setting("provider_model")
        )
    if not resolved_model:
        try:
            from sago.config.loader import get_config

            cfg = get_config()
            if hasattr(cfg, "orchestrator") and getattr(cfg.orchestrator, "model", None):
                resolved_model = cfg.orchestrator.model
        except Exception:
            logger.debug("Could not load config for model resolution")

    # If provider was fallback-changed (or none configured), use its default model
    provider_changed = resolved_provider != _original_provider
    if (provider_changed or not resolved_model) and not model:
        fspec = get_provider_spec(resolved_provider)
        resolved_model = fspec.default_model if fspec else "openrouter/free"

    # 3. Resolve API Key
    if api_key:
        resolved_key = api_key
    else:
        resolved_key = resolve_api_key(resolved_provider, resolved_model)
        if not resolved_key:
            # Last resort: any configured cloud key
            for fallback in fallback_order():
                fspec = get_provider_spec(fallback)
                if fspec and fspec.api_key_env:
                    resolved_key = os.environ.get(fspec.api_key_env, "")
                    if resolved_key:
                        break

    # 4. Resolve Base URL
    if base_url is not None:
        resolved_base_url = base_url
    else:
        resolved_base_url = resolve_base_url(resolved_provider)
        if resolved_provider == "openai":
            resolved_base_url = resolved_base_url or "https://api.openai.com/v1"
        elif resolved_provider == "openrouter":
            resolved_base_url = resolved_base_url or "https://openrouter.ai/api/v1"

    return {
        "provider": resolved_provider,
        "model": resolved_model,
        "api_key": resolved_key,
        "base_url": resolved_base_url,
    }


def get_tui_client(provider: str, model: str) -> tuple[Any, str]:
    """Get (client, api_model) for the TUI.

    Returns:
        (client, model_name_for_api) — client is OpenAI-compatible or native SDK
    """
    canonical = normalize_provider(provider)
    spec = get_provider_spec(canonical)
    if canonical == "google":
        return _get_google_client(model)
    elif canonical == "openai":
        return _get_openai_client(model)
    elif canonical == "ollama" or (model or "").startswith("ollama/"):
        return _get_ollama_client(model)
    elif canonical == "anthropic":
        raise ValueError(
            "Direct Anthropic chat is handled via OpenRouter routing; "
            "use /provider openrouter with a claude-* model."
        )
    elif spec and spec.base_url and spec.local:
        # Registry-driven local/OpenAI-compatible providers
        return _get_openai_compatible_client(model, spec.base_url, key="ollama")
    elif canonical in ("openrouter", ""):
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        return _get_openrouter_client(model, api_key), model

    raise ValueError(
        f"Unknown provider {provider!r}. Known providers: {', '.join(known_providers())}"
    )


def _get_openai_compatible_client(model: str, base_url: str, key: str = "") -> tuple[Any, str]:
    """Generic OpenAI-compatible client builder."""
    try:
        from openai import OpenAI
    except ImportError as err:
        raise ImportError(
            "The 'openai' package is required for this provider. Install it via: pip install openai"
        ) from err
    api_model = model.split("/", 1)[1] if "/" in model else model
    return OpenAI(api_key=key or "local", base_url=base_url, timeout=180.0), api_model


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
