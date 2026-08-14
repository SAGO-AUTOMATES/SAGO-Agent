"""Unit tests for LangGraph Workflow Engine."""

from __future__ import annotations

from sago.workflow.langgraph_engine import (
    SagoWorkflowEngine,
    WorkflowResult,
    _discover_tools,
    _extract_tool_calls,
    _get_context,
    _get_tool_descriptions,
)


def test_discover_tools_and_descriptions():
    tools = _discover_tools()
    assert isinstance(tools, dict)
    assert len(tools) > 0

    desc = _get_tool_descriptions(tools)
    assert isinstance(desc, str)
    assert len(desc) > 0


def test_get_context():
    ctx = _get_context()
    assert "Working directory:" in ctx


def test_extract_tool_calls():
    # Single line json
    c1 = '{"name": "read_file", "args": {"file_path": "README.md"}}'
    calls1 = _extract_tool_calls(c1)
    assert len(calls1) == 1
    assert calls1[0]["name"] == "read_file"

    # Markdown json block
    c2 = '```json\n{\n  "name": "edit_file",\n  "args": {"file_path": "test.py", "old_string": "a", "new_string": "b"}\n}\n```'
    calls2 = _extract_tool_calls(c2)
    assert len(calls2) == 1
    assert calls2[0]["name"] == "edit_file"

    # Non tool json
    c3 = "Hello this is normal text."
    assert _extract_tool_calls(c3) == []


def test_workflow_result_to_dict():
    res = WorkflowResult(
        success=True,
        output="Done",
        tool_calls=[{"name": "read_file"}],
        files_created=["out.txt"],
        iterations=2,
        tokens={"in": 100, "out": 50},
        elapsed=1.23,
    )
    d = res.to_dict()
    assert d["success"] is True
    assert d["output"] == "Done"
    assert d["elapsed"] == 1.23
    assert d["iterations"] == 2


def test_engine_execute_tool_success_and_missing():
    engine = SagoWorkflowEngine(api_key="fake-key")

    # Missing tool
    res, is_err = engine._execute_tool({"name": "non_existent_tool_123", "args": {}})
    assert is_err is True
    assert "Unknown tool" in res

    # Real tool
    res2, is_err2 = engine._execute_tool({"name": "os_detector", "args": {}})
    assert is_err2 is False
    assert len(res2) > 0
