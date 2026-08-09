"""LangGraph Workflow Engine - Stateful multi-agent workflows with streaming."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Annotated, Callable, TypedDict

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver


class WorkflowState(TypedDict):
    """State passed between workflow nodes."""
    task: str
    messages: Annotated[list[dict], add_messages]
    current_agent: str
    tool_calls: list[dict]
    files_created: list[str]
    iterations: int
    max_iterations: int
    status: str
    error: str | None
    result: str | None
    context: dict[str, Any]
    tokens_in: int
    tokens_out: int


@dataclass
class WorkflowResult:
    """Result of a workflow execution."""
    success: bool
    output: str
    tool_calls: list[dict]
    files_created: list[str]
    iterations: int
    tokens: dict[str, int]
    elapsed: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "tool_calls": self.tool_calls,
            "files_created": self.files_created,
            "iterations": self.iterations,
            "tokens": self.tokens,
            "elapsed": self.elapsed,
        }


def _execute_tools(state: WorkflowState, api_key: str) -> dict:
    """Execute tool calls found in the last assistant message."""
    from sago.engine.simple_executor import _discover_tools, _extract_tool_calls

    tools = _discover_tools()
    messages = state["messages"]
    tool_history = list(state.get("tool_calls", []))
    files_created = list(state.get("files_created", []))
    failed_calls = set(state.get("context", {}).get("failed_calls", []))
    tool_counts = dict(state.get("context", {}).get("tool_counts", {}))

    # Find tool calls in last message
    if not messages:
        return {"tool_calls": tool_history, "files_created": files_created}

    last_msg = messages[-1]
    content = last_msg.get("content", "") if isinstance(last_msg, dict) else ""
    if not content:
        return {"tool_calls": tool_history, "files_created": files_created}

    tool_calls = _extract_tool_calls(content)
    results_for_llm = []

    for call_str in tool_calls:
        try:
            call = json.loads(call_str) if isinstance(call_str, str) else call_str
            name = call.get("name", "")
            args = call.get("args", {})

            call_key = f"{name}:{json.dumps(args, sort_keys=True)}"
            if call_key in failed_calls:
                results_for_llm.append(f"[SKIP] Already failed: {name}")
                continue

            if name not in tools:
                results_for_llm.append(f"Unknown tool: {name}")
                continue

            tool_counts[name] = tool_counts.get(name, 0) + 1
            if tool_counts[name] > 5:
                results_for_llm.append(f"[STOP] Used {name} {tool_counts[name]} times. Finish now.")
                continue

            tool_instance = tools[name]()
            result = tool_instance.run(**args)
            result_str = str(result)[:3000]

            is_error = result_str.lower().startswith("error") or "traceback" in result_str.lower()
            if is_error:
                failed_calls.add(call_key)

            if name == "write_file" and not is_error:
                fp = args.get("file_path", "")
                if fp and fp not in files_created:
                    files_created.append(fp)

            tool_history.append({
                "tool": name,
                "args": args,
                "result": result_str[:500],
                "success": not is_error,
            })

            status = "ERROR" if is_error else "OK"
            results_for_llm.append(f"[{status}] {name}:\n{result_str[:1500]}")

        except json.JSONDecodeError:
            results_for_llm.append("Invalid JSON format")
        except Exception as e:
            results_for_llm.append(f"Tool error: {e}")

    return {
        "tool_calls": tool_history,
        "files_created": files_created,
        "failed_calls": list(failed_calls),
        "tool_counts": tool_counts,
        "results": results_for_llm,
    }


class SagoWorkflowEngine:
    """LangGraph-based workflow engine for complex multi-step tasks."""

    def __init__(self, api_key: str = "", model: str = "openrouter/free") -> None:
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
        self.model = model
        self.checkpointer = MemorySaver()
        self._stream_callback: Callable | None = None

    def set_stream_callback(self, callback: Callable) -> None:
        """Set callback for streaming updates."""
        self._stream_callback = callback

    def _notify(self, event: str, data: Any) -> None:
        """Notify stream callback."""
        if self._stream_callback:
            self._stream_callback(event, data)

    def _planner_node(self, state: WorkflowState) -> dict:
        """Plan the approach for the task."""
        self._notify("thinking", "Planning approach...")

        from openai import OpenAI
        from sago.engine.simple_executor import _get_context

        client = OpenAI(api_key=self.api_key, base_url="https://openrouter.ai/api/v1", timeout=90.0)
        project_ctx = _get_context()

        planning_prompt = (
            f"Task: {state['task']}\n\n"
            f"Project context:\n{project_ctx}\n\n"
            "Create a brief plan for this task. List the steps as numbered items.\n"
            "Be concise - just the plan, no explanation."
        )

        messages = [
            {"role": "system", "content": "You are a planning agent. Create concise execution plans."},
            {"role": "user", "content": planning_prompt},
        ]

        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=1024,
            temperature=0.3,
        )

        plan = response.choices[0].message.content or "No plan generated"

        usage = response.usage
        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0

        return {
            "messages": [{"role": "assistant", "content": f"Plan:\n{plan}"}],
            "context": {"plan": plan},
            "tokens_in": state.get("tokens_in", 0) + tokens_in,
            "tokens_out": state.get("tokens_out", 0) + tokens_out,
        }

    def _executor_node(self, state: WorkflowState) -> dict:
        """Execute the task with tools."""
        self._notify("thinking", "Executing...")

        from openai import OpenAI
        from sago.engine.simple_executor import _get_context, _extract_tool_calls

        client = OpenAI(api_key=self.api_key, base_url="https://openrouter.ai/api/v1", timeout=90.0)
        tools_result = _execute_tools(state, self.api_key)

        messages = list(state.get("messages", []))

        # If we have tool results, add them
        if tools_result.get("results"):
            combined = "\n\n".join(tools_result["results"])
            progress = f"\n[{len(tools_result['tool_calls'])} tools used, {len(tools_result['files_created'])} files created]"
            messages.append({"role": "user", "content": combined + progress})
        else:
            # First execution - send the task
            project_ctx = _get_context()
            plan = state.get("context", {}).get("plan", "")
            messages = [
                {"role": "system", "content": (
                    f"You are {state.get('current_agent', 'Sago Orchestrator')}.\n"
                    f"Plan:\n{plan}\n\n"
                    f"Project context:\n{project_ctx}\n\n"
                    "Execute this plan using tools. Output ONE JSON per tool call.\n"
                    "After all tools complete, provide your final answer."
                )},
                {"role": "user", "content": state["task"]},
            ]

        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=4096,
            temperature=0.3,
        )

        content = response.choices[0].message.content or ""
        if not content and hasattr(response.choices[0].message, "reasoning"):
            content = response.choices[0].message.reasoning or ""

        usage = response.usage
        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0

        # Check for tool calls
        tool_calls = _extract_tool_calls(content)

        return {
            "messages": [{"role": "assistant", "content": content}],
            "tool_calls": tools_result["tool_calls"],
            "files_created": tools_result["files_created"],
            "iterations": state.get("iterations", 0) + 1,
            "tokens_in": state.get("tokens_in", 0) + tokens_in,
            "tokens_out": state.get("tokens_out", 0) + tokens_out,
            "context": {
                **state.get("context", {}),
                "failed_calls": tools_result.get("failed_calls", []),
                "tool_counts": tools_result.get("tool_counts", {}),
                "has_more_tools": bool(tool_calls),
            },
        }

    def _should_continue(self, state: WorkflowState) -> str:
        """Decide whether to continue executing or finish."""
        iterations = state.get("iterations", 0)
        max_iter = state.get("max_iterations", 8)
        has_more_tools = state.get("context", {}).get("has_more_tools", False)

        if iterations >= max_iter:
            return "finish"
        if has_more_tools and iterations < max_iter:
            return "execute"
        return "finish"

    def _finish_node(self, state: WorkflowState) -> dict:
        """Finalize the workflow."""
        # Get last assistant message as result
        messages = state.get("messages", [])
        result = ""
        for msg in reversed(messages):
            if isinstance(msg, dict) and msg.get("role") == "assistant":
                result = msg.get("content", "")
                break

        return {
            "status": "completed",
            "result": result,
        }

    def build_graph(self) -> StateGraph:
        """Build the workflow graph."""
        graph = StateGraph(WorkflowState)

        # Add nodes
        graph.add_node("plan", self._planner_node)
        graph.add_node("execute", self._executor_node)
        graph.add_node("finish", self._finish_node)

        # Set entry point
        graph.set_entry_point("plan")

        # Add edges
        graph.add_edge("plan", "execute")
        graph.add_conditional_edges(
            "execute",
            self._should_continue,
            {
                "execute": "execute",
                "finish": "finish",
            },
        )
        graph.add_edge("finish", END)

        return graph.compile(checkpointer=self.checkpointer)

    def run(
        self,
        task: str,
        agent: str = "Sago Orchestrator",
        max_iterations: int = 8,
        thread_id: str | None = None,
    ) -> WorkflowResult:
        """Execute a workflow."""
        start_time = time.time()

        graph = self.build_graph()

        initial_state: WorkflowState = {
            "task": task,
            "messages": [],
            "current_agent": agent,
            "tool_calls": [],
            "files_created": [],
            "iterations": 0,
            "max_iterations": max_iterations,
            "status": "running",
            "error": None,
            "result": None,
            "context": {},
            "tokens_in": 0,
            "tokens_out": 0,
        }

        config = {"configurable": {"thread_id": thread_id or f"workflow_{int(time.time())}"}}

        try:
            final_state = graph.invoke(initial_state, config)

            return WorkflowResult(
                success=final_state.get("status") == "completed",
                output=final_state.get("result") or final_state.get("messages", [{}])[-1].get("content", "") if final_state.get("messages") else "No output",
                tool_calls=final_state.get("tool_calls", []),
                files_created=final_state.get("files_created", []),
                iterations=final_state.get("iterations", 0),
                tokens={
                    "input": final_state.get("tokens_in", 0),
                    "output": final_state.get("tokens_out", 0),
                },
                elapsed=time.time() - start_time,
            )
        except Exception as e:
            return WorkflowResult(
                success=False,
                output=f"Workflow error: {e}",
                tool_calls=[],
                files_created=[],
                iterations=0,
                tokens={"input": 0, "output": 0},
                elapsed=time.time() - start_time,
            )

    def run_streaming(
        self,
        task: str,
        agent: str = "Sago Orchestrator",
        max_iterations: int = 8,
        on_update: Callable | None = None,
    ) -> WorkflowResult:
        """Execute a workflow with streaming updates."""
        self._stream_callback = on_update
        return self.run(task, agent, max_iterations)
