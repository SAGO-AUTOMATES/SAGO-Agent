"""Tests for missing coverage: update_last_user_metadata, LogManager, LogViewer."""

from __future__ import annotations

import json
import time

import pytest

from sago.database import (
    MessageStore,
    Session,
    init_db,
)
from sago.log_manager import LogManager


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Use a temporary database for each test."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr("sago.database.get_db_path", lambda: db_path)
    from sago.database import _connections, _pool_lock

    with _pool_lock:
        _connections.clear()
    init_db()
    yield
    from sago.database import close_thread_connection

    close_thread_connection()


# --- update_last_user_metadata tests ---


class TestUpdateLastUserMetadata:
    def test_update_metadata_on_user_message(self):
        s = Session()
        s.create()
        ms = MessageStore(s.id)
        ms.add("user", "hello world")
        ms.add("assistant", "hi there")
        ms.flush()

        enhancement = {"enhanced_prompt": "improved prompt", "was_modified": True}
        ms.update_last_user_metadata(metadata=enhancement)

        history = ms.get_history()
        user_msgs = [m for m in history if m["role"] == "user"]
        assert len(user_msgs) == 1
        stored_meta = json.loads(user_msgs[0]["metadata"])
        assert stored_meta["enhanced_prompt"] == "improved prompt"
        assert stored_meta["was_modified"] is True

    def test_update_metadata_no_user_messages(self):
        s = Session()
        s.create()
        ms = MessageStore(s.id)
        ms.add("assistant", "only assistant message")
        ms.flush()

        # Should not raise even with no user messages
        ms.update_last_user_metadata(metadata={"key": "value"})

        history = ms.get_history()
        assert len(history) == 1
        assert history[0]["role"] == "assistant"

    def test_update_metadata_empty_dict(self):
        s = Session()
        s.create()
        ms = MessageStore(s.id)
        ms.add("user", "test prompt")
        ms.flush()

        ms.update_last_user_metadata(metadata={})
        history = ms.get_history()
        user_msgs = [m for m in history if m["role"] == "user"]
        assert json.loads(user_msgs[0]["metadata"]) == {}

    def test_update_metadata_overwrites_previous(self):
        s = Session()
        s.create()
        ms = MessageStore(s.id)
        ms.add("user", "first prompt")
        ms.flush()

        ms.update_last_user_metadata(metadata={"v": 1})
        ms.update_last_user_metadata(metadata={"v": 2})

        history = ms.get_history()
        user_msgs = [m for m in history if m["role"] == "user"]
        assert json.loads(user_msgs[0]["metadata"]) == {"v": 2}


# --- LogManager tests ---


class TestLogManager:
    def test_get_log_files_empty_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sago.log_manager.get_logs_dir", lambda: tmp_path)
        monkeypatch.setattr("sago.log_manager.get_sago_home", lambda: tmp_path / "nonexistent")
        manager = LogManager(log_dir=tmp_path)
        files = manager.get_log_files()
        assert files == []

    def test_get_log_files_with_logs(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sago.log_manager.get_sago_home", lambda: tmp_path / "nonexistent")
        (tmp_path / "sago.log").write_text("test")
        (tmp_path / "sago.log.1").write_text("test")
        (tmp_path / "errors.log").write_text("test")
        (tmp_path / "not_a_log.txt").write_text("test")

        manager = LogManager(log_dir=tmp_path)
        files = manager.get_log_files()
        log_files = [f.name for f in files]
        assert "sago.log" in log_files
        assert "sago.log.1" in log_files
        assert "errors.log" in log_files
        assert "not_a_log.txt" not in log_files

    def test_parse_line_valid(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sago.log_manager.get_logs_dir", lambda: tmp_path)
        monkeypatch.setattr("sago.log_manager.get_sago_home", lambda: tmp_path / "nonexistent")
        manager = LogManager(log_dir=tmp_path)
        line = "2026-08-20 03:35:44 | INFO     | abc123def456 | sago.tui.app | Message here"
        parsed = manager.parse_line(line)
        assert parsed is not None
        assert parsed.level == "INFO"
        assert parsed.session_id == "abc123def456"
        assert parsed.module == "sago.tui.app"
        assert parsed.message == "Message here"

    def test_parse_line_invalid(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sago.log_manager.get_logs_dir", lambda: tmp_path)
        monkeypatch.setattr("sago.log_manager.get_sago_home", lambda: tmp_path / "nonexistent")
        manager = LogManager(log_dir=tmp_path)
        assert manager.parse_line("random garbage") is None
        assert manager.parse_line("") is None

    def test_read_lines_filters_by_level(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sago.log_manager.get_logs_dir", lambda: tmp_path)
        monkeypatch.setattr("sago.log_manager.get_sago_home", lambda: tmp_path / "nonexistent")
        log_content = (
            "2026-08-20 03:35:44 | INFO     | sess11111111 | mod | info msg\n"
            "2026-08-20 03:35:45 | ERROR    | sess11111111 | mod | error msg\n"
            "2026-08-20 03:35:46 | INFO     | sess11111111 | mod | another info\n"
        )
        log_file = tmp_path / "test.log"
        log_file.write_text(log_content)

        manager = LogManager(log_dir=tmp_path)
        lines = manager.read_lines(log_file, level="ERROR")
        assert len(lines) == 1
        assert lines[0].message == "error msg"

    def test_read_lines_filters_by_session(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sago.log_manager.get_logs_dir", lambda: tmp_path)
        monkeypatch.setattr("sago.log_manager.get_sago_home", lambda: tmp_path / "nonexistent")
        log_content = (
            "2026-08-20 03:35:44 | INFO     | sessaaaaaaaa | mod | msg1\n"
            "2026-08-20 03:35:45 | INFO     | sessbbbbbbbb | mod | msg2\n"
        )
        log_file = tmp_path / "test.log"
        log_file.write_text(log_content)

        manager = LogManager(log_dir=tmp_path)
        lines = manager.read_lines(log_file, session_id="sessaaaaaaaa")
        assert len(lines) == 1
        assert lines[0].session_id == "sessaaaaaaaa"

    def test_read_lines_with_limit(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sago.log_manager.get_logs_dir", lambda: tmp_path)
        monkeypatch.setattr("sago.log_manager.get_sago_home", lambda: tmp_path / "nonexistent")
        log_content = "\n".join(
            f"2026-08-20 03:35:{i:02d} | INFO     | sess00000001 | mod | msg{i}" for i in range(10)
        )
        log_file = tmp_path / "test.log"
        log_file.write_text(log_content)

        manager = LogManager(log_dir=tmp_path)
        lines = manager.read_lines(log_file, limit=3)
        assert len(lines) == 3

    def test_get_stats(self, tmp_path, monkeypatch):
        monkeypatch.setattr("sago.log_manager.get_logs_dir", lambda: tmp_path)
        monkeypatch.setattr("sago.log_manager.get_sago_home", lambda: tmp_path / "nonexistent")
        log_content = (
            "2026-08-20 03:35:44 | INFO     | sess00000001 | mod | msg1\n"
            "2026-08-20 03:35:45 | ERROR    | sess00000001 | mod | msg2\n"
        )
        log_file = tmp_path / "test.log"
        log_file.write_text(log_content)

        manager = LogManager(log_dir=tmp_path)
        stats = manager.get_stats()
        assert stats.total_lines >= 2
        assert stats.error_lines >= 1


# --- LogViewer tests ---


class TestLogViewer:
    def test_parse_since_minutes(self):
        from sago.log_viewer import _parse_since

        result = _parse_since("30m")
        assert result is not None
        expected = time.time() - 30 * 60
        assert abs(result - expected) < 2

    def test_parse_since_hours(self):
        from sago.log_viewer import _parse_since

        result = _parse_since("2h")
        assert result is not None
        expected = time.time() - 2 * 3600
        assert abs(result - expected) < 2

    def test_parse_since_days(self):
        from sago.log_viewer import _parse_since

        result = _parse_since("7d")
        assert result is not None
        expected = time.time() - 7 * 86400
        assert abs(result - expected) < 2

    def test_parse_since_weeks(self):
        from sago.log_viewer import _parse_since

        result = _parse_since("2w")
        assert result is not None
        expected = time.time() - 2 * 604800
        assert abs(result - expected) < 2

    def test_parse_since_empty(self):
        from sago.log_viewer import _parse_since

        assert _parse_since("") is None

    def test_parse_since_invalid(self):
        from sago.log_viewer import _parse_since

        assert _parse_since("abc") is None
        assert _parse_since("123") is None

    def test_colorize_level(self):
        from sago.log_viewer import _colorize_level

        text = _colorize_level("ERROR")
        assert str(text) == "ERROR"
        text = _colorize_level("INFO")
        assert str(text) == "INFO"
