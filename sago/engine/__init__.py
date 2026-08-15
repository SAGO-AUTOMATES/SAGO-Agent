"""SAGO Execution Engine."""

from __future__ import annotations

from sago.engine.async_executor import AsyncAgentExecutor, execute_parallel_tasks
from sago.engine.checkpoint import CheckpointManager
from sago.engine.context_assembler import ContextAssembler, get_context_assembler
from sago.engine.simple_executor import execute_agent_task
from sago.engine.verifier import ProjectVerifier, get_project_verifier

__all__ = [
    "execute_agent_task",
    "AsyncAgentExecutor",
    "execute_parallel_tasks",
    "ContextAssembler",
    "get_context_assembler",
    "CheckpointManager",
    "ProjectVerifier",
    "get_project_verifier",
]
