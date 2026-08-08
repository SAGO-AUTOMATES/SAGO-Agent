"""Base Agent class for Sago agents.

All agents inherit from BaseAgent and are registered with CrewAI.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    """Configuration for an agent."""

    name: str
    role: str
    description: str
    goal: str
    backstory: str
    tools: list[str] = Field(default_factory=list)
    model: str | None = None
    max_iterations: int = 15
    verbose: bool = True
    allow_delegation: bool = False
    priority: int = 5
