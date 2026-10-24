"""Tests for dynamic context compaction thresholds based on model and provider capabilities."""

from __future__ import annotations

import os
from unittest.mock import patch

from sago.memory.compaction import (
    CompactionThresholds,
    SessionCompactor,
    get_dynamic_compaction_thresholds,
)


def test_dynamic_compaction_local_tier_ollama():
    """Verify local models (Ollama, LM Studio) default to 50k-100k context guard (75k tokens)."""
    thresholds = get_dynamic_compaction_thresholds(provider="ollama", model="llama3.2")
    assert isinstance(thresholds, CompactionThresholds)
    assert thresholds.tier == "local"
    assert 50_000 <= thresholds.trigger_tokens <= 100_000
    assert thresholds.trigger_tokens == 75_000
    assert thresholds.target_tokens < thresholds.trigger_tokens
    assert thresholds.trigger_messages == 20
    assert "Local model tier" in thresholds.description


def test_dynamic_compaction_local_tier_lmstudio_and_localhost():
    """Verify LM Studio and localhost endpoints default to local tier."""
    thresholds_lms = get_dynamic_compaction_thresholds(
        provider="lmstudio", model="qwen2.5-coder-7b"
    )
    assert thresholds_lms.tier == "local"
    assert thresholds_lms.trigger_tokens == 75_000

    thresholds_local_url = get_dynamic_compaction_thresholds(
        provider="custom",
        model="custom-model",
        base_url="http://127.0.0.1:8000/v1",
    )
    assert thresholds_local_url.tier == "local"


def test_dynamic_compaction_standard_cloud_tier():
    """Verify standard cloud models (OpenAI, Anthropic 200k, DeepSeek, Groq) use 150k-200k tokens."""
    # OpenAI GPT-4o
    thresh_openai = get_dynamic_compaction_thresholds(provider="openai", model="gpt-4o")
    assert thresh_openai.tier == "standard"
    assert 150_000 <= thresh_openai.trigger_tokens <= 200_000
    assert thresh_openai.trigger_tokens == 175_000
    assert thresh_openai.trigger_messages == 45
    assert "Standard cloud tier" in thresh_openai.description

    # Anthropic Claude 3.5 Sonnet
    thresh_claude = get_dynamic_compaction_thresholds(
        provider="anthropic", model="claude-3-5-sonnet-20241022"
    )
    assert thresh_claude.tier == "standard"
    assert thresh_claude.trigger_tokens == 175_000

    # DeepSeek
    thresh_deepseek = get_dynamic_compaction_thresholds(provider="deepseek", model="deepseek-chat")
    assert thresh_deepseek.tier == "standard"

    # Default OpenRouter free tier
    thresh_openrouter = get_dynamic_compaction_thresholds(
        provider="openrouter", model="openrouter/free"
    )
    assert thresh_openrouter.tier == "standard"


def test_dynamic_compaction_massive_context_tier():
    """Verify massive context models (Gemini 1M/2M, 1M context models) use 750k-1M tokens."""
    # Google Gemini 2.5 Pro
    thresh_google = get_dynamic_compaction_thresholds(provider="google", model="gemini-2.5-pro")
    assert thresh_google.tier == "massive"
    assert 750_000 <= thresh_google.trigger_tokens <= 1_000_000
    assert thresh_google.trigger_tokens == 750_000
    assert thresh_google.target_tokens == 250_000
    assert thresh_google.trigger_messages == 120
    assert "Massive context tier" in thresh_google.description

    # OpenRouter routing to Gemini 1.5 Pro
    thresh_or_gemini = get_dynamic_compaction_thresholds(
        provider="openrouter", model="google/gemini-1.5-pro"
    )
    assert thresh_or_gemini.tier == "massive"
    assert thresh_or_gemini.trigger_tokens == 750_000

    # Explicit 1M token variant
    thresh_1m = get_dynamic_compaction_thresholds(provider="custom", model="qwen-2.5-1m")
    assert thresh_1m.tier == "massive"
    assert thresh_1m.trigger_tokens == 750_000


def test_dynamic_compaction_env_overrides():
    """Verify granular and global environment variable overrides."""
    with patch.dict(
        os.environ,
        {"SAGO_COMPACTION_THRESHOLD_LOCAL": "85000"},
        clear=False,
    ):
        local_override = get_dynamic_compaction_thresholds(provider="ollama", model="llama3")
        assert local_override.trigger_tokens == 85_000

    with patch.dict(
        os.environ,
        {"SAGO_COMPACTION_THRESHOLD_STANDARD": "190000"},
        clear=False,
    ):
        standard_override = get_dynamic_compaction_thresholds(provider="openai", model="gpt-4o")
        assert standard_override.trigger_tokens == 190_000

    with patch.dict(
        os.environ,
        {"SAGO_COMPACTION_THRESHOLD_MASSIVE": "900000"},
        clear=False,
    ):
        massive_override = get_dynamic_compaction_thresholds(
            provider="google", model="gemini-1.5-flash"
        )
        assert massive_override.trigger_tokens == 900_000

    with patch.dict(
        os.environ,
        {"SAGO_COMPACTION_THRESHOLD": "120000"},
        clear=False,
    ):
        global_override = get_dynamic_compaction_thresholds(provider="openai", model="gpt-4o")
        assert global_override.trigger_tokens == 120_000


def test_session_compactor_dynamic_initialization():
    """Verify SessionCompactor automatically uses dynamic thresholds when max_context_tokens is None."""
    # Local
    compactor_local = SessionCompactor(provider="ollama", model="llama3.2")
    assert compactor_local.thresholds is not None
    assert compactor_local.thresholds.tier == "local"
    assert compactor_local.max_context_tokens == 75_000

    # Massive
    compactor_massive = SessionCompactor(provider="google", model="gemini-2.5-pro")
    assert compactor_massive.thresholds is not None
    assert compactor_massive.thresholds.tier == "massive"
    assert compactor_massive.max_context_tokens == 750_000

    # Explicit override preserves custom max_context_tokens
    compactor_explicit = SessionCompactor(max_context_tokens=1234)
    assert compactor_explicit.max_context_tokens == 1234
    assert compactor_explicit.thresholds is None


def test_dynamic_context_window_suffix_and_custom_budget():
    """Verify context size is dynamically parsed from model suffixes without static model mapping."""
    # Suffix :32k
    th_32k = get_dynamic_compaction_thresholds(provider="custom_runtime", model="any-model:32k")
    assert th_32k.tier == "local"
    assert th_32k.trigger_tokens == 50_000 or th_32k.trigger_tokens <= 50_000

    # Suffix -128k
    th_128k = get_dynamic_compaction_thresholds(provider="custom_runtime", model="my-model-128k")
    assert th_128k.tier == "local"
    assert th_128k.trigger_tokens == 96_000

    # Explicit context_window argument
    th_custom = get_dynamic_compaction_thresholds(
        context_window=64_000, provider="custom", model="unknown"
    )
    assert th_custom.tier == "local"
    assert th_custom.trigger_tokens == 50_000  # min bounded for local tier

    # Explicit 2M context window
    th_2m = get_dynamic_compaction_thresholds(
        context_window=2_000_000, provider="custom", model="unknown"
    )
    assert th_2m.tier == "massive"
    assert th_2m.trigger_tokens == 1_000_000  # max bounded for massive tier


def test_executor_does_not_pollute_model_messages_with_compaction():
    """Verify that auto-compaction does not append [COMPACTED] messages to the model payload."""
    import inspect

    from sago.engine.simple_executor import execute_agent_task

    src = inspect.getsource(execute_agent_task)
    assert "[COMPACTED]" not in src
