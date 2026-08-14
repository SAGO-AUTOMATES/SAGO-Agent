"""Configuration loader for Sago.

Loads and validates YAML configuration files from the config directory.
Supports environment variable overrides and user-level customization.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ProjectConfig(BaseModel):
    """Project-level configuration."""

    name: str = "sago"
    version: str = "0.1.5"
    description: str = "Sophisticated Multi-Agent Orchestration System"


class OrchestratorConfig(BaseModel):
    """Master orchestrator configuration."""

    name: str = "Sago"
    description: str = "Master orchestrator that routes tasks to specialist agents"
    model: str | None = None
    max_iterations: int = 25
    verbose: bool = True
    memory: bool = True
    planning: bool = True


class SettingsConfig(BaseModel):
    """Global settings."""

    auto_detect_os: bool = True
    preferred_shell: str | None = None
    max_concurrent_tools: int = 5
    tool_timeout_seconds: int = 300
    retry_on_failure: bool = True
    max_retries: int = 3
    log_level: str = "INFO"
    log_to_file: bool = True
    log_directory: str = "~/.sago/logs"
    session_persistence: bool = True
    session_directory: str = "~/.sago/sessions"
    max_session_history: int = 100
    verbose_output: bool = False
    color_output: bool = True
    markdown_output: bool = True


class AgentOverride(BaseModel):
    """Per-agent configuration override."""

    model: str | None = None
    max_iterations: int | None = None
    verbose: bool | None = None


class AgentsConfig(BaseModel):
    """Agent selection configuration."""

    enabled: list[str] = Field(
        default_factory=lambda: [
            "sago",
            "coder",
            "debugger",
            "architect",
            "devops",
            "reviewer",
            "researcher",
            "planner",
        ]
    )
    overrides: dict[str, AgentOverride] = Field(default_factory=dict)


class ToolCategoryConfig(BaseModel):
    """Tool category enable/disable flags."""

    file: bool = True
    shell: bool = True
    ssh: bool = True
    session: bool = True
    coding: bool = True
    network: bool = True
    admin: bool = True
    system: bool = True


class ToolsConfig(BaseModel):
    """Tools configuration."""

    categories: ToolCategoryConfig = Field(default_factory=ToolCategoryConfig)


class LLMProviderConfig(BaseModel):
    """Individual LLM provider configuration."""

    enabled: bool = False
    api_key_env: str | None = None
    base_url: str | None = None
    model: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7


class LLMProvidersConfig(BaseModel):
    """LLM providers configuration."""

    default: str = "gemini"
    providers: dict[str, LLMProviderConfig] = Field(default_factory=dict)


class RoutingConfig(BaseModel):
    """Task routing configuration."""

    triggers: dict[str, list[str]] = Field(default_factory=dict)


class SagoConfig(BaseModel):
    """Root configuration model for Sago."""

    project: ProjectConfig = Field(default_factory=ProjectConfig)
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    settings: SettingsConfig = Field(default_factory=SettingsConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    llm_providers: LLMProvidersConfig = Field(default_factory=LLMProvidersConfig)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)


def _expand_path(path_str: str) -> Path:
    """Expand ~ and environment variables in a path string."""
    expanded = os.path.expanduser(path_str)
    expanded = os.path.expandvars(expanded)
    return Path(expanded).resolve()


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries, with override taking precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(
    config_dir: Path | None = None,
    user_config_path: Path | None = None,
) -> SagoConfig:
    """Load Sago configuration from YAML files.

    Args:
        config_dir: Directory containing default config files.
                   Defaults to sago/config/ relative to this file.
        user_config_path: Optional user-level config to merge on top.

    Returns:
        Validated SagoConfig instance.
    """
    if config_dir is None:
        config_dir = Path(__file__).parent

    # Load main config
    sago_yaml = config_dir / "sago.yaml"
    raw_config: dict[str, Any] = {}
    if sago_yaml.exists():
        with open(sago_yaml) as f:
            raw_config = yaml.safe_load(f) or {}

    # Load agents config
    agents_yaml = config_dir / "agents.yaml"
    if agents_yaml.exists():
        with open(agents_yaml) as f:
            agents_data = yaml.safe_load(f) or {}
            raw_config["agents"] = _deep_merge(raw_config.get("agents", {}), agents_data)

    # Load tools config
    tools_yaml = config_dir / "tools.yaml"
    if tools_yaml.exists():
        with open(tools_yaml) as f:
            tools_data = yaml.safe_load(f) or {}
            raw_config["tools"] = _deep_merge(raw_config.get("tools", {}), tools_data)

    # Load LLM providers config
    llm_yaml = config_dir / "llm_providers.yaml"
    if llm_yaml.exists():
        with open(llm_yaml) as f:
            llm_data = yaml.safe_load(f) or {}
            raw_config["llm_providers"] = _deep_merge(raw_config.get("llm_providers", {}), llm_data)

    # Merge user config if provided
    if user_config_path and user_config_path.exists():
        with open(user_config_path) as f:
            user_data = yaml.safe_load(f) or {}
            raw_config = _deep_merge(raw_config, user_data)

    # Expand paths in settings
    if "settings" in raw_config:
        settings = raw_config["settings"]
        for key in ("log_directory", "session_directory"):
            if key in settings:
                settings[key] = str(_expand_path(settings[key]))

    return SagoConfig(**raw_config)


_config_cache: SagoConfig | None = None
_config_cache_key: str | None = None


def get_config() -> SagoConfig:
    """Get the global Sago configuration.

    Loads from default locations:
    1. sago/config/ (bundled defaults)
    2. ~/.sago/config.yaml (user overrides)
    3. .sago.yaml in current directory (project overrides)

    Results are cached. Call ``invalidate_config_cache()`` to force a reload.

    Returns:
        Validated SagoConfig instance.
    """
    global _config_cache, _config_cache_key

    config_dir = Path(__file__).parent
    user_config = Path.home() / ".sago" / "config.yaml"
    project_config = Path.cwd() / ".sago.yaml"
    user_path = project_config if project_config.exists() else user_config

    cache_key = f"{config_dir}:{user_path}"
    if _config_cache is not None and _config_cache_key == cache_key:
        return _config_cache

    _config_cache = load_config(config_dir=config_dir, user_config_path=user_path)
    _config_cache_key = cache_key
    return _config_cache


def invalidate_config_cache() -> None:
    """Force config to be reloaded on next get_config() call."""
    global _config_cache, _config_cache_key
    _config_cache = None
    _config_cache_key = None
