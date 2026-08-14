"""Tests for DevTracer telemetry and developer mode features."""

from sago.tracking.dev_tracer import DevTracer, TraceEventType, get_dev_tracer


def test_dev_tracer_singleton():
    t1 = get_dev_tracer()
    t2 = get_dev_tracer()
    assert t1 is t2


def test_dev_tracer_recording_and_listener():
    tracer = DevTracer(max_events=100)
    tracer.set_enabled(True)

    received_events = []
    tracer.add_listener(lambda ev: received_events.append(ev))

    tracer.record(
        event_type=TraceEventType.FUNCTION_CALL,
        source="test_module",
        action="execute",
        data={"param1": 123},
        duration_ms=4.5,
    )

    assert len(received_events) == 1
    ev = received_events[0]
    assert ev.source == "test_module"
    assert ev.action == "execute"
    assert ev.data["param1"] == 123
    assert "test_module -> execute" in ev.format_line()


def test_dev_tracer_trace_block():
    tracer = DevTracer(max_events=50)
    tracer.set_enabled(True)

    with tracer.trace_block(source="engine", action="compile", data={"opt": True}) as data:
        data["steps"] = 3

    traces = tracer.get_recent_traces()
    assert len(traces) == 2
    assert traces[0].action == "START: compile"
    assert traces[1].action == "FINISH: compile"
    assert traces[1].data["steps"] == 3
    assert traces[1].duration_ms >= 0


def test_dev_tracer_clear():
    tracer = DevTracer()
    tracer.record(TraceEventType.LOG_EVENT, "logger", "msg")
    assert len(tracer.get_recent_traces()) == 1
    tracer.clear()
    assert len(tracer.get_recent_traces()) == 0


def test_dev_tracer_export(tmp_path):
    tracer = DevTracer()
    tracer.record(TraceEventType.LLM_PAYLOAD, "llm", "create", data={"model": "gpt-4o"})
    tracer.record(TraceEventType.TOOL_DISPATCH, "dispatcher", "run", data={"tool": "read_file"})

    json_file = tmp_path / "traces.json"
    ok, path = tracer.export_traces(json_file, format="json")
    assert ok is True
    assert json_file.exists()

    md_file = tmp_path / "traces.md"
    ok, path = tracer.export_traces(md_file, format="md")
    assert ok is True
    assert md_file.exists()
