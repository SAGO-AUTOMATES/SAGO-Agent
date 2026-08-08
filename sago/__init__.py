"""Sago - Sophisticated Multi-Agent Orchestration System.

A CrewAI-based multi-agent system with infinite tool support,
cross-platform compatibility, and a master orchestrator named Sago.
"""

__version__ = "0.1.0"
__author__ = "Sago Contributors"

from sago.main import main
from sago.database import init as init_db

__all__ = ["main", "init_db"]
