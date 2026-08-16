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
    md_file = tmp_path / "traces.md"
    ok, path = tracer.export_traces(md_file, format="md")
    assert ok is True
    assert md_file.exists()


def test_export_session_dev_artifacts(tmp_path):
    from sago.tracking.dev_tracer import export_session_dev_artifacts, get_dev_tracer

    tracer = get_dev_tracer()
    tracer.set_enabled(True)
    tracer.record(TraceEventType.TOOL_DISPATCH, "executor", "grep_search", data={"query": "test"})

    messages = [
        {"role": "user", "content": "Hello, build an API"},
        {
            "role": "assistant",
            "agent_name": "nextjs-engineer",
            "content": "Here is the Next.js API route.",
        },
    ]

    session_id = "test_sess_12345"
    artifacts = export_session_dev_artifacts(session_id=session_id, messages=messages, cwd=tmp_path)

    assert "chat_export" in artifacts
    assert "trace_md" in artifacts
    assert "trace_json" in artifacts

    chat_path = tmp_path / ".sago" / "data" / session_id / "chat_export.md"
    trace_md_path = tmp_path / ".sago" / "data" / session_id / "trace.md"
    trace_json_path = tmp_path / ".sago" / "data" / session_id / "trace.json"

    assert chat_path.exists()
    assert trace_md_path.exists()
    assert trace_json_path.exists()

    chat_content = chat_path.read_text(encoding="utf-8")
    assert "SAGO Session Transcript Export" in chat_content
    assert "test_sess_12345" in chat_content
    assert "nextjs-engineer" in chat_content


def test_is_dev_mode_enabled(tmp_path, monkeypatch):
    from sago.config.loader import is_dev_mode_enabled

    # 1. Via environment variable
    monkeypatch.setenv("SAGO_DEV_MODE", "true")
    assert is_dev_mode_enabled() is True

    monkeypatch.setenv("SAGO_DEV_MODE", "0")
    assert is_dev_mode_enabled() is False

    monkeypatch.delenv("SAGO_DEV_MODE", raising=False)
