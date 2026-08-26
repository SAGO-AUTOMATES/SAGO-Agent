"""Integration tests for session creation, persistence, and export."""

import tempfile

from sago.database import MessageStore, Session, ToolUsageStore, init_db
from sago.tracking.dev_tracer import export_session_dev_artifacts


class TestSessionLifecycle:
    def setup_method(self):
        init_db()

    def test_create_session(self):
        session = Session()
        result = session.create(title="Integration Test")
        assert "id" in result
        assert len(result["id"]) > 0
        session.close()

    def test_create_and_load_session(self):
        session = Session()
        result = session.create(title="Load Test")
        sid = result["id"]

        loaded = Session(sid)
        assert loaded.id == sid
        loaded.close()
        session.close()

    def test_message_persistence(self):
        session = Session()
        result = session.create(title="Message Test")
        sid = result["id"]

        store = MessageStore(sid)
        store.add(role="user", content="Hello world")
        store.add(role="assistant", content="Hi there!", agent_name="main")
        store.add(role="tool", content="Tool output", agent_name="architect")
        store.flush()

        history = store.get_history(limit=10)
        assert len(history) == 3
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello world"
        assert history[1]["role"] == "assistant"
        assert history[1]["agent_name"] == "main"
        assert history[2]["role"] == "tool"

        store.close()
        session.close()

    def test_tool_usage_persistence(self):
        session = Session()
        result = session.create(title="Tool Test")
        sid = result["id"]

        store = ToolUsageStore(sid)
        store.log(
            tool_name="glob_files",
            arguments={"pattern": "*.py"},
            result="Found 5 files",
            agent="architect",
            duration_ms=123,
            success=True,
        )
        store.flush()

        all_usage = store.get_all()
        assert len(all_usage) == 1
        assert all_usage[0]["tool_name"] == "glob_files"
        assert all_usage[0]["agent"] == "architect"

        store.close()
        session.close()

    def test_export_session(self):
        session = Session()
        result = session.create(title="Export Test")
        sid = result["id"]

        msg_store = MessageStore(sid)
        msg_store.add(role="user", content="What is Python?")
        msg_store.add(
            role="assistant", content="Python is a programming language.", agent_name="main"
        )
        msg_store.add(role="tool", content="Found 5 files matching *.py", agent_name="architect")
        msg_store.flush()

        tool_store = ToolUsageStore(sid)
        tool_store.log(
            tool_name="glob_files",
            arguments={"pattern": "*.py"},
            result="Found 5 files",
            agent="architect",
        )
        tool_store.flush()

        with tempfile.TemporaryDirectory() as tmp:
            export_result = export_session_dev_artifacts(
                session_id=sid,
                messages=msg_store.get_history(limit=100),
                cwd=tmp,
                tool_calls=tool_store.get_all(),
            )
            assert "chat_export" in export_result
            export_path = export_result["chat_export"]

            import os

            assert os.path.exists(export_path)
            with open(export_path) as f:
                content = f.read()
            assert "Python is a programming language" in content
            assert "glob_files" in content

        msg_store.close()
        tool_store.close()
        session.close()

    def test_session_update_title(self):
        session = Session()
        result = session.create(title="Original Title")
        sid = result["id"]
        session.update(title="Updated Title")
        session.close()

        loaded = Session(sid)
        loaded.close()
