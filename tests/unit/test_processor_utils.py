"""Tests for sago/tui/processor.py utility functions."""

from sago.tui.processor import _build_local_summary_markdown, _is_summary_intent


class TestIsSummaryIntent:
    def test_empty(self):
        assert _is_summary_intent("") is False
        assert _is_summary_intent("  ") is False
        assert _is_summary_intent(None) is False

    def test_spec_regex(self):
        assert _is_summary_intent("so what was the summary") is True
        assert _is_summary_intent("what was the summary?") is True
        assert _is_summary_intent("summarize what you did") is True
        assert _is_summary_intent("what did you do") is True
        assert _is_summary_intent("what was done") is True

    def test_typo_tolerant(self):
        assert _is_summary_intent("so what was the sumamry") is True
        assert _is_summary_intent("sumamry of what you did") is True
        assert _is_summary_intent("summarise what was done") is True

    def test_short_generic_summar(self):
        assert _is_summary_intent("summary") is True
        assert _is_summary_intent("show me the summary") is True
        assert _is_summary_intent("give me a summary") is True

    def test_file_specific_not_summary(self):
        assert _is_summary_intent("summarize this file") is False
        assert _is_summary_intent("summarize README.md") is False
        assert _is_summary_intent("summarize the main.py file") is False
        assert _is_summary_intent("#file summarize this") is False

    def test_file_specific_with_what_did(self):
        assert _is_summary_intent("summarize this file, what did you do") is True

    def test_long_non_summary(self):
        long_msg = (
            "summarize the entire codebase including all tests and documentation for the project"
        )
        assert _is_summary_intent(long_msg) is False

    def test_not_summary(self):
        assert _is_summary_intent("hello world") is False
        assert _is_summary_intent("read the file") is False
        assert _is_summary_intent("what is 2+2") is False


class TestBuildLocalSummaryMarkdown:
    def test_empty(self):
        result = _build_local_summary_markdown([], [])
        assert "Summary" in result

    def test_with_messages_and_tools(self):
        messages = [
            {"role": "user", "content": "analyze this"},
            {"role": "assistant", "content": "Here is the analysis", "agent_name": "architect"},
        ]
        tool_calls = [
            {
                "tool": "glob_files",
                "agent": "architect",
                "args": '{"pattern": "*.py"}',
                "result": "Found 5 files",
            },
        ]
        result = _build_local_summary_markdown(messages, tool_calls)
        assert "architect" in result
        assert "glob_files" in result

    def test_thinking_tags_stripped(self):
        messages = [
            {
                "role": "assistant",
                "content": "<thinking>Analyze this</thinking>Here is the result",
                "agent_name": "main",
            },
        ]
        result = _build_local_summary_markdown(messages, [])
        assert "<thinking>" not in result
        assert "Here is the result" in result

    def test_multiple_agents(self):
        messages = [
            {"role": "assistant", "content": "Architect analysis", "agent_name": "architect"},
            {
                "role": "assistant",
                "content": "Engineer implementation",
                "agent_name": "python-engineer",
            },
        ]
        tool_calls = [
            {"tool": "read_file", "agent": "architect"},
            {"tool": "write_file", "agent": "python-engineer"},
        ]
        result = _build_local_summary_markdown(messages, tool_calls)
        assert "architect" in result
        assert "python-engineer" in result

    def test_agent_inference_from_tool(self):
        tool_calls = [
            {"tool": "grep_content", "args": '{"pattern": "TODO"}', "result": "Found 3 matches"},
        ]
        result = _build_local_summary_markdown([], tool_calls)
        assert "sago" in result  # default agent
