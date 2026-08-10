"""Agents module for Sago.

Provides specialist agent definitions, spawning, and orchestration.
"""

from sago.agents.registry import (
    AGENTS,
    AgentDefinition,
    get_agent,
    get_agents_by_skill,
    get_handoff_targets,
    list_agents,
)
from sago.agents.spawner import AgentSpawner

__all__ = [
    "AgentDefinition",
    "AgentSpawner",
    "AGENTS",
    "get_agent",
    "get_agents_by_skill",
    "get_handoff_targets",
    "list_agents",
]
