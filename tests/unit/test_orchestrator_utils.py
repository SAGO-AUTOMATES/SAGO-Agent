"""Tests for sago/tui/orchestrator.py utility functions."""

import tempfile
from pathlib import Path

from sago.tui.orchestrator import (
    _detect_file_count_for_task,
    _direct_simple_analyze,
    _is_error_result,
    _is_simple_analyze_task,
)


class TestIsErrorResult:
    def test_empty(self):
        assert _is_error_result("") is False
        assert _is_error_result("  ") is False

    def test_none(self):
        assert _is_error_result(None) is False

    def test_strong_error_start(self):
        assert _is_error_result("Error: file not found") is True
        assert _is_error_result("ERROR: connection refused") is True
        assert _is_error_result("Traceback (most recent call last):") is True
        assert _is_error_result("permission denied") is True
        assert _is_error_result("Execution error: file not found") is True

    def test_embedded_error_markers(self):
        assert _is_error_result("could not be spawned: permission denied") is True
        assert _is_error_result("last error: connection refused") is True

    def test_rate_limit(self):
        assert _is_error_result("rate limit exceeded, try again") is True
        assert _is_error_result("Rate limit hit after 100 requests") is True

    def test_not_error(self):
        assert _is_error_result("no errors found") is False
        assert _is_error_result("0 failed tests") is False
        assert _is_error_result("Found 5 files matching *.py") is False
        assert _is_error_result("Successfully wrote 3 files") is False

    def test_error_in_middle_not_error(self):
        assert _is_error_result("The file contains no errors") is False
        assert _is_error_result("Analysis complete: 0 errors, 3 warnings") is False


class TestDetectFileCountForTask:
    def test_no_path(self):
        assert _detect_file_count_for_task("analyze the codebase") is None

    def test_nonexistent_path(self):
        assert _detect_file_count_for_task("analyze /nonexistent/path/to/dir") is None

    def test_single_file(self):
        with tempfile.NamedTemporaryFile(suffix=".py") as f:
            count = _detect_file_count_for_task(f"analyze {f.name}")
            assert count == 1

    def test_small_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(3):
                Path(tmp, f"file{i}.py").write_text("pass")
            count = _detect_file_count_for_task(f"analyze {tmp}")
            assert count == 3

    def test_large_directory_capped(self):
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(60):
                Path(tmp, f"file{i}.py").write_text("pass")
            count = _detect_file_count_for_task(f"analyze {tmp}")
            assert count <= 51  # capped (breaks when count > 50, returns 51)

    def test_skips_hidden_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "visible.py").write_text("pass")
            hidden = Path(tmp, ".hidden")
            hidden.mkdir()
            (hidden / ".secret.py").write_text("pass")
            count = _detect_file_count_for_task(f"analyze {tmp}")
            assert count == 1

    def test_skips_pycache(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "main.py").write_text("pass")
            cache = Path(tmp, "__pycache__")
            cache.mkdir()
            (cache, "module.pyc").__class__  # just to show intent
            Path(cache, "module.pyc").write_bytes(b"\x00")
            count = _detect_file_count_for_task(f"analyze {tmp}")
            assert count == 1

    def test_skips_md_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "code.py").write_text("pass")
            Path(tmp, "README.md").write_text("# Title")
            count = _detect_file_count_for_task(f"analyze {tmp}")
            assert count == 1


class TestIsSimpleAnalyzeTask:
    def test_not_analyze(self):
        assert _is_simple_analyze_task("create a file") is False
        assert _is_simple_analyze_task("fix the bug") is False

    def test_analyze_no_path(self):
        assert _is_simple_analyze_task("analyze the codebase") is False

    def test_analyze_small_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(3):
                Path(tmp, f"file{i}.py").write_text("pass")
            assert _is_simple_analyze_task(f"analyze {tmp}") is True

    def test_analyze_large_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(10):
                Path(tmp, f"file{i}.py").write_text("pass")
            assert _is_simple_analyze_task(f"analyze {tmp}") is False


class TestDirectSimpleAnalyze:
    def test_returns_none_for_no_path(self):
        assert _direct_simple_analyze("analyze the codebase") is None

    def test_returns_none_for_too_many_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(10):
                Path(tmp, f"file{i}.py").write_text("pass")
            assert _direct_simple_analyze(f"analyze {tmp}") is None

    def test_returns_none_for_nonexistent(self):
        assert _direct_simple_analyze("analyze /nonexistent/dir") is None
