"""Unit tests for database layer: Session, MessageStore, TaskStore, ToolUsageStore."""

import json
import threading

import pytest

from sago.database import (
    MessageStore,
    Session,
    TaskStore,
    ToolUsageStore,
    init_db,
)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Use a temporary database for each test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("sago.database.get_db_path", lambda: db_path)
    # Reset connection pool
    from sago.database import _connections, _pool_lock

    with _pool_lock:
        _connections.clear()
    init_db()
    yield
    from sago.database import close_thread_connection

    close_thread_connection()


# ── Session ──────────────────────────────────────────────────────────────


class TestSession:
    def test_create_session(self):
        s = Session()
        result = s.create(title="Test Session")
        assert result["id"] == s.id
        assert result["title"] == "Test Session"

    def test_create_with_custom_id(self):
        s = Session(session_id="custom-id")
        result = s.create()
        assert result["id"] == "custom-id"

    def test_get_session(self):
        s = Session()
        s.create(title="Get Me")
        data = s.get()
        assert data is not None
        assert data["title"] == "Get Me"

    def test_get_nonexistent_session(self):
        s = Session(session_id="no-such-id")
        data = s.get()
        assert data is None

    def test_update_session(self):
        s = Session()
        s.create()
        s.update(title="Updated")
        data = s.get()
        assert data["title"] == "Updated"

    def test_update_status(self):
        s = Session()
        s.create()
        s.update(status="archived")
        data = s.get()
        assert data["status"] == "archived"

    def test_update_ignores_unknown_keys(self):
        s = Session()
        s.create()
        s.update(unknown_field="value")
        data = s.get()
        assert "unknown_field" not in data

    def test_list_sessions(self):
        s1 = Session()
        s1.create(title="First")
        s2 = Session()
        s2.create(title="Second")
        all_sessions = s1.list_all(limit=10)
        titles = [sess["title"] for sess in all_sessions]
        assert "First" in titles
        assert "Second" in titles

    def test_list_sessions_limit(self):
        for i in range(5):
            s = Session()
            s.create(title=f"S{i}")
        result = Session().list_all(limit=2)
        assert len(result) == 2

    def test_delete_session(self):
        s = Session()
        s.create(title="Doomed")
        s.delete()
        assert s.get() is None

    def test_context_manager(self):
        with Session() as s:
            s.create(title="CM Test")
            assert s.get() is not None

    def test_close_is_noop(self):
        s = Session()
        s.create()
        s.close()  # Should not raise

    def test_get_full_export(self):
        s = Session()
        s.create(title="Export")
        ms = MessageStore(s.id)
        ms.add(role="user", content="Hello")
        ms.flush()
        export = s.get_full_export()
        assert "session" in export
        assert "messages" in export
        assert "tool_usage" in export
        assert "tasks" in export
        assert len(export["messages"]) == 1


# ── MessageStore ─────────────────────────────────────────────────────────


class TestMessageStore:
    def test_add_message(self):
        s = Session()
        s.create()
        ms = MessageStore(s.id)
        result = ms.add(role="user", content="Hello")
        assert result["role"] == "user"
        assert result["content"] == "Hello"

    def test_flush_and_get_history(self):
        s = Session()
        s.create()
        ms = MessageStore(s.id)
        ms.add(role="user", content="Msg1")
        ms.add(role="assistant", content="Msg2")
        ms.flush()
        history = ms.get_history()
        assert len(history) == 2
        assert history[0]["content"] == "Msg1"

    def test_batch_flush(self):
        s = Session()
        s.create()
        ms = MessageStore(s.id)
        ms._batch_size = 3
        for i in range(3):
            ms.add(role="user", content=f"Batch{i}")
        assert len(ms._pending) == 0  # auto-flushed

    def test_get_history_limit(self):
        s = Session()
        s.create()
        ms = MessageStore(s.id)
        for i in range(10):
            ms.add(role="user", content=f"Msg{i}")
        ms.flush()
        history = ms.get_history(limit=3)
        assert len(history) == 3

    def test_get_for_task(self):
        s = Session()
        s.create()
        ts = TaskStore(s.id)
        task = ts.create(description="T", assigned_agent="a")
        ms = MessageStore(s.id)
        ms.add(role="user", content="Task msg", task_id=task["id"])
        ms.flush()
        msgs = ms.get_for_task(task["id"])
        assert len(msgs) == 1
        assert msgs[0]["content"] == "Task msg"

    def test_count(self):
        s = Session()
        s.create()
        ms = MessageStore(s.id)
        ms.add(role="user", content="A")
        ms.add(role="assistant", content="B")
        ms.flush()
        assert ms.count() == 2

    def test_context_manager_flushes(self):
        s = Session()
        s.create()
        ms = MessageStore(s.id)
        with ms:
            ms.add(role="user", content="auto")
        history = ms.get_history()
        assert len(history) == 1

    def test_close_flushes(self):
        s = Session()
        s.create()
        ms = MessageStore(s.id)
        ms.add(role="user", content="closed")
        ms.close()
        history = ms.get_history()
        assert len(history) == 1


# ── TaskStore ────────────────────────────────────────────────────────────


class TestTaskStore:
    def test_create_task(self):
        s = Session()
        s.create()
        ts = TaskStore(s.id)
        task = ts.create(description="Do stuff", assigned_agent="dev")
        assert task["assigned_agent"] == "dev"

    def test_update_task(self):
        s = Session()
        s.create()
        ts = TaskStore(s.id)
        task = ts.create(description="Do stuff", assigned_agent="dev")
        ts.update(task["id"], status="running", result="in progress")
        updated = ts.get(task["id"])
        assert updated["status"] == "running"
        assert updated["result"] == "in progress"

    def test_get_all(self):
        s = Session()
        s.create()
        ts = TaskStore(s.id)
        ts.create(description="T1", assigned_agent="a")
        ts.create(description="T2", assigned_agent="b")
        all_tasks = ts.get_all()
        assert len(all_tasks) == 2

    def test_get_by_status(self):
        s = Session()
        s.create()
        ts = TaskStore(s.id)
        t1 = ts.create(description="T1", assigned_agent="a")
        ts.create(description="T2", assigned_agent="b")
        ts.update(t1["id"], status="done")
        done = ts.get_by_status("done")
        assert len(done) == 1
        assert done[0]["id"] == t1["id"]

    def test_get_chain(self):
        s = Session()
        s.create()
        ts = TaskStore(s.id)
        parent = ts.create(description="Parent", assigned_agent="a")
        child = ts.create(description="Child", assigned_agent="b", parent_task_id=parent["id"])
        grandchild = ts.create(description="GC", assigned_agent="c", parent_task_id=child["id"])
        chain = ts.get_chain(grandchild["id"])
        assert len(chain) == 3
        assert chain[0]["id"] == parent["id"]
        assert chain[-1]["id"] == grandchild["id"]

    def test_get_chain_circular_guard(self):
        s = Session()
        s.create()
        ts = TaskStore(s.id)
        t1 = ts.create(description="T1", assigned_agent="a")
        t2 = ts.create(description="T2", assigned_agent="b", parent_task_id=t1["id"])
        # Manually create a circular reference
        ts.update(t1["id"], context=json.dumps({"_parent_override": t2["id"]}))
        # get_chain should not loop forever
        chain = ts.get_chain(t2["id"])
        assert len(chain) >= 1

    def test_context_manager(self):
        s = Session()
        s.create()
        with TaskStore(s.id) as ts:
            ts.create(description="CM", assigned_agent="a")
        assert ts.get_all() is not None


# ── ToolUsageStore ───────────────────────────────────────────────────────


class TestToolUsageStore:
    def test_log_tool_usage(self):
        s = Session()
        s.create()
        tus = ToolUsageStore(s.id)
        tus.log(tool_name="read_file", arguments={"file_path": "x.py"}, duration_ms=100)
        tus.flush()
        usages = tus.get_all()
        assert len(usages) == 1
        assert usages[0]["tool_name"] == "read_file"

    def test_log_failure(self):
        s = Session()
        s.create()
        tus = ToolUsageStore(s.id)
        tus.log(tool_name="write_file", success=False, result="Error: permission denied")
        tus.flush()
        usages = tus.get_all()
        assert usages[0]["success"] == 0

    def test_batch_flush(self):
        s = Session()
        s.create()
        tus = ToolUsageStore(s.id)
        tus._batch_size = 2
        tus.log(tool_name="a")
        assert len(tus._pending) == 1  # not flushed yet
        tus.log(tool_name="b")
        assert len(tus._pending) == 0  # auto-flushed

    def test_get_stats(self):
        s = Session()
        s.create()
        tus = ToolUsageStore(s.id)
        tus.log(tool_name="read_file", duration_ms=10, success=True)
        tus.log(tool_name="read_file", duration_ms=20, success=True)
        tus.log(tool_name="write_file", duration_ms=50, success=False)
        tus.flush()
        stats = tus.get_stats()
        assert "read_file" in stats
        assert stats["read_file"]["count"] == 2
        assert stats["read_file"]["avg_ms"] == pytest.approx(15.0)
        assert "write_file" in stats

    def test_context_manager(self):
        s = Session()
        s.create()
        with ToolUsageStore(s.id) as tus:
            tus.log(tool_name="test_tool")
        usages = tus.get_all()
        assert len(usages) == 1

    def test_close_flushes(self):
        s = Session()
        s.create()
        tus = ToolUsageStore(s.id)
        tus.log(tool_name="close_test")
        tus.close()
        usages = tus.get_all()
        assert len(usages) == 1

    def test_empty_stats(self):
        s = Session()
        s.create()
        tus = ToolUsageStore(s.id)
        stats = tus.get_stats()
        assert stats == {}


# ── Connection Pool ──────────────────────────────────────────────────────


class TestConnectionPool:
    def test_get_connection_returns_same(self):
        from sago.database import _get_connection

        conn1 = _get_connection()
        conn2 = _get_connection()
        assert conn1 is conn2

    def test_thread_isolation(self):
        from sago.database import _get_connection

        main_conn = _get_connection()
        results = {}

        def thread_fn():
            results["conn"] = _get_connection()

        t = threading.Thread(target=thread_fn)
        t.start()
        t.join()
        assert results["conn"] is not main_conn

    def test_close_thread_connection(self):
        from sago.database import close_thread_connection

        close_thread_connection()  # Should not raise


class TestCheckpointStore:
    def test_record_and_get_checkpoint(self):
        from sago.database import CheckpointStore

        store = CheckpointStore()
        store.record_checkpoint(
            checkpoint_id="chk_test_01",
            description="Unit test snapshot",
            file_paths=["src/app.py", "src/util.py"],
            workspace_root="/test/workspace",
            session_id="session-123",
        )

        cp = store.get_checkpoint("chk_test_01")
        assert cp is not None
        assert cp["id"] == "chk_test_01"
        assert cp["description"] == "Unit test snapshot"
        assert cp["file_count"] == 2
        assert "src/app.py" in cp["file_paths"]
        assert cp["workspace_root"] == "/test/workspace"

    def test_list_and_delete_checkpoint(self):
        from sago.database import CheckpointStore

        store = CheckpointStore()
        store.record_checkpoint(
            checkpoint_id="chk_list_01",
            description="Snapshot 1",
            file_paths=["file1.py"],
            workspace_root="/ws_a",
        )
        store.record_checkpoint(
            checkpoint_id="chk_list_02",
            description="Snapshot 2",
            file_paths=["file2.py"],
            workspace_root="/ws_a",
        )

        all_cps = store.list_checkpoints(workspace_root="/ws_a")
        assert len(all_cps) == 2

        deleted = store.delete_checkpoint("chk_list_01")
        assert deleted is True
        assert store.get_checkpoint("chk_list_01") is None
        assert len(store.list_checkpoints(workspace_root="/ws_a")) == 1
