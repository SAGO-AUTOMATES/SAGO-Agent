"""Multi-Session Manager

Manages multiple concurrent sessions with thread support.
Each session can have multiple threads running in parallel.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from sago.utils.safe import log_exception

logger = logging.getLogger("sago.sessions")


class SessionStatus(Enum):
    """Session status states."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class ThreadStatus(Enum):
    """Thread status states."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Migration map for legacy / unknown session status values that may appear
# when restoring sessions written by an older schema. Missing values default
# to IDLE so a session is never left in an invalid state.
_SESSION_STATUS_MIGRATIONS: dict[str, SessionStatus] = {
    "interrupted": SessionStatus.PAUSED,
}

# Migration map for legacy / unknown thread status values.
_THREAD_STATUS_MIGRATIONS: dict[str, ThreadStatus] = {
    "interrupted": ThreadStatus.CANCELLED,
}


def _restore_session_status(data: dict[str, Any]) -> SessionStatus:
    """Restore a SessionStatus from serialized data, migrating old schemas."""
    raw = data.get("status")
    if raw is None:
        return SessionStatus.IDLE
    if isinstance(raw, SessionStatus):
        return raw
    try:
        return SessionStatus(raw)
    except ValueError:
        return _SESSION_STATUS_MIGRATIONS.get(raw, SessionStatus.IDLE)


def _restore_thread_status(data: dict[str, Any]) -> ThreadStatus:
    """Restore a ThreadStatus from serialized data, migrating old schemas."""
    raw = data.get("status", "pending")
    if isinstance(raw, ThreadStatus):
        return raw
    try:
        return ThreadStatus(raw)
    except ValueError:
        return _THREAD_STATUS_MIGRATIONS.get(raw, ThreadStatus.PENDING)


@dataclass
class Thread:
    """A single thread of execution within a session."""

    id: str
    session_id: str
    agent_name: str
    task: str
    status: ThreadStatus = ThreadStatus.PENDING
    result: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    effort: str = "medium"
    tokens_used: int = 0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def duration(self) -> float:
        """Get thread duration in seconds."""
        if self.started_at is None:
            return 0.0
        end = self.completed_at or time.time()
        return end - self.started_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "task": self.task,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration": self.duration(),
            "effort": self.effort,
            "tokens_used": self.tokens_used,
            "tool_calls_count": len(self.tool_calls),
        }


@dataclass
class Message:
    """A message in a conversation thread."""

    id: str
    session_id: str
    thread_id: str | None
    role: str  # user, assistant, system, tool
    content: str
    agent_name: str | None = None
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "thread_id": self.thread_id,
            "role": self.role,
            "content": self.content,
            "agent_name": self.agent_name,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class Session:
    """A conversation session with threads."""

    id: str
    title: str
    status: SessionStatus = SessionStatus.IDLE
    threads: list[Thread] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def active_threads(self) -> list[Thread]:
        """Get all running threads."""
        return [t for t in self.threads if t.status == ThreadStatus.RUNNING]

    def completed_threads(self) -> list[Thread]:
        """Get all completed threads."""
        return [t for t in self.threads if t.status == ThreadStatus.COMPLETED]

    def add_message(self, role: str, content: str, agent_name: str | None = None) -> Message:
        """Add a message to the session."""
        msg = Message(
            id=str(uuid.uuid4()),
            session_id=self.id,
            thread_id=None,
            role=role,
            content=content,
            agent_name=agent_name,
        )
        self.messages.append(msg)
        self.updated_at = time.time()
        return msg

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status.value,
            "threads": [t.to_dict() for t in self.threads],
            "message_count": len(self.messages),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class SessionManager:
    """Manages multiple concurrent sessions with thread support."""

    def __init__(self, max_workers: int = 4) -> None:
        self.sessions: dict[str, Session] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._futures: dict[str, Future] = {}
        self._callbacks: list[Callable[..., None]] = []
        self._lock = threading.Lock()

    def add_callback(self, callback: Callable[..., None]) -> None:
        """Add a callback for session events."""
        self._callbacks.append(callback)

    def create_session(self, title: str = "New Session") -> Session:
        """Create a new session."""
        session = Session(id=str(uuid.uuid4()), title=title)
        with self._lock:
            self.sessions[session.id] = session
        logger.info("Session created: id=%s title=%s", session.id, title)
        self._notify("session_created", {"session_id": session.id})
        return session

    def get_session(self, session_id: str) -> Session | None:
        """Get a session by ID."""
        with self._lock:
            session = self.sessions.get(session_id)
        if session:
            logger.debug("Session found: id=%s", session_id)
        else:
            logger.debug("Session not found: id=%s", session_id)
        return session

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all sessions."""
        with self._lock:
            return [s.to_dict() for s in self.sessions.values()]

    def create_thread(
        self,
        session_id: str,
        agent_name: str,
        task: str,
        effort: str = "medium",
    ) -> Thread | None:
        """Create a new thread in a session."""
        session = self.sessions.get(session_id)
        if not session:
            logger.error("create_thread failed: session not found id=%s", session_id)
            return None

        thread = Thread(
            id=str(uuid.uuid4()),
            session_id=session_id,
            agent_name=agent_name,
            task=task,
            effort=effort,
        )
        session.threads.append(thread)
        session.updated_at = time.time()
        logger.info(
            "Thread created: thread_id=%s session_id=%s agent=%s",
            thread.id,
            session_id,
            agent_name,
        )
        self._notify("thread_created", {"thread_id": thread.id})
        return thread

    def execute_thread(
        self,
        thread_id: str,
        executor_fn: Callable[..., str],
    ) -> Future[str] | None:
        """Execute a thread in the background."""
        thread = self._find_thread(thread_id)
        if not thread:
            logger.error("execute_thread failed: thread not found id=%s", thread_id)
            return None

        logger.info("Thread start: thread_id=%s agent=%s", thread.id, thread.agent_name)

        def _run() -> str:
            thread.status = ThreadStatus.RUNNING
            thread.started_at = time.time()
            self._notify("thread_started", {"thread_id": thread.id})

            try:
                result = executor_fn(thread)
                thread.result = result
                thread.status = ThreadStatus.COMPLETED
            except TimeoutError as e:
                thread.error = str(e)
                thread.status = ThreadStatus.FAILED
                logger.error(
                    "Thread timed out: thread_id=%s agent=%s error=%s",
                    thread.id,
                    thread.agent_name,
                    e,
                )
            except Exception as e:
                thread.error = str(e)
                thread.status = ThreadStatus.FAILED
                logger.error(
                    "Thread failed: thread_id=%s agent=%s error=%s",
                    thread.id,
                    thread.agent_name,
                    e,
                )
            finally:
                thread.completed_at = time.time()
                session = self.sessions.get(thread.session_id)
                if session:
                    session.updated_at = time.time()

            logger.info(
                "Thread completed: thread_id=%s status=%s duration=%.2fs",
                thread.id,
                thread.status.value,
                thread.duration(),
            )
            self._notify(
                "thread_completed",
                {"thread_id": thread.id, "status": thread.status.value},
            )
            return thread.result or thread.error or ""

        future = self.executor.submit(_run)
        self._futures[thread_id] = future
        return future

    def execute_thread_sync(
        self,
        thread_id: str,
        executor_fn: Callable[..., str],
    ) -> str:
        """Execute a thread synchronously."""
        future = self.execute_thread(thread_id, executor_fn)
        if future:
            try:
                return future.result()
            except Exception as e:
                logger.error("execute_thread_sync failed: thread_id=%s error=%s", thread_id, e)
                return f"Error: {e}"
        return "Error: Thread not found"

    def wait_for_thread(self, thread_id: str, timeout: float = 300) -> str:
        """Wait for a thread to complete."""
        future = self._futures.get(thread_id)
        if not future:
            logger.debug("wait_for_thread: thread not found id=%s", thread_id)
            return "Error: Thread not found"

        try:
            result = future.result(timeout=timeout)
            return result
        except TimeoutError:
            logger.warning("Thread timed out: thread_id=%s timeout=%s", thread_id, timeout)
            return "Error: Thread timed out"

    def cancel_thread(self, thread_id: str) -> bool:
        """Cancel a running thread."""
        thread = self._find_thread(thread_id)
        if not thread:
            logger.debug("cancel_thread: thread not found id=%s", thread_id)
            return False

        if thread.status == ThreadStatus.RUNNING:
            future = self._futures.get(thread_id)
            if future:
                future.cancel()
            thread.status = ThreadStatus.CANCELLED
            thread.completed_at = time.time()
            logger.info("Thread cancelled: thread_id=%s agent=%s", thread.id, thread.agent_name)
            return True
        return False

    def get_thread(self, thread_id: str) -> Thread | None:
        """Get a thread by ID."""
        return self._find_thread(thread_id)

    def get_thread_history(self, thread_id: str) -> list[dict[str, Any]]:
        """Get the history of a thread."""
        thread = self._find_thread(thread_id)
        if not thread:
            return []
        return thread.tool_calls

    def pause_session(self, session_id: str) -> bool:
        """Pause all threads in a session."""
        session = self.sessions.get(session_id)
        if not session:
            return False

        for thread in session.threads:
            if thread.status == ThreadStatus.RUNNING:
                self.cancel_thread(thread.id)
                thread.status = ThreadStatus.PENDING

        session.status = SessionStatus.PAUSED
        return True

    def resume_session(self, session_id: str) -> bool:
        """Resume a paused session."""
        session = self.sessions.get(session_id)
        if not session or session.status != SessionStatus.PAUSED:
            return False

        session.status = SessionStatus.IDLE
        return True

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        with self._lock:
            if session_id in self.sessions:
                self.pause_session(session_id)
                del self.sessions[session_id]
                logger.info("Session deleted: id=%s", session_id)
                self._notify("session_deleted", {"session_id": session_id})
                return True
            logger.error("delete_session failed: session not found id=%s", session_id)
            return False

    def _find_thread(self, thread_id: str) -> Thread | None:
        """Find a thread by ID across all sessions."""
        with self._lock:
            for session in self.sessions.values():
                for thread in session.threads:
                    if thread.id == thread_id:
                        return thread
            return None

    def _notify(self, event: str, data: dict[str, Any]) -> None:
        """Notify all callbacks of an event."""
        for callback in self._callbacks:
            try:
                callback(event, data)
            except Exception as e:
                log_exception(e, "Session callback failed")

    def shutdown(self) -> None:
        """Shutdown the executor."""
        self.executor.shutdown(wait=False)

    def export_session(self, session_id: str) -> str | None:
        """Export a session as JSON."""
        session = self.sessions.get(session_id)
        if not session:
            return None
        return json.dumps(session.to_dict(), indent=2)

    def import_session(self, json_data: str) -> Session | None:
        """Import a session from JSON, preserving all data."""
        try:
            data = json.loads(json_data)
            session = Session(
                id=data["id"],
                title=data["title"],
                status=_restore_session_status(data),
                created_at=data.get("created_at", time.time()),
                updated_at=data.get("updated_at", time.time()),
                metadata=data.get("metadata", {}),
            )

            # Restore threads
            for thread_data in data.get("threads", []):
                thread = Thread(
                    id=thread_data["id"],
                    session_id=session.id,
                    agent_name=thread_data.get("agent_name", ""),
                    task=thread_data.get("task", ""),
                    effort=thread_data.get("effort", "medium"),
                    status=_restore_thread_status(thread_data),
                    result=thread_data.get("result"),
                    created_at=thread_data.get("created_at", time.time()),
                    started_at=thread_data.get("started_at"),
                    completed_at=thread_data.get("completed_at"),
                    tokens_used=thread_data.get("tokens_used", 0),
                )
                session.threads.append(thread)

            # Restore messages
            for msg_data in data.get("messages", []):
                msg = Message(
                    id=msg_data["id"],
                    session_id=session.id,
                    thread_id=msg_data.get("thread_id"),
                    role=msg_data.get("role", "user"),
                    content=msg_data.get("content", ""),
                    agent_name=msg_data.get("agent_name"),
                    timestamp=msg_data.get("timestamp", time.time()),
                    metadata=msg_data.get("metadata", {}),
                )
                session.messages.append(msg)

            self.sessions[session.id] = session
            return session
        except Exception:
            return None

    def get_summary_by_agent(self, session_id: str) -> dict[str, Any]:
        """Build categorized summary by agent without re-running tools — 0 wasted tokens.

        Uses cached Session.get_full_export() + ToolUsageStore + DevTracer traces.
        Called by summary-intent short-circuit to avoid new grep/execute_shell calls.
        """
        session = self.sessions.get(session_id)
        if not session:
            return {"error": "session not found"}
        # Reuse export already cached
        try:
            from pathlib import Path

            pa = Path.cwd() / "PROJECT_ANALYSIS.md"
            cached = pa.read_text(encoding="utf-8", errors="replace")[:5000] if pa.exists() else ""
        except Exception:
            cached = ""
        # Group by agent
        from collections import defaultdict

        per_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for t in session.threads:
            per_agent[t.agent_name].append(t.to_dict())
        # Messages by agent
        msg_by_agent: dict[str, int] = {}
        for m in session.messages:
            ag = m.agent_name or "sago"
            msg_by_agent[ag] = msg_by_agent.get(ag, 0) + 1
        return {
            "session_id": session_id,
            "per_agent_threads": dict(per_agent),
            "per_agent_messages": msg_by_agent,
            "cached_analysis_preview": cached[:800],
            "total_threads": len(session.threads),
            "total_messages": len(session.messages),
        }


# Summary intent detection — shared helper (spec regex)
_SUMMARY_INTENT_RE = None  # lazy init


def _get_summary_re():
    import re

    global _SUMMARY_INTENT_RE
    if _SUMMARY_INTENT_RE is None:
        _SUMMARY_INTENT_RE = re.compile(
            r"\b(summar|what was done|what did you do)\b", re.IGNORECASE
        )
    return _SUMMARY_INTENT_RE


def is_summary_intent(msg: str) -> bool:
    """Detect summary intent via spec regex plus typo tolerance (sumamry).

    Avoids false-positive on file-specific 'summarize this file' (needs tools).
    """
    import re

    if not msg or not msg.strip():
        return False
    low = msg.lower().strip()
    has_file_hint = bool(
        re.search(
            r"\b[\w\-/\\.]+\.(?:py|js|ts|tsx|jsx|md|txt|json|yaml|yml|toml|html|css|java|go|rs|c|cpp|h|rb|php|sh|sql)\b",
            low,
        )
        or "#file" in low
        or "this file" in low
        or "the file" in low
    )
    if _get_summary_re().search(low):
        # Even if file hint, still check explicit prior-work phrase
        if has_file_hint and not re.search(
            r"\b(what you did|what was done|what did you do)\b", low
        ):
            return False
        return True
    if "summar" in low or "sumam" in low:
        if has_file_hint and not re.search(
            r"\b(what you did|what was done|what did you do|so what)\b", low
        ):
            return False
        # Short queries like "summary" are prior-session summaries
        if len(low) < 60 and not has_file_hint:
            return True
        if re.search(r"\b(what|done|did|so)\b", low):
            return True
        if re.search(r"\bsummar\w*\b.*\b(what|you did|was done)\b", low):
            return True
    if re.search(r"\bsum\w*ry\b", low) and len(low.split()) <= 10 and not has_file_hint:
        return True
    return False
