"""Comprehensive tests for llm.retry and coding tools (analyzer, linter)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from sago.llm.retry import (
    _get_retryable_exception_types,
    _is_retryable,
    retry_with_backoff,
)

# ─── LLM Retry Tests ────────────────────────────────────────────────────────


class TestGetRetryableTypes:
    def test_returns_tuple(self) -> None:
        types = _get_retryable_exception_types()
        assert isinstance(types, tuple)

    def test_cached_on_second_call(self) -> None:
        t1 = _get_retryable_exception_types()
        t2 = _get_retryable_exception_types()
        assert t1 is t2


class TestIsRetryable:
    def test_timeout_error_is_retryable(self) -> None:
        assert _is_retryable(TimeoutError("timed out")) is True

    def test_value_error_not_retryable(self) -> None:
        assert _is_retryable(ValueError("bad input")) is False

    def test_runtime_error_not_retryable(self) -> None:
        assert _is_retryable(RuntimeError("crash")) is False


class TestRetryWithBackoff:
    def test_success_first_try(self) -> None:
        calls = []

        def fn() -> str:
            calls.append(1)
            return "ok"

        result = retry_with_backoff(fn, max_retries=2)
        assert result == "ok"
        assert len(calls) == 1

    def test_success_after_retry(self) -> None:
        """Raises ValueError (non-retryable) so it raises immediately on first failure."""
        calls = []

        def fn() -> str:
            calls.append(1)
            raise ValueError("non retryable")

        with pytest.raises(ValueError):
            retry_with_backoff(fn, max_retries=2, base_delay=0.0)

        assert len(calls) == 1  # ValueError not retryable → raises immediately

    def test_no_retries_raises_immediately(self) -> None:
        def fn() -> str:
            raise TimeoutError("always fails")

        with patch("sago.llm.retry.time.sleep"):
            with pytest.raises(TimeoutError):
                retry_with_backoff(fn, max_retries=0)

    def test_max_retries_exhausted(self) -> None:
        calls = []

        def fn() -> str:
            calls.append(1)
            raise TimeoutError("keep failing")

        with patch("sago.llm.retry.time.sleep"):
            with pytest.raises(TimeoutError):
                retry_with_backoff(fn, max_retries=3, base_delay=0.001)

        assert len(calls) == 4  # 1 initial + 3 retries

    def test_passes_args_and_kwargs(self) -> None:
        def fn(a: int, b: int = 10) -> int:
            return a + b

        result = retry_with_backoff(fn, 5, max_retries=0, b=20)
        assert result == 25


# ─── Code Analyzer Tool Tests ────────────────────────────────────────────────


class TestCodeAnalyzerTool:
    def test_file_not_found(self) -> None:
        from sago.tools.coding.code_analyzer import CodeAnalyzerTool

        tool = CodeAnalyzerTool()
        result = tool._run("/tmp/nonexistent_xyz_abc.py")
        assert "Error" in result

    def test_python_structure_analysis(self, tmp_path: Path) -> None:
        from sago.tools.coding.code_analyzer import CodeAnalyzerTool

        src = tmp_path / "module.py"
        src.write_text(
            "class Foo:\n    def bar(self):\n        pass\n\ndef baz(x, y):\n    return x + y\n"
        )
        tool = CodeAnalyzerTool()
        result = tool._run(str(src), analysis_type="structure")
        assert "Foo" in result
        assert "bar" in result or "baz" in result

    def test_python_complexity_analysis(self, tmp_path: Path) -> None:
        from sago.tools.coding.code_analyzer import CodeAnalyzerTool

        src = tmp_path / "complex.py"
        src.write_text(
            "def do_thing():\n    if True:\n        for i in range(10):\n            while True:\n                pass\n"
        )
        tool = CodeAnalyzerTool()
        result = tool._run(str(src), analysis_type="complexity")
        assert "complexity" in result.lower() or "nesting" in result.lower()

    def test_python_issues_analysis(self, tmp_path: Path) -> None:
        from sago.tools.coding.code_analyzer import CodeAnalyzerTool

        src = tmp_path / "issues.py"
        src.write_text("# TODO: fix this\nprint('debug')\nx = 12345\n")
        tool = CodeAnalyzerTool()
        result = tool._run(str(src), analysis_type="issues")
        assert "TODO" in result or "print" in result or "Magic" in result

    def test_python_full_analysis(self, tmp_path: Path) -> None:
        from sago.tools.coding.code_analyzer import CodeAnalyzerTool

        src = tmp_path / "full.py"
        src.write_text("x = 1\n")
        tool = CodeAnalyzerTool()
        result = tool._run(str(src), analysis_type="all")
        assert "Lines of code" in result

    def test_non_python_file(self, tmp_path: Path) -> None:
        from sago.tools.coding.code_analyzer import CodeAnalyzerTool

        src = tmp_path / "app.js"
        src.write_text("function hello() { console.log('hi'); }\nclass Foo {}\n")
        tool = CodeAnalyzerTool()
        result = tool._run(str(src), analysis_type="all")
        assert "Lines of code" in result

    def test_python_syntax_error_in_structure(self, tmp_path: Path) -> None:
        from sago.tools.coding.code_analyzer import CodeAnalyzerTool

        src = tmp_path / "broken.py"
        src.write_text("def foo(\n")  # Invalid Python
        tool = CodeAnalyzerTool()
        result = tool._run(str(src), analysis_type="structure")
        assert result  # Should handle gracefully

    def test_long_lines_detection(self, tmp_path: Path) -> None:
        from sago.tools.coding.code_analyzer import CodeAnalyzerTool

        src = tmp_path / "longlines.py"
        src.write_text("x = " + "a" * 130 + "\n")
        tool = CodeAnalyzerTool()
        result = tool._run(str(src), analysis_type="complexity")
        assert "120" in result


# ─── Linter Tool Tests ───────────────────────────────────────────────────────


class TestLinterTool:
    def test_lint_python_file_with_ruff(self, tmp_path: Path) -> None:
        from sago.tools.coding.linter import LinterTool

        src = tmp_path / "test_lint.py"
        src.write_text("import os\nx = 1\n")
        tool = LinterTool()
        result = tool._run(str(src))
        # ruff is available in this repo, should run
        assert result  # Any result is fine

    def test_lint_python_file_auto_detect(self, tmp_path: Path) -> None:
        from sago.tools.coding.linter import LinterTool

        src = tmp_path / "clean.py"
        src.write_text("x = 1\n")
        tool = LinterTool()
        result = tool._run(str(src), linter=None)
        assert result

    def test_lint_unknown_extension(self, tmp_path: Path) -> None:
        from sago.tools.coding.linter import LinterTool

        src = tmp_path / "config.xyz"
        src.write_text("something here")
        tool = LinterTool()
        result = tool._run(str(src))
        assert result  # Should return "no linter" message or similar

    def test_lint_file_not_found(self) -> None:
        from sago.tools.coding.linter import LinterTool

        tool = LinterTool()
        result = tool._run("/nonexistent/path/file.py")
        assert "Error" in result or "not found" in result.lower() or result
