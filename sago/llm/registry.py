"""Provider Registry — single source of truth for LLM provider metadata.

Adding a new provider is now ONE step:

    from sago.llm.registry import ProviderSpec, register_provider

    register_provider(ProviderSpec(
        name="deepseek",
        api_key_env="DEEPSEEK_API_KEY",
        default_model="deepseek-chat",
        base_url="https://api.deepseek.com/v1",
        billing_url="https://platform.deepseek.com/usage",
    ))

Everything else (TUI key resolution, /provider validation, model prefix
stripping, auto-fallback chains) reads from this registry.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderSpec:
    """Declarative metadata for one LLM provider."""

    name: str  # canonical name used by settings/TUI
    aliases: tuple[str, ...] = ()  # alternate names (e.g. "gemini" -> google)
    api_key_env: str = ""  # env var holding the API key ("" = local/no key)
    default_model: str = ""  # model used when none configured
    base_url_env: str = ""  # env var overriding base URL
    base_url: str = ""  # OpenAI-compatible endpoint ("" = native SDK)
    local: bool = False  # runs locally; no API key needed
    billing_url: str = ""  # shown to users on credit/auth failures


_REGISTRY: dict[str, ProviderSpec] = {}  # canonical name -> spec
_ALIAS_TO_NAME: dict[str, str] = {}  # alias -> canonical name


def register_provider(spec: ProviderSpec) -> None:
    """Register a provider and its aliases. Later registrations win."""
    if spec.name in _REGISTRY:
        logger.debug("Re-registering provider %r", spec.name)
    _REGISTRY[spec.name.lower()] = spec
    _ALIAS_TO_NAME[spec.name.lower()] = spec.name.lower()
    for alias in spec.aliases:
        _ALIAS_TO_NAME[alias.lower()] = spec.name.lower()


def normalize_provider(name: str | None) -> str:
    """Map any provider alias to its canonical name ('gemini'->'google')."""
    n = (name or "").lower().strip()
    return _ALIAS_TO_NAME.get(n, n)


def get_provider_spec(name: str | None) -> ProviderSpec | None:
    """Get the spec for a provider name or alias. Returns None if unknown."""
    return _REGISTRY.get(normalize_provider(name))


def known_providers() -> list[str]:
    """Canonical provider names in registration order."""
    return list(_REGISTRY)


def known_provider_keys() -> dict[str, str]:  # pragma: no cover - trivial
    """Map of every accepted name/alias -> env var."""
    out: dict[str, str] = {}
    for canon, spec in _REGISTRY.items():
        out[canon] = spec.api_key_env
        for alias in spec.aliases:
            out[alias] = spec.api_key_env
    return out


def fallback_order() -> list[str]:
    """Canonical names to try when the configured provider has no API key.

    Cloud providers first (cheapest/free-routing first), local runtimes last.
    """
    ordered: list[str] = []
    preferred = ("openrouter", "openai", "google", "anthropic", "ollama")
    for name in preferred:
        if name in _REGISTRY:
            ordered.append(name)
    for name in _REGISTRY:
        if name not in ordered:
            ordered.append(name)
    return ordered


def split_provider_and_model(
    model_spec: str | None, default_provider: str | None = None
) -> tuple[str | None, str]:
    """Extract (provider, model_id) cleanly from an explicit provider:model or provider/model string.

    Never guesses or overrides providers based on substring heuristics (e.g. 'llama' or 'claude').
    If no recognized provider prefix is present, returns (default_provider, model_spec).
    """
    if not model_spec:
        return default_provider, ""
    spec_str = model_spec.strip()

    # Check for provider:model syntax (e.g., "google:gemini-2.5-pro", "ollama:llama3.2")
    if ":" in spec_str and not spec_str.startswith("http"):
        parts = spec_str.split(":", 1)
        canonical = normalize_provider(parts[0])
        if get_provider_spec(canonical):
            return canonical, parts[1]

    # Check for provider/model syntax (e.g., "google/gemini-2.5-pro", "openai/gpt-4o")
    if "/" in spec_str:
        prefix, rest = spec_str.split("/", 1)
        canonical = normalize_provider(prefix)
        if get_provider_spec(canonical):
            if canonical == "openrouter":
                return "openrouter", rest if rest else spec_str
            return canonical, rest

    return default_provider, spec_str


def guess_provider_from_model(model: str | None) -> str | None:
    """Extract explicit provider prefix from model string if present, or None.

    Does not guess or assume providers based on substrings.
    """
    prov, _ = split_provider_and_model(model)
    return prov


def resolve_api_key(provider: str | None, model: str | None = None) -> str:
    """Resolve the API key for a provider (with model-based sniffing fallback)."""
    spec = get_provider_spec(provider)
    if spec and spec.api_key_env:
        key = os.environ.get(spec.api_key_env, "")
        if key:
            return key
    # Model-prefix sniffing as secondary signal
    sniffed = guess_provider_from_model(model)
    if sniffed:
        sspec = get_provider_spec(sniffed)
        if sspec and sspec.api_key_env:
            return os.environ.get(sspec.api_key_env, "")
    return ""


def resolve_base_url(provider: str | None) -> str | None:
    """Resolve the OpenAI-compatible base URL for a provider (None = native SDK)."""
    spec = get_provider_spec(provider)
    if not spec:
        return None
    if spec.base_url_env:
        override = os.environ.get(spec.base_url_env, "")
        if override:
            return override
    return spec.base_url or None


def strip_model_prefix(provider: str | None, model: str) -> str:
    """Strip a redundant provider prefix from a model id.

    e.g. ('google', 'google/gemini-2.0-flash') -> 'gemini-2.0-flash'
    """
    spec = get_provider_spec(provider)
    if not spec:
        return model
    for candidate in (spec.name, *spec.aliases):
        prefix = f"{candidate}/"
        if model.lower().startswith(prefix):
            return model[len(prefix) :]
    return model


def infer_provider_for_model(model: str | None) -> str | None:
    """Extract explicit provider prefix from model string if present, or infer from canonical model name prefix."""
    if not model:
        return None
    prov, clean = split_provider_and_model(model)
    if prov:
        return prov
    m = clean.lower()
    if m.startswith("gemini"):
        return "google"
    if m.startswith("claude"):
        return "anthropic"
    return None


# --- Built-in providers -----------------------------------------------------

register_provider(
    ProviderSpec(
        name="google",
        aliases=("gemini",),
        api_key_env="GEMINI_API_KEY",
        default_model="gemini-2.5-pro",
        billing_url="https://aistudio.google.com/apikey",
    )
)
register_provider(
    ProviderSpec(
        name="openai",
        aliases=("gpt", "chatgpt"),
        api_key_env="OPENAI_API_KEY",
        default_model="gpt-4o",
        base_url_env="OPENAI_BASE_URL",
        base_url="https://api.openai.com/v1",
        billing_url="https://platform.openai.com/account/billing",
    )
)
register_provider(
    ProviderSpec(
        name="openrouter",
        api_key_env="OPENROUTER_API_KEY",
        default_model="openrouter/free",
        base_url_env="OPENROUTER_BASE_URL",
        base_url="https://openrouter.ai/api/v1",
        billing_url="https://openrouter.ai/settings/credits",
    )
)
register_provider(
    ProviderSpec(
        name="anthropic",
        aliases=("claude",),
        api_key_env="ANTHROPIC_API_KEY",
        default_model="claude-3-7-sonnet-20250219",
        billing_url="https://console.anthropic.com/settings/billing",
    )
)
register_provider(
    ProviderSpec(
        name="deepseek",
        api_key_env="DEEPSEEK_API_KEY",
        default_model="deepseek-chat",
        base_url_env="DEEPSEEK_BASE_URL",
        base_url="https://api.deepseek.com/v1",
        billing_url="https://platform.deepseek.com/usage",
    )
)
register_provider(
    ProviderSpec(
        name="groq",
        api_key_env="GROQ_API_KEY",
        default_model="llama-3.3-70b-versatile",
        base_url_env="GROQ_BASE_URL",
        base_url="https://api.groq.com/openai/v1",
        billing_url="https://console.groq.com/keys",
    )
)
register_provider(
    ProviderSpec(
        name="mistral",
        api_key_env="MISTRAL_API_KEY",
        default_model="mistral-large-latest",
        base_url_env="MISTRAL_BASE_URL",
        base_url="https://api.mistral.ai/v1",
        billing_url="https://console.mistral.ai/billing",
    )
)
register_provider(
    ProviderSpec(
        name="together",
        api_key_env="TOGETHER_API_KEY",
        default_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        base_url_env="TOGETHER_BASE_URL",
        base_url="https://api.together.xyz/v1",
        billing_url="https://api.together.ai/settings/billing",
    )
)
register_provider(
    ProviderSpec(
        name="ollama",
        aliases=("local",),
        default_model="deepseek-r1",
        base_url_env="OLLAMA_BASE_URL",
        base_url="http://localhost:11434/v1",
        local=True,
    )
)
register_provider(
    ProviderSpec(
        name="lmstudio",
        aliases=("lms",),
        default_model="local-model",
        base_url_env="LMSTUDIO_BASE_URL",
        base_url="http://localhost:1234/v1",
        local=True,
    )
)
register_provider(
    ProviderSpec(
        name="mock",
        aliases=("test",),
        default_model="mock-1",
        local=True,
    )
)
