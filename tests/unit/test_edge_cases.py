"""Edge case tests for database, export, and cache operations."""

import tempfile

from sago.database import MessageStore, Session, ToolUsageStore, init_db
from sago.tools.web.search import _CACHE, _get_cached, _set_cache
from sago.tracking.dev_tracer import export_session_dev_artifacts


class TestDatabaseEdgeCases:
    def setup_method(self):
        init_db()

    def test_empty_session_export(self):
        session = Session()
        result = session.create(title="Empty Test")
        sid = result["id"]
        msg_store = MessageStore(sid)
        msg_store.flush()
        with tempfile.TemporaryDirectory() as tmp:
            export = export_session_dev_artifacts(
                session_id=sid,
                messages=[],
                cwd=tmp,
            )
            assert "chat_export" in export
        session.close()
        msg_store.close()

    def test_special_characters_in_messages(self):
        session = Session()
        result = session.create(title="Special Chars")
        sid = result["id"]
        store = MessageStore(sid)
        store.add(role="user", content="Hello [bold]world[/bold] & <html>")
        store.add(role="assistant", content="Quotes \"double\" and 'single' backticks `code`")
        store.flush()
        history = store.get_history(limit=10)
        assert len(history) == 2
        assert "[bold]" in history[0]["content"]
        store.close()
        session.close()

    def test_sequential_writes(self):
        """Test sequential writes to verify batch persistence works."""
        session = Session()
        result = session.create(title="Sequential Test")
        sid = result["id"]

        for thread_id in range(3):
            store = MessageStore(sid)
            for i in range(5):
                store.add(role="user", content=f"Thread {thread_id} msg {i}")
            store.flush()
            store.close()

        msg_store = MessageStore(sid)
        count = msg_store.count()
        msg_store.close()
        session.close()
        assert count == 15  # 3 threads * 5 messages

    def test_flush_empty(self):
        session = Session()
        result = session.create(title="Flush Empty")
        sid = result["id"]
        store = MessageStore(sid)
        store.flush()  # should not crash
        store.flush()  # double flush
        store.close()
        session.close()

    def test_tool_usage_empty_args(self):
        session = Session()
        result = session.create(title="Tool Empty Args")
        sid = result["id"]
        store = ToolUsageStore(sid)
        store.log(tool_name="test_tool")
        store.flush()
        all_usage = store.get_all()
        assert len(all_usage) == 1
        store.close()
        session.close()


class TestCacheEdgeCases:
    def test_cache_expire(self):
        _CACHE.clear()
        _set_cache("test_query", 5, "result")
        cached = _get_cached("test_query", 5)
        assert cached == "result"

    def test_cache_different_params(self):
        _CACHE.clear()
        _set_cache("query", 5, "result5")
        _set_cache("query", 10, "result10")
        assert _get_cached("query", 5) == "result5"
        assert _get_cached("query", 10) == "result10"

    def test_cache_eviction(self):
        _CACHE.clear()
        for i in range(205):
            _set_cache(f"query_{i}", 5, f"result_{i}")
        assert len(_CACHE) <= 200

    def test_cache_miss(self):
        _CACHE.clear()
        assert _get_cached("nonexistent", 5) is None


class TestExportEdgeCases:
    def test_export_with_malformed_metadata(self):
        import tempfile

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi", "metadata": "not json {{{"},
            {"role": "assistant", "content": "Done", "metadata": {"thinking_blocks": "not a list"}},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            result = export_session_dev_artifacts(
                session_id="test-malformed",
                messages=messages,
                cwd=tmp,
            )
            assert "chat_export" in result

    def test_export_with_empty_tool_result(self):
        import tempfile

        tool_calls = [
            {"tool_name": "test", "result": "", "agent": "main"},
            {"tool_name": "test2", "result": None, "agent": "main"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            result = export_session_dev_artifacts(
                session_id="test-empty-tools",
                messages=[],
                cwd=tmp,
                tool_calls=tool_calls,
            )
            assert "chat_export" in result

    def test_export_with_unicode(self):
        import tempfile

        messages = [
            {"role": "user", "content": "分析这段代码"},
            {"role": "assistant", "content": "Código ejecutado correctamente"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            result = export_session_dev_artifacts(
                session_id="test-unicode",
                messages=messages,
                cwd=tmp,
            )

            with open(result["chat_export"]) as f:
                content = f.read()
            assert "分析" in content
            assert "Código" in content
