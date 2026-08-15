"""Unit tests for Developer Mode Telemetry during multi-agent delegation."""

from __future__ import annotations

import pytest

from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer
from sago.tui.app import SagoApp


@pytest.mark.anyio
async def test_delegation_records_in_dev_tracer(monkeypatch):
    """Verify that agent delegation records events into DevTracer."""
    tracer = get_dev_tracer()
    tracer.set_enabled(True)
    tracer.clear()

    app = SagoApp()
    async with app.run_test() as pilot:
        # Mock spawn_agent tool run and provider API key
        from sago.tools.file.spawn_agent import SpawnAgentTool

        monkeypatch.setattr(
            SpawnAgentTool,
            "run",
            lambda self, task, agent_name, **kw: f"Completed delegation to {agent_name}",
        )
        monkeypatch.setattr(
            SagoApp,
            "_get_provider_api_key",
            lambda self: "mock-test-key",
        )

        import anyio

        app._process_delegation("python-engineer", "Build unit tests for auth")
        await anyio.sleep(0.3)
        await pilot.pause()

        events = tracer.get_events()
        assert len(events) >= 2

        # Check AGENT_ROUTING and FUNCTION_RETURN events
        routing_events = [e for e in events if e.event_type == TraceEventType.AGENT_ROUTING]
        assert len(routing_events) >= 1
        assert "python-engineer" in routing_events[0].action

        return_events = [e for e in events if e.event_type == TraceEventType.FUNCTION_RETURN]
        assert len(return_events) >= 1
        assert return_events[0].source == "agent.python-engineer"
