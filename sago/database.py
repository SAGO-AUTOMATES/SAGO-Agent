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
import logging
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from sago.paths import get_db_path
from sago.utils.errors import log_error

logger = logging.getLogger("sago.database")

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
    logger.debug("Creating new connection for thread %s -> %s", tid, db_path)
    try:
        conn = sqlite3.connect(str(db_path), timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
    except Exception as e:
        logger.error("Failed to create database connection for thread %s: %s", tid, e)
        raise

    with _pool_lock:
        _connections[tid] = conn
    logger.debug("Connection pool now has %d connections", len(_connections))
    return conn


def close_all_connections() -> None:
    """Close all pooled connections. Use at process exit."""
    with _pool_lock:
        conns = list(_connections.values())
        _connections.clear()
    logger.debug("Closing %d pooled connections", len(conns))
    for conn in conns:
        try:
            conn.close()
        except (sqlite3.ProgrammingError, sqlite3.OperationalError):
            pass
        except Exception as e:
            log_error("Failed to close database connection", e)
            logger.error("Failed to close database connection: %s", e)


atexit.register(close_all_connections)


def close_thread_connection() -> None:
    """Close the connection for the current thread."""
    tid = threading.get_ident()
    with _pool_lock:
        conn = _connections.pop(tid, None)
    if conn is not None:
        logger.debug("Closing connection for thread %s", tid)
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
    logger.info("Initializing database schema")
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
                agent TEXT DEFAULT '',
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS checkpoints (
                id TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                workspace_root TEXT,
                session_id TEXT,
                file_count INTEGER DEFAULT 0,
                file_paths TEXT DEFAULT '[]',
                git_commit TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                metadata TEXT DEFAULT '{}'
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
            CREATE INDEX IF NOT EXISTS idx_checkpoints_created ON checkpoints(created_at);
            CREATE INDEX IF NOT EXISTS idx_checkpoints_workspace ON checkpoints(workspace_root);
            CREATE INDEX IF NOT EXISTS idx_checkpoints_session ON checkpoints(session_id);
        """)
        # Migration: add agent column if missing (legacy DBs before this fix)
        try:
            cols = [row[1] for row in conn.execute("PRAGMA table_info(tool_usage)").fetchall()]
            if "agent" not in cols:
                logger.info("Migrating tool_usage table: adding agent column")
                conn.execute("ALTER TABLE tool_usage ADD COLUMN agent TEXT DEFAULT ''")
        except Exception as me:
            logger.debug("tool_usage migration check failed: %s", me)
        # Ensure agent index exists (for both new and migrated DBs)
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_usage_agent ON tool_usage(agent)")
        except Exception as me:
            logger.debug("create idx_tool_usage_agent failed: %s", me)
        conn.commit()
        logger.info("Database schema initialized successfully (6 tables, 14 indexes)")
    except Exception as e:
        logger.error("Failed to initialize database schema: %s", e)
        raise
    finally:
        pass  # connection stays in pool


class Session:
    """Represents an agent session with full history."""

    def __init__(self, session_id: str | None = None) -> None:
        self.id = session_id or str(uuid.uuid4())
        self.conn = _get_connection()
        logger.debug("Session created: %s", self.id)

    def __enter__(self) -> Session:
        return self

    def __exit__(self, *args: Any) -> None:
        pass  # connection stays in pool

    def create(self, title: str = "", agent_chain: list[str] | None = None) -> dict[str, Any]:
        """Create a new session."""
        now = datetime.now(UTC).isoformat()
        chain = json.dumps(agent_chain or ["sago"])
        logger.debug("INSERT session id=%s title=%r", self.id, title)
        self.conn.execute(
            "INSERT INTO sessions (id, created_at, updated_at, title, agent_chain) VALUES (?, ?, ?, ?, ?)",
            (self.id, now, now, title, chain),
        )
        self.conn.commit()
        return {"id": self.id, "title": title, "created_at": now}

    def get(self) -> dict[str, Any] | None:
        """Get session by ID."""
        logger.debug("SELECT session id=%s", self.id)
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
        logger.debug("UPDATE session id=%s fields=%s", self.id, list(kwargs.keys()))
        self.conn.execute(f"UPDATE sessions SET {', '.join(sets)} WHERE id = ?", values)
        self.conn.commit()

    def list_all(self, limit: int = 50) -> list[dict[str, Any]]:
        """List all sessions."""
        logger.debug("SELECT sessions ORDER BY created_at DESC LIMIT %d", limit)
        rows = self.conn.execute(
            "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def find_by_prefix(self, prefix: str) -> dict[str, Any] | None:
        """Find a session by exact ID or prefix match."""
        logger.debug("SELECT session by prefix=%r", prefix)
        row = self.conn.execute("SELECT * FROM sessions WHERE id = ?", (prefix,)).fetchone()
        if row:
            return dict(row)
        row = self.conn.execute(
            "SELECT * FROM sessions WHERE id LIKE ? ORDER BY created_at DESC LIMIT 1",
            (f"{prefix}%",),
        ).fetchone()
        return dict(row) if row else None

    def has_human_messages(self, session_id: str | None = None) -> bool:
        """Check if a session contains at least one real human message (not a slash command)."""
        sid = session_id or self.id
        logger.debug("SELECT has_human_messages session_id=%s", sid)
        row = self.conn.execute(
            """SELECT 1 FROM messages
               WHERE session_id = ?
                 AND role = 'user'
                 AND content NOT LIKE '/%'
                 AND TRIM(content) != ''
               LIMIT 1""",
            (sid,),
        ).fetchone()
        return bool(row)

    def cleanup_useless_sessions(self) -> int:
        """Delete sessions that contain no real user messages (only commands, system messages, or empty)."""
        cursor = self.conn.cursor()
        cursor.execute("""
            DELETE FROM sessions
            WHERE id NOT IN (
                SELECT DISTINCT session_id
                FROM messages
                WHERE role = 'user'
                  AND content NOT LIKE '/%'
                  AND TRIM(content) != ''
            )
        """)
        deleted = cursor.rowcount
        logger.info("Cleaned up %d useless sessions", deleted)
        self.conn.commit()
        return deleted

    def delete(self) -> None:
        """Delete session and all cascaded data."""
        logger.debug("DELETE session id=%s (cascade)", self.id)
        self.conn.execute("DELETE FROM sessions WHERE id = ?", (self.id,))
        self.conn.commit()

    def close(self) -> None:
        """No-op - connection is pooled."""

    def get_full_export(self) -> dict[str, Any]:
        """Get complete session data for export."""
        logger.debug("Exporting full session data id=%s", self.id)
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
        logger.debug(
            "Export complete: %d messages, %d tool usages, %d tasks",
            len(messages),
            len(tool_usage),
            len(tasks),
        )
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
        logger.debug("TaskStore created for session %s", session_id)

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
        logger.debug(
            "INSERT task id=%s agent=%s session=%s", task_id, assigned_agent, self.session_id
        )
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
        logger.debug("UPDATE task id=%s fields=%s", task_id, list(kwargs.keys()))
        self.conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", values)
        self.conn.commit()

    def get(self, task_id: str) -> dict[str, Any] | None:
        logger.debug("SELECT task id=%s", task_id)
        row = self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def get_all(self) -> list[dict[str, Any]]:
        """Get all tasks for this session."""
        logger.debug("SELECT all tasks session_id=%s", self.session_id)
        rows = self.conn.execute(
            "SELECT * FROM tasks WHERE session_id = ? ORDER BY created_at",
            (self.session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_by_status(self, status: str) -> list[dict[str, Any]]:
        logger.debug("SELECT tasks session_id=%s status=%s", self.session_id, status)
        rows = self.conn.execute(
            "SELECT * FROM tasks WHERE session_id = ? AND status = ? ORDER BY priority",
            (self.session_id, status),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_chain(self, task_id: str) -> list[dict[str, Any]]:
        """Get the full chain of tasks from root to this task.
        Guards against circular references."""
        logger.debug("Traversing task chain from %s", task_id)
        chain = []
        seen: set[str] = set()
        current = task_id
        while current:
            if current in seen:
                logger.warning("Circular reference detected in task chain at %s", current)
                break  # circular reference guard
            seen.add(current)
            task = self.get(current)
            if task:
                chain.insert(0, task)
                current = task.get("parent_task_id")
            else:
                break
        logger.debug("Task chain length: %d", len(chain))
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
        logger.debug("MessageStore created for session %s", session_id)

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
        logger.debug(
            "Queued message id=%s role=%s agent=%s pending=%d",
            msg_id,
            role,
            agent_name,
            len(self._pending),
        )
        if len(self._pending) >= self._batch_size:
            self.flush()
        return {"id": msg_id, "role": role, "content": content}

    def flush(self) -> None:
        """Flush pending messages to disk."""
        if not self._pending:
            return
        count = len(self._pending)
        logger.debug("Flushing %d messages for session %s", count, self.session_id)
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
        logger.debug("SELECT message history session_id=%s limit=%d", self.session_id, limit)
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (self.session_id, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def update_last_user_metadata(
        self, agent_name: str | None = None, metadata: dict[str, Any] | None = None
    ) -> None:
        """Update metadata on the most recent user message in this session."""
        self.flush()
        row = self.conn.execute(
            "SELECT id FROM messages WHERE session_id = ? AND role = 'user' ORDER BY created_at DESC LIMIT 1",
            (self.session_id,),
        ).fetchone()
        if row:
            self.conn.execute(
                "UPDATE messages SET metadata = ? WHERE id = ?",
                (json.dumps(metadata or {}), row["id"]),
            )
            self.conn.commit()

    def get_for_task(self, task_id: str) -> list[dict[str, Any]]:
        """Get messages for a specific task."""
        logger.debug("SELECT messages for task_id=%s", task_id)
        rows = self.conn.execute(
            "SELECT * FROM messages WHERE task_id = ? ORDER BY created_at",
            (task_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def count(self) -> int:
        """Count messages in session."""
        logger.debug("SELECT COUNT messages session_id=%s", self.session_id)
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
        logger.debug("ToolUsageStore created for session %s", session_id)

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
        agent: str | None = None,
    ) -> None:
        """Log a tool usage (batched for performance)."""
        usage_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        # Normalize agent: lowercase, strip @, trim
        norm_agent = ""
        if agent:
            norm_agent = str(agent).strip().lstrip("@").lower()
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
                norm_agent,
            )
        )
        logger.debug(
            "Queued tool_usage tool=%s agent=%s success=%s duration_ms=%d pending=%d",
            tool_name,
            norm_agent,
            success,
            duration_ms,
            len(self._pending),
        )
        if len(self._pending) >= self._batch_size:
            self.flush()

    def flush(self) -> None:
        """Flush pending tool usage logs to disk."""
        if not self._pending:
            return
        count = len(self._pending)
        logger.debug("Flushing %d tool_usage records for session %s", count, self.session_id)

        def _do_insert(rows: list[tuple]) -> None:
            # Handle both 9-field (legacy without agent) and 10-field (with agent) pending tuples
            if rows and len(rows[0]) == 10:
                self.conn.executemany(
                    """INSERT INTO tool_usage (id, session_id, task_id, created_at, tool_name,
                       arguments, result, duration_ms, success, agent)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    rows,
                )
            else:
                # Legacy fallback: no agent column
                try:
                    self.conn.executemany(
                        """INSERT INTO tool_usage (id, session_id, task_id, created_at, tool_name,
                           arguments, result, duration_ms, success, agent)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        [(*p, "") if len(p) == 9 else p for p in rows],
                    )
                except Exception:
                    self.conn.executemany(
                        """INSERT INTO tool_usage (id, session_id, task_id, created_at, tool_name,
                           arguments, result, duration_ms, success)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        [p[:9] for p in rows],
                    )

        try:
            _do_insert(self._pending)
        except sqlite3.IntegrityError as e:
            if "FOREIGN KEY" in str(e):
                # Auto-create missing session for tool_usage (e.g. simple_executor dummy session)
                try:
                    now = datetime.now(UTC).isoformat()
                    self.conn.execute(
                        "INSERT OR IGNORE INTO sessions (id, created_at, updated_at, title) VALUES (?, ?, ?, ?)",
                        (self.session_id, now, now, "auto-created for tool_usage"),
                    )
                    self.conn.commit()
                    _do_insert(self._pending)
                except Exception as e2:
                    logger.debug("tool_usage FK auto-create failed: %s", e2)
                    # Last resort: temporarily disable FK checks
                    try:
                        self.conn.execute("PRAGMA foreign_keys=OFF")
                        _do_insert(self._pending)
                        self.conn.execute("PRAGMA foreign_keys=ON")
                    except Exception as e3:
                        logger.debug("tool_usage insert failed even with FK off: %s", e3)
                        raise
            else:
                raise
        self.conn.commit()
        self._pending.clear()

    def get_all(self) -> list[dict[str, Any]]:
        """Get all tool usage for this session."""
        self.flush()
        logger.debug("SELECT all tool_usage session_id=%s", self.session_id)
        rows = self.conn.execute(
            "SELECT * FROM tool_usage WHERE session_id = ? ORDER BY created_at",
            (self.session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict[str, Any]:
        """Get tool usage statistics."""
        self.flush()
        logger.debug("SELECT tool_usage stats session_id=%s", self.session_id)
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


class CheckpointStore:
    """Store for managing workspace snapshot metadata in SQLite."""

    def __init__(self) -> None:
        init_db()
        self.conn = _get_connection()
        logger.debug("CheckpointStore initialized")

    def record_checkpoint(
        self,
        checkpoint_id: str,
        description: str,
        file_paths: list[str],
        workspace_root: str = "",
        session_id: str | None = None,
        git_commit: str = "",
        timestamp: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record or update a checkpoint in SQLite."""
        created_at = (
            datetime.fromtimestamp(timestamp, tz=UTC).isoformat()
            if timestamp
            else datetime.now(UTC).isoformat()
        )
        logger.debug(
            "INSERT/REPLACE checkpoint id=%s files=%d git=%s",
            checkpoint_id,
            len(file_paths),
            git_commit[:8] if git_commit else "",
        )
        self.conn.execute(
            """
            INSERT OR REPLACE INTO checkpoints
            (id, description, workspace_root, session_id, file_count, file_paths, git_commit, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                checkpoint_id,
                description,
                workspace_root,
                session_id,
                len(file_paths),
                json.dumps(file_paths),
                git_commit,
                created_at,
                json.dumps(metadata or {}),
            ),
        )
        self.conn.commit()

    def get_checkpoint(self, checkpoint_id: str) -> dict[str, Any] | None:
        """Retrieve a specific checkpoint by ID."""
        logger.debug("SELECT checkpoint id=%s", checkpoint_id)
        row = self.conn.execute(
            "SELECT * FROM checkpoints WHERE id = ?", (checkpoint_id,)
        ).fetchone()
        if not row:
            logger.debug("Checkpoint %s not found", checkpoint_id)
            return None
        return {
            "id": row["id"],
            "description": row["description"],
            "workspace_root": row["workspace_root"],
            "session_id": row["session_id"],
            "file_count": row["file_count"],
            "file_paths": json.loads(row["file_paths"] or "[]"),
            "git_commit": row["git_commit"],
            "created_at": row["created_at"],
            "metadata": json.loads(row["metadata"] or "{}"),
        }

    def list_checkpoints(
        self, workspace_root: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """List checkpoints ordered by creation time descending."""
        if workspace_root:
            logger.debug("SELECT checkpoints workspace=%s limit=%d", workspace_root, limit)
            rows = self.conn.execute(
                "SELECT * FROM checkpoints WHERE workspace_root = ? ORDER BY created_at DESC LIMIT ?",
                (workspace_root, limit),
            ).fetchall()
        else:
            logger.debug("SELECT checkpoints limit=%d", limit)
            rows = self.conn.execute(
                "SELECT * FROM checkpoints ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()

        results = []
        for row in rows:
            results.append(
                {
                    "id": row["id"],
                    "description": row["description"],
                    "workspace_root": row["workspace_root"],
                    "session_id": row["session_id"],
                    "file_count": row["file_count"],
                    "file_paths": json.loads(row["file_paths"] or "[]"),
                    "git_commit": row["git_commit"],
                    "created_at": row["created_at"],
                    "metadata": json.loads(row["metadata"] or "{}"),
                }
            )
        return results

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint from SQLite."""
        logger.debug("DELETE checkpoint id=%s", checkpoint_id)
        cur = self.conn.execute("DELETE FROM checkpoints WHERE id = ?", (checkpoint_id,))
        self.conn.commit()
        deleted = cur.rowcount > 0
        if not deleted:
            logger.debug("Checkpoint %s not found for deletion", checkpoint_id)
        return deleted


def init() -> None:
    """Initialize the database."""
    logger.info("Initializing database")
    init_db()


def vacuum() -> None:
    """Reclaim disk space and optimize the database."""
    logger.info("Running VACUUM on database")
    conn = _get_connection()
    try:
        conn.execute("VACUUM")
        logger.info("VACUUM completed successfully")
    except Exception as e:
        logger.error("VACUUM failed: %s", e)
        raise


def get_db_stats() -> dict[str, Any]:
    """Get database size and row counts."""
    logger.debug("Retrieving database stats")
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
    logger.debug(
        "DB stats: sessions=%s tasks=%s messages=%s size=%d bytes",
        stats.get("sessions"),
        stats.get("tasks"),
        stats.get("messages"),
        stats["size_bytes"],
    )
    return stats
