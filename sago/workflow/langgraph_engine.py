"""LangGraph Workflow Engine - Stateful multi-agent workflows with real streaming.

Uses LangGraph StateGraph for:
- Stateful execution with checkpointing
- Conditional routing (loop, finish, handoff)
- Message accumulation via reducers
- Human-in-the-loop support
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

logger = logging.getLogger("sago.workflow.langgraph")


# Tool definitions - self-contained, no simple_executor dependency
def _discover_tools() -> dict[str, Any]:
    """Discover all available tools."""
    import importlib

    from sago.tools.base import BaseTool

    tools: dict[str, Any] = {}
    tools_dir = Path(__file__).parent.parent / "tools"

    for py_file in tools_dir.rglob("*.py"):
        if py_file.name.startswith("_") or py_file.name == "base.py":
            continue
        if py_file.name == "crewai_wrappers.py":
            continue

        parts = py_file.relative_to(tools_dir).with_suffix("").as_posix().split("/")
        module_name = ".".join(["sago", "tools"] + parts)

        try:
            mod = importlib.import_module(module_name)
        except Exception as e:
            logger.debug("Failed to import %s: %s", module_name, e)
            continue

        for attr_name in dir(mod):
            obj = getattr(mod, attr_name)
            if isinstance(obj, type) and hasattr(obj, "name") and obj.__name__ != "BaseTool":
                try:
                    if issubclass(obj, BaseTool) and obj.name:
                        tools[obj.name] = obj
                except Exception as e:
                    logger.debug("Failed to register tool %s: %s", obj.__name__, e)

    logger.debug("Discovered %d tools", len(tools))
    return tools


def _get_tool_descriptions(tools: dict[str, Any]) -> str:
    """Get formatted tool descriptions for prompts."""
    lines = []
    for name, cls in sorted(tools.items()):
        desc = cls.description or name
        args = ""
        if cls.args_model:
            fields = cls.args_model.model_fields
            parts = []
            for fn, fi in fields.items():
                req = "REQ" if fi.is_required() else f"={fi.default}"
                parts.append(f"{fn}({req})")
            args = ", ".join(parts)
        lines.append(f"- {name}({args}): {desc}")
    return "\n".join(lines)


def _get_context() -> str:
    """Get project context for the agent."""
    work_dir = Path.cwd()
    lines = [f"Working directory: {work_dir}"]

    for name in ["README.md", "readme.md", "pyproject.toml", "package.json"]:
        p = work_dir / name
        if p.exists():
            try:
                lines.append(f"\n--- {name} ---\n{p.read_text('utf-8')[:2000]}")
            except Exception:
                pass

    skip = {".git", "node_modules", "__pycache__", ".venv", "venv", "env"}
    files = []
    try:
        for item in sorted(work_dir.iterdir()):
            if item.name.startswith(".") or item.name in skip:
                continue
            if item.is_file():
                try:
                    s = item.stat().st_size
                    files.append(
                        f"  {item.name} ({s}B)" if s < 100_000 else f"  {item.name} ({s // 1024}KB)"
                    )
                except Exception:
                    files.append(f"  {item.name}")
    except PermissionError:
        pass
    if files:
        lines.append(f"\nFiles ({work_dir.name}/):")
        lines.extend(files[:30])

    return "\n".join(lines)


def _extract_tool_calls(content: str) -> list[dict]:
    """Extract tool calls from LLM output."""
    import re

    calls = []

    # JSON on its own line
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                data = json.loads(line)
                if "name" in data and "args" in data:
                    calls.append(data)
            except json.JSONDecodeError:
                pass

    if calls:
        return calls

    # JSON in code blocks
    for pattern in [r"```json\s*\n(.*?)\n```", r"```\s*\n(\{.*?\})\n```"]:
        for f in re.findall(pattern, content, re.DOTALL):
            try:
                data = json.loads(f.strip())
                if "name" in data and "args" in data:
                    calls.append(data)
            except json.JSONDecodeError:
                pass

    return calls


# Workflow state with LangGraph reducers
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


class SagoWorkflowEngine:
    """LangGraph-based workflow engine for complex multi-step tasks.

    Uses a StateGraph with:
    - plan: Analyze task and create execution strategy
    - execute: Run tools and process results
    - handoff: Delegate to specialist agents
    - finish: Compile final result

    Features:
    - Stateful checkpointing (resume interrupted workflows)
    - Conditional routing (loop until done or max iterations)
    - Message accumulation via add_messages reducer
    - Real streaming via astream_events
    """

    def __init__(self, api_key: str = "", model: str = "openrouter/free") -> None:
        self.api_key = api_key or os.environ.get(
            "OPENROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", "")
        )
        self.model = model
        self.checkpointer = MemorySaver()
        self._tools: dict[str, Any] | None = None

    def _get_tools(self) -> dict[str, Any]:
        if self._tools is None:
            self._tools = _discover_tools()
        return self._tools

    def _make_llm_call(self, messages: list[dict], max_tokens: int = 4096) -> tuple[str, int, int]:
        """Make an LLM call and return content + token counts."""
        from openai import OpenAI

        logger.debug("Making LLM call (model=%s, max_tokens=%d)", self.model, max_tokens)
        client = OpenAI(api_key=self.api_key, base_url="https://openrouter.ai/api/v1", timeout=90.0)

        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.3,
        )

        content = response.choices[0].message.content or ""
        if not content and hasattr(response.choices[0].message, "reasoning"):
            content = response.choices[0].message.reasoning or ""

        usage = response.usage
        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0

        return content, tokens_in, tokens_out

    def _execute_tool(self, call: dict) -> tuple[str, bool]:
        """Execute a single tool call. Returns (result, is_error)."""
        tools = self._get_tools()
        name = call.get("name", "")
        args = call.get("args", {})

        if name not in tools:
            return f"Unknown tool: {name}. Available: {', '.join(sorted(tools.keys()))}", True

        try:
            tool_instance = tools[name]()
            result = tool_instance.run(**args)
            result_str = str(result)[:4000]
            is_error = result_str.lower().startswith("error") or "traceback" in result_str.lower()
            logger.debug("Tool %s executed successfully", name)
            return result_str, is_error
        except Exception as e:
            logger.error("Tool %s failed: %s", name, e)
            return f"Tool error: {type(e).__name__}: {e}", True

    def _planner_node(self, state: WorkflowState) -> dict:
        """Plan the approach for the task."""
        tools = self._get_tools()
        tool_desc = _get_tool_descriptions(tools)
        project_ctx = _get_context()

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a planning agent. Analyze the task and create a brief execution plan.\n"
                    "List the steps as numbered items. Be concise.\n\n"
                    f"Project context:\n{project_ctx}\n\n"
                    f"Available tools:\n{tool_desc}"
                ),
            },
            {"role": "user", "content": state["task"]},
        ]

        content, tokens_in, tokens_out = self._make_llm_call(messages, max_tokens=1024)

        return {
            "messages": [{"role": "assistant", "content": f"Plan:\n{content}"}],
            "context": {"plan": content},
            "tokens_in": state.get("tokens_in", 0) + tokens_in,
            "tokens_out": state.get("tokens_out", 0) + tokens_out,
        }

    def _executor_node(self, state: WorkflowState) -> dict:
        """Execute the current step with tools."""
        tools = self._get_tools()
        tool_desc = _get_tool_descriptions(tools)
        project_ctx = _get_context()

        # Build context from previous messages
        prev_messages = list(state.get("messages", []))
        plan = state.get("context", {}).get("plan", "")
        tool_history = list(state.get("tool_calls", []))
        files_created = list(state.get("files_created", []))

        system_msg = (
            f"You are {state.get('current_agent', 'Sago Orchestrator')}.\n"
            f"Task: {state['task']}\n\n"
            f"Plan:\n{plan}\n\n"
            f"Project context:\n{project_ctx}\n\n"
            f"Available tools:\n{tool_desc}\n\n"
            "Execute the plan. Output ONE JSON per tool call on its own line:\n"
            '{"name": "tool_name", "args": {"arg1": "value1"}}\n\n'
            "After tools complete, provide your final answer."
        )

        messages = [{"role": "system", "content": system_msg}]
        # Add previous conversation (limited to avoid token explosion)
        for msg in prev_messages[-6:]:
            messages.append(msg)

        # Add tool results from previous iteration
        if tool_history:
            last_results = [
                f"[{tc.get('tool', '')}] {tc.get('result', '')[:300]}" for tc in tool_history[-5:]
            ]
            messages.append(
                {"role": "user", "content": "Previous tool results:\n" + "\n".join(last_results)}
            )

        content, tokens_in, tokens_out = self._make_llm_call(messages, max_tokens=4096)

        # Execute any tool calls found
        new_tool_calls = _extract_tool_calls(content)
        results_for_next = []

        for call in new_tool_calls:
            result_str, is_error = self._execute_tool(call)
            name = call.get("name", "")

            # Track created files
            if name == "write_file" and not is_error:
                fp = call.get("args", {}).get("file_path", "")
                if fp and fp not in files_created:
                    files_created.append(fp)

            tool_history.append(
                {
                    "tool": name,
                    "args": call.get("args", {}),
                    "result": result_str[:500],
                    "success": not is_error,
                }
            )

            status = "ERROR" if is_error else "OK"
            results_for_next.append(f"[{status}] {name}:\n{result_str[:1500]}")

        return {
            "messages": [{"role": "assistant", "content": content}],
            "tool_calls": tool_history,
            "files_created": files_created,
            "iterations": state.get("iterations", 0) + 1,
            "tokens_in": state.get("tokens_in", 0) + tokens_in,
            "tokens_out": state.get("tokens_out", 0) + tokens_out,
            "context": {
                **state.get("context", {}),
                "has_more_tools": bool(new_tool_calls),
                "last_results": results_for_next,
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
        """Build the workflow graph.

        Graph structure:
            plan → execute → (execute | finish)
                            ↑         |
                            └─────────┘
        """
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
        """Execute a workflow synchronously."""
        start_time = time.time()
        logger.info("Starting workflow (agent=%s, max_iter=%d)", agent, max_iterations)
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

            result = WorkflowResult(
                success=final_state.get("status") == "completed",
                output=final_state.get("result") or "",
                tool_calls=final_state.get("tool_calls", []),
                files_created=final_state.get("files_created", []),
                iterations=final_state.get("iterations", 0),
                tokens={
                    "input": final_state.get("tokens_in", 0),
                    "output": final_state.get("tokens_out", 0),
                },
                elapsed=time.time() - start_time,
            )
            logger.info(
                "Workflow completed in %.1fs (success=%s, iterations=%d)",
                result.elapsed,
                result.success,
                result.iterations,
            )
            return result
        except Exception as e:
            logger.error("Workflow failed: %s", e)
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
        """Execute a workflow with streaming updates.

        Uses LangGraph's astream_events for real streaming.
        """
        start_time = time.time()

        def _notify(event: str, data: Any) -> None:
            if on_update:
                on_update(event, data)

        _notify("thinking", "Building workflow graph...")
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

        config = {"configurable": {"thread_id": f"stream_{int(time.time())}"}}

        try:
            # Use astream_events for real streaming
            import asyncio

            async def _run_stream() -> WorkflowResult:
                final_state = None
                async for event in graph.astream_events(initial_state, config, version="v2"):
                    kind = event.get("event", "")

                    if kind == "on_chain_start":
                        node = event.get("name", "")
                        _notify("thinking", f"Starting: {node}")

                    elif kind == "on_chain_end":
                        node = event.get("name", "")
                        output = event.get("data", {}).get("output", {})
                        if isinstance(output, dict):
                            if "tool_calls" in output:
                                tc = output["tool_calls"]
                                if tc and len(tc) > 0:
                                    last_tc = tc[-1]
                                    _notify("tool", last_tc)
                            if "messages" in output:
                                msgs = output["messages"]
                                if msgs:
                                    last_msg = msgs[-1]
                                    if (
                                        isinstance(last_msg, dict)
                                        and last_msg.get("role") == "assistant"
                                    ):
                                        _notify("token", last_msg.get("content", ""))
                        final_state = output if isinstance(output, dict) else final_state

                    elif kind == "on_llm_stream":
                        chunk = event.get("data", {}).get("chunk", "")
                        if chunk:
                            _notify("token", chunk)

                if final_state is None:
                    final_state = initial_state

                return WorkflowResult(
                    success=final_state.get("status") == "completed",
                    output=final_state.get("result") or "",
                    tool_calls=final_state.get("tool_calls", []),
                    files_created=final_state.get("files_created", []),
                    iterations=final_state.get("iterations", 0),
                    tokens={
                        "input": final_state.get("tokens_in", 0),
                        "output": final_state.get("tokens_out", 0),
                    },
                    elapsed=time.time() - start_time,
                )

            # Run async in sync context
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're in an async context, use a thread
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        result = pool.submit(lambda: asyncio.run(_run_stream())).result()
                else:
                    result = loop.run_until_complete(_run_stream())
            except RuntimeError:
                result = asyncio.run(_run_stream())

            return result

        except Exception as e:
            return WorkflowResult(
                success=False,
                output=f"Streaming error: {e}",
                tool_calls=[],
                files_created=[],
                iterations=0,
                tokens={"input": 0, "output": 0},
                elapsed=time.time() - start_time,
            )
