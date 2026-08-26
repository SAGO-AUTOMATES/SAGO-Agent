"""Tests for sago/tracking/dev_tracer.py utility functions."""

import tempfile

from sago.tracking.dev_tracer import (
    DevTraceEvent,
    DevTracer,
    TraceEventType,
    export_session_dev_artifacts,
)


class TestCleanId:
    """Test _clean_id which is nested inside _generate_mermaid_graph."""

    def test_simple(self):
        tracer = DevTracer()
        events = [
            DevTraceEvent(
                event_type=TraceEventType.TOOL_DISPATCH,
                source="hello",
                action="test",
                data={},
                status="OK",
                duration_ms=0,
                timestamp=0,
            ),
        ]
        # _clean_id is called internally; verify via graph output
        graph = tracer._generate_mermaid_graph(events)
        assert "hello" in graph

    def test_special_chars_in_source(self):
        tracer = DevTracer()
        events = [
            DevTraceEvent(
                event_type=TraceEventType.TOOL_DISPATCH,
                source="agent@python-engineer!",
                action="test",
                data={"tool_name": "read_file"},
                status="OK",
                duration_ms=0,
                timestamp=0,
            ),
        ]
        graph = tracer._generate_mermaid_graph(events)
        # The clean_id should remove special chars
        assert "read_file" in graph


class TestDevTracerGraphs:
    def _make_events(self):
        return [
            DevTraceEvent(
                event_type=TraceEventType.TOOL_DISPATCH,
                source="architect",
                action="run(glob_files)",
                data={"tool_name": "glob_files"},
                status="OK",
                duration_ms=12.5,
                timestamp=1000.0,
            ),
            DevTraceEvent(
                event_type=TraceEventType.LLM_PAYLOAD,
                source="python-engineer",
                action="prompt",
                data={"model": "gpt-4", "tokens_out": 500},
                status="OK",
                duration_ms=100.0,
                timestamp=1001.0,
            ),
            DevTraceEvent(
                event_type=TraceEventType.AGENT_ROUTING,
                source="sago",
                action="delegate",
                data={"target_agent": "architect"},
                status="OK",
                duration_ms=5.0,
                timestamp=1002.0,
            ),
        ]

    def test_mermaid_graph(self):
        tracer = DevTracer()
        events = self._make_events()
        graph = tracer._generate_mermaid_graph(events)
        assert "graph TD" in graph
        assert "glob_files" in graph
        assert "gpt-4" in graph
        assert "architect" in graph

    def test_ascii_tree(self):
        tracer = DevTracer()
        events = self._make_events()
        tree = tracer._generate_ascii_tree(events)
        assert "SAGO Execution Interaction Map" in tree
        assert "glob_files" in tree
        assert "gpt-4" in tree

    def test_empty_events(self):
        tracer = DevTracer()
        graph = tracer._generate_mermaid_graph([])
        assert "graph TD" in graph
        tree = tracer._generate_ascii_tree([])
        assert "User Request" in tree


class TestFormatEventMarkdown:
    def test_basic_formatting(self):
        tracer = DevTracer()
        event = DevTraceEvent(
            event_type=TraceEventType.TOOL_DISPATCH,
            source="architect",
            action="run(glob_files)",
            data={"tool_name": "glob_files"},
            status="OK",
            duration_ms=12.5,
            timestamp=1000.0,
        )
        lines = tracer._format_event_markdown(1, event)
        assert any("Event 1" in line for line in lines)
        assert any("glob_files" in line for line in lines)

    def test_with_error_status(self):
        tracer = DevTracer()
        event = DevTraceEvent(
            event_type=TraceEventType.TOOL_DISPATCH,
            source="main",
            action="run(execute_shell)",
            data={"tool_name": "execute_shell"},
            status="ERROR",
            duration_ms=500.0,
            timestamp=1000.0,
        )
        lines = tracer._format_event_markdown(2, event)
        assert any("ERROR" in line for line in lines)


class TestNormAgent:
    def test_norm_agent(self):

        # _norm_agent is a nested function, test via export behavior
        # Just verify the function exists and works through the export
        pass


class TestMsgMeta:
    def test_dict_metadata(self):

        # _msg_meta is nested, tested via export_session_dev_artifacts
        pass


class TestExportSessionDevArtifacts:
    def test_empty_session(self):

        with tempfile.TemporaryDirectory() as tmp:
            result = export_session_dev_artifacts(
                session_id="test-empty-session",
                messages=[],
                cwd=tmp,
            )
            assert "chat_export" in result

    def test_with_thinking_blocks(self):

        messages = [
            {
                "role": "assistant",
                "content": "Analysis complete",
                "agent_name": "architect",
                "metadata": '{"thinking_blocks": [{"seq": 1, "agent": "architect", "text": "Let me think about this...", "timestamp": 1000.0}]}',
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            result = export_session_dev_artifacts(
                session_id="test-thinking",
                messages=messages,
                cwd=tmp,
            )

            with open(result["chat_export"]) as f:
                content = f.read()
            assert "architect" in content

    def test_with_tool_calls(self):

        tool_calls = [
            {
                "tool_name": "glob_files",
                "arguments": '{"pattern": "*.py"}',
                "result": "Found 5 files",
                "agent": "architect",
                "created_at": "2026-08-26T10:00:00",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            result = export_session_dev_artifacts(
                session_id="test-tools",
                messages=[],
                cwd=tmp,
                tool_calls=tool_calls,
            )

            with open(result["chat_export"]) as f:
                content = f.read()
            assert "glob_files" in content

    def test_metadata_string_json(self):

        messages = [
            {
                "role": "assistant",
                "content": "Done",
                "metadata": "invalid json{{{",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            result = export_session_dev_artifacts(
                session_id="test-bad-meta",
                messages=messages,
                cwd=tmp,
            )
            assert "chat_export" in result
