"""SQLite database layer for Sago.

Stores sessions, agent state, task history, and context.
All data lives in ~/.sago/data/sago.db
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sago.paths import get_db_path


def _get_connection() -> sqlite3.Connection:
    """Get a database connection."""
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


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
                FOREIGN KEY (session_id) REFERENCES sessions(id)
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
                FOREIGN KEY (session_id) REFERENCES sessions(id),
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            );

            CREATE TABLE IF NOT EXISTS agent_state (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                state_data TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
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
                FOREIGN KEY (session_id) REFERENCES sessions(id),
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_tool_usage_session ON tool_usage(session_id);
        """)
        conn.commit()
    finally:
        conn.close()


class Session:
    """Represents an agent session with full history."""

    def __init__(self, session_id: str | None = None) -> None:
        self.id = session_id or str(uuid.uuid4())
        self.conn = _get_connection()

    def create(self, title: str = "", agent_chain: list[str] | None = None) -> dict[str, Any]:
        """Create a new session."""
        now = datetime.now(timezone.utc).isoformat()
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
        now = datetime.now(timezone.utc).isoformat()
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

    def close(self) -> None:
        self.conn.close()


class TaskStore:
    """Store and manage tasks within sessions."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.conn = _get_connection()

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
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO tasks (id, session_id, parent_task_id, created_at, updated_at,
               assigned_agent, description, context, priority)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task_id, self.session_id, parent_task_id, now, now,
             assigned_agent, description, json.dumps(context or {}), priority),
        )
        self.conn.commit()
        return {"id": task_id, "assigned_agent": assigned_agent, "description": description}

    def update(self, task_id: str, **kwargs: Any) -> None:
        """Update a task."""
        now = datetime.now(timezone.utc).isoformat()
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

    def get_by_status(self, status: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM tasks WHERE session_id = ? AND status = ? ORDER BY priority",
            (self.session_id, status),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_chain(self, task_id: str) -> list[dict[str, Any]]:
        """Get the full chain of tasks from root to this task."""
        chain = []
        current = task_id
        while current:
            task = self.get(current)
            if task:
                chain.insert(0, task)
                current = task.get("parent_task_id")
            else:
                break
        return chain

    def close(self) -> None:
        self.conn.close()


class MessageStore:
    """Store messages/conversations within sessions."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.conn = _get_connection()

    def add(
        self,
        role: str,
        content: str,
        agent_name: str | None = None,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Add a message."""
        msg_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO messages (id, session_id, task_id, created_at, role, agent_name, content, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (msg_id, self.session_id, task_id, now, role, agent_name, content,
             json.dumps(metadata or {})),
        )
        self.conn.commit()
        return {"id": msg_id, "role": role, "content": content}

    def get_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get message history."""
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

    def close(self) -> None:
        self.conn.close()


class ToolUsageStore:
    """Track tool usage across sessions."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.conn = _get_connection()

    def log(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        result: str | None = None,
        duration_ms: int = 0,
        success: bool = True,
        task_id: str | None = None,
    ) -> None:
        """Log a tool usage."""
        usage_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO tool_usage (id, session_id, task_id, created_at, tool_name,
               arguments, result, duration_ms, success)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (usage_id, self.session_id, task_id, now, tool_name,
             json.dumps(arguments or {}), result, duration_ms, 1 if success else 0),
        )
        self.conn.commit()

    def get_stats(self) -> dict[str, Any]:
        """Get tool usage statistics."""
        rows = self.conn.execute(
            """SELECT tool_name, COUNT(*) as count, AVG(duration_ms) as avg_ms,
               SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes
               FROM tool_usage WHERE session_id = ? GROUP BY tool_name""",
            (self.session_id,),
        ).fetchall()
        return {r["tool_name"]: dict(r) for r in rows}

    def close(self) -> None:
        self.conn.close()


def init() -> None:
    """Initialize the database."""
    init_db()
