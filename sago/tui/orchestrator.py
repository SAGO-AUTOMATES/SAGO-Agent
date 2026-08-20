"""Agent Orchestrator Mixin for Sago TUI - Delegation, Chaining, and Parallel Execution."""

from __future__ import annotations

import concurrent.futures
import json
import logging
import re
import threading
import time
from typing import TYPE_CHECKING, Any

from textual.widgets import Static

from sago.tui.widgets import AgentStatus, get_task_manager

logger = logging.getLogger("sago.tui.orchestrator")

if TYPE_CHECKING:
    from sago.tui.app import SagoApp

_time = time


class AgentOrchestrationMixin:
    """Mixin for multi-agent delegation, chaining, parallel execution, and approval flows."""

    def _process_delegation(self: SagoApp, agent_name: str, task: str) -> None:
        logger.info("delegation requested: agent=%s task_len=%d", agent_name, len(task))
        self.is_thinking = True
        t = threading.Thread(
            target=self._process_delegation_thread, args=(agent_name, task), daemon=True
        )
        t.start()

    def _process_delegation_thread(self: SagoApp, agent_name: str, task: str) -> None:
        logger.debug("delegation thread started: agent=%s", agent_name)
        tm = self._task_manager or get_task_manager()
        info = tm.create_task(agent_name, task)
        info.status = AgentStatus.RUNNING
        try:
            self.call_from_thread(self._update_dashboard)
            self.call_from_thread(self._show_spinner, f"Delegating to {agent_name}...")
        except Exception as e:
            logger.debug("delegation UI setup failed: %s", e)

        # Record dev trace for delegation start
        t0 = _time.time()
        try:
            from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer

            get_dev_tracer().record(
                event_type=TraceEventType.AGENT_ROUTING,
                source="orchestrator",
                action=f"delegate -> @{agent_name}",
                data={"agent": agent_name, "task": task},
            )
        except Exception as e:
            logger.debug("dev tracer record failed (delegation start): %s", e)

        try:
            api_key = self._get_provider_api_key()
            if not api_key:
                self.call_from_thread(self._hide_spinner)
                self.call_from_thread(
                    self._add_notice_inline,
                    f"No API key. Set {self._get_provider_key_name()} environment variable.",
                )
                return

            from sago.tools.file.spawn_agent import SpawnAgentTool

            logger.debug("spawn_agent called: agent=%s task_len=%d", agent_name, len(task))
            tool = SpawnAgentTool()
            result = tool.run(task=task, agent_name=agent_name)

            dur_ms = (_time.time() - t0) * 1000
            # Detect error embedded in result string (agent returns error as text)
            result_is_error = (
                "could not be spawned" in result
                or result.startswith("Error")
                or result.startswith("Last error")
                or "REJECTED" in result
            )
            logger.info(
                "delegation complete: agent=%s dur_ms=%.1f result_len=%d error=%s",
                agent_name,
                dur_ms,
                len(result),
                result_is_error,
            )
            try:
                from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer

                get_dev_tracer().record(
                    event_type=TraceEventType.FUNCTION_RETURN,
                    source=f"agent.{agent_name}",
                    action="delegation_complete",
                    duration_ms=dur_ms,
                    status="ERROR" if result_is_error else "OK",
                    data={
                        "agent": agent_name,
                        "result_preview": str(result)[:300],
                        "success": not result_is_error,
                    },
                )
            except Exception as e:
                logger.debug("dev tracer record failed (delegation complete): %s", e)

            if result_is_error:
                info.status = AgentStatus.FAILED
                info.error = result
            else:
                info.status = AgentStatus.COMPLETED
                info.result = result
            info.elapsed = _time.time() - info.start_time
            self.call_from_thread(self._update_dashboard)
            self.call_from_thread(self._hide_spinner)
            if result_is_error:
                self.call_from_thread(
                    self._add_error_inline,
                    result,
                    "Try running the task directly or check your API key.",
                )
            else:
                self.call_from_thread(self._add_assistant_message, result, agent_name=agent_name)
        except Exception as e:
            logger.error("delegation failed: agent=%s error=%s", agent_name, e, exc_info=True)
            dur_ms = (_time.time() - t0) * 1000
            try:
                from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer

                get_dev_tracer().record(
                    event_type=TraceEventType.ERROR,
                    source=f"agent.{agent_name}",
                    action="delegation_error",
                    duration_ms=dur_ms,
                    status="ERROR",
                    data={"agent": agent_name, "error": str(e)},
                )
            except Exception as e:
                logger.debug("dev tracer record failed (delegation error): %s", e)

            info.status = AgentStatus.FAILED
            info.error = str(e)
            self.call_from_thread(self._update_dashboard)
            self.call_from_thread(self._hide_spinner)
            self.call_from_thread(self._add_error_inline, f"Delegation error: {e}")
        finally:
            self.is_thinking = False

    def _process_chain(self: SagoApp, chain_steps: list[list[str]], task: str) -> None:
        step_summary = " -> ".join("+".join(s) for s in chain_steps)
        logger.info("chain requested: steps=%s task_len=%d", step_summary, len(task))
        self.is_thinking = True
        t = threading.Thread(
            target=self._process_chain_thread, args=(chain_steps, task), daemon=True
        )
        t.start()

    def _process_chain_thread(self: SagoApp, chain_steps: list[list[str]], task: str) -> None:
        logger.debug("chain thread started: %d steps", len(chain_steps))
        tm = self._task_manager or get_task_manager()
        flat_agents = [a for step in chain_steps for a in step]
        try:
            self.call_from_thread(
                self._show_spinner,
                f"Chain: {' → '.join(['+'.join(s) for s in chain_steps])}",
            )
        except Exception as e:
            logger.debug("chain spinner setup failed: %s", e)

        # Build and mount HandoffFlow widget for visual chain progress
        from sago.tui.widgets import HandoffFlow

        chain_flow_data = [
            {"agent": agent, "status": "pending"} for step in chain_steps for agent in step
        ]
        handoff_widget = HandoffFlow(chain_flow_data)

        def _mount_handoff() -> None:
            try:
                target = getattr(self, "_active_exchange_card", None)
                if target is not None:
                    resp = getattr(target, "_response_container", None)
                    if resp is not None:
                        resp.mount(handoff_widget)
                    else:
                        target.mount(handoff_widget)
                else:
                    self.query_one("#messages").mount(handoff_widget)
            except Exception as e:
                logger.debug("mount handoff flow failed: %s", e)

        self.call_from_thread(_mount_handoff)

        try:
            api_key = self._get_provider_api_key()
            if not api_key:
                self.call_from_thread(self._hide_spinner)
                self.call_from_thread(
                    self._add_notice_inline,
                    f"No API key. Set {self._get_provider_key_name()} environment variable.",
                )
                return

            from sago.agents.handoff import HandoffContext, get_recursion_guard
            from sago.tools.file.spawn_agent import SpawnAgentTool

            handoff_ctx = HandoffContext(original_task=task, task_type="chain")
            guard = get_recursion_guard()
            guard.reset()

            tool = SpawnAgentTool()
            current_input = task
            # Track flat index into handoff_widget.chain for status updates
            _hf_idx = 0

            for step_idx, step_agents in enumerate(chain_steps):
                allowed_agents = []
                for agent in step_agents:
                    can, reason = guard.can_spawn(agent)
                    if can:
                        allowed_agents.append(agent)
                    else:
                        self.call_from_thread(self._add_notice_inline, f"Skip {agent}: {reason}")

                if not allowed_agents:
                    continue

                for agent in allowed_agents:
                    guard.enter(agent)

                if len(allowed_agents) == 1:
                    # Sequential single agent
                    agent = allowed_agents[0]
                    logger.debug("chain step %d: sequential agent=%s", step_idx + 1, agent)
                    info = tm.create_task(agent, f"Step {step_idx + 1}: {task[:50]}")
                    info.status = AgentStatus.RUNNING
                    self.call_from_thread(self._update_dashboard)
                    self.call_from_thread(self._update_spinner, f"Step {step_idx + 1}: {agent}")
                    # Update handoff flow: mark running
                    self.call_from_thread(handoff_widget.update_step, _hf_idx, "running")

                    t_step = _time.time()
                    try:
                        from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer

                        get_dev_tracer().record(
                            event_type=TraceEventType.AGENT_ROUTING,
                            source="orchestrator.chain",
                            action=f"CHAIN_STEP_{step_idx + 1} -> @{agent}",
                            data={
                                "agent": agent,
                                "step": step_idx + 1,
                                "task": str(current_input)[:200],
                            },
                        )
                    except Exception as e:
                        logger.debug("dev tracer record failed (chain step routing): %s", e)

                    context_str = (
                        handoff_ctx.get_compact_handoff_prompt(agent)
                        if step_idx > 0 or handoff_ctx.agent_results
                        else ""
                    )
                    result = tool.run(task=current_input, agent_name=agent, context=context_str)

                    dur_ms = (_time.time() - t_step) * 1000
                    is_success = not (result.startswith("Error") or "REJECTED" in result)
                    try:
                        from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer

                        get_dev_tracer().record(
                            event_type=TraceEventType.FUNCTION_RETURN,
                            source=f"agent.{agent}",
                            action=f"chain_step_{step_idx + 1}_complete",
                            duration_ms=dur_ms,
                            status="OK" if is_success else "ERROR",
                            data={"agent": agent, "result_preview": str(result)[:300]},
                        )
                    except Exception as e:
                        logger.debug("dev tracer record failed (chain step complete): %s", e)

                    handoff_ctx.add_result(agent, result, success=is_success)
                    logger.info(
                        "chain step %d result: agent=%s dur_ms=%.1f success=%s result_len=%d",
                        step_idx + 1,
                        agent,
                        dur_ms,
                        is_success,
                        len(result),
                    )
                    if "Files created/modified:" in result:
                        files_line = result.split("Files created/modified:")[1].split("\n")[0]
                        for f in files_line.split(","):
                            f = f.strip()
                            if f and f not in handoff_ctx.files_created:
                                handoff_ctx.files_created.append(f)

                    info.status = AgentStatus.COMPLETED
                    info.result = result
                    info.elapsed = _time.time() - info.start_time
                    self.call_from_thread(self._update_dashboard)
                    # Update handoff flow: mark completed/failed
                    _step_status = "completed" if is_success else "failed"
                    self.call_from_thread(handoff_widget.update_step, _hf_idx, _step_status)
                    _hf_idx += 1
                    current_input = result
                else:
                    # Parallel agents
                    logger.info(
                        "chain step %d: parallel agents=%s",
                        step_idx + 1,
                        allowed_agents,
                    )
                    self.call_from_thread(
                        self._update_spinner,
                        f"Step {step_idx + 1}: {len(allowed_agents)} agents in parallel",
                    )
                    results = {}
                    errors = {}

                    def _run_parallel(agent_name: str):
                        try:
                            ctx = (
                                handoff_ctx.get_compact_handoff_prompt(agent_name)
                                if step_idx > 0 or handoff_ctx.agent_results
                                else ""
                            )
                            r = tool.run(task=current_input, agent_name=agent_name, context=ctx)
                            results[agent_name] = r
                        except Exception as e:
                            errors[agent_name] = str(e)

                    threads = []
                    # Mark parallel agents as running in handoff flow
                    _parallel_indices = []
                    for agent in allowed_agents:
                        self.call_from_thread(handoff_widget.update_step, _hf_idx, "running")
                        _parallel_indices.append(_hf_idx)
                        _hf_idx += 1
                        t = threading.Thread(target=_run_parallel, args=(agent,), daemon=True)
                        threads.append((agent, t))
                        t.start()

                    for agent, t in threads:
                        t.join(timeout=300)
                        if t.is_alive():
                            errors[agent] = "Timeout (300s)"

                    # Merge parallel results and update handoff flow
                    merged_parts = []
                    for agent, hf_idx in zip(allowed_agents, _parallel_indices):
                        if agent in results:
                            r = results[agent]
                            is_ok = not (r.startswith("Error") or "REJECTED" in r)
                            handoff_ctx.add_result(agent, r, success=is_ok)
                            if "Files created/modified:" in r:
                                files_line = r.split("Files created/modified:")[1].split("\n")[0]
                                for f in files_line.split(","):
                                    f = f.strip()
                                    if f and f not in handoff_ctx.files_created:
                                        handoff_ctx.files_created.append(f)
                            merged_parts.append(f"[{agent}]: {r}")
                            _p_status = "completed" if is_ok else "failed"
                            self.call_from_thread(handoff_widget.update_step, hf_idx, _p_status)
                        elif agent in errors:
                            merged_parts.append(f"[{agent}] Error: {errors[agent]}")
                            self.call_from_thread(handoff_widget.update_step, hf_idx, "failed")

                    current_input = "\n\n".join(merged_parts)
                    logger.debug(
                        "chain step %d parallel merge: ok=%d errors=%d",
                        step_idx + 1,
                        len(results),
                        len(errors),
                    )

                    for agent in allowed_agents:
                        guard.exit(agent)

            logger.info("chain completed: %d steps", len(chain_steps))
            self.call_from_thread(self._hide_spinner)
            self.call_from_thread(
                self._add_assistant_message,
                current_input,
                agent_name=flat_agents[-1] if flat_agents else "chain",
            )
        except Exception as e:
            logger.error("chain failed: error=%s", e, exc_info=True)
            try:
                from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer

                get_dev_tracer().record(
                    event_type=TraceEventType.ERROR,
                    source="orchestrator.chain",
                    action="chain_failed",
                    status="ERROR",
                    data={"error": str(e), "error_type": type(e).__name__},
                )
            except Exception as exc:
                logger.debug("dev tracer record failed (chain failed): %s", exc)
            self.call_from_thread(self._hide_spinner)
            self.call_from_thread(self._add_error_inline, f"Chain error: {e}")
        finally:
            self.is_thinking = False

    def _process_orchestration(self: SagoApp, task: str) -> None:
        logger.info("orchestration requested: task_len=%d", len(task))
        self.is_thinking = True
        t = threading.Thread(target=self._process_orchestration_thread, args=(task,), daemon=True)
        t.start()

    def _process_orchestration_thread(self: SagoApp, task: str) -> None:
        self.call_from_thread(self._show_spinner, "Analyzing task for delegation...")
        try:
            api_key = self._get_provider_api_key()
            if not api_key:
                self.call_from_thread(self._hide_spinner)
                self.call_from_thread(
                    self._add_notice_inline,
                    f"No API key. Set {self._get_provider_key_name()} environment variable.",
                )
                return

            from openai import OpenAI

            from sago.agents.registry import list_agents

            client = OpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                timeout=30.0,
            )
            agents = list_agents()
            agent_list_str = "\n".join(
                [
                    f"- {a['name']}: {a.get('role', '')} | Skills: {', '.join(a.get('skills', [])[:3])}"
                    for a in agents[:50]
                ]
            )

            system_prompt = (
                "You are a task orchestrator. Analyze the task and break it into steps.\n"
                "For each step, specify which agent should handle it.\n"
                'Reply with a JSON list of steps: [{"agent": "agent-name", "task": "what to do"}]\n\n'
                f"Available agents:\n{agent_list_str}"
            )
            prompt_len = len(system_prompt) + len(task)
            logger.info(
                "planning LLM call: model=%s prompt_len=%d agent_count=%d",
                self.current_model,
                prompt_len,
                len(agents),
            )

            try:
                response = client.chat.completions.create(
                    model=self.current_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": task},
                    ],
                    max_tokens=1024,
                )
                plan_text = response.choices[0].message.content or "[]"
                logger.info(
                    "planning LLM response: model=%s response_len=%d finish_reason=%s",
                    self.current_model,
                    len(plan_text),
                    response.choices[0].finish_reason if response.choices else "unknown",
                )
            except Exception as api_err:
                logger.error(
                    "planning LLM call failed: model=%s error=%s", self.current_model, api_err
                )
                self.call_from_thread(self._hide_spinner)
                self.call_from_thread(
                    self._add_error_inline,
                    f"Failed to create plan: {api_err}",
                )
                return

            try:
                json_match = re.search(r"\[.*\]", plan_text, re.DOTALL)
                if json_match:
                    plan = json.loads(json_match.group())
                else:
                    plan = [{"agent": "python-engineer", "task": task}]
            except json.JSONDecodeError:
                logger.debug("plan JSON parse failed, falling back to python-engineer")
                plan = [{"agent": "python-engineer", "task": task}]

            logger.debug("plan parsed: %d steps", len(plan))
            for i, step in enumerate(plan):
                logger.debug(
                    "plan step %d: agent=%s task=%s",
                    i + 1,
                    step.get("agent", "python-engineer"),
                    step.get("task", "")[:80],
                )

            # Show plan with OrchestrationPlanWidget
            from sago.tui.widgets import OrchestrationPlanWidget

            plan_data = [
                {
                    "agent": step.get("agent", "python-engineer"),
                    "task": step.get("task", ""),
                    "status": "pending",
                }
                for step in plan
            ]
            plan_widget = OrchestrationPlanWidget(plan_data)

            def _mount_plan() -> None:
                try:
                    target = getattr(self, "_active_exchange_card", None)
                    if target is not None:
                        resp = getattr(target, "_response_container", None)
                        if resp is not None:
                            resp.mount(plan_widget)
                        else:
                            target.mount(plan_widget)
                    else:
                        self.query_one("#messages").mount(plan_widget)
                except Exception as e:
                    logger.debug("mount orchestration plan failed: %s", e)

            self.call_from_thread(self._hide_spinner)
            self.call_from_thread(_mount_plan)

            # Store plan widget reference for step updates during execution
            self._orchestration_plan_widget = plan_widget

            # Show approval bar with buttons
            approval_msg = f"Execute {len(plan)} steps?  Press [Y] Approve or [N] Deny"
            self.call_from_thread(self._show_approval_bar, approval_msg)

            # Store plan for /approve command
            self.pending_orchestration = {"task": task, "plan": plan}

        except Exception as e:
            logger.error("orchestration planning failed: error=%s", e, exc_info=True)
            try:
                from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer

                get_dev_tracer().record(
                    event_type=TraceEventType.ERROR,
                    source="orchestrator.plan_parse",
                    action="orchestration_plan_failed",
                    status="ERROR",
                    data={"error": str(e), "error_type": type(e).__name__, "task": task[:200]},
                )
            except Exception as exc:
                logger.debug("dev tracer record failed (orchestration plan failed): %s", exc)
            self.call_from_thread(self._hide_spinner)
            self.call_from_thread(self._add_error_inline, f"Orchestration error: {e}")
        finally:
            self.is_thinking = False

    def _execute_orchestration_plan(self: SagoApp, plan: list[dict]) -> None:
        """Execute an approved orchestration plan — dispatches to background thread."""
        logger.info("plan execution started: %d steps", len(plan))
        self.is_thinking = True
        self._show_spinner(f"Executing {len(plan)} steps...")
        t = threading.Thread(
            target=self._execute_orchestration_plan_thread, args=(plan,), daemon=True
        )
        t.start()

    def _execute_orchestration_plan_thread(self: SagoApp, plan: list[dict]) -> None:
        """Runs in a background thread — all call_from_thread calls are safe here."""
        try:
            from sago.agents.handoff import HandoffContext, get_recursion_guard
            from sago.tools.file.spawn_agent import SpawnAgentTool

            handoff_ctx = HandoffContext(
                original_task=plan[0].get("task", "") if plan else "",
                task_type="orchestrate",
            )
            guard = get_recursion_guard()
            guard.reset()

            tool = SpawnAgentTool()
            results = []
            for i, step in enumerate(plan):
                agent = step.get("agent", "python-engineer")
                step_task = step.get("task", "")

                # Check recursion guard
                allowed, reason = guard.can_spawn(agent)
                if not allowed:
                    results.append(f"**{agent}**: SKIPPED — {reason}")
                    continue

                guard.enter(agent)
                logger.debug(
                    "plan step %d/%d: agent=%s task=%s", i + 1, len(plan), agent, step_task[:80]
                )
                self.call_from_thread(self._update_spinner, f"Step {i + 1}/{len(plan)}: {agent}")

                # Update orchestration plan widget: mark step as active
                plan_widget = getattr(self, "_orchestration_plan_widget", None)
                if plan_widget is not None:
                    self.call_from_thread(plan_widget.set_current_step, i)

                # Build structured context from previous steps
                context_str = ""
                if i > 0:
                    context_str = handoff_ctx.get_compact_handoff_prompt(agent)

                result = tool.run(task=step_task, agent_name=agent, context=context_str)

                # Record in handoff context
                is_success = not (
                    result.startswith("Error")
                    or result.startswith("Last error")
                    or "REJECTED" in result
                )
                logger.info(
                    "plan step %d/%d result: agent=%s success=%s result_len=%d",
                    i + 1,
                    len(plan),
                    agent,
                    is_success,
                    len(result),
                )
                handoff_ctx.add_result(agent, result, success=is_success)

                # Dev trace: per-step result with correct status
                try:
                    from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer

                    get_dev_tracer().record(
                        event_type=TraceEventType.FUNCTION_RETURN,
                        source=f"agent.{agent}",
                        action=f"orchestrate_step_{i + 1}_complete",
                        duration_ms=0.0,
                        status="ERROR" if not is_success else "OK",
                        data={
                            "step": i + 1,
                            "agent": agent,
                            "task_preview": step_task[:200],
                            "success": is_success,
                            "result_preview": result[:300],
                        },
                    )
                except Exception as exc:
                    logger.debug("dev tracer record failed (orchestrate step %d): %s", i + 1, exc)

                # Extract files created
                if "Files created/modified:" in result:
                    files_line = result.split("Files created/modified:")[1].split("\n")[0]
                    for f in files_line.split(","):
                        f = f.strip()
                        if f and f not in handoff_ctx.files_created:
                            handoff_ctx.files_created.append(f)

                results.append(f"**{agent}**: {result[:500]}")
                # Update orchestration plan widget: mark step completed/failed
                plan_widget = getattr(self, "_orchestration_plan_widget", None)
                if plan_widget is not None:
                    _step_status = "completed" if is_success else "failed"
                    self.call_from_thread(plan_widget.mark_step, i, _step_status)
                guard.exit(agent)

            logger.info("plan execution completed: %d steps", len(plan))
            self.call_from_thread(self._hide_spinner)
            final = f"Orchestration complete ({len(plan)} steps):\n\n" + "\n\n".join(results)
            self.call_from_thread(self._add_assistant_message, final)
        except Exception as e:
            logger.error("plan execution failed: error=%s", e, exc_info=True)
            try:
                from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer

                get_dev_tracer().record(
                    event_type=TraceEventType.ERROR,
                    source="orchestrator.plan",
                    action="orchestration_failed",
                    status="ERROR",
                    data={"error": str(e), "error_type": type(e).__name__},
                )
            except Exception as exc:
                logger.debug("dev tracer record failed (orchestration failed): %s", exc)
            self.call_from_thread(self._hide_spinner)
            self.call_from_thread(self._add_error_inline, f"Execution error: {e}")
        finally:
            self.is_thinking = False

    def _process_parallel(self: SagoApp, agents: list[str], task: str) -> None:
        """Run multiple agents in parallel on the same task."""
        logger.info("parallel requested: agents=%s task_len=%d", agents, len(task))
        self.is_thinking = True
        t = threading.Thread(target=self._process_parallel_thread, args=(agents, task), daemon=True)
        t.start()

    def _process_parallel_thread(self: SagoApp, agents: list[str], task: str) -> None:
        """Runs in a background thread."""
        logger.info("parallel thread started: agents=%s", agents)
        tm = self._task_manager or get_task_manager()

        # Create task entries for each agent
        task_infos = []
        for agent_name in agents:
            info = tm.create_task(agent_name, task)
            info.status = AgentStatus.RUNNING
            task_infos.append(info)

        # Show parallel bar
        try:
            self.call_from_thread(self._show_parallel_bar, agents)
            self.call_from_thread(self._update_dashboard)
        except Exception as e:
            logger.debug("parallel bar setup failed: %s", e)

        try:
            from sago.tools.file.spawn_agent import SpawnAgentTool

            tool = SpawnAgentTool()
            results: list[dict[str, Any]] = []

            def execute_agent(agent_name: str, subtask: str, info: Any) -> dict[str, Any]:
                """Execute a single agent, respecting cancellation and streaming immediately."""
                start = _time.time()
                self.call_from_thread(
                    self._update_parallel_agent_status, agent_name, "⚡ Running..."
                )
                try:
                    # Check cancellation before starting
                    if info.cancel_event.is_set():
                        info.status = AgentStatus.CANCELLED
                        self.call_from_thread(
                            self._update_parallel_agent_status, agent_name, "🚫 Cancelled"
                        )
                        return {
                            "agent": agent_name,
                            "result": "Cancelled",
                            "elapsed": 0,
                            "success": False,
                        }

                    result = tool.run(task=subtask, agent_name=agent_name)
                    elapsed = _time.time() - start
                    info.elapsed = elapsed
                    info.status = AgentStatus.COMPLETED
                    info.result = result
                    self.call_from_thread(self._update_dashboard)
                    self.call_from_thread(
                        self._update_parallel_agent_status, agent_name, f"✓ Done ({elapsed:.1f}s)"
                    )
                    # Progressively stream results as soon as this agent completes
                    self.call_from_thread(
                        self._add_parallel_result,
                        agent_name,
                        result,
                        elapsed,
                        True,
                    )
                    return {
                        "agent": agent_name,
                        "result": result,
                        "elapsed": elapsed,
                        "success": True,
                    }
                except Exception as e:
                    elapsed = _time.time() - start
                    info.elapsed = elapsed
                    info.status = AgentStatus.FAILED
                    info.error = str(e)
                    self.call_from_thread(self._update_dashboard)
                    self.call_from_thread(
                        self._update_parallel_agent_status, agent_name, f"✗ Failed ({elapsed:.1f}s)"
                    )
                    self.call_from_thread(
                        self._add_parallel_result,
                        agent_name,
                        f"Error: {e}",
                        elapsed,
                        False,
                    )
                    return {
                        "agent": agent_name,
                        "result": f"Error: {e}",
                        "elapsed": elapsed,
                        "success": False,
                    }

            logger.info("parallel execution starting: %d agents", len(agents))
            # Execute all agents in parallel using ThreadPoolExecutor
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(agents)) as executor:
                futures = {}
                for info in task_infos:
                    future = executor.submit(execute_agent, info.agent_name, task, info)
                    futures[future] = info
                    if self._parallel_lock:
                        with self._parallel_lock:
                            self._active_parallel_futures[info.agent_id] = future

                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    results.append(result)

            # Hide parallel bar and spinner
            self.call_from_thread(self._hide_parallel_bar)
            self.call_from_thread(self._hide_spinner)

            # Summary
            ok = sum(1 for r in results if r["success"])
            fail = len(results) - ok
            total_time = sum(r["elapsed"] for r in results)
            max_time = max(r["elapsed"] for r in results) if results else 0
            logger.info(
                "parallel completed: ok=%d fail=%d wall_time=%.1fs combined=%.1fs",
                ok,
                fail,
                max_time,
                total_time,
            )
            self.call_from_thread(
                self._add_system_message,
                f"Parallel complete: {ok} ok, {fail} failed | "
                f"Total wall time: {max_time:.1f}s | Combined: {total_time:.1f}s",
            )

        except Exception as e:
            logger.error("parallel execution failed: error=%s", e, exc_info=True)
            self.call_from_thread(self._hide_parallel_bar)
            self.call_from_thread(self._hide_spinner)
            self.call_from_thread(self._add_error_inline, f"Parallel error: {e}")
        finally:
            self.is_thinking = False
            if self._parallel_lock:
                with self._parallel_lock:
                    self._active_parallel_futures.clear()
            self.call_from_thread(self._update_dashboard)

    def _show_parallel_bar(self: SagoApp, agents: list[str]) -> None:
        """Show the parallel agent status bar."""
        container = self.query_one("#parallel-agents")
        container.remove_children()
        for agent_name in agents:
            safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", agent_name)
            container.mount(
                Static(
                    f"⏳ {agent_name}: Waiting...",
                    id=f"pagent-{safe_id}",
                    classes="parallel-agent",
                    markup=False,
                )
            )
        self.query_one("#parallel-bar").add_class("visible")

    def _update_parallel_agent_status(self: SagoApp, agent_name: str, status_text: str) -> None:
        """Update status label for a specific parallel agent in real-time."""
        try:
            safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", agent_name)
            node = self.query_one(f"#pagent-{safe_id}", Static)
            node.update(f"{agent_name}: {status_text}")
        except Exception as exc:
            logger.debug("parallel agent status update failed for %s: %s", agent_name, exc)

    def _hide_parallel_bar(self: SagoApp) -> None:
        """Hide the parallel agent status bar."""
        self.query_one("#parallel-bar").remove_class("visible")
