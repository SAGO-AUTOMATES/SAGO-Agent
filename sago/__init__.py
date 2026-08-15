"""Sago - Sophisticated Multi-Agent Orchestration System.

A CrewAI-based multi-agent system with infinite tool support,
cross-platform compatibility, and a master orchestrator named Sago.
"""

try:
    import importlib.metadata

    __version__ = importlib.metadata.version("sago-agent")
except Exception:
    __version__ = "0.1.6"

__author__ = "Sago Contributors"

from sago.database import init as init_db
from sago.main import main

__all__ = ["main", "init_db", "__version__"]
