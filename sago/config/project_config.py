"""Project Configuration Schema

Defines the config.sago.json schema for per-project customization.
Users can enable/disable agents, tools, modify prompts, and configure settings.
"""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

logger = logging.getLogger(__name__)

# Default configuration template
DEFAULT_CONFIG: dict[str, Any] = {
    "version": "1.0.0",
    "project": {
        "name": "",
        "description": "",
        "languages": [],
        "frameworks": [],
    },
    "agents": {
        # All agents enabled by default
        # Users can override individual agent settings
    },
    "tools": {
        # All tools enabled by default
        # Users can disable specific tools
    },
    "orchestrator": {
        "default_provider": "gemini",
        "default_model": None,
        "max_iterations": 15,
        "temperature": 0.7,
        "auto_route": True,
    },
    "permissions": {
        "allow_file_write": True,
        "allow_shell_execute": True,
        "allow_ssh": False,
        "allowed_paths": [],
        "blocked_paths": ["/etc", "/sys", "/proc"],
    },
    "features": {
        "tui_enabled": True,
        "session_history": True,
        "auto_save": True,
        "verbose_logging": False,
    },
}

# Agent configuration template (per-agent overrides)
AGENT_CONFIG_TEMPLATE: dict[str, Any] = {
    "enabled": True,
    "system_prompt_override": None,  # None = use default
    "tools": None,  # None = use default tools
    "tools_add": [],  # Additional tools to add
    "tools_remove": [],  # Tools to remove from defaults
    "handoff_to": None,  # None = use default handoffs
    "model_preference": None,
    "max_iterations": None,
    "temperature": None,
    "custom_skills": [],  # Additional skills
}


class _ProjectSection(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str = ""
    description: str = ""
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)


class _AgentSection(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = True
    system_prompt_override: str | None = None
    tools: list[str] | None = None
    tools_add: list[str] = Field(default_factory=list)
    tools_remove: list[str] = Field(default_factory=list)
    handoff_to: str | None = None
    model_preference: str | None = None
    max_iterations: int | None = None
    temperature: float | None = None
    custom_skills: list[str] = Field(default_factory=list)


class _OrchestratorSection(BaseModel):
    model_config = ConfigDict(extra="allow")
    default_provider: str = "gemini"
    default_model: str | None = None
    max_iterations: int = Field(default=15, ge=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    auto_route: bool = True


class _PermissionsSection(BaseModel):
    model_config = ConfigDict(extra="allow")
    allow_file_write: bool = True
    allow_shell_execute: bool = True
    allow_ssh: bool = False
    allowed_paths: list[str] = Field(default_factory=list)
    blocked_paths: list[str] = Field(default_factory=list)


class _FeaturesSection(BaseModel):
    model_config = ConfigDict(extra="allow")
    tui_enabled: bool = True
    session_history: bool = True
    auto_save: bool = True
    verbose_logging: bool = False


class ProjectConfig(BaseModel):
    """Validated representation of a config.sago.json document.

    Missing fields fall back to sane defaults (backward compatible); only
    structurally malformed documents (e.g. wrong types, out-of-range values,
    or a non-object root) fail validation with a clear error.
    """

    model_config = ConfigDict(extra="allow")
    version: str = "1.0.0"
    project: _ProjectSection = Field(default_factory=_ProjectSection)
    agents: dict[str, _AgentSection] = Field(default_factory=dict)
    tools: dict[str, Any] = Field(default_factory=dict)
    orchestrator: _OrchestratorSection = Field(default_factory=_OrchestratorSection)
    permissions: _PermissionsSection = Field(default_factory=_PermissionsSection)
    features: _FeaturesSection = Field(default_factory=_FeaturesSection)


def _validate_config(raw: Any, source: Path) -> dict[str, Any]:
    """Validate a decoded config document, raising ValueError on failure."""
    try:
        model = ProjectConfig.model_validate(raw)
    except ValidationError as exc:
        logger.error("Invalid project config in %s", source)
        raise ValueError(f"Invalid project config in {source}: {exc}") from exc
    return model.model_dump()


def create_config_file(
    project_path: Path,
    project_name: str = "",
    languages: list[str] | None = None,
    frameworks: list[str] | None = None,
    enable_all_agents: bool = True,
    enable_ssh: bool = False,
) -> Path:
    """Create a config.sago.json file in the project directory.

    Args:
        project_path: Path to the project root
        project_name: Name of the project
        languages: Detected programming languages
        frameworks: Detected frameworks
        enable_all_agents: Whether all agents start enabled
        enable_ssh: Whether SSH tools are enabled

    Returns:
        Path to the created config file
    """
    from sago.agents.loader import load_all_profiles

    config = copy.deepcopy(DEFAULT_CONFIG)
    config["project"]["name"] = project_name or project_path.name
    config["project"]["languages"] = languages or []
    config["project"]["frameworks"] = frameworks or []
    config["permissions"]["allow_ssh"] = enable_ssh

    # Add agent configs
    profiles = load_all_profiles()
    for agent_name in profiles:
        agent_config = copy.deepcopy(AGENT_CONFIG_TEMPLATE)
        agent_config["enabled"] = enable_all_agents
        config["agents"][agent_name] = agent_config

    # Validate before writing so a broken template can never be persisted.
    _validate_config(config, project_path / "config.sago.json")

    # Write config file
    config_path = project_path / "config.sago.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    return config_path


def load_config(project_path: Path) -> dict[str, Any]:
    """Load config.sago.json from the project directory.

    Falls back to parent directories, then home, and finally the built-in
    defaults when no file exists. A present-but-malformed file raises a clear
    ValueError instead of silently returning defaults.
    """
    current = project_path.resolve()

    while current != current.parent:
        config_path = current / "config.sago.json"
        if config_path.exists():
            try:
                raw = json.loads(config_path.read_text())
            except json.JSONDecodeError as exc:
                logger.error("Failed to parse config %s: %s", config_path, exc)
                raise ValueError(f"Malformed project config JSON in {config_path}: {exc}") from exc
            return _validate_config(raw, config_path)
        current = current.parent

    # Check home directory as final fallback
    from sago.paths import get_sago_home

    home_config = get_sago_home() / "config.sago.json"
    if home_config.exists():
        try:
            raw = json.loads(home_config.read_text())
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse config %s: %s", home_config, exc)
            raise ValueError(f"Malformed project config JSON in {home_config}: {exc}") from exc
        return _validate_config(raw, home_config)

    # Return default config
    return copy.deepcopy(DEFAULT_CONFIG)


def detect_project_languages(project_path: Path) -> list[str]:
    """Auto-detect project languages based on file extensions."""
    language_extensions = {
        "python": [".py", ".pyi"],
        "javascript": [".js", ".jsx", ".mjs"],
        "typescript": [".ts", ".tsx"],
        "rust": [".rs"],
        "go": [".go"],
        "java": [".java"],
        "c++": [".cpp", ".cc", ".cxx", ".h", ".hpp"],
        "c": [".c", ".h"],
        "ruby": [".rb"],
        "php": [".php"],
        "swift": [".swift"],
        "kotlin": [".kt", ".kts"],
        "shell": [".sh", ".bash", ".zsh"],
    }

    detected = set()
    max_files = 1000
    count = 0

    try:
        for ext_files in project_path.rglob("*"):
            if count >= max_files:
                break
            count += 1

            if ext_files.is_file():
                for lang, extensions in language_extensions.items():
                    if ext_files.suffix in extensions:
                        detected.add(lang)
    except PermissionError as e:
        logger.warning("Permission denied walking project directory %s: %s", project_path, e)

    return sorted(detected)


def detect_project_frameworks(project_path: Path) -> list[str]:
    """Auto-detect frameworks based on config files."""
    frameworks = []

    # Python frameworks
    if (project_path / "requirements.txt").exists():
        try:
            reqs = (project_path / "requirements.txt").read_text().lower()
            if "django" in reqs:
                frameworks.append("django")
            if "fastapi" in reqs:
                frameworks.append("fastapi")
            if "flask" in reqs:
                frameworks.append("flask")
        except Exception as e:
            logger.warning("Failed to read requirements.txt for framework detection: %s", e)

    if (project_path / "pyproject.toml").exists():
        try:
            pyproject = (project_path / "pyproject.toml").read_text().lower()
            if "django" in pyproject:
                frameworks.append("django")
            if "fastapi" in pyproject:
                frameworks.append("fastapi")
            if "flask" in pyproject:
                frameworks.append("flask")
        except Exception as e:
            logger.warning("Failed to read pyproject.toml for framework detection: %s", e)

    # JavaScript/TypeScript frameworks
    if (project_path / "package.json").exists():
        try:
            pkg = json.loads((project_path / "package.json").read_text())
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "next" in deps:
                frameworks.append("nextjs")
            if "nuxt" in deps:
                frameworks.append("nuxt")
            if "react" in deps:
                frameworks.append("react")
            if "vue" in deps:
                frameworks.append("vue")
            if "@angular/core" in deps:
                frameworks.append("angular")
            if "svelte" in deps:
                frameworks.append("svelte")
            if "express" in deps:
                frameworks.append("express")
            if "fastify" in deps:
                frameworks.append("fastify")
        except Exception as e:
            logger.warning("Failed to read/parse package.json for framework detection: %s", e)

    # Go frameworks
    if (project_path / "go.mod").exists():
        try:
            gomod = (project_path / "go.mod").read_text()
            if "gin-gonic" in gomod:
                frameworks.append("gin")
            if "labstack/echo" in gomod:
                frameworks.append("echo")
        except Exception as e:
            logger.warning("Failed to read go.mod for framework detection: %s", e)

    return sorted(set(frameworks))
