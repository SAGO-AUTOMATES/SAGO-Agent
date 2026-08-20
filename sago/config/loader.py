"""Configuration loader for Sago.

Loads and validates YAML configuration files from the config directory.
Supports environment variable overrides and user-level customization.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from sago.utils.safe import log_exception
from sago.version import __version__

logger = logging.getLogger("sago.config")


def init_user_config(force: bool = False) -> None:
    """Initialize user config directory with default files if not present.

    Creates:
    - ~/.sago/config/ directory with default YAML configs
    - ~/.sago/settings.json with default preferences (if missing)

    Args:
        force: If True, overwrite existing user config files with defaults.
    """
    import json

    from sago.paths import get_config_dir, get_sago_home

    user_config_dir = get_config_dir()
    default_config_dir = Path(__file__).parent

    # Default config files to copy
    default_files = ["sago.yaml", "agents.yaml", "tools.yaml", "llm_providers.yaml"]

    for filename in default_files:
        user_file = user_config_dir / filename
        default_file = default_config_dir / filename

        if not default_file.exists():
            continue

        if user_file.exists() and not force:
            logger.debug("User config already exists: %s", user_file)
            continue

        try:
            shutil.copy2(default_file, user_file)
            logger.info("Copied default config to: %s", user_file)
        except Exception as e:
            logger.warning("Failed to copy default config %s: %s", filename, e)

    # Create default settings.json if missing
    settings_file = get_sago_home() / "settings.json"
    if not settings_file.exists() or force:
        default_settings = {
            "model": "gemini-2.5-flash",
            "provider": "google",
            "effort": "medium",
            "agent": "sago-orchestrator",
            "yolo": False,
            "show_summary": True,
            "show_action_bar": True,
            "dev_mode": False,
            "log_level": "info",
        }
        try:
            settings_file.write_text(json.dumps(default_settings, indent=2))
            logger.info("Created default settings: %s", settings_file)
        except Exception as e:
            logger.warning("Failed to create default settings: %s", e)


class ProjectConfig(BaseModel):
    """Project-level configuration."""

    name: str = "sago"
    version: str = Field(default_factory=lambda: __version__)
    environment: str = "development"
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
    dev_mode: bool = False


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


class SearchConfig(BaseModel):
    """Hybrid search configuration."""

    max_files: int = 50000
    use_embeddings: bool = False
    cache_dir: str = "~/.sago/cache/hybrid_index"


class DaemonConfig(BaseModel):
    """Daemon server configuration."""

    host: str = "127.0.0.1"
    port: int = 7654
    max_connections: int = 10


class MeshConfig(BaseModel):
    """P2P Mesh network configuration."""

    port: int = 7655
    task_timeout_seconds: int = 120


class ExecutorConfig(BaseModel):
    """Execution engine thresholds and behavior."""

    project_context_ttl: int = 300
    max_tokens: int = 32000
    circular_detection_threshold: int = 3
    auto_complete_min_tools: int = 5
    auto_complete_min_success: int = 3
    auto_complete_min_iterations: int = 4


class SagoConfig(BaseModel):
    """Root configuration model for Sago."""

    project: ProjectConfig = Field(default_factory=ProjectConfig)
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    settings: SettingsConfig = Field(default_factory=SettingsConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    llm_providers: LLMProvidersConfig = Field(default_factory=LLMProvidersConfig)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    daemon: DaemonConfig = Field(default_factory=DaemonConfig)
    mesh: MeshConfig = Field(default_factory=MeshConfig)
    executor: ExecutorConfig = Field(default_factory=ExecutorConfig)


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

    logger.info("Loading config from directory: %s", config_dir)

    # Load main config
    sago_yaml = config_dir / "sago.yaml"
    raw_config: dict[str, Any] = {}
    if sago_yaml.exists():
        size = sago_yaml.stat().st_size
        logger.info("Loading main config: %s (%d bytes)", sago_yaml, size)
        try:
            with open(sago_yaml) as f:
                raw_config = yaml.safe_load(f) or {}
            logger.info("Successfully loaded main config: %d top-level keys", len(raw_config))
        except Exception as e:
            logger.error("Failed to load main config %s: %s", sago_yaml, e)
            raise
    else:
        logger.info("Main config not found: %s, using defaults", sago_yaml)

    # Load agents config
    agents_yaml = config_dir / "agents.yaml"
    if agents_yaml.exists():
        size = agents_yaml.stat().st_size
        logger.info("Loading agents config: %s (%d bytes)", agents_yaml, size)
        try:
            with open(agents_yaml) as f:
                agents_data = yaml.safe_load(f) or {}
            raw_config["agents"] = _deep_merge(raw_config.get("agents", {}), agents_data)
            logger.info("Successfully loaded agents config")
        except Exception as e:
            logger.error("Failed to load agents config %s: %s", agents_yaml, e)
            raise
    else:
        logger.info("Agents config not found: %s, using defaults", agents_yaml)

    # Load tools config
    tools_yaml = config_dir / "tools.yaml"
    if tools_yaml.exists():
        size = tools_yaml.stat().st_size
        logger.info("Loading tools config: %s (%d bytes)", tools_yaml, size)
        try:
            with open(tools_yaml) as f:
                tools_data = yaml.safe_load(f) or {}
            raw_config["tools"] = _deep_merge(raw_config.get("tools", {}), tools_data)
            logger.info("Successfully loaded tools config")
        except Exception as e:
            logger.error("Failed to load tools config %s: %s", tools_yaml, e)
            raise
    else:
        logger.info("Tools config not found: %s, using defaults", tools_yaml)

    # Load LLM providers config
    llm_yaml = config_dir / "llm_providers.yaml"
    if llm_yaml.exists():
        size = llm_yaml.stat().st_size
        logger.info("Loading LLM providers config: %s (%d bytes)", llm_yaml, size)
        try:
            with open(llm_yaml) as f:
                llm_data = yaml.safe_load(f) or {}
            raw_config["llm_providers"] = _deep_merge(raw_config.get("llm_providers", {}), llm_data)
            logger.info("Successfully loaded LLM providers config")
        except Exception as e:
            logger.error("Failed to load LLM providers config %s: %s", llm_yaml, e)
            raise
    else:
        logger.info("LLM providers config not found: %s, using defaults", llm_yaml)

    # Merge user config if provided
    if user_config_path and user_config_path.exists():
        if user_config_path.is_dir():
            # User config is a directory - load individual YAML files
            logger.info("Loading user config from directory: %s", user_config_path)
            for yaml_file in sorted(user_config_path.glob("*.yaml")):
                try:
                    logger.info("Loading user config file: %s", yaml_file.name)
                    with open(yaml_file) as f:
                        user_data = yaml.safe_load(f) or {}
                    raw_config = _deep_merge(raw_config, user_data)
                except Exception as e:
                    logger.error("Failed to load user config %s: %s", yaml_file, e)
                    raise
        else:
            # User config is a single file
            size = user_config_path.stat().st_size
            logger.info("Merging user config: %s (%d bytes)", user_config_path, size)
            try:
                with open(user_config_path) as f:
                    user_data = yaml.safe_load(f) or {}
                raw_config = _deep_merge(raw_config, user_data)
                logger.info("Successfully merged user config")
            except Exception as e:
                logger.error("Failed to load user config %s: %s", user_config_path, e)
                raise
    elif user_config_path:
        logger.debug("User config path provided but does not exist: %s", user_config_path)

    # Expand paths in settings
    if "settings" in raw_config:
        settings = raw_config["settings"]
        for key in ("log_directory", "session_directory"):
            if key in settings:
                settings[key] = str(_expand_path(settings[key]))

    try:
        config = SagoConfig(**raw_config)
        logger.info("Config validation succeeded")
        return config
    except Exception as e:
        logger.error("Config validation failed: %s", e)
        raise


_config_cache: SagoConfig | None = None
_config_cache_key: str | None = None
_config_lock = threading.Lock()


def get_config() -> SagoConfig:
    """Get the global Sago configuration.

    Loads from default locations:
    1. sago/config/ (bundled defaults)
    2. ~/.sago/config/ directory (user overrides - individual YAML files)
    3. ~/.sago/config.yaml (single file user overrides)
    4. .sago.yaml in current directory (project overrides)

    Results are cached. Call ``invalidate_config_cache()`` to force a reload.

    Returns:
        Validated SagoConfig instance.
    """
    global _config_cache, _config_cache_key

    # Default configs from package directory
    config_dir = Path(__file__).parent

    # User configs: check ~/.sago/config/ directory first, then single file
    user_config_dir = Path.home() / ".sago" / "config"
    user_config_file = Path.home() / ".sago" / "config.yaml"
    project_config = Path.cwd() / ".sago.yaml"

    # Initialize user config if it doesn't exist
    if not user_config_dir.is_dir() and not user_config_file.exists():
        try:
            init_user_config()
        except Exception as e:
            logger.debug("Failed to initialize user config: %s", e)

    # Determine which user config to use
    if project_config.exists():
        user_path = project_config
    elif user_config_dir.is_dir():
        user_path = user_config_dir
    elif user_config_file.exists():
        user_path = user_config_file
    else:
        user_path = None

    cache_key = f"{config_dir}:{user_path}"
    with _config_lock:
        if _config_cache is not None and _config_cache_key == cache_key:
            logger.debug("Config cache hit (key=%s)", cache_key)
            return _config_cache

        logger.debug("Config cache miss (key=%s), loading config", cache_key)
        _config_cache = load_config(config_dir=config_dir, user_config_path=user_path)
        _config_cache_key = cache_key
        return _config_cache


def invalidate_config_cache() -> None:
    """Invalidate the cached configuration, forcing reload on next get_config()."""
    global _config_cache, _config_cache_key
    with _config_lock:
        logger.debug("Invalidating config cache")
        _config_cache = None
        _config_cache_key = None


def is_dev_mode_enabled() -> bool:
    """Check if developer mode is enabled via ~/.sago/ config or environment.

    Checks:
    1. Environment variable SAGO_DEV_MODE or DEV_MODE (1, true, yes, on)
    2. ~/.sago/config.json or ~/.sago/settings.json or ~/.sago/config.yaml or ~/.sago/config
    3. Project-level .sago/config.json or .sago.yaml
    4. SagoConfig.settings.dev_mode
    """
    env_val = os.environ.get("SAGO_DEV_MODE") or os.environ.get("DEV_MODE")
    if env_val is not None:
        enabled = env_val.strip().lower() in ("1", "true", "yes", "on")
        logger.info(
            "Dev mode from env var: %s -> %s",
            "SAGO_DEV_MODE" if os.environ.get("SAGO_DEV_MODE") else "DEV_MODE",
            enabled,
        )
        return enabled

    # Inspect ~/.sago/ and workspace configs directly
    candidates = [
        Path.home() / ".sago" / "config.json",
        Path.home() / ".sago" / "settings.json",
        Path.home() / ".sago" / "config.yaml",
        Path.home() / ".sago" / "config",
        Path.cwd() / ".sago" / "config.json",
        Path.cwd() / ".sago" / "settings.json",
        Path.cwd() / ".sago.yaml",
    ]

    for p in candidates:
        if p.exists() and p.is_file():
            try:
                txt = p.read_text(encoding="utf-8").strip()
                if not txt:
                    continue
                if p.suffix == ".json" or txt.startswith("{"):
                    import json

                    data = json.loads(txt)
                else:
                    data = yaml.safe_load(txt) or {}

                if isinstance(data, dict):
                    if data.get("dev_mode") is True:
                        logger.info("Dev mode enabled via config file: %s", p)
                        return True
                    if (
                        isinstance(data.get("settings"), dict)
                        and data["settings"].get("dev_mode") is True
                    ):
                        logger.info("Dev mode enabled via settings in: %s", p)
                        return True
            except Exception as e:
                log_exception(e, "parsing dev_mode config file")

    try:
        cfg = get_config()
        enabled = bool(cfg.settings.dev_mode)
        logger.info("Dev mode from SagoConfig.settings.dev_mode: %s", enabled)
        return enabled
    except Exception as e:
        log_exception(e, "getting config for dev_mode check")
        return False


def set_dev_mode(enabled: bool, persist: bool = True) -> None:
    """Enable or disable developer mode in ~/.sago/settings.json."""
    logger.info("Setting dev_mode=%s (persist=%s)", enabled, persist)
    if persist:
        import json

        cfg_dir = Path.home() / ".sago"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        settings_file = cfg_dir / "settings.json"
        data: dict[str, Any] = {}
        if settings_file.exists():
            try:
                data = json.loads(settings_file.read_text(encoding="utf-8"))
            except Exception as e:
                log_exception(e, "reading existing settings file")
                data = {}
        data["dev_mode"] = enabled
        settings_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        invalidate_config_cache()
