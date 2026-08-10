"""Specialist Agent Definitions for Sago.

Loads agent profiles from individual .py files in agents/profiles/.
Each profile file exports a get_profile() function returning an AgentProfile.

For customization:
- Edit profiles in agents/profiles/ to modify default prompts
- Use config.sago.json to enable/disable agents per project
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AgentDefinition:
    """Definition of a specialist agent."""

    name: str
    codename: str
    role: str
    description: str
    system_prompt: str
    skills: list[str]
    tools: list[str]
    handoff_to: list[str] = field(default_factory=list)
    model_preference: str | None = None
    max_iterations: int = 15
    temperature: float = 0.7


# ============================================================================
# LOAD AGENTS FROM PROFILE FILES
# ============================================================================

AGENTS: dict[str, AgentDefinition] = {}


def _load_profiles() -> None:
    """Load all agent profiles from the profiles directory."""
    profiles_dir = Path(__file__).parent / "profiles"

    if not profiles_dir.exists():
        return

    for py_file in sorted(profiles_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue

        try:
            from importlib.util import module_from_spec, spec_from_file_location

            module_name = f"sago.agents.profiles.{py_file.stem}"
            spec = spec_from_file_location(module_name, py_file)

            if spec is None or spec.loader is None:
                continue

            module = module_from_spec(spec)
            spec.loader.exec_module(module)

            # Get profile from module
            profile = None
            if hasattr(module, "get_profile"):
                profile = module.get_profile()
            elif hasattr(module, "PROFILE"):
                profile = module.PROFILE

            if profile and hasattr(profile, "name"):
                # Convert to AgentDefinition
                agent = AgentDefinition(
                    name=profile.name,
                    codename=profile.codename,
                    role=profile.role,
                    description=profile.description,
                    system_prompt=profile.system_prompt,
                    skills=profile.skills,
                    tools=profile.tools,
                    handoff_to=profile.handoff_to,
                    model_preference=getattr(profile, "model_preference", None),
                    max_iterations=getattr(profile, "max_iterations", 15),
                    temperature=getattr(profile, "temperature", 0.7),
                )
                AGENTS[agent.name] = agent

        except Exception as e:
            print(f"Warning: Failed to load profile {py_file.name}: {e}")


# Load profiles on module import
_load_profiles()


def get_agent(name: str) -> AgentDefinition | None:
    """Get an agent definition by name."""
    return AGENTS.get(name)


def list_agents() -> list[dict[str, Any]]:
    """List all available agents."""
    return [
        {
            "name": a.name,
            "codename": a.codename,
            "role": a.role,
            "description": a.description,
            "skills": a.skills,
        }
        for a in AGENTS.values()
    ]


def get_agents_by_skill(skill: str) -> list[AgentDefinition]:
    """Find agents with a specific skill."""
    return [a for a in AGENTS.values() if skill.lower() in [s.lower() for s in a.skills]]


def get_handoff_targets(agent_name: str) -> list[AgentDefinition]:
    """Get agents that a given agent can hand off to."""
    agent = AGENTS.get(agent_name)
    if not agent:
        return []
    return [AGENTS[name] for name in agent.handoff_to if name in AGENTS]


def reload_agents() -> None:
    """Reload all agent profiles from disk."""
    AGENTS.clear()
    _load_profiles()
