"""SQLite database layer for Sago.

Stores sessions, agent state, task history, and context.
All data lives in ~/.sago/data/sago.db

Features:
- Connection pooling via module-level singleton
- Context manager support for all stores
- Batch commits for high-frequency operations
- CASCADE foreign keys for data integrity
- WAL mode for concurrent reads
"""

from __future__ import annotations

import atexit
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from sago.paths import get_db_path
from sago.utils.errors import log_error

# ---------------------------------------------------------------------------
# Connection pool - single shared connection per thread
# ---------------------------------------------------------------------------

_pool_lock = threading.Lock()
_connections: dict[int, sqlite3.Connection] = {}


def _get_connection() -> sqlite3.Connection:
    """Get a thread-local database connection (pooled)."""
    tid = threading.get_ident()
    with _pool_lock:
        conn = _connections.get(tid)
        if conn is not None:
            return conn

    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")

    with _pool_lock:
        _connections[tid] = conn
    return conn


def close_all_connections() -> None:
    """Close all pooled connections. Use at process exit."""
    with _pool_lock:
        conns = list(_connections.values())
        _connections.clear()
    for conn in conns:
        try:
            conn.close()
        except Exception as e:
            log_error("Failed to close database connection", e)


atexit.register(close_all_connections)


def close_thread_connection() -> None:
    """Close the connection for the current thread."""
    tid = threading.get_ident()
    with _pool_lock:
        conn = _connections.pop(tid, None)
    if conn is not None:
        conn.close()


@contextmanager
def get_db():
    """Context manager that yields a connection and ensures cleanup."""
    conn = _get_connection()
    try:
        yield conn
    finally:
        pass  # connection stays in pool; caller controls commit


def init_db() -> None:
    """Initialize the database schema."""
    conn = _get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                title TEXT,
                agent_chain TEXT,
                status TEXT DEFAULT 'active',
                metadata TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                parent_task_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                assigned_agent TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                result TEXT,
                context TEXT DEFAULT '{}',
                priority INTEGER DEFAULT 5,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
                FOREIGN KEY (parent_task_id) REFERENCES tasks(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                task_id TEXT,
                created_at TEXT NOT NULL,
                role TEXT NOT NULL,
                agent_name TEXT,
                content TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS agent_state (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                state_data TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS tool_usage (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                task_id TEXT,
                created_at TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                arguments TEXT,
                result TEXT,
                duration_ms INTEGER,
                success INTEGER DEFAULT 1,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_task_id);
            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);
            CREATE INDEX IF NOT EXISTS idx_messages_role ON messages(role);
            CREATE INDEX IF NOT EXISTS idx_messages_task ON messages(task_id);
            CREATE INDEX IF NOT EXISTS idx_tool_usage_session ON tool_usage(session_id);
            CREATE INDEX IF NOT EXISTS idx_tool_usage_tool ON tool_usage(tool_name);
            CREATE INDEX IF NOT EXISTS idx_tool_usage_task ON tool_usage(task_id);
            CREATE INDEX IF NOT EXISTS idx_agent_state_session ON agent_state(session_id);
        """)
        conn.commit()
    finally:
        pass  # connection stays in pool


class Session:
    """Represents an agent session with full history."""

    def __init__(self, session_id: str | None = None) -> None:
        self.id = session_id or str(uuid.uuid4())
        self.conn = _get_connection()

    def __enter__(self) -> Session:
        return self

    def __exit__(self, *args: Any) -> None:
        pass  # connection stays in pool

    def create(self, title: str = "", agent_chain: list[str] | None = None) -> dict[str, Any]:
        """Create a new session."""
        now = datetime.now(UTC).isoformat()
        chain = json.dumps(agent_chain or ["sago"])
        self.conn.execute(
            "INSERT INTO sessions (id, created_at, updated_at, title, agent_chain) VALUES (?, ?, ?, ?, ?)",
            (self.id, now, now, title, chain),
        )
        self.conn.commit()
        return {"id": self.id, "title": title, "created_at": now}

    def get(self) -> dict[str, Any] | None:
        """Get session by ID."""
        row = self.conn.execute("SELECT * FROM sessions WHERE id = ?", (self.id,)).fetchone()
        return dict(row) if row else None

    def update(self, **kwargs: Any) -> None:
        """Update session fields."""
        now = datetime.now(UTC).isoformat()
        sets = ["updated_at = ?"]
        values: list[Any] = [now]
        for key, val in kwargs.items():
            if key in ("title", "status", "agent_chain", "metadata"):
                sets.append(f"{key} = ?")
                values.append(json.dumps(val) if isinstance(val, (dict, list)) else val)
        values.append(self.id)
        self.conn.execute(f"UPDATE sessions SET {', '.join(sets)} WHERE id = ?", values)
        self.conn.commit()

    def list_all(self, limit: int = 50) -> list[dict[str, Any]]:
        """List all sessions."""
        rows = self.conn.execute(
            "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def delete(self) -> None:
        """Delete session and all cascaded data."""
        self.conn.execute("DELETE FROM sessions WHERE id = ?", (self.id,))
        self.conn.commit()

    def close(self) -> None:
        """No-op - connection is pooled."""

    def get_full_export(self) -> dict[str, Any]:
        """Get complete session data for export."""
        session = self.get() or {}
        ms = MessageStore(self.id)
        ms.flush()
        rows = ms.conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at",
            (self.id,),
        ).fetchall()
        messages = [dict(r) for r in rows]
        tus = ToolUsageStore(self.id)
        tool_usage = tus.get_all()
        ts = TaskStore(self.id)
        tasks = ts.get_all()
        return {
            "session": session,
            "messages": messages,
            "tool_usage": tool_usage,
            "tasks": tasks,
        }


class TaskStore:
    """Store and manage tasks within sessions."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.conn = _get_connection()

    def __enter__(self) -> TaskStore:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def create(
        self,
        description: str,
        assigned_agent: str,
        parent_task_id: str | None = None,
        priority: int = 5,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new task."""
        task_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        self.conn.execute(
            """INSERT INTO tasks (id, session_id, parent_task_id, created_at, updated_at,
               assigned_agent, description, context, priority)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task_id,
                self.session_id,
                parent_task_id,
                now,
                now,
                assigned_agent,
                description,
                json.dumps(context or {}),
                priority,
            ),
        )
        self.conn.commit()
        return {"id": task_id, "assigned_agent": assigned_agent, "description": description}

    def update(self, task_id: str, **kwargs: Any) -> None:
        """Update a task."""
        now = datetime.now(UTC).isoformat()
        sets = ["updated_at = ?"]
        values: list[Any] = [now]
        for key, val in kwargs.items():
            if key in ("status", "result", "context", "priority"):
                sets.append(f"{key} = ?")
                values.append(json.dumps(val) if isinstance(val, (dict, list)) else val)
        values.append(task_id)
        self.conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", values)
        self.conn.commit()

    def get(self, task_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def get_all(self) -> list[dict[str, Any]]:
        """Get all tasks for this session."""
        rows = self.conn.execute(
            "SELECT * FROM tasks WHERE session_id = ? ORDER BY created_at",
            (self.session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_by_status(self, status: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM tasks WHERE session_id = ? AND status = ? ORDER BY priority",
            (self.session_id, status),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_chain(self, task_id: str) -> list[dict[str, Any]]:
        """Get the full chain of tasks from root to this task.
        Guards against circular references."""
        chain = []
        seen: set[str] = set()
        current = task_id
        while current:
            if current in seen:
                break  # circular reference guard
            seen.add(current)
            task = self.get(current)
            if task:
                chain.insert(0, task)
                current = task.get("parent_task_id")
            else:
                break
        return chain

    def close(self) -> None:
        """No-op - connection is pooled."""


class MessageStore:
    """Store messages/conversations within sessions."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.conn = _get_connection()
        self._pending: list[tuple] = []
        self._batch_size = 50

    def __enter__(self) -> MessageStore:
        return self

    def __exit__(self, *args: Any) -> None:
        self.flush()

    def add(
        self,
        role: str,
        content: str,
        agent_name: str | None = None,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Add a message (batched for performance)."""
        msg_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        self._pending.append(
            (
                msg_id,
                self.session_id,
                task_id,
                now,
                role,
                agent_name,
                content,
                json.dumps(metadata or {}),
            )
        )
        if len(self._pending) >= self._batch_size:
            self.flush()
        return {"id": msg_id, "role": role, "content": content}

    def flush(self) -> None:
        """Flush pending messages to disk."""
        if not self._pending:
            return
        self.conn.executemany(
            """INSERT INTO messages (id, session_id, task_id, created_at, role, agent_name, content, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            self._pending,
        )
        self.conn.commit()
        self._pending.clear()

    def get_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get message history."""
        self.flush()  # ensure pending are written
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (self.session_id, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def get_for_task(self, task_id: str) -> list[dict[str, Any]]:
        """Get messages for a specific task."""
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE task_id = ? ORDER BY created_at",
            (task_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def count(self) -> int:
        """Count messages in session."""
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE session_id = ?",
            (self.session_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    def close(self) -> None:
        """Flush and no-op - connection is pooled."""
        self.flush()


class ToolUsageStore:
    """Track tool usage across sessions."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.conn = _get_connection()
        self._pending: list[tuple] = []
        self._batch_size = 20

    def __enter__(self) -> ToolUsageStore:
        return self

    def __exit__(self, *args: Any) -> None:
        self.flush()

    def log(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        result: str | None = None,
        duration_ms: int = 0,
        success: bool = True,
        task_id: str | None = None,
    ) -> None:
        """Log a tool usage (batched for performance)."""
        usage_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        self._pending.append(
            (
                usage_id,
                self.session_id,
                task_id,
                now,
                tool_name,
                json.dumps(arguments or {}),
                result,
                duration_ms,
                1 if success else 0,
            )
        )
        if len(self._pending) >= self._batch_size:
            self.flush()

    def flush(self) -> None:
        """Flush pending tool usage logs to disk."""
        if not self._pending:
            return
        self.conn.executemany(
            """INSERT INTO tool_usage (id, session_id, task_id, created_at, tool_name,
               arguments, result, duration_ms, success)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            self._pending,
        )
        self.conn.commit()
        self._pending.clear()

    def get_all(self) -> list[dict[str, Any]]:
        """Get all tool usage for this session."""
        self.flush()
        rows = self.conn.execute(
            "SELECT * FROM tool_usage WHERE session_id = ? ORDER BY created_at",
            (self.session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict[str, Any]:
        """Get tool usage statistics."""
        self.flush()
        rows = self.conn.execute(
            """SELECT tool_name, COUNT(*) as count, AVG(duration_ms) as avg_ms,
               SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes
               FROM tool_usage WHERE session_id = ? GROUP BY tool_name""",
            (self.session_id,),
        ).fetchall()
        return {r["tool_name"]: dict(r) for r in rows}

    def close(self) -> None:
        """Flush and no-op - connection is pooled."""
        self.flush()


def init() -> None:
    """Initialize the database."""
    init_db()


def vacuum() -> None:
    """Reclaim disk space and optimize the database."""
    conn = _get_connection()
    conn.execute("VACUUM")


def get_db_stats() -> dict[str, Any]:
    """Get database size and row counts."""
    conn = _get_connection()
    stats: dict[str, Any] = {}
    for table in ("sessions", "tasks", "messages", "agent_state", "tool_usage"):
        row = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
        stats[table] = row["cnt"]
    row = conn.execute("PRAGMA page_count").fetchone()
    page_count = row[0]
    row = conn.execute("PRAGMA page_size").fetchone()
    page_size = row[0]
    stats["size_bytes"] = page_count * page_size
    return stats
