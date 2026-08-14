"""Tests for HierarchicalMemoryPyramid and state delta handoffs."""

from __future__ import annotations

from sago.agents.handoff import HandoffContext
from sago.memory.compaction import HierarchicalMemoryPyramid


def test_hierarchical_memory_pyramid() -> None:
    pyramid = HierarchicalMemoryPyramid()
    pyramid.record_turn(
        "user", "Goal: Build a high-performance REST API with FastAPI and PostgreSQL."
    )
    pyramid.record_turn("assistant", "We decided to use async SQLAlchemy for database access.")
    pyramid.record_file_mod("app/main.py")
    pyramid.record_file_mod("app/models.py")

    assert len(pyramid.architectural_goals) > 0
    assert len(pyramid.architectural_decisions) > 0
    assert len(pyramid.modified_files) == 2

    context = pyramid.assemble_compact_pyramid()
    assert len(context) >= 3
    assert "[ARCHITECTURAL MEMORY PYRAMID - TIER 1]" in context[0]["content"]
    assert "[WORKING DELTA - TIER 2]" in context[1]["content"]


def test_handoff_context_state_delta() -> None:
    ctx = HandoffContext(
        original_task="Migrate database to PostgreSQL and run tests",
        completed_agents=["system-architect"],
        files_created=["alembic/env.py"],
        errors=[],
        shared_state={"db_engine": "asyncpg"},
    )
    delta = ctx.to_state_delta()
    assert delta["task_intent"] == "Migrate database to PostgreSQL and run tests"
    assert delta["chain"] == ["system-architect"]
    assert delta["files_touched"] == ["alembic/env.py"]
    assert "db_engine" in delta["shared_keys"]

    prompt = ctx.get_compact_handoff_prompt("db-engineer")
    assert "[AGENT HANDOFF DELTA -> DB-ENGINEER]" in prompt
