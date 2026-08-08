"""Streaming Response Handler

Handles streaming LLM responses with token-by-token output.
Supports effort levels and thinking traces.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generator


class EffortLevel(Enum):
    """Effort levels for task execution."""

    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    MAX = "max"


@dataclass
class ThinkingTrace:
    """Tracks thinking process for transparency."""

    step: int
    thought: str
    timestamp: float = field(default_factory=time.time)
    duration_ms: float = 0.0
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "thought": self.thought,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "confidence": self.confidence,
        }


@dataclass
class StreamChunk:
    """A chunk of streaming output."""

    content: str
    chunk_type: str = "text"  # text, thinking, tool_call, tool_result, error
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "chunk_type": self.chunk_type,
            "metadata": self.metadata,
        }


class StreamingResponse:
    """Manages streaming responses with effort tracking."""

    def __init__(
        self,
        effort: EffortLevel = EffortLevel.MEDIUM,
        show_thinking: bool = False,
    ) -> None:
        self.effort = effort
        self.show_thinking = show_thinking
        self.thinking_traces: list[ThinkingTrace] = []
        self.chunks: list[StreamChunk] = []
        self.start_time: float = 0.0
        self.end_time: float = 0.0
        self.token_count: int = 0
        self._callbacks: list[Any] = []

    def add_callback(self, callback: Any) -> None:
        """Add a callback for stream events."""
        self._callbacks.append(callback)

    def start(self) -> None:
        """Start the streaming response."""
        self.start_time = time.time()
        self._notify("start", {})

    def add_thinking(self, thought: str, confidence: float = 0.8) -> None:
        """Add a thinking trace."""
        trace = ThinkingTrace(
            step=len(self.thinking_traces) + 1,
            thought=thought,
            confidence=confidence,
        )
        self.thinking_traces.append(trace)

        if self.show_thinking:
            chunk = StreamChunk(
                content=f"💭 {thought}",
                chunk_type="thinking",
                metadata={"confidence": confidence},
            )
            self.chunks.append(chunk)
            self._notify("chunk", chunk.to_dict())

    def add_text(self, text: str) -> None:
        """Add text content to the stream."""
        chunk = StreamChunk(content=text, chunk_type="text")
        self.chunks.append(chunk)
        self.token_count += len(text.split())
        self._notify("chunk", chunk.to_dict())

    def add_tool_call(self, tool_name: str, args: dict[str, Any]) -> None:
        """Add a tool call to the stream."""
        chunk = StreamChunk(
            content=f"🔧 Calling {tool_name}...",
            chunk_type="tool_call",
            metadata={"tool": tool_name, "args": args},
        )
        self.chunks.append(chunk)
        self._notify("chunk", chunk.to_dict())

    def add_tool_result(self, tool_name: str, result: str) -> None:
        """Add a tool result to the stream."""
        chunk = StreamChunk(
            content=f"✅ {tool_name} completed",
            chunk_type="tool_result",
            metadata={"tool": tool_name, "result": result[:500]},
        )
        self.chunks.append(chunk)
        self._notify("chunk", chunk.to_dict())

    def add_error(self, error: str) -> None:
        """Add an error to the stream."""
        chunk = StreamChunk(content=f"❌ {error}", chunk_type="error")
        self.chunks.append(chunk)
        self._notify("chunk", chunk.to_dict())

    def end(self) -> str:
        """End the streaming response and return full content."""
        self.end_time = time.time()
        self._notify("end", self.get_stats())

        return self.get_full_content()

    def get_full_content(self) -> str:
        """Get the full accumulated content."""
        return "".join(c.content for c in self.chunks if c.chunk_type == "text")

    def get_stats(self) -> dict[str, Any]:
        """Get response statistics."""
        duration = (self.end_time or time.time()) - self.start_time
        return {
            "effort": self.effort.value,
            "duration_seconds": round(duration, 2),
            "token_count": self.token_count,
            "thinking_steps": len(self.thinking_traces),
            "tool_calls": sum(1 for c in self.chunks if c.chunk_type == "tool_call"),
            "errors": sum(1 for c in self.chunks if c.chunk_type == "error"),
            "total_chunks": len(self.chunks),
        }

    def get_thinking_traces(self) -> list[dict[str, Any]]:
        """Get all thinking traces as dicts."""
        return [t.to_dict() for t in self.thinking_traces]

    def _notify(self, event: str, data: dict[str, Any]) -> None:
        """Notify all callbacks of an event."""
        for callback in self._callbacks:
            try:
                callback(event, data)
            except Exception:
                pass  # Don't let callback errors break the stream

    def to_json(self) -> str:
        """Export stream as JSON."""
        return json.dumps(
            {
                "stats": self.get_stats(),
                "thinking": self.get_thinking_traces(),
                "chunks": [c.to_dict() for c in self.chunks],
            },
            indent=2,
        )


class StreamPrinter:
    """Prints streaming output to terminal."""

    def __init__(self, show_thinking: bool = False, use_color: bool = True) -> None:
        self.show_thinking = show_thinking
        self.use_color = use_color
        self._last_chunk_type = ""

    def __call__(self, event: str, data: dict[str, Any]) -> None:
        """Handle stream events."""
        if event == "chunk":
            self._print_chunk(data)
        elif event == "end":
            self._print_stats(data)

    def _print_chunk(self, data: dict[str, Any]) -> None:
        """Print a chunk to terminal."""
        content = data.get("content", "")
        chunk_type = data.get("chunk_type", "text")

        if chunk_type == "thinking" and not self.show_thinking:
            return

        if chunk_type == "text":
            print(content, end="", flush=True)
        elif chunk_type == "thinking":
            if self.use_color:
                print(f"\033[90m{content}\033[0m", flush=True)
            else:
                print(content, flush=True)
        elif chunk_type == "tool_call":
            print(f"\n{content}", flush=True)
        elif chunk_type == "tool_result":
            print(f"  {content}", flush=True)
        elif chunk_type == "error":
            if self.use_color:
                print(f"\033[91m{content}\033[0m", flush=True)
            else:
                print(content, flush=True)

        self._last_chunk_type = chunk_type

    def _print_stats(self, data: dict[str, Any]) -> None:
        """Print response statistics."""
        print()  # New line after stream
        duration = data.get("duration_seconds", 0)
        tokens = data.get("token_count", 0)
        tools = data.get("tool_calls", 0)

        parts = [f"{duration:.1f}s", f"{tokens} tokens"]
        if tools > 0:
            parts.append(f"{tools} tool calls")

        if self.use_color:
            print(f"\033[90m[{' | '.join(parts)}]\033[0m")
        else:
            print(f"[{' | '.join(parts)}]")
