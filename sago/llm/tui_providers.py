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
    split_provider_and_model,
    strip_model_prefix,
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
    explicit_provider, clean_model = split_provider_and_model(model)

    resolved_provider = (
        normalize_provider(provider)
        or explicit_provider
        or normalize_provider(os.environ.get("SAGO_PROVIDER") or load_setting("provider"))
    )

    if not resolved_provider:
        try:
            from sago.config.loader import get_config

            cfg = get_config()
            raw = getattr(getattr(cfg, "llm_providers", None), "default", None)
            if raw and isinstance(raw, str):
                resolved_provider = normalize_provider(raw)
        except Exception:
            pass

    # Only fall back to an available key if user has NO configured provider anywhere
    if not resolved_provider:
        for fallback in fallback_order():
            fspec = get_provider_spec(fallback)
            if fspec and (fspec.local or resolve_api_key(fallback)):
                resolved_provider = fallback
                break
        if not resolved_provider:
            resolved_provider = "openrouter"

    # 2. Resolve Model
    resolved_model = clean_model if clean_model else None
    if not resolved_model:
        resolved_model = (
            os.environ.get("SAGO_MODEL") or load_setting("model") or load_setting("provider_model")
        )
    if not resolved_model:
        try:
            from sago.config.loader import get_config

            cfg = get_config()
            orch_model = getattr(getattr(cfg, "orchestrator", None), "model", None)
            if orch_model and isinstance(orch_model, str):
                resolved_model = orch_model
        except Exception:
            pass
    if not resolved_model:
        fspec = get_provider_spec(resolved_provider)
        resolved_model = fspec.default_model if fspec else "openrouter/free"

    # Strip redundant provider prefix unless provider is openrouter (which needs vendor/model)
    if resolved_provider != "openrouter":
        resolved_model = strip_model_prefix(resolved_provider, resolved_model)

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
        try:
            import anthropic  # noqa: F401

            key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not key:
                raise ValueError(
                    "ANTHROPIC_API_KEY not set. Get one at: https://console.anthropic.com"
                )
            # If anthropic SDK is installed and key is set, check if openrouter is preferred or route
            if os.environ.get("OPENROUTER_API_KEY") and not key:
                openrouter_model = f"anthropic/{model.replace('anthropic/', '')}"
                return _get_openrouter_client(
                    openrouter_model, os.environ["OPENROUTER_API_KEY"]
                ), openrouter_model
        except ImportError:
            pass

        # If direct anthropic SDK is not installed, route via OpenRouter if key is available
        if os.environ.get("OPENROUTER_API_KEY"):
            openrouter_model = f"anthropic/{model.replace('anthropic/', '')}"
            return _get_openrouter_client(
                openrouter_model, os.environ["OPENROUTER_API_KEY"]
            ), openrouter_model

        raise ValueError(
            "Direct Anthropic chat requires 'anthropic' package (pip install anthropic) and ANTHROPIC_API_KEY, "
            "or set OPENROUTER_API_KEY to route Anthropic models via OpenRouter."
        )
    elif canonical in ("openrouter", ""):
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        return _get_openrouter_client(model, api_key), model
    elif spec and spec.base_url:
        # Standard OpenAI-compatible provider (DeepSeek, Groq, Mistral, Together, LM Studio, etc.)
        key = resolve_api_key(canonical, model)
        if not key and not spec.local:
            key_name = spec.api_key_env or f"{canonical.upper()}_API_KEY"
            raise ValueError(
                f"{key_name} not set for provider '{canonical}'. Get one at: {spec.billing_url or spec.base_url}"
            )
        from sago.llm.registry import strip_model_prefix

        api_model = strip_model_prefix(canonical, model)
        return _get_openai_compatible_client(api_model, spec.base_url, key=key or "local")

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
    try:
        from google import genai as google_genai
    except ImportError as err:
        raise ImportError(
            "The 'google-genai' package is required for Google Gemini models. "
            "Install it via: pip install google-genai"
        ) from err

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
        contents = []
        sys_msg = system_prompt
        for msg in messages:
            if msg["role"] == "system":
                sys_msg = msg["content"]
            elif msg["role"] in ("user", "assistant"):
                contents.append(msg["content"])
        if not contents:
            contents = ["Hello"]

        try:
            from google.genai import types as google_types

            gen_config = google_types.GenerateContentConfig(
                system_instruction=sys_msg or None,
                max_output_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception:
            gen_config = None

        if stream:
            return client.models.generate_content_stream(
                model=api_model,
                contents=contents,
                config=gen_config,
            )
        else:
            response = client.models.generate_content(
                model=api_model,
                contents=contents,
                config=gen_config,
            )
            return getattr(response, "text", "") or ""

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
