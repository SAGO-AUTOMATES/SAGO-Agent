"""Tests for sago.utils.safe."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from sago.utils.safe import (
    log_exception,
    safe_call,
    safe_file_read,
    safe_import,
    safe_json_dumps,
    safe_json_loads,
)


class TestSafeJsonLoads:
    """Tests for safe_json_loads function."""

    def test_parses_valid_json_object(self):
        result = safe_json_loads('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parses_valid_json_array(self):
        result = safe_json_loads("[1, 2, 3]")
        assert result == [1, 2, 3]

    def test_parses_nested_json(self):
        result = safe_json_loads('{"a": {"b": [1, 2]}}')
        assert result == {"a": {"b": [1, 2]}}

    def test_returns_default_on_invalid_json(self):
        result = safe_json_loads("not valid json", default=None)
        assert result is None

    def test_returns_none_on_invalid_json_no_default(self):
        result = safe_json_loads("not valid json")
        assert result is None

    def test_returns_custom_default_on_invalid_json(self):
        result = safe_json_loads("invalid", default="fallback")
        assert result == "fallback"


class TestSafeJsonDumps:
    """Tests for safe_json_dumps function."""

    def test_serializes_dict_to_json(self):
        result = safe_json_dumps({"key": "value"})
        assert result == '{"key": "value"}'

    def test_serializes_list_to_json(self):
        result = safe_json_dumps([1, 2, 3])
        assert result == "[1, 2, 3]"

    def test_serializes_nested_structure(self):
        result = safe_json_dumps({"a": {"b": [1, 2]}})
        assert result == '{"a": {"b": [1, 2]}}'

    def test_uses_indent_when_specified(self):
        result = safe_json_dumps({"key": "value"}, indent=2)
        expected = '{\n  "key": "value"\n}'
        assert result == expected

    def test_handles_unicode_characters(self):
        result = safe_json_dumps({"emoji": "🚀", "unicode": "café"})
        assert "🚀" in result
        assert "café" in result

    def test_returns_default_on_unserializable(self):
        # Create an object that cannot be JSON serialized
        class NotSerializable:
            pass

        obj = NotSerializable()
        result = safe_json_dumps(obj, default="fallback")
        assert result == "fallback"

    def test_returns_empty_string_on_unserializable_no_default(self):
        class NotSerializable:
            pass

        obj = NotSerializable()
        result = safe_json_dumps(obj)
        assert result == ""


class TestSafeFileRead:
    """Tests for safe_file_read function."""

    def test_reads_valid_file(self, tmp_path: Path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!", encoding="utf-8")

        result = safe_file_read(str(test_file))
        assert result == "Hello, World!"

    def test_reads_binary_file_as_text(self, tmp_path: Path):
        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"binary content")

        result = safe_file_read(str(test_file))
        assert result == "binary content"

    def test_returns_empty_string_for_nonexistent_file(self):
        result = safe_file_read("/nonexistent/path/to/file.txt")
        assert result == ""

    def test_uses_custom_encoding(self, tmp_path: Path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("こんにちは", encoding="utf-8")

        result = safe_file_read(str(test_file), encoding="utf-8")
        assert result == "こんにちは"


class TestSafeImport:
    """Tests for safe_import function."""

    def test_imports_existing_module(self):
        result = safe_import("json")
        assert result is not None
        assert result.__name__ == "json"

    def test_imports_existing_submodule(self):
        result = safe_import("os.path")
        assert result is not None

    def test_returns_none_for_nonexistent_module(self):
        result = safe_import("nonexistent_module_12345")
        assert result is None


class TestSafeCall:
    """Tests for safe_call decorator."""

    def test_calls_function_normally(self):
        @safe_call
        def add(a: int, b: int) -> int:
            return a + b

        result = add(2, 3)
        assert result == 5

    def test_returns_default_on_exception(self):
        @safe_call(default=-1)
        def failing_function() -> int:
            raise ValueError("Test error")

        result = failing_function()
        assert result == -1

    def test_returns_none_on_exception_no_default(self):
        @safe_call
        def failing_function() -> int:
            raise ValueError("Test error")

        result = failing_function()
        assert result is None

    def test_passes_arguments_correctly(self):
        @safe_call(default={})
        def make_dict(a: str, b: int, c: bool = True) -> dict:
            return {"a": a, "b": b, "c": c}

        result = make_dict("test", 42, c=False)
        assert result == {"a": "test", "b": 42, "c": False}


class TestLogException:
    """Tests for log_exception function."""

    def test_logs_exception_with_context(self, caplog: pytest.LogCaptureFixture):
        with caplog.at_level(logging.DEBUG):
            try:
                raise ValueError("test error")
            except ValueError as e:
                log_exception(e, context="Test context")

        assert "Test context" in caplog.text
        assert "ValueError" in caplog.text
        assert "test error" in caplog.text

    def test_logs_exception_without_context(self, caplog: pytest.LogCaptureFixture):
        with caplog.at_level(logging.DEBUG):
            try:
                raise RuntimeError("error message")
            except RuntimeError as e:
                log_exception(e)

        assert "RuntimeError" in caplog.text
        assert "error message" in caplog.text

    def test_logs_with_custom_level(self, caplog: pytest.LogCaptureFixture):
        with caplog.at_level(logging.INFO):
            try:
                raise TypeError("type error")
            except TypeError as e:
                log_exception(e, level=logging.INFO)

        assert "TypeError" in caplog.text

    def test_includes_traceback_when_requested(self, caplog: pytest.LogCaptureFixture):
        with caplog.at_level(logging.DEBUG):
            try:
                raise ValueError("trace test")
            except ValueError as e:
                log_exception(e, include_traceback=True)

        assert "traceback" in caplog.text.lower() or "Traceback" in caplog.text
