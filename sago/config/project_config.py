"""Project Configuration Schema

Defines the config.sago.json schema for per-project customization.
Users can enable/disable agents, tools, modify prompts, and configure settings.
"""

import json
from pathlib import Path
from typing import Any

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

    config = DEFAULT_CONFIG.copy()
    config["project"]["name"] = project_name or project_path.name
    config["project"]["languages"] = languages or []
    config["project"]["frameworks"] = frameworks or []
    config["permissions"]["allow_ssh"] = enable_ssh

    # Add agent configs
    profiles = load_all_profiles()
    for agent_name in profiles:
        agent_config = AGENT_CONFIG_TEMPLATE.copy()
        agent_config["enabled"] = enable_all_agents
        config["agents"][agent_name] = agent_config

    # Write config file
    config_path = project_path / "config.sago.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2, default=str)

    return config_path


def load_config(project_path: Path) -> dict[str, Any]:
    """Load config.sago.json from the project directory.

    Falls back to parent directories if not found in current directory.
    """
    current = project_path.resolve()

    while current != current.parent:
        config_path = current / "config.sago.json"
        if config_path.exists():
            with open(config_path) as f:
                return json.load(f)
        current = current.parent

    # Check home directory as final fallback
    home_config = Path.home() / ".sago" / "config.sago.json"
    if home_config.exists():
        with open(home_config) as f:
            return json.load(f)

    # Return default config
    return DEFAULT_CONFIG.copy()


def get_agent_config(config: dict[str, Any], agent_name: str) -> dict[str, Any]:
    """Get the effective configuration for an agent."""
    base = AGENT_CONFIG_TEMPLATE.copy()
    override = config.get("agents", {}).get(agent_name, {})
    base.update(override)
    return base


def is_agent_enabled(config: dict[str, Any], agent_name: str) -> bool:
    """Check if an agent is enabled in the config."""
    agent_config = get_agent_config(config, agent_name)
    return agent_config.get("enabled", True)


def is_tool_enabled(config: dict[str, Any], tool_name: str) -> bool:
    """Check if a tool is enabled in the config."""
    disabled_tools = config.get("tools", {}).get("disabled", [])
    return tool_name not in disabled_tools


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
    except PermissionError:
        pass

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
        except Exception:
            pass

    if (project_path / "pyproject.toml").exists():
        try:
            pyproject = (project_path / "pyproject.toml").read_text().lower()
            if "django" in pyproject:
                frameworks.append("django")
            if "fastapi" in pyproject:
                frameworks.append("fastapi")
            if "flask" in pyproject:
                frameworks.append("flask")
        except Exception:
            pass

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
        except Exception:
            pass

    # Go frameworks
    if (project_path / "go.mod").exists():
        try:
            gomod = (project_path / "go.mod").read_text()
            if "gin-gonic" in gomod:
                frameworks.append("gin")
            if "labstack/echo" in gomod:
                frameworks.append("echo")
        except Exception:
            pass

    return sorted(set(frameworks))
