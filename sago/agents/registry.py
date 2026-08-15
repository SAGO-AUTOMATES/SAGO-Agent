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
    category: str = "general"
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

            # Determine category from docstring
            category = "general"
            doc = getattr(module, "__doc__", "") or ""
            if "Category:" in doc:
                category = doc.split("Category:")[1].splitlines()[0].strip()

            # Get profile from module
            profile = None
            if hasattr(module, "get_profile"):
                profile = module.get_profile()
            elif hasattr(module, "PROFILE"):
                profile = module.PROFILE

            if profile and hasattr(profile, "name"):
                final_category = getattr(profile, "category", category)
                temp = getattr(profile, "temperature", 0.7)

                # Domain-aware hyperparameter tuning when default temperature (0.7) is used
                if temp == 0.7:
                    cat_lower = final_category.lower()
                    name_lower = profile.name.lower()
                    if any(
                        k in cat_lower or k in name_lower
                        for k in (
                            "security",
                            "database",
                            "compliance",
                            "legal",
                            "finance",
                            "testing",
                            "qa",
                            "audit",
                            "crypto",
                        )
                    ):
                        temp = 0.2
                    elif any(
                        k in cat_lower or k in name_lower
                        for k in ("language", "engineering-dev", "infra", "devops", "backend")
                    ):
                        temp = 0.3
                    elif any(
                        k in cat_lower or k in name_lower
                        for k in ("architecture", "orchestration", "planning", "design")
                    ):
                        temp = 0.5

                agent = AgentDefinition(
                    name=profile.name,
                    codename=profile.codename,
                    role=profile.role,
                    description=profile.description,
                    system_prompt=profile.system_prompt,
                    skills=profile.skills,
                    tools=profile.tools,
                    category=final_category,
                    handoff_to=profile.handoff_to,
                    model_preference=getattr(profile, "model_preference", None),
                    max_iterations=getattr(profile, "max_iterations", 15),
                    temperature=temp,
                )
                AGENTS[agent.name] = agent

        except Exception as e:
            print(f"Warning: Failed to load profile {py_file.name}: {e}")


# Load profiles on module import
_load_profiles()


AGENT_ALIASES: dict[str, str] = {
    "system-architect": "architect",
    "test-runner": "tester",
    "ui-designer": "frontend-engineer",
    "python-pro": "python-engineer",
    "fullstack-dev": "backend-engineer",
    "rust-systems": "rust-engineer",
    "go-backend": "go-engineer",
    "debugger": "python-engineer",
    "security-debugger": "security-engineer",
    "code-reviewer": "reviewer",
    "security-reviewer": "security-engineer",
    "db-optimizer": "database-administrator",
    "api-designer": "api-engineer",
    "frontend-expert": "frontend-engineer",
    "tech-writer": "documentation-updater",
    "devops-engineer": "devops",
    "cloud-engineer": "cloud-architect",
    "sre-engineer": "devops",
}


def get_agent(name: str) -> AgentDefinition | None:
    """Get an agent definition by name or alias."""
    resolved_name = AGENT_ALIASES.get(name, name)
    return AGENTS.get(resolved_name)


def list_agents() -> list[dict[str, Any]]:
    """List all available agents."""
    return [
        {
            "name": a.name,
            "codename": a.codename,
            "role": a.role,
            "description": a.description,
            "skills": a.skills,
            "category": a.category,
        }
        for a in AGENTS.values()
    ]


def list_categories() -> dict[str, list[AgentDefinition]]:
    """Get all agents grouped by category."""
    cats: dict[str, list[AgentDefinition]] = {}
    for a in sorted(AGENTS.values(), key=lambda x: (x.category, x.name)):
        cats.setdefault(a.category, []).append(a)
    return cats


def get_agents_by_category(category: str) -> list[AgentDefinition]:
    """Find agents in a specific category (case-insensitive fuzzy match)."""
    target = category.lower().strip()
    return [
        a
        for a in AGENTS.values()
        if target in a.category.lower() or target in a.name.lower() or target in a.role.lower()
    ]


def get_agents_by_skill(skill: str) -> list[AgentDefinition]:
    """Find agents with a specific skill."""
    return [a for a in AGENTS.values() if skill.lower() in [s.lower() for s in a.skills]]


def get_handoff_targets(agent_name: str) -> list[AgentDefinition]:
    """Get agents that a given agent can hand off to."""
    agent = get_agent(agent_name)
    if not agent:
        return []
    targets: list[AgentDefinition] = []
    for name in agent.handoff_to:
        target_agent = get_agent(name)
        if target_agent and target_agent not in targets:
            targets.append(target_agent)
    return targets


def reload_agents() -> None:
    """Reload all agent profiles from disk."""
    AGENTS.clear()
    _load_profiles()
