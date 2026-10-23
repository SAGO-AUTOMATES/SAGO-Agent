"""Lightweight in-process message bus for inter-agent communication (additive).

Provides structured, observable handoff messages between agents without changing
existing orchestration paths. Opt-in usage only.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("sago.orchestrator.message_bus")


@dataclass
class AgentMessage:
    sender: str
    recipient: str
    content: Any
    metadata: dict[str, Any] = field(default_factory=dict)


class MessageBus:
    """Async message bus with per-recipient queues."""

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[AgentMessage]] = {}
        self._handlers: dict[str, list[Callable[[AgentMessage], Any]]] = {}

    def register(self, agent: str) -> None:
        self._queues.setdefault(agent, asyncio.Queue())

    async def send(self, msg: AgentMessage) -> None:
        self._queues.setdefault(msg.recipient, asyncio.Queue())
        await self._queues[msg.recipient].put(msg)
        for handler in self._handlers.get(msg.recipient, []):
            try:
                await handler(msg) if asyncio.iscoroutinefunction(handler) else handler(msg)
            except Exception as e:
                logger.debug("Message handler error: %s", e)

    async def receive(self, agent: str, timeout: float | None = None) -> AgentMessage | None:
        q = self._queues.setdefault(agent, asyncio.Queue())
        try:
            if timeout is None:
                return await q.get()
            return await asyncio.wait_for(q.get(), timeout=timeout)
        except TimeoutError:
            return None

    def subscribe(self, agent: str, handler: Callable[[AgentMessage], Any]) -> None:
        self._handlers.setdefault(agent, []).append(handler)

    def pending(self, agent: str) -> int:
        q = self._queues.get(agent)
        return q.qsize() if q else 0


_GLOBAL_BUS: MessageBus | None = None


def get_message_bus() -> MessageBus:
    global _GLOBAL_BUS
    if _GLOBAL_BUS is None:
        _GLOBAL_BUS = MessageBus()
    return _GLOBAL_BUS


def publish(sender: str, recipient: str, content: Any, **metadata: Any) -> None:
    """Fire-and-forget publish usable from sync contexts (executors, tools).

    Semantics:
    - Inside a running event loop: full async path (queues + handlers) via task.
    - From sync code: registered handlers are invoked directly; plain queues are
      skipped because their consumers require an event loop. This avoids per-call
      event-loop creation while keeping subscribers notified.
    """
    msg = AgentMessage(sender=sender, recipient=recipient, content=content, metadata=dict(metadata))
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # Sync context: notify subscribers directly (best-effort).
        for handler in get_message_bus()._handlers.get(recipient, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    logger.debug("Skipping async handler %r without running loop", handler)
                    continue
                handler(msg)
            except Exception as e:
                logger.debug("Message handler error: %s", e)
        return
    # Async context: full path (queues + handlers) as a background task.
    asyncio.get_running_loop().create_task(get_message_bus().send(msg))
