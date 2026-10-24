"""Comprehensive tests for ModelSwitcherScreen, modernized providers, and CLI onboarding."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
from textual.widgets import Button, Input, OptionList

from sago.llm.registry import (
    get_provider_spec,
    guess_provider_from_model,
    infer_provider_for_model,
)
from sago.llm.tui_providers import get_tui_client, resolve_active_llm_config
from sago.settings import load_setting, save_setting
from sago.tui.app import SagoApp
from sago.tui.modals import ModelSwitcherScreen


def test_registry_providers_registered():
    """Verify all modern LLM providers are properly registered."""
    for prov in (
        "google",
        "openai",
        "anthropic",
        "deepseek",
        "groq",
        "mistral",
        "together",
        "ollama",
        "lmstudio",
        "openrouter",
    ):
        spec = get_provider_spec(prov)
        assert spec is not None, f"Provider {prov} must be registered"
        assert spec.default_model != ""


def test_guess_and_infer_provider():
    """Verify provider extraction from explicit prefixes and no random substring guessing."""
    # Explicit provider prefix
    assert guess_provider_from_model("google/gemini-2.0-flash") == "google"
    assert guess_provider_from_model("google:gemini-2.5-pro") == "google"
    assert guess_provider_from_model("openai/gpt-4o") == "openai"
    assert guess_provider_from_model("deepseek/deepseek-chat") == "deepseek"
    assert guess_provider_from_model("groq/llama-3.3-70b-versatile") == "groq"
    assert guess_provider_from_model("ollama/deepseek-r1") == "ollama"

    # Bare model IDs: no heuristic guessing! Never overrides user provider
    assert guess_provider_from_model("gemini-2.5-pro") is None
    assert guess_provider_from_model("claude-3-7-sonnet") is None
    assert guess_provider_from_model("gpt-4o") is None
    assert guess_provider_from_model("llama3.2") is None
    assert guess_provider_from_model("qwen2.5-coder") is None

    assert infer_provider_for_model("google/gemini-2.0-flash") == "google"
    assert infer_provider_for_model("openai/gpt-4o") == "openai"
    assert infer_provider_for_model("deepseek/deepseek-chat") == "deepseek"
    assert infer_provider_for_model("groq/qwen-2.5-coder-32b") == "groq"
    assert infer_provider_for_model("custom-model") is None


def test_tui_client_openai_compatible_providers(monkeypatch):
    """Verify get_tui_client handles DeepSeek, Groq, Mistral, and local endpoints."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek-test-123")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-groq-test-123")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-123")

    # Mock OpenAI client
    mock_openai = MagicMock()
    monkeypatch.setattr("openai.OpenAI", mock_openai)

    # 1. DeepSeek
    client, model = get_tui_client("deepseek", "deepseek-chat")
    assert model == "deepseek-chat"
    assert mock_openai.called

    # 2. Groq
    client, model = get_tui_client("groq", "llama-3.3-70b-versatile")
    assert model == "llama-3.3-70b-versatile"

    # 3. OpenRouter
    client, model = get_tui_client("openrouter", "deepseek/deepseek-r1:free")
    assert model == "deepseek/deepseek-r1:free"

    # 4. Ollama (local)
    client, model = get_tui_client("ollama", "ollama/deepseek-r1")
    assert model == "deepseek-r1"

    # 5. Missing key raises helpful error
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY not set"):
        get_tui_client("deepseek", "deepseek-chat")


def test_resolve_active_llm_config_persistence(tmp_path, monkeypatch):
    """Verify active LLM config resolves correctly from settings."""
    save_setting("provider", "deepseek")
    save_setting("model", "deepseek-chat")

    cfg = resolve_active_llm_config()
    assert cfg["provider"] in ("deepseek", "openrouter")
    assert "deepseek" in cfg["model"] or "openrouter" in cfg["model"]


@pytest.mark.asyncio
async def test_model_switcher_screen_modal():
    """Verify ModelSwitcherScreen UI mount, search filtering, and selection."""
    screen = ModelSwitcherScreen()
    app = SagoApp()

    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(screen)
        await pilot.pause()

        options = screen.query_one("#model-options", OptionList)
        assert options.option_count > 0

        # Test search filtering
        search_input = screen.query_one("#model-search-input", Input)
        search_input.value = "deepseek"
        await pilot.pause()
        assert options.option_count > 0

        # Filter by provider tab
        screen._provider_filter = "google"
        screen._search_query = ""
        screen._populate_options()
        await pilot.pause()
        assert options.option_count > 0

        # Keyboard arrow navigation
        mock_down = MagicMock(key="down")
        screen.on_key(mock_down)
        assert mock_down.prevent_default.called
        assert mock_down.stop.called

        mock_up = MagicMock(key="up")
        screen.on_key(mock_up)
        assert mock_up.prevent_default.called
        assert mock_up.stop.called

        mock_pgdn = MagicMock(key="pagedown")
        screen.on_key(mock_pgdn)
        assert mock_pgdn.prevent_default.called

        mock_pgup = MagicMock(key="pageup")
        screen.on_key(mock_pgup)
        assert mock_pgup.prevent_default.called

        # Selecting an option highlights and populates details without closing
        opt = options.get_option_at_index(0)
        screen.on_option_selected(MagicMock(option=opt))
        assert screen._selected_entry is not None
        assert "✓ Use Selected Model" in str(screen.query_one("#btn-select-model", Button).label)

        # Confirming selection
        dismiss_result = None

        def mock_dismiss(result):
            nonlocal dismiss_result
            dismiss_result = result

        screen.dismiss = mock_dismiss

        screen.action_select_current()
        assert dismiss_result == screen._selected_entry

        # Custom model entry
        custom_input = screen.query_one("#custom-model-input", Input)
        custom_input.value = "custom-fine-tuned-model"
        screen._apply_custom_model()
        await pilot.pause()


@pytest.mark.asyncio
async def test_tui_model_and_provider_commands():
    """Verify /model and /provider command execution and settings persistence."""
    app = SagoApp()
    async with app.run_test() as pilot:
        await pilot.pause()

        # 1. /provider deepseek
        os.environ["DEEPSEEK_API_KEY"] = "sk-deepseek-test"
        app._handle_command("/provider deepseek")
        assert app.current_provider == "deepseek"
        assert app.current_model == "deepseek-chat"
        assert load_setting("provider") == "deepseek"

        # 2. /model google gemini-2.5-pro (explicit syntax)
        app._handle_command("/model google gemini-2.5-pro")
        assert app.current_provider == "google"
        assert app.current_model == "gemini-2.5-pro"
        assert load_setting("provider") == "google"
        assert load_setting("model") == "gemini-2.5-pro"

        # 3. /model openai/gpt-4o (slash syntax)
        app._handle_command("/model openai/gpt-4o")
        assert app.current_provider == "openai"
        assert app.current_model == "gpt-4o"

        # 4. /model custom-model (keeps active provider, doesn't force openrouter)
        app._handle_command("/model my-private-model")
        assert app.current_provider == "openai"
        assert app.current_model == "my-private-model"

        # 5. /model list (outputs text collapsible)
        app._handle_command("/model list")
        await pilot.pause()

        # 6. Action button click
        btn = app.query_one("#btn-input-model")
        assert btn is not None

        # 7. Press F6 while input is focused
        input_widget = app.query_one("#msg-input")
        input_widget.focus()
        await pilot.press("f6")
        await pilot.pause()
        assert isinstance(app.screen, ModelSwitcherScreen)
        await pilot.press("escape")
        await pilot.pause()

        # 8. Press Ctrl+M while input is focused
        input_widget.focus()
        await pilot.press("ctrl+m")
        await pilot.pause()
        assert isinstance(app.screen, ModelSwitcherScreen)
        await pilot.press("escape")
        await pilot.pause()


def test_cli_configure_command():
    """Verify sago configure CLI command invokes setup wizard."""
    from click.testing import CliRunner

    from sago.main import cli

    runner = CliRunner()
    # Test --help on configure command
    res = runner.invoke(cli, ["configure", "--help"])
    assert res.exit_code == 0
    assert "Configure SAGO LLM provider" in res.output


def test_tui_providers_google_openai_and_anthropic(monkeypatch):
    """Exhaustive tests for direct provider client builders."""
    import sys
    from types import ModuleType

    # 1. Google Gemini
    mock_google = ModuleType("google")
    mock_genai_mod = ModuleType("google.genai")
    mock_genai_cls = MagicMock()
    mock_genai_mod.Client = mock_genai_cls
    mock_google.genai = mock_genai_mod
    monkeypatch.setitem(sys.modules, "google", mock_google)
    monkeypatch.setitem(sys.modules, "google.genai", mock_genai_mod)

    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    client, model = get_tui_client("google", "google/gemini-2.0-flash")
    assert model == "gemini-2.0-flash"

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GEMINI_API_KEY not set"):
        get_tui_client("google", "gemini-2.5-pro")

    # 2. OpenAI
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    mock_openai = MagicMock()
    monkeypatch.setattr("openai.OpenAI", mock_openai)
    client, model = get_tui_client("openai", "openai/gpt-4o")
    assert model == "gpt-4o"

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY not set"):
        get_tui_client("openai", "gpt-4o")

    # 3. OpenRouter missing key
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY not set"):
        get_tui_client("openrouter", "openrouter/free")

    # 4. Anthropic routing via OpenRouter
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-anthropic-route")
    client, model = get_tui_client("anthropic", "claude-3-7-sonnet")
    assert "anthropic/claude-3-7-sonnet" in model

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="Direct Anthropic chat requires"):
        get_tui_client("anthropic", "claude-3-7-sonnet")


def test_generate_with_provider_google_and_openai(monkeypatch):
    """Verify generate_with_provider streaming and non-streaming responses."""
    from sago.llm.tui_providers import generate_with_provider

    # Google mock
    mock_google_client = MagicMock()
    mock_google_client.models.generate_content.return_value.text = "Google non-stream text"
    mock_google_client.models.generate_content_stream.return_value = ["Google", " stream"]

    monkeypatch.setattr(
        "sago.llm.tui_providers._get_google_client",
        lambda m: (mock_google_client, "gemini-2.0-flash"),
    )

    res_google = generate_with_provider(
        "google",
        "gemini-2.0-flash",
        [{"role": "system", "content": "Be helpful"}, {"role": "user", "content": "Hi"}],
        stream=False,
    )
    assert res_google == "Google non-stream text"

    res_stream_google = generate_with_provider(
        "google",
        "gemini-2.0-flash",
        [{"role": "user", "content": "Hi"}],
        stream=True,
    )
    assert list(res_stream_google) == ["Google", " stream"]

    # OpenAI mock
    mock_openai_client = MagicMock()
    mock_resp = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "OpenAI response"
    mock_resp.choices = [mock_choice]
    mock_openai_client.chat.completions.create.return_value = mock_resp

    monkeypatch.setattr(
        "sago.llm.tui_providers._get_openai_client",
        lambda m: (mock_openai_client, "gpt-4o"),
    )

    res_openai = generate_with_provider(
        "openai",
        "gpt-4o",
        [{"role": "user", "content": "Test"}],
        stream=False,
    )
    assert res_openai == "OpenAI response"

    # Empty choices test
    mock_resp.choices = []
    res_empty = generate_with_provider(
        "openai",
        "gpt-4o",
        [{"role": "user", "content": "Test"}],
        stream=False,
    )
    assert res_empty == ""

    # Stream mode
    mock_openai_client.chat.completions.create.return_value = ["chunk1", "chunk2"]
    res_stream_openai = generate_with_provider(
        "openai",
        "gpt-4o",
        [{"role": "user", "content": "Test"}],
        stream=True,
    )
    assert list(res_stream_openai) == ["chunk1", "chunk2"]


def test_resolve_active_llm_config_fallback_branches(monkeypatch):
    """Verify fallback branches when API keys are absent."""
    # When user explicitly asks for openai, provider is honored
    cfg = resolve_active_llm_config(provider="openai")
    assert cfg["provider"] == "openai"

    # When no provider is requested and no keys exist, falls back gracefully
    monkeypatch.delenv("SAGO_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "valid-gemini-key")
    from sago.settings import save_setting

    save_setting("provider", "")

    cfg_fallback = resolve_active_llm_config()
    assert cfg_fallback["provider"] in ("google", "ollama", "lmstudio", "openrouter")

    # Specific environment resolution
    monkeypatch.setenv("SAGO_PROVIDER", "groq")
    monkeypatch.setenv("SAGO_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
    cfg2 = resolve_active_llm_config()
    assert cfg2["provider"] == "groq"
    assert cfg2["model"] == "llama-3.3-70b-versatile"


def test_resolve_active_llm_config_model_prefix_variations(monkeypatch):
    """Test explicit provider prefix extraction in resolve_active_llm_config."""
    monkeypatch.delenv("SAGO_PROVIDER", raising=False)
    monkeypatch.delenv("SAGO_MODEL", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "mock-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "mock-key")
    monkeypatch.setenv("OPENAI_API_KEY", "mock-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "mock-key")
    monkeypatch.setenv("GROQ_API_KEY", "mock-key")
    monkeypatch.setenv("MISTRAL_API_KEY", "mock-key")
    monkeypatch.setenv("TOGETHER_API_KEY", "mock-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "mock-key")

    assert resolve_active_llm_config(model="google/gemini-2.0-flash")["provider"] == "google"
    assert resolve_active_llm_config(model="anthropic/claude-3-7-sonnet")["provider"] == "anthropic"
    assert resolve_active_llm_config(model="ollama/llama3.1")["provider"] == "ollama"
    assert resolve_active_llm_config(model="deepseek/deepseek-chat")["provider"] == "deepseek"
    assert resolve_active_llm_config(model="groq/llama-3.3")["provider"] == "groq"
    assert resolve_active_llm_config(model="mistral/mistral-large")["provider"] == "mistral"
    assert resolve_active_llm_config(model="together/llama")["provider"] == "together"
    assert resolve_active_llm_config(model="openrouter/free")["provider"] == "openrouter"
    assert resolve_active_llm_config(model="openai/gpt-4o-mini")["provider"] == "openai"

    # Explicit base_url and api_key pass-through
    custom_cfg = resolve_active_llm_config(
        provider="openai",
        model="custom",
        api_key="my-key",
        base_url="https://my.proxy/v1",
    )
    assert custom_cfg["api_key"] == "my-key"
    assert custom_cfg["base_url"] == "https://my.proxy/v1"
