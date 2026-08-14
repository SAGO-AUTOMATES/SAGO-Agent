"""Unified Executor - Single entry point for all execution paths.

Provides a consistent interface whether using simple_executor, CrewAI, or LangGraph.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

from openai import OpenAI


class UnifiedExecutor:
    """Unified executor that routes to the appropriate backend."""

    def __init__(
        self,
        api_key: str = "",
        model: str = "openrouter/free",
        base_url: str = "https://openrouter.ai/api/v1",
    ) -> None:
        self.api_key = api_key or os.environ.get(
            "OPENROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", "")
        )
        self.model = model
        self.base_url = base_url

    def execute(
        self,
        task: str,
        agent_name: str = "sago-orchestrator",
        system_prompt: str = "",
        max_tokens: int = 50000,
        max_iterations: int = 30,
        backend: str = "simple",
        on_tool_call: Callable | None = None,
        on_thinking: Callable | None = None,
    ) -> dict[str, Any]:
        """Execute a task using the specified backend.

        Args:
            task: The task to execute.
            agent_name: Name of the agent to use.
            system_prompt: Custom system prompt.
            max_tokens: Maximum tokens per response.
            max_iterations: Maximum tool-calling iterations.
            backend: Execution backend ("simple", "crewai", "langgraph").
            on_tool_call: Callback for tool calls.
            on_thinking: Callback for thinking updates.

        Returns:
            Execution result with output, tool_calls, tokens, etc.
        """
        from sago.tracking.dev_tracer import get_dev_tracer

        tracer = get_dev_tracer()
        with tracer.trace_block(
            source=f"sago.engine.{backend}",
            action=f"execute({agent_name})",
            data={"task": task[:120], "agent": agent_name, "model": self.model, "backend": backend},
        ) as trace_data:
            if backend == "crewai":
                res = self._execute_crewai(
                    task, agent_name, system_prompt, max_tokens, max_iterations
                )
            elif backend == "langgraph":
                res = self._execute_langgraph(task, agent_name, max_iterations)
            else:
                res = self._execute_simple(
                    task,
                    agent_name,
                    system_prompt,
                    max_tokens,
                    max_iterations,
                    on_tool_call,
                    on_thinking,
                )
            trace_data["tool_calls"] = len(res.get("tool_calls", []))
            trace_data["iterations"] = res.get("iterations", 1)
            return res

    def _execute_simple(
        self,
        task: str,
        agent_name: str,
        system_prompt: str,
        max_tokens: int,
        max_iterations: int,
        on_tool_call: Callable | None,
        on_thinking: Callable | None,
    ) -> dict[str, Any]:
        """Execute using simple_executor (all 50 tools)."""
        from sago.engine.simple_executor import execute_agent_task

        return execute_agent_task(
            task=task,
            agent_role=agent_name.replace("-", " ").title(),
            system_prompt=system_prompt,
            api_key=self.api_key,
            model=self.model,
            base_url=self.base_url,
            max_tokens=max_tokens,
            max_iterations=max_iterations,
            on_tool_call=on_tool_call,
            on_thinking=on_thinking,
        )

    def _execute_crewai(
        self,
        task: str,
        agent_name: str,
        system_prompt: str,
        max_tokens: int,
        max_iterations: int,
    ) -> dict[str, Any]:
        """Execute using CrewAI (multi-agent orchestration)."""
        try:
            from sago.agents.spawner import AgentSpawner

            spawner = AgentSpawner()
            result_str = spawner.execute_with_agent(
                agent_name=agent_name,
                task=task,
                model_override=self.model,
            )
            return {
                "success": not result_str.startswith("Error:"),
                "output": result_str,
                "tool_calls": [],
                "iterations": 1,
                "tokens": {"input": 0, "output": 0},
                "elapsed": 0,
                "files_created": [],
            }
        except Exception as e:
            return {
                "success": False,
                "output": f"CrewAI error: {e}",
                "tool_calls": [],
                "iterations": 0,
                "tokens": {"input": 0, "output": 0},
                "elapsed": 0,
                "files_created": [],
            }

    def _execute_langgraph(
        self,
        task: str,
        agent_name: str,
        max_iterations: int,
    ) -> dict[str, Any]:
        """Execute using LangGraph (stateful workflow)."""
        try:
            from sago.workflow.langgraph_engine import SagoWorkflowEngine

            engine = SagoWorkflowEngine(api_key=self.api_key, model=self.model)
            result = engine.run(task, agent_name, max_iterations)
            return result.to_dict()
        except Exception as e:
            return {
                "success": False,
                "output": f"LangGraph error: {e}",
                "tool_calls": [],
                "iterations": 0,
                "tokens": {"input": 0, "output": 0},
                "elapsed": 0,
                "files_created": [],
            }

    def stream(
        self,
        task: str,
        agent_name: str = "sago-orchestrator",
        system_prompt: str = "",
        max_tokens: int = 50000,
        max_iterations: int = 30,
        on_token: Callable | None = None,
        on_tool_call: Callable | None = None,
        on_thinking: Callable | None = None,
    ) -> dict[str, Any]:
        """Stream execution with token-by-token updates.

        Args:
            task: The task to execute.
            agent_name: Name of the agent to use.
            system_prompt: Custom system prompt.
            max_tokens: Maximum tokens per response.
            max_iterations: Maximum tool-calling iterations.
            on_token: Callback for each token.
            on_tool_call: Callback for tool calls.
            on_thinking: Callback for thinking updates.

        Returns:
            Execution result.
        """
        import json

        from sago.engine.simple_executor import (
            PROMPTS,
            _build_openai_tools,
            _detect_task_type,
            _discover_tools,
            _get_context,
            _load_agent_profile,
        )

        tools = _discover_tools()
        openai_tools = _build_openai_tools(tools)
        client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=90.0)
        project_ctx = _get_context()
        start_time = time.time()

        # Load profile
        profile = _load_agent_profile(agent_name.replace("-", " ").title())

        # Build prompt
        task_type = _detect_task_type(task)
        template = PROMPTS.get(task_type, PROMPTS["create"])
        system_prompt = system_prompt or template.format(
            agent_role=agent_name.replace("-", " ").title(),
            project_ctx=project_ctx,
        )

        if profile and profile.get("system_prompt"):
            system_prompt = profile["system_prompt"]

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]

        tool_history = []
        files_created = []
        total_tokens_in = 0
        total_tokens_out = 0
        content = ""
        last_iteration = 0

        for iteration in range(max_iterations):
            last_iteration = iteration
            if on_thinking:
                phase = "Planning" if iteration == 0 else "Working"
                on_thinking(f"{phase}... (step {iteration + 1}/{max_iterations})")

            api_kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.3,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            if openai_tools:
                api_kwargs["tools"] = openai_tools
                api_kwargs["tool_choice"] = "auto"

            stream = client.chat.completions.create(**api_kwargs)

            content = ""
            # Accumulate streaming tool calls
            tool_call_deltas: dict[int, dict[str, Any]] = {}

            for chunk in stream:
                # Get usage from final chunk
                if hasattr(chunk, "usage") and chunk.usage:
                    total_tokens_in = chunk.usage.prompt_tokens or 0
                    total_tokens_out = chunk.usage.completion_tokens or 0
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                if delta.content:
                    token = delta.content
                    content += token
                    if on_token:
                        on_token(token)

                # Accumulate streaming tool calls
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_call_deltas:
                            tool_call_deltas[idx] = {
                                "id": tc_delta.id or "",
                                "name": "",
                                "arguments": "",
                            }
                        if tc_delta.id:
                            tool_call_deltas[idx]["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                tool_call_deltas[idx]["name"] = tc_delta.function.name
                            if tc_delta.function.arguments:
                                tool_call_deltas[idx]["arguments"] += tc_delta.function.arguments

            messages.append({"role": "assistant", "content": content or None})

            # Process accumulated tool calls
            if not tool_call_deltas:
                break

            # Add tool_calls to assistant message
            assistant_tool_calls = []
            for idx in sorted(tool_call_deltas.keys()):
                tc = tool_call_deltas[idx]
                assistant_tool_calls.append(
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": tc["arguments"],
                        },
                    }
                )
            messages[-1]["tool_calls"] = assistant_tool_calls

            # Execute each tool call
            for tc in assistant_tool_calls:
                tc_id = tc["id"]
                name = tc["function"]["name"]
                try:
                    args = (
                        json.loads(tc["function"]["arguments"])
                        if tc["function"]["arguments"]
                        else {}
                    )
                except json.JSONDecodeError:
                    args = {}

                if name not in tools:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": f"Unknown tool: {name}",
                        }
                    )
                    continue

                # Permission check
                try:
                    from sago.permissions import get_permission_manager

                    pm = get_permission_manager()
                    allowed, reason = pm.check_permission(name, args)
                    if not allowed:
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "content": f"Permission denied: {reason}",
                            }
                        )
                        continue
                except Exception:
                    pass

                if on_tool_call:
                    on_tool_call(name, args)

                try:
                    tool_cls = tools.get(name)
                    if tool_cls is None:
                        result_str = f"Error: Tool '{name}' not found."
                        is_error = True
                    else:
                        clean_args = dict(args)
                        if "file_path" not in clean_args and "path" in clean_args:
                            clean_args["file_path"] = clean_args["path"]
                        if "file_path" not in clean_args and "filename" in clean_args:
                            clean_args["file_path"] = clean_args["filename"]
                        if "command" not in clean_args and "cmd" in clean_args:
                            clean_args["command"] = clean_args["cmd"]
                        if (
                            "pattern" not in clean_args
                            and "query" in clean_args
                            and name in ("grep_content", "grep_search")
                        ):
                            clean_args["pattern"] = clean_args["query"]

                        tool_instance = tool_cls()
                        result = tool_instance.run(**clean_args)
                        result_str = str(result)
                        is_error = (
                            result_str.lower().startswith("error")
                            or "traceback" in result_str.lower()
                        )
                except Exception as tool_exc:
                    result_str = f"Error executing tool '{name}': {tool_exc}"
                    is_error = True

                if name == "write_file" and not is_error:
                    fp = args.get("file_path", "")
                    if fp and fp not in files_created:
                        files_created.append(fp)

                tool_history.append(
                    {
                        "tool": name,
                        "args": args,
                        "result": result_str[:2000],
                        "success": not is_error,
                    }
                )

                # Log tool usage to DB
                try:
                    from sago.database import ToolUsageStore, init_db

                    init_db()
                    _tus = ToolUsageStore("unified")
                    _tus.log(
                        tool_name=name,
                        arguments=args,
                        result=result_str[:1000],
                        success=not is_error,
                    )
                    _tus.flush()
                except Exception:
                    pass

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": result_str,
                    }
                )

        elapsed = time.time() - start_time

        # Record token usage
        if total_tokens_in > 0 or total_tokens_out > 0:
            try:
                from sago.tracking.token_tracker import get_token_tracker

                tracker = get_token_tracker()
                tracker.record(
                    provider="openai",
                    model=self.model,
                    input_tokens=total_tokens_in,
                    output_tokens=total_tokens_out,
                    latency_ms=elapsed * 1000,
                    metadata={"session_id": "unified"},
                )
                tracker.save()
            except Exception:
                pass

        return {
            "success": True,
            "output": content,
            "tool_calls": tool_history,
            "iterations": min(last_iteration + 1, max_iterations),
            "tokens": {"input": total_tokens_in, "output": total_tokens_out},
            "elapsed": elapsed,
            "files_created": files_created,
        }


# Convenience functions
def execute_task(
    task: str,
    agent: str = "sago-orchestrator",
    backend: str = "simple",
    **kwargs: Any,
) -> dict[str, Any]:
    """Execute a task with the unified executor."""
    executor = UnifiedExecutor()
    return executor.execute(task, agent, backend=backend, **kwargs)


def stream_task(
    task: str,
    agent: str = "sago-orchestrator",
    on_token: Callable | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Stream a task with token-by-token updates."""
    executor = UnifiedExecutor()
    return executor.stream(task, agent, on_token=on_token, **kwargs)


def execute_parallel(
    tasks: list[dict[str, Any]],
    max_workers: int = 4,
) -> list[dict[str, Any]]:
    """Execute multiple tasks in parallel.

    Args:
        tasks: List of task dicts with keys: task, agent, backend, etc.
        max_workers: Maximum number of parallel workers.

    Returns:
        List of results in the same order as tasks.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: list[dict[str, Any] | None] = [None] * len(tasks)

    def _exec_one(idx: int, task_config: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        executor = UnifiedExecutor()
        result = executor.execute(
            task=task_config.get("task", ""),
            agent_name=task_config.get("agent", "sago-orchestrator"),
            system_prompt=task_config.get("system_prompt", ""),
            max_tokens=task_config.get("max_tokens", 50000),
            max_iterations=task_config.get("max_iterations", 30),
            backend=task_config.get("backend", "simple"),
        )
        return idx, result

    with ThreadPoolExecutor(max_workers=min(max_workers, len(tasks))) as pool:
        futures = {pool.submit(_exec_one, i, t): i for i, t in enumerate(tasks)}
        for future in as_completed(futures):
            idx, result = future.result()
            results[idx] = result

    return [r or {} for r in results]
