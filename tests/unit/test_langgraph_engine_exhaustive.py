from unittest.mock import MagicMock, patch

import pytest

from sago.workflow.langgraph_engine import (
    HAS_LANGGRAPH,
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
    # Plain JSON on its own line
    content_plain = (
        'Here is the plan:\n{"name": "read_file", "args": {"file_path": "a.txt"}}\nDone.'
    )
    calls = _extract_tool_calls(content_plain)
    assert len(calls) == 1
    assert calls[0]["name"] == "read_file"

    # Markdown block
    content_block = '```json\n{"name": "write_file", "args": {"file_path": "b.txt"}}\n```'
    calls_block = _extract_tool_calls(content_block)
    assert len(calls_block) == 1
    assert calls_block[0]["name"] == "write_file"


def test_workflow_result_to_dict():
    res = WorkflowResult(
        success=True,
        output="Result text",
        tool_calls=[{"tool": "read_file"}],
        files_created=["out.txt"],
        iterations=2,
        tokens={"input": 100, "output": 50},
        elapsed=1.5,
    )
    d = res.to_dict()
    assert d["success"] is True
    assert d["iterations"] == 2
    assert d["elapsed"] == 1.5


def test_engine_execute_tool():
    engine = SagoWorkflowEngine()
    # Unknown tool
    res_unk, is_err_unk = engine._execute_tool({"name": "nonexistent_tool_xyz", "args": {}})
    assert is_err_unk is True
    assert "Unknown tool" in res_unk

    # Valid tool
    with patch.object(engine, "_get_tools") as mock_tools:
        mock_tool_inst = MagicMock()
        mock_tool_inst.run.return_value = "Tool execution output"
        mock_tool_cls = MagicMock(return_value=mock_tool_inst)
        mock_tools.return_value = {"mock_tool": mock_tool_cls}

        res, is_err = engine._execute_tool({"name": "mock_tool", "args": {"key": "val"}})
        assert is_err is False
        assert res == "Tool execution output"


def test_engine_nodes():
    engine = SagoWorkflowEngine()

    with patch.object(engine, "_make_llm_call") as mock_llm:
        mock_llm.return_value = ("Plan output: 1. read 2. write", 10, 20)
        state_in = {
            "task": "Test task",
            "messages": [],
            "tokens_in": 0,
            "tokens_out": 0,
        }
        res_plan = engine._planner_node(state_in)
        assert "Plan:" in res_plan["messages"][0]["content"]

        # Executor node
        mock_llm.return_value = (
            'Calling tool:\n{"name": "read_file", "args": {"file_path": "test.txt"}}',
            15,
            25,
        )
        with patch.object(engine, "_execute_tool", return_value=("file contents", False)):
            state_exec = {
                "task": "Test task",
                "current_agent": "Coder",
                "messages": [],
                "context": {"plan": "Plan text"},
                "tool_calls": [],
                "files_created": [],
                "iterations": 0,
            }
            res_exec = engine._executor_node(state_exec)
            assert len(res_exec["tool_calls"]) == 1
            assert res_exec["iterations"] == 1

        # Finish node
        state_finish = {"messages": [{"role": "assistant", "content": "All done successfully."}]}
        res_fin = engine._finish_node(state_finish)
        assert res_fin["status"] == "completed"
        assert res_fin["result"] == "All done successfully."


def test_engine_should_continue():
    engine = SagoWorkflowEngine()
    # Iteration limit reached
    assert engine._should_continue({"iterations": 10, "max_iterations": 10}) == "finish"
    # More tools and under limit
    assert (
        engine._should_continue(
            {"iterations": 2, "max_iterations": 5, "context": {"has_more_tools": True}}
        )
        == "execute"
    )
    # No more tools
    assert (
        engine._should_continue(
            {"iterations": 2, "max_iterations": 5, "context": {"has_more_tools": False}}
        )
        == "finish"
    )


def test_engine_run_without_langgraph():
    engine = SagoWorkflowEngine()
    if not HAS_LANGGRAPH:
        with pytest.raises(RuntimeError, match="LangGraph is not installed"):
            engine.build_graph()


def test_engine_run_with_mock_graph():
    engine = SagoWorkflowEngine()
    mock_graph = MagicMock()
    mock_graph.invoke.return_value = {
        "status": "completed",
        "result": "Graph execution output",
        "tool_calls": [{"tool": "read_file"}],
        "files_created": ["out.txt"],
        "iterations": 1,
        "tokens_in": 100,
        "tokens_out": 200,
    }

    with patch.object(engine, "build_graph", return_value=mock_graph):
        res = engine.run("Do something", max_iterations=3)
        assert res.success is True
        assert res.output == "Graph execution output"
        assert res.iterations == 1


def test_engine_run_streaming_with_mock_graph():
    engine = SagoWorkflowEngine()
    mock_graph = MagicMock()

    async def mock_events(*args, **kwargs):
        yield {
            "event": "on_chain_start",
            "name": "plan",
        }
        yield {
            "event": "on_chain_end",
            "name": "plan",
            "data": {
                "output": {
                    "status": "completed",
                    "result": "Stream output",
                    "tool_calls": [],
                    "messages": [{"role": "assistant", "content": "Stream output"}],
                }
            },
        }

    mock_graph.astream_events = mock_events

    updates = []

    def on_update(event, data):
        updates.append((event, data))

    with patch.object(engine, "build_graph", return_value=mock_graph):
        res = engine.run_streaming("Do streaming", max_iterations=3, on_update=on_update)
        assert res.success is True
        assert len(updates) >= 1


def test_engine_make_llm_call():
    engine = SagoWorkflowEngine()
    with patch("sago.llm.tui_providers.get_tui_client") as mock_get_client:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "Model output text"
        mock_choice.message.reasoning = None
        mock_resp.choices = [mock_choice]
        mock_resp.usage.prompt_tokens = 25
        mock_resp.usage.completion_tokens = 50
        mock_client.chat.completions.create.return_value = mock_resp
        mock_get_client.return_value = (mock_client, "gpt-4o")

        content, tin, tout = engine._make_llm_call([{"role": "user", "content": "hi"}])
        assert content == "Model output text"
        assert tin == 25
        assert tout == 50
