"""Integration tests for executor."""

from sago.engine.simple_executor import (
    _detect_task_type,
    _discover_tools,
    _get_context,
)
from sago.workflow.langgraph_engine import _extract_tool_calls


class TestToolDiscovery:
    def test_discover_tools(self):
        tools = _discover_tools()
        assert len(tools) >= 40

    def test_tool_descriptions(self):
        _discover_tools()
        from sago.engine.simple_executor import _TOOL_DESCRIPTIONS

        assert len(_TOOL_DESCRIPTIONS) > 0

    def test_tool_classes_cached(self):
        tools1 = _discover_tools()
        tools2 = _discover_tools()
        assert tools1 is tools2


class TestTaskTypeDetection:
    def test_create_task(self):
        assert _detect_task_type("create a new file") == "create"

    def test_fix_task(self):
        assert _detect_task_type("fix the bug in main.py") == "fix"

    def test_analyze_task(self):
        assert _detect_task_type("analyze the codebase") == "analyze"

    def test_explain_task(self):
        # "explain" is detected as "analyze" in the current implementation
        assert _detect_task_type("explain how this works") == "analyze"

    def test_default_task(self):
        assert _detect_task_type("do something") == "create"


class TestToolCallExtraction:
    def test_extract_tool_calls(self):
        content = 'I will use a tool.\n```json\n{"name": "read_file", "args": {"file_path": "test.py"}}\n```\nDone.'
        calls = _extract_tool_calls(content)
        assert len(calls) == 1

    def test_extract_multiple_calls(self):
        content = '''
```json
{"name": "read_file", "args": {"file_path": "a.py"}}
```
```json
{"name": "write_file", "args": {"file_path": "b.py", "content": "x"}}
```
'''
        calls = _extract_tool_calls(content)
        assert len(calls) == 2

    def test_no_tool_calls(self):
        content = "Just a normal response without tools."
        calls = _extract_tool_calls(content)
        assert len(calls) == 0


class TestContext:
    def test_get_context(self):
        ctx = _get_context()
        assert isinstance(ctx, str)
