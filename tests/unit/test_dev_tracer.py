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


def _multi_agent_messages(now):
    """Fake session: 2 agents with per-step thinking blocks (regression data)."""
    return [
        {"role": "user", "content": "Inspect and fix", "timestamp": now},
        {
            "role": "assistant",
            "agent_name": "architect",
            "content": "Plan ready.",
            "timestamp": now + 10,
            "metadata": {
                "thinking_blocks": [
                    {
                        "seq": 1,
                        "agent": "architect",
                        "text": "Key finding: target dir exists and is not empty.",
                        "timestamp": now + 5,
                    },
                ],
            },
        },
        {
            "role": "assistant",
            "agent_name": "python-engineer",
            "content": "Timed out after 300s (9 iterations completed)",
            "timestamp": now + 400,
            "metadata": {
                "thinking_blocks": [
                    {
                        "seq": 2,
                        "agent": "python-engineer",
                        "text": "Reading main.py first, then patching the loop guard.",
                        "timestamp": now + 100,
                    },
                ],
            },
        },
    ]


def test_export_includes_reasoning_timeline_for_all_agents(tmp_path):
    import time as time_mod

    from sago.tracking.dev_tracer import export_session_dev_artifacts

    now = time_mod.time()
    messages = _multi_agent_messages(now)
    tool_calls = [
        {
            "tool": "list_directory",
            "args": {"path": "/tmp/x"},
            "result": "main.py",
            "success": True,
            "agent": "architect",
        },
        {
            "tool": "read_file",
            "args": {"file_path": "/tmp/x/main.py"},
            "result": "X" * 9000,  # > 4000 chars
            "success": True,
            "agent": "python-engineer",
        },
    ]

    artifacts = export_session_dev_artifacts(
        session_id="timeline_sess", messages=messages, cwd=tmp_path, tool_calls=tool_calls
    )
    chat = (tmp_path / ".sago" / "data" / "timeline_sess" / "chat_export.md").read_text(
        encoding="utf-8"
    )

    assert "## Reasoning Timeline" in chat
    assert "Key finding: target dir exists" in chat
    assert "Reading main.py first" in chat
    assert "`@architect`" in chat
    assert "`@python-engineer`" in chat
    assert "**Reasoning Blocks**: 2" in chat
    assert artifacts["chat_export"]


def test_export_tool_usage_by_agent_and_outputs_section(tmp_path):
    from sago.tracking.dev_tracer import export_session_dev_artifacts

    tool_calls = [
        {
            "tool": "edit_file",
            "args": {"file_path": "/w/src/main.py"},
            "result": "patched",
            "success": True,
            "agent": "python-engineer",
        },
        {
            "tool": "write_file",
            "args": {"path": "/w/FIXES.md"},
            "result": "written",
            "success": True,
            "agent": "@Python-Engineer",  # normalization check
        },
        {
            "tool": "read_file",
            "args": {"file_path": "/w/other.py"},
            "result": "Y" * 5000,
            "success": True,
            "agent": "architect",
        },
    ]

    export_session_dev_artifacts(
        session_id="outputs_sess", messages=[{"role": "user", "content": "go"}],
        cwd=tmp_path, tool_calls=tool_calls,
    )
    chat = (tmp_path / ".sago" / "data" / "outputs_sess" / "chat_export.md").read_text(
        encoding="utf-8"
    )

    assert "## Tool Usage by Agent" in chat
    assert "`@python-engineer` — 2 calls" in chat
    assert "`@architect` — 1 calls" in chat
    assert "## Outputs" in chat
    assert "`/w/src/main.py`" in chat
    assert "`/w/FIXES.md`" in chat
    # read_file is NOT an output tool
    assert "/w/other.py` — via `write_file" not in chat
    # Result raised to 4000-char cap with truncation note
    assert ("Y" * 4000) in chat
    assert "truncated to first 4000 chars" in chat


def test_export_flushes_shared_store_queues(tmp_path, monkeypatch):
    """Pending rows queued on one store instance must be flushed by another."""
    db_path = tmp_path / "flush.db"
    monkeypatch.setattr("sago.database.get_db_path", lambda: db_path)
    from sago.database import (
        MessageStore,
        Session,
        ToolUsageStore,
        _connections,
        _pool_lock,
        init_db,
    )

    with _pool_lock:
        _connections.clear()
    init_db()

    s = Session("flush_sess")
    s.create()
    s.close()

    writer_ms = MessageStore("flush_sess")
    writer_ms.add(role="user", content="queued-not-flushed")
    writer_tu = ToolUsageStore("flush_sess")
    writer_tu.log(tool_name="probe_tool", agent="tester")

    # Fresh instances (as the dev-artifact exporter creates) drain them
    MessageStore("flush_sess").flush()
    rows_ms = MessageStore("flush_sess").get_history()
    ToolUsageStore("flush_sess").flush()
    rows_tu = ToolUsageStore("flush_sess").get_all()

    assert any(m["content"] == "queued-not-flushed" for m in rows_ms)
    assert any(t["tool_name"] == "probe_tool" for t in rows_tu)
    assert rows_tu[0]["agent"] == "tester"
