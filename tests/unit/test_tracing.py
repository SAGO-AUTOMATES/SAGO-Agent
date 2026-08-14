"""Tests for the stdlib-only tracing module in sago.observability.tracing."""

from __future__ import annotations

import time

from sago.observability.tracing import (
    end_span,
    get_collector,
    get_trace,
    record_marker,
    record_token_usage,
    record_tool_call,
    span,
    start_span,
    start_trace,
    stop_trace,
    trace_tool,
)


def _reset_context() -> None:
    stop_trace()


def test_no_active_trace_is_safe_noop():
    # With no trace active, helpers must not raise or produce side effects.
    s = start_span("x")
    end_span(s)
    record_token_usage(10, 5)
    record_tool_call("t", duration=1.0, success=True)
    record_marker("k", "n")
    assert get_trace() is None
    assert get_collector() is None


def test_span_timing_and_duration():
    _reset_context()
    c = start_trace()
    s = c.start_span("op")
    time.sleep(0.01)
    c.end_span(s)
    assert s.end_time is not None
    assert s.duration is not None
    assert s.duration >= 0.01
    # get_trace reports the same duration
    trace = get_trace()
    assert trace["span_count"] == 1
    assert trace["spans"][0]["duration"] >= 0.01


def test_nested_spans_via_stack():
    _reset_context()
    c = start_trace()
    outer = c.start_span("outer")
    inner = c.start_span("inner")
    # inner should be a child of outer
    assert inner.parent_id == outer.span_id
    c.end_span(inner)
    c.end_span(outer)
    trace = get_trace()
    assert trace["span_count"] == 2
    assert len(trace["spans"]) == 1
    assert trace["spans"][0]["name"] == "outer"
    assert trace["spans"][0]["children"][0]["name"] == "inner"


def test_context_manager_span():
    _reset_context()
    start_trace()
    with span("cm") as sp:
        assert sp.parent_id is None
        assert sp.end_time is None
    assert sp.end_time is not None
    assert get_trace()["span_count"] == 1


def test_token_recording_aggregation():
    _reset_context()
    start_trace()
    record_token_usage(prompt_tokens=10, completion_tokens=5)
    record_token_usage(prompt_tokens=20, completion_tokens=7)
    trace = get_trace()
    assert trace["token_usage"]["prompt_tokens"] == 30
    assert trace["token_usage"]["completion_tokens"] == 12
    assert trace["token_usage"]["total_tokens"] == 42


def test_tool_call_recording():
    _reset_context()
    start_trace()
    record_tool_call("write_file", duration=0.5, success=True)
    record_tool_call("read_file", duration=0.2, success=False, error="boom")
    trace = get_trace()
    assert trace["tool_call_count"] == 2
    assert trace["tool_duration"] == 0.7
    assert trace["tool_calls"][0]["success"] is True
    assert trace["tool_calls"][1]["success"] is False
    assert trace["tool_calls"][1]["error"] == "boom"


def test_markers_recorded():
    _reset_context()
    start_trace()
    record_marker("step", "1", model="gpt-4o")
    trace = get_trace()
    assert any(m["kind"] == "step" for m in trace["markers"])


def test_trace_is_context_local():
    _reset_context()
    c1 = start_trace()
    c1.record_token_usage(prompt_tokens=5)
    assert get_collector() is c1
    stop_trace()
    assert get_collector() is None


def test_instrumenting_tool_does_not_change_result():
    _reset_context()
    start_trace()

    class FakeTool:
        name = "fake"

        def _run(self, x: int, y: int = 0) -> str:
            return str(x + y)

        def run(self, **kwargs):
            from sago.observability.tracing import end_span, record_tool_call, start_span

            _span = start_span(f"tool:{self.name}", tool=self.name)
            try:
                result = self._run(**kwargs)
                record_tool_call(self.name, duration=_span.duration, success=True)
                return result
            except Exception:
                record_tool_call(self.name, duration=_span.duration, success=False)
                raise
            finally:
                end_span(_span)

    t = FakeTool()
    assert t.run(x=2, y=3) == "5"
    assert t.run(x=10) == "10"

    trace = get_trace()
    assert trace["tool_call_count"] == 2
    assert all(call["success"] for call in trace["tool_calls"])


def test_trace_tool_propagates_exceptions_unchanged():
    _reset_context()
    start_trace()

    def boom():
        raise ValueError("nope")

    try:
        trace_tool("boomtool", boom)
    except ValueError as e:
        assert str(e) == "nope"
    else:
        raise AssertionError("exception was swallowed")

    trace = get_trace()
    assert trace["tool_call_count"] == 1
    assert trace["tool_calls"][0]["success"] is False
