"""Tests for ContinuousVerifier and targeted file verification."""

from __future__ import annotations

import tempfile
from pathlib import Path

from sago.engine.verifier import ContinuousVerifier, ProjectVerifier


def test_project_verifier_verify_files() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        py_file = tmp_path / "valid.py"
        py_file.write_text("x: int = 42\nprint(x)\n", encoding="utf-8")

        verifier = ProjectVerifier(root_dir=tmp_path)
        report = verifier.verify_files([py_file])
        assert report.passed is True
        assert report.linter_passed is True
        assert len(report.issues) == 0


def test_project_verifier_syntax_error() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        bad_py = tmp_path / "bad.py"
        bad_py.write_text("def broken_syntax(\n", encoding="utf-8")

        verifier = ProjectVerifier(root_dir=tmp_path)
        report = verifier.verify_files([bad_py])
        assert report.passed is False
        assert len(report.issues) > 0
        assert report.issues[0].rule == "SYNTAX_ERROR"


def test_continuous_verifier_background_queue() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        test_file = tmp_path / "sample.py"
        test_file.write_text("a = 10\n", encoding="utf-8")

        cv = ContinuousVerifier(root_dir=tmp_path)
        try:
            cv.enqueue_files([test_file])
            import time

            time.sleep(0.5)
            report = cv.get_latest_report()
            assert report is not None
            assert report.passed is True
        finally:
            cv.stop()
