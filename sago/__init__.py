"""Sago - Sophisticated Multi-Agent Orchestration System.

A CrewAI-based multi-agent system with infinite tool support,
cross-platform compatibility, and a master orchestrator named Sago.
"""

from sago.version import __version__

__author__ = "Sago Contributors"

from sago.database import init as init_db
from sago.main import main

__all__ = ["main", "init_db", "__version__"]
