from unittest.mock import MagicMock, patch

from sago.log_manager import LogFileInfo, LogLine, LogManager, LogStats
from sago.log_viewer import (
    _colorize_level,
    _parse_since,
    display_logs,
    display_sessions,
    display_stats,
    export_logs,
    follow_logs,
)


def test_colorize_level():
    assert _colorize_level("DEBUG").plain == "DEBUG"
    assert _colorize_level("INFO").plain == "INFO"
    assert _colorize_level("WARNING").plain == "WARNING"
    assert _colorize_level("ERROR").plain == "ERROR"
    assert _colorize_level("CRITICAL").plain == "CRITICAL"
    assert _colorize_level("UNKNOWN").plain == "UNKNOWN"


def test_parse_since():
    assert _parse_since("") is None
    assert _parse_since("invalid") is None
    now_m = _parse_since("10m")
    assert now_m is not None
    now_h = _parse_since("2h")
    assert now_h is not None
    now_d = _parse_since("1d")
    assert now_d is not None
    now_w = _parse_since("1w")
    assert now_w is not None

    iso_ts = _parse_since("2026-01-01T00:00:00")
    assert iso_ts is not None


def test_display_logs_empty(tmp_path):
    mgr = MagicMock(spec=LogManager)
    mgr.get_log_files.return_value = []
    with patch("sago.log_viewer.console.print") as mock_print:
        display_logs(mgr)
        mock_print.assert_called()


def test_display_logs_with_data(tmp_path):
    mgr = MagicMock(spec=LogManager)
    mgr.get_log_files.return_value = [tmp_path / "app.log"]
    mgr.read_lines.return_value = [
        LogLine(
            timestamp="2026-01-01 12:00:00",
            level="INFO",
            session_id="sess_1",
            module="test_mod",
            message="Test message",
        )
    ]
    with patch("sago.log_viewer.console.print") as mock_print:
        display_logs(mgr, limit=10)
        mock_print.assert_called()


def test_display_stats(tmp_path):
    mgr = MagicMock(spec=LogManager)
    finfo = LogFileInfo(
        path=tmp_path / "app.log",
        size_bytes=1024,
        modified_time=1700000000.0,
        line_count=100,
    )
    stats = LogStats(
        total_files=1,
        total_size_bytes=1024,
        total_lines=100,
        total_sessions=1,
        debug_lines=10,
        info_lines=70,
        warning_lines=10,
        error_lines=10,
        date_range=("2026-01-01", "2026-01-02"),
        top_modules=[("module_a", 50), ("module_b", 50)],
        top_errors=[("An error occurred", 5)],
        files=[finfo],
    )
    mgr.get_stats.return_value = stats

    with patch("sago.log_viewer.console.print") as mock_print:
        # Full stats
        display_stats(mgr, quick=False)
        assert mock_print.call_count >= 1

        # Quick stats
        display_stats(mgr, quick=True)
        assert mock_print.call_count >= 2


def test_display_sessions():
    mgr = MagicMock(spec=LogManager)
    mgr.get_sessions.return_value = []
    with patch("sago.log_viewer.console.print") as mock_print:
        display_sessions(mgr)
        mock_print.assert_called()

    mgr.get_sessions.return_value = ["sess_1", "sess_2"]
    with patch("sago.log_viewer.console.print") as mock_print:
        display_sessions(mgr)
        mock_print.assert_called()


def test_export_logs(tmp_path):
    mgr = MagicMock(spec=LogManager)
    mgr.get_log_files.return_value = [tmp_path / "app.log"]
    mgr.read_lines.return_value = [
        LogLine(
            timestamp="2026-01-01 12:00:00",
            level="INFO",
            session_id="sess_1",
            module="test_mod",
            message="Export line",
        )
    ]
    out_file = tmp_path / "exported.log"
    with patch("sago.log_viewer.console.print"):
        export_logs(mgr, str(out_file))

    assert out_file.exists()
    content = out_file.read_text()
    assert "Export line" in content


def test_follow_logs(tmp_path):
    mgr = MagicMock(spec=LogManager)
    mgr.get_log_files.return_value = []
    # Test empty files
    with patch("sago.log_viewer.console.print"):
        follow_logs(mgr)

    # Test loop interrupted
    log_file = tmp_path / "follow.log"
    log_file.write_text("2026-01-01 12:00:00 [INFO] test: message\n")
    mgr.get_log_files.return_value = [log_file]
    mgr.parse_line.return_value = LogLine(
        timestamp="2026-01-01 12:00:00",
        level="INFO",
        session_id="sess",
        module="test",
        message="message",
    )

    with (
        patch("sago.log_viewer.console.print"),
        patch("time.sleep", side_effect=KeyboardInterrupt),
    ):
        follow_logs(mgr, interval=0.01)
