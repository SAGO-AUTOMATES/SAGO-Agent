"""Unit tests for the central error-handling / structured-logging layer."""

import logging

import pytest

from sago.utils.errors import handle_errors, log_error


class TestLogError:
    def test_emits_message_without_exc(self, caplog):
        with caplog.at_level(logging.ERROR, logger="sago"):
            log_error("something failed")
        assert any("something failed" in r.message for r in caplog.records)
        assert caplog.records[-1].levelno == logging.ERROR

    def test_emits_with_exception_and_context(self, caplog):
        with caplog.at_level(logging.WARNING, logger="sago"):
            log_error(
                "boom",
                ValueError("bad value"),
                level=logging.WARNING,
                context={"task_id": 42},
            )
        record = caplog.records[-1]
        assert "boom" in record.message
        assert record.levelno == logging.WARNING
        assert record.exc_info is not None
        assert "task_id=42" in record.message

    def test_custom_level(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="sago"):
            log_error("debug thing", level=logging.DEBUG)
        assert caplog.records[-1].levelno == logging.DEBUG


class TestHandleErrors:
    def test_returns_default_on_failure(self):
        @handle_errors(default="fallback")
        def boom():
            raise RuntimeError("nope")

        assert boom() == "fallback"

    def test_reraises_when_configured(self):
        @handle_errors(reraise=True)
        def boom():
            raise RuntimeError("nope")

        with pytest.raises(RuntimeError):
            boom()

    def test_passes_through_on_success(self):
        @handle_errors(default="fallback")
        def ok():
            return 123

        assert ok() == 123

    def test_logs_on_failure(self, caplog):
        @handle_errors(default=None, log_level=logging.ERROR)
        def boom():
            raise KeyError("missing")

        with caplog.at_level(logging.ERROR, logger="sago"):
            boom()
        assert any("boom" in r.message for r in caplog.records)
        assert caplog.records[-1].exc_info is not None
