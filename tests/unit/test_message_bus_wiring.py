"""Unit tests for the orchestrator message bus and sync publisher."""

from __future__ import annotations

import asyncio


class TestMessageBus:
    """Core bus mechanics."""

    def test_register_creates_queue(self) -> None:
        from sago.orchestrator.message_bus import MessageBus

        bus = MessageBus()
        assert bus.pending("agent-x") == 0
        bus.register("agent-x")
        assert bus.pending("agent-x") == 0

    def test_send_receive_roundtrip(self) -> None:
        from sago.orchestrator.message_bus import AgentMessage, MessageBus

        bus = MessageBus()

        async def scenario() -> None:
            await bus.send(AgentMessage(sender="a", recipient="b", content="hello"))
            msg = await bus.receive("b", timeout=0.5)
            assert msg is not None
            assert msg.sender == "a"
            assert msg.content == "hello"

        asyncio.run(scenario())

    def test_receive_timeout_returns_none(self) -> None:
        from sago.orchestrator.message_bus import MessageBus

        bus = MessageBus()

        async def scenario() -> None:
            bus.register("empty")
            msg = await bus.receive("empty", timeout=0.05)
            assert msg is None

        asyncio.run(scenario())

    def test_subscribe_handler_called_on_send(self) -> None:
        from sago.orchestrator.message_bus import AgentMessage, MessageBus

        bus = MessageBus()
        seen: list = []
        bus.subscribe("worker", lambda m: seen.append(m.content))

        async def scenario() -> None:
            await bus.send(AgentMessage(sender="x", recipient="worker", content="ping"))
            assert bus.pending("worker") >= 1

        asyncio.run(scenario())
        assert seen == ["ping"]

    def test_handler_exceptions_swallowed(self) -> None:
        from sago.orchestrator.message_bus import AgentMessage, MessageBus

        bus = MessageBus()

        def boom(msg) -> None:
            raise RuntimeError("boom")

        bus.subscribe("r", boom)

        async def scenario() -> None:
            await bus.send(AgentMessage(sender="x", recipient="r", content={"a": 1}))

        asyncio.run(scenario())  # must not raise


class TestSyncPublish:
    """publish() must work from sync contexts without an event loop."""

    def test_publish_sync_calls_handler(self) -> None:
        from sago.orchestrator.message_bus import publish

        got: list = []

        def handler(msg) -> None:
            got.append(msg)

        from sago.orchestrator.message_bus import get_message_bus

        get_message_bus().subscribe("executor", handler)
        publish("executor", "executor", {"event": "task_started", "n": 1}, extra="meta")
        assert len(got) == 1
        assert got[0].content["event"] == "task_started"
        assert got[0].metadata.get("extra") == "meta"

    def test_publish_sync_is_fire_and_forget(self) -> None:
        from sago.orchestrator.message_bus import publish

        def bad_handler(msg) -> None:
            raise ValueError("should be swallowed")

        from sago.orchestrator.message_bus import get_message_bus

        get_message_bus().subscribe("executor", bad_handler)
        publish("executor", "executor", {"event": "ok"})  # must not raise


class TestBusEventFromExecutor:
    """Executor bus events are env-gated and default to off."""

    def test_bus_event_noop_without_env(self) -> None:
        # Without SAGO_BUS_EVENTS=1 the publish must be a no-op.
        import os
        from unittest.mock import patch

        from sago.engine.simple_executor import _bus_event

        os.environ.pop("SAGO_BUS_EVENTS", None)
        with patch("sago.orchestrator.message_bus.publish") as fake_pub:
            _bus_event("executor", "test_event", a=1)
            fake_pub.assert_not_called()
