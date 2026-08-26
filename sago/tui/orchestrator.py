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


_STRONG_ERROR_START = re.compile(
    r"""^\s*(?:
        error \b |
        exception \b |
        traceback \b |
        fatal \b |
        rejected \s* : |
        cannot \s+ spawn |
        delegation \s+ error |
        chain \s+ error |
        parallel \s+ error |
        execution \s+ error |
        orchestration \s+ error |
        api \s+ error |
        unauthorized |
        permission \s+ denied
    )""",
    re.IGNORECASE | re.VERBOSE,
)

# Structured failure markers emitted by spawn_agent/executor on real failures.
_EMBEDDED_ERROR_MARKERS = (
    "could not be spawned",
    "last error:",
    "traceback (most recent call last)",
)


def _is_error_result(result: str) -> bool:
    """Check if a tool result indicates a hard failure.

    Only strong signals count (result *starting* with an error marker, or an
    explicit embedded failure marker). Generic words like "error" or "failed"
    appearing anywhere in prose must NOT abort chains — e.g. an agent saying
    "no errors found" or "0 failed tests" previously killed the chain.
    """
    if not isinstance(result, str) or not result.strip():
        return False
    if _STRONG_ERROR_START.match(result):
        return True
    lowered = result.lower()
    if any(marker in lowered for marker in _EMBEDDED_ERROR_MARKERS):
        return True
    return "rate limit" in lowered[:300]


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

        # Set callbacks in context so spawned agents inherit UI updates (per-agent distinct)
        from sago.engine.simple_executor import set_execution_callbacks

        def _on_tool_call(n, a, ag=""):
            self.call_from_thread(self._update_spinner, f"Running: {n}")

        def _on_tool_result(n, a, r, s, ag=""):
            _ag = ag or agent_name
            try:
                self.call_from_thread(self._add_tool_call, n, a, r, s, _ag)
            except TypeError:
                self.call_from_thread(self._add_tool_call, n, a, r, s)

        def _on_thinking(t, ag=""):
            self.call_from_thread(self._update_spinner, t)
            low = t.strip().lower() if t else ""
            if low.startswith("planning...") or low.startswith("working...") or ("step " in low and "intent:" in low):
                return
            if t and len(t.strip()) >= 20:
                _ag2 = ag or agent_name
                try:
                    self.call_from_thread(self._add_thinking_card, t, _ag2)
                except TypeError:
                    self.call_from_thread(self._add_thinking_card, t)
                # Also record per-agent thinking to dev tracer (distinct)
                try:
                    from sago.tracking.dev_tracer import get_dev_tracer

                    get_dev_tracer().record_thinking(
                        source=f"agent.{_ag2}", model=getattr(self, "current_model", ""), thinking_content=t
                    )
                except Exception:
                    pass

        set_execution_callbacks(
            on_tool_call=_on_tool_call,
            on_tool_result=_on_tool_result,
            on_thinking=_on_thinking,
        )

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
            result_is_error = "could not be spawned" in result or _is_error_result(result)
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
                # Auto summary card by agent for delegation
                try:
                    _pa = ""
                    try:
                        _pa_path = __import__("pathlib").Path.cwd() / "PROJECT_ANALYSIS.md"
                        if _pa_path.exists():
                            _pa = _pa_path.read_text(encoding="utf-8", errors="replace")[:8000]
                    except Exception:
                        _pa = ""
                    self.call_from_thread(self._add_summary_by_agent_card, None, _pa)
                except Exception as _e:
                    logger.debug("Auto summary after delegation failed: %s", _e)
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
            try:
                self.call_from_thread(self._try_process_queue)
            except Exception:
                pass

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

        # Set callbacks in context so spawned agents inherit UI updates (per-agent distinct, sequential)
        from sago.engine.simple_executor import set_execution_callbacks

        def _on_tool_call(n, a, ag=""):
            self.call_from_thread(self._update_spinner, f"Running: {n}")

        def _on_tool_result(n, a, r, s, ag=""):
            _ag = ag or getattr(self, "current_agent", "")
            try:
                self.call_from_thread(self._add_tool_call, n, a, r, s, _ag)
            except TypeError:
                self.call_from_thread(self._add_tool_call, n, a, r, s)

        def _on_thinking(t, ag=""):
            self.call_from_thread(self._update_spinner, t)
            low = t.strip().lower() if t else ""
            if low.startswith("planning...") or low.startswith("working...") or ("step " in low and "intent:" in low):
                return
            if t and len(t.strip()) >= 20:
                _ag2 = ag or getattr(self, "current_agent", "") or "sago"
                try:
                    self.call_from_thread(self._add_thinking_card, t, _ag2)
                except TypeError:
                    self.call_from_thread(self._add_thinking_card, t)
                try:
                    from sago.tracking.dev_tracer import get_dev_tracer

                    get_dev_tracer().record_thinking(
                        source=f"agent.{_ag2}", model=getattr(self, "current_model", ""), thinking_content=t
                    )
                except Exception:
                    pass

        set_execution_callbacks(
            on_tool_call=_on_tool_call,
            on_tool_result=_on_tool_result,
            on_thinking=_on_thinking,
        )

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
                        resp.display = True
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

            from sago.agents.handoff import HandoffContext, create_fresh_guard
            from sago.tools.file.spawn_agent import SpawnAgentTool

            handoff_ctx = HandoffContext(original_task=task, task_type="chain")
            guard = create_fresh_guard()

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
                    result = tool.run(
                        task=current_input, agent_name=agent, context=context_str, guard=guard
                    )

                    dur_ms = (_time.time() - t_step) * 1000
                    is_success = not _is_error_result(result)
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
                    # Stop chain on failure — subsequent steps depend on this one
                    if not is_success:
                        logger.info(
                            "chain step %d failed — stopping chain, skipping remaining steps",
                            step_idx + 1,
                        )
                        self.call_from_thread(
                            self._add_notice_inline,
                            f"Chain stopped: step {step_idx + 1} failed ({result[:80]}...)",
                        )
                        break
                    current_input = result
                    # NOTE: SpawnAgentTool.enter/exit uses the RESOLVED agent name
                    # (aliases like code-reviewer -> reviewer) inside its own
                    # finally-block. Exiting here with the raw plan name used to
                    # mismatch on aliased agents and leave permanent residue in
                    # the guard, poisoning later steps with false cycle errors.
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
                            # Pass the shared chain guard explicitly: worker threads
                            # would otherwise get a fresh thread-local guard, silently
                            # disabling cycle/depth protection.
                            r = tool.run(
                                task=current_input,
                                agent_name=agent_name,
                                context=ctx,
                                guard=guard,
                            )
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
                    parallel_has_failure = False
                    for agent, hf_idx in zip(allowed_agents, _parallel_indices):
                        if agent in results:
                            r = results[agent]
                            is_ok = not _is_error_result(r)
                            handoff_ctx.add_result(agent, r, success=is_ok)
                            if "Files created/modified:" in r:
                                files_line = r.split("Files created/modified:")[1].split("\n")[0]
                                for f in files_line.split(","):
                                    f = f.strip()
                                    if f and f not in handoff_ctx.files_created:
                                        handoff_ctx.files_created.append(f)
                            merged_parts.append(f"[{agent}]: {r}")
                            _p_status = "completed" if is_ok else "failed"
                            if not is_ok:
                                parallel_has_failure = True
                            self.call_from_thread(handoff_widget.update_step, hf_idx, _p_status)
                        elif agent in errors:
                            merged_parts.append(f"[{agent}] Error: {errors[agent]}")
                            parallel_has_failure = True
                            self.call_from_thread(handoff_widget.update_step, hf_idx, "failed")

                    # Stop chain on parallel failure
                    if parallel_has_failure:
                        logger.info(
                            "chain step %d parallel agents failed — stopping chain",
                            step_idx + 1,
                        )
                        self.call_from_thread(
                            self._add_notice_inline,
                            f"Chain stopped: parallel step {step_idx + 1} had failures",
                        )
                        break

                    current_input = "\n\n".join(merged_parts)
                    logger.debug(
                        "chain step %d parallel merge: ok=%d errors=%d",
                        step_idx + 1,
                        len(results),
                        len(errors),
                    )

                    # Guard lifecycle for parallel agents is handled by SpawnAgentTool
                    # No need to exit here since we removed the pre-enter calls

            logger.info("chain completed: %d steps", len(chain_steps))
            self.call_from_thread(self._hide_spinner)
            self.call_from_thread(
                self._add_assistant_message,
                current_input,
                agent_name=flat_agents[-1] if flat_agents else "chain",
            )
            # Auto-mount Summary Card by agent (spec: collapsed=False, per-agent sections)
            try:
                # Reuse cached analysis if available for output file hint
                _pa = ""
                try:
                    _pa_path = __import__("pathlib").Path.cwd() / "PROJECT_ANALYSIS.md"
                    if _pa_path.exists():
                        _pa = _pa_path.read_text(encoding="utf-8", errors="replace")[:8000]
                except Exception:
                    _pa = ""
                self.call_from_thread(self._add_summary_by_agent_card, None, _pa)
            except Exception as _e:
                logger.debug("Auto summary card after chain failed: %s", _e)
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
            try:
                self.call_from_thread(self._try_process_queue)
            except Exception:
                pass

    def _process_orchestration(self: SagoApp, task: str) -> None:
        logger.info("orchestration requested: task_len=%d", len(task))
        self.is_thinking = True
        t = threading.Thread(target=self._process_orchestration_thread, args=(task,), daemon=True)
        t.start()

    def _process_orchestration_thread(self: SagoApp, task: str) -> None:
        # Set callbacks in context so spawned agents inherit UI updates (per-agent distinct, sequential)
        from sago.engine.simple_executor import set_execution_callbacks

        def _on_tool_call(n, a, ag=""):
            self.call_from_thread(self._update_spinner, f"Running: {n}")

        def _on_tool_result(n, a, r, s, ag=""):
            _ag = ag or getattr(self, "current_agent", "")
            try:
                self.call_from_thread(self._add_tool_call, n, a, r, s, _ag)
            except TypeError:
                self.call_from_thread(self._add_tool_call, n, a, r, s)

        def _on_thinking(t, ag=""):
            self.call_from_thread(self._update_spinner, t)
            low = t.strip().lower() if t else ""
            if low.startswith("planning...") or low.startswith("working...") or ("step " in low and "intent:" in low):
                return
            if t and len(t.strip()) >= 20:
                _ag2 = ag or getattr(self, "current_agent", "") or "sago"
                try:
                    self.call_from_thread(self._add_thinking_card, t, _ag2)
                except TypeError:
                    self.call_from_thread(self._add_thinking_card, t)
                try:
                    from sago.tracking.dev_tracer import get_dev_tracer

                    get_dev_tracer().record_thinking(
                        source=f"agent.{_ag2}", model=getattr(self, "current_model", ""), thinking_content=t
                    )
                except Exception:
                    pass

        set_execution_callbacks(
            on_tool_call=_on_tool_call,
            on_tool_result=_on_tool_result,
            on_thinking=_on_thinking,
        )

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

            from sago.agents.registry import list_agents
            from sago.llm.tui_providers import get_tui_client

            client, api_model = get_tui_client(self.current_provider, self.current_model)
            use_native_gemini = self.current_provider == "google"
            agents = list_agents()
            # Cap displayed agents to avoid token blowup (339 agents → ~17k chars)
            MAX_PLAN_AGENTS = 60
            display_agents = agents[:MAX_PLAN_AGENTS]
            agent_list_str = "\n".join(
                [
                    f"- {a['name']}: {a.get('role', '')} | Skills: {', '.join(a.get('skills', [])[:3])}"
                    for a in display_agents
                ]
            )
            if len(agents) > MAX_PLAN_AGENTS:
                agent_list_str += f"\n... and {len(agents) - MAX_PLAN_AGENTS} more agents available"

            system_prompt = (
                "You are a task orchestrator. Analyze the task and break it into steps.\n"
                "IMPORTANT: For simple tasks (reading files, answering questions, checking status), "
                "use a SINGLE step with python-engineer. Do NOT over-decompose simple tasks.\n"
                "Only break into multiple steps for genuinely complex multi-phase work "
                "(e.g., create API + write tests + add docs).\n"
                "Each step should be minimal and focused — one agent doing ONE thing.\n"
                'Reply with a JSON list: [{"agent": "agent-name", "task": "specific action"}]\n\n'
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
                if use_native_gemini:
                    from google.genai import types as google_types

                    contents = [
                        google_types.Content(
                            role="user",
                            parts=[google_types.Part(text=f"{system_prompt}\n\n{task}")],
                        )
                    ]
                    # Retry with backoff for rate limits
                    max_retries = 3
                    plan_text = None
                    for attempt in range(max_retries):
                        try:
                            response = client.models.generate_content(
                                model=api_model,
                                contents=contents,
                                config=google_types.GenerateContentConfig(max_output_tokens=1024),
                            )
                            plan_text = response.text or "[]"
                            break
                        except Exception as api_err:
                            err_str = str(api_err).lower()
                            if (
                                "rate" in err_str or "limit" in err_str
                            ) and attempt < max_retries - 1:
                                wait_sec = (2**attempt) * 2
                                logger.warning("Planning rate limit, retrying in %ds", wait_sec)
                                time.sleep(wait_sec)
                            else:
                                raise
                    if plan_text is None:
                        plan_text = "[]"
                else:
                    max_retries = 3
                    plan_text = None
                    for attempt in range(max_retries):
                        try:
                            response = client.chat.completions.create(
                                model=api_model,
                                messages=[
                                    {"role": "system", "content": system_prompt},
                                    {"role": "user", "content": task},
                                ],
                                max_tokens=1024,
                            )
                            plan_text = response.choices[0].message.content or "[]"
                            break
                        except Exception as api_err:
                            err_str = str(api_err).lower()
                            if (
                                "429" in err_str or "rate" in err_str
                            ) and attempt < max_retries - 1:
                                wait_sec = (2**attempt) * 2
                                logger.warning("Planning rate limit, retrying in %ds", wait_sec)
                                time.sleep(wait_sec)
                            else:
                                raise
                    if plan_text is None:
                        plan_text = "[]"
                logger.info(
                    "planning LLM response: model=%s response_len=%d",
                    self.current_model,
                    len(plan_text),
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

            # Validate agent names against registry, fix hallucinated names
            valid_agents = {a["name"] for a in list_agents()}
            for step in plan:
                agent_name = step.get("agent", "")
                if agent_name not in valid_agents:
                    # Fuzzy match against the registry. Iterating a SET made the
                    # pick nondeterministic — the same hallucinated name could
                    # map to a different engineer on every run.
                    best_name = None
                    best_score = 0
                    for valid in sorted(valid_agents):
                        if valid == agent_name:
                            best_name, best_score = valid, 10**6
                            break
                        overlap = min(len(valid), len(agent_name))
                        if (valid in agent_name or agent_name in valid) and overlap > best_score:
                            best_name, best_score = valid, overlap
                    if best_name:
                        step["agent"] = best_name
                    else:
                        # Default to python-engineer for unknown agents
                        logger.warning(
                            "Hallucinated agent '%s' not in registry, falling back to python-engineer",
                            agent_name,
                        )
                        step["agent"] = "python-engineer"

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
                    container = None
                    if target is not None:
                        container = getattr(target, "_response_container", None)
                    if container is None:
                        container = self.query_one("#messages")
                    else:
                        container.display = True

                    # Mount the visual plan widget
                    container.mount(plan_widget)

                    # Mount editable plan summary with instructions
                    from rich.markup import escape as _escape
                    from textual.widgets import Static as TextualStatic

                    plan_lines = []
                    for i, step in enumerate(plan):
                        agent = step.get("agent", "python-engineer")
                        task = step.get("task", "")
                        plan_lines.append(f"  {i + 1}. ({_escape(agent)}) {_escape(task)}")

                    plan_text = "\n".join(plan_lines)
                    instructions = (
                        f"[dim]{plan_text}[/dim]\n\n"
                        f"[bold yellow]Commands:[/bold yellow] "
                        f"[dim]/plan edit <step> <new task>[/dim] — modify a step  •  "
                        f"[dim]/plan add <agent>: <task>[/dim] — add a step  •  "
                        f"[dim]/plan remove <step>[/dim] — remove a step  •  "
                        f"[bold green]Y[/bold green] — approve  •  [bold red]N[/bold red] — deny"
                    )
                    # Use markup=False fallback for user-controlled task text to avoid MarkupError
                    # from stray brackets like "|agents=339', 'path': '/mnt/ramdisk/sago]"
                    try:
                        container.mount(
                            TextualStatic(instructions, markup=True, classes="msg-assistant")
                        )
                    except Exception:
                        try:
                            container.mount(
                                TextualStatic(
                                    _escape(instructions), markup=True, classes="msg-assistant"
                                )
                            )
                        except Exception:
                            container.mount(
                                TextualStatic(instructions, markup=False, classes="msg-assistant")
                            )
                    container.scroll_end()
                except Exception as e:
                    logger.debug("mount orchestration plan failed: %s", e)

            self.call_from_thread(self._hide_spinner)
            self.call_from_thread(_mount_plan)

            # Store plan widget reference for step updates during execution
            self._orchestration_plan_widget = plan_widget

            # Show approval bar with a compact summary of WHAT will run
            from rich.markup import escape as _escape

            step_lines = [
                f"{i + 1}. ({_escape(s.get('agent', '?'))}) {_escape((s.get('task', '') or '')[:70])}"
                for i, s in enumerate(plan[:5])
            ]
            more = f"\n… +{len(plan) - 5} more" if len(plan) > 5 else ""
            steps_text = "\n".join(step_lines) + more
            approval_msg = (
                f"Execute {len(plan)} step(s)?\n{steps_text}\n"
                f"\\[Y] Approve · \\[N] Deny · edit with /plan"
            )
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
            try:
                self.call_from_thread(self._try_process_queue)
            except Exception:
                pass

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
        # Set callbacks in context so spawned agents inherit UI updates (per-agent distinct, sequential)
        from sago.engine.simple_executor import set_execution_callbacks

        def _on_tool_call(n, a, ag=""):
            self.call_from_thread(self._update_spinner, f"Running: {n}")

        def _on_tool_result(n, a, r, s, ag=""):
            _ag = ag or getattr(self, "current_agent", "")
            try:
                self.call_from_thread(self._add_tool_call, n, a, r, s, _ag)
            except TypeError:
                self.call_from_thread(self._add_tool_call, n, a, r, s)

        def _on_thinking(t, ag=""):
            self.call_from_thread(self._update_spinner, t)
            low = t.strip().lower() if t else ""
            if low.startswith("planning...") or low.startswith("working...") or ("step " in low and "intent:" in low):
                return
            if t and len(t.strip()) >= 20:
                _ag2 = ag or getattr(self, "current_agent", "") or "sago"
                try:
                    self.call_from_thread(self._add_thinking_card, t, _ag2)
                except TypeError:
                    self.call_from_thread(self._add_thinking_card, t)
                try:
                    from sago.tracking.dev_tracer import get_dev_tracer

                    get_dev_tracer().record_thinking(
                        source=f"agent.{_ag2}", model=getattr(self, "current_model", ""), thinking_content=t
                    )
                except Exception:
                    pass

        set_execution_callbacks(
            on_tool_call=_on_tool_call,
            on_tool_result=_on_tool_result,
            on_thinking=_on_thinking,
        )

        try:
            from sago.agents.handoff import HandoffContext, create_fresh_guard
            from sago.tools.file.spawn_agent import SpawnAgentTool

            handoff_ctx = HandoffContext(
                original_task=plan[0].get("task", "") if plan else "",
                task_type="orchestrate",
            )
            guard = create_fresh_guard()

            tool = SpawnAgentTool()
            step_results = []  # (agent, success) tuples for summary
            for i, step in enumerate(plan):
                agent = step.get("agent", "python-engineer")
                step_task = step.get("task", "")

                # Check recursion guard
                allowed, reason = guard.can_spawn(agent)
                if not allowed:
                    step_results.append((agent, False))
                    self.call_from_thread(
                        self._add_orchestrate_step,
                        i + 1,
                        len(plan),
                        agent,
                        step_task,
                        f"SKIPPED — {reason}",
                        [],
                        False,
                        0.0,
                    )
                    continue

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

                step_start = time.time()
                # Explicitly share the plan's guard: SpawnAgentTool would otherwise
                # fall back to thread-local lookup, which can return a stale guard
                # left behind by an earlier command (thread idents get recycled),
                # producing false 'Cycle detected' rejections for every step.
                result = tool.run(
                    task=step_task, agent_name=agent, context=context_str, guard=guard
                )
                step_elapsed = time.time() - step_start

                # Record in handoff context
                is_success = not _is_error_result(result)
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
                        duration_ms=step_elapsed * 1000,
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

                # Extract files created and tools used from result
                files_created = []
                tools_used = []
                if "Files created/modified:" in result:
                    files_line = result.split("Files created/modified:")[1].split("\n")[0]
                    for f in files_line.split(","):
                        f = f.strip()
                        if f and f not in handoff_ctx.files_created:
                            handoff_ctx.files_created.append(f)
                            files_created.append(f)
                if "Tools used:" in result:
                    tools_line = result.split("Tools used:")[1].split("\n")[0]
                    tools_used = [t.strip() for t in tools_line.split(",") if t.strip()]

                step_results.append((agent, is_success))

                # Mount step result into exchange card
                self.call_from_thread(
                    self._add_orchestrate_step,
                    i + 1,
                    len(plan),
                    agent,
                    step_task,
                    result,
                    tools_used,
                    is_success,
                    step_elapsed,
                )

                # Update orchestration plan widget: mark step completed/failed
                plan_widget = getattr(self, "_orchestration_plan_widget", None)
                if plan_widget is not None:
                    _step_status = "completed" if is_success else "failed"
                    self.call_from_thread(plan_widget.mark_step, i, _step_status)

            logger.info("plan execution completed: %d steps", len(plan))
            self.call_from_thread(self._hide_spinner)

            # Mount final summary into exchange card
            ok_count = sum(1 for _, ok in step_results if ok)
            fail_count = len(step_results) - ok_count
            summary_parts = [f"[bold]Orchestration complete[/bold] ({len(plan)} steps)"]
            if ok_count:
                summary_parts.append(f"[green]{ok_count} succeeded[/green]")
            if fail_count:
                summary_parts.append(f"[red]{fail_count} failed[/red]")
            summary = " — ".join(summary_parts)

            target_card = getattr(self, "_active_exchange_card", None)
            container = None
            if target_card is not None:
                container = getattr(target_card, "_response_container", None)
            from textual.widgets import Static as TextualStatic

            if container is not None:
                container.display = True
                self.call_from_thread(container.mount, TextualStatic(summary, markup=True))
                self.call_from_thread(container.scroll_end)
            else:
                # No active turn card (cleared mid-run / card creation failed):
                # the summary must NEVER vanish silently — fall back to #messages.
                logger.warning(
                    "No active exchange card for orchestration summary; falling back to #messages"
                )
                self.call_from_thread(
                    self.query_one("#messages").mount,
                    TextualStatic(summary, markup=True, classes="msg-assistant"),
                )
            # Auto summary card by agent after orchestration
            try:
                _pa = ""
                try:
                    _pa_path = __import__("pathlib").Path.cwd() / "PROJECT_ANALYSIS.md"
                    if _pa_path.exists():
                        _pa = _pa_path.read_text(encoding="utf-8", errors="replace")[:8000]
                except Exception:
                    _pa = ""
                self.call_from_thread(self._add_summary_by_agent_card, None, _pa)
            except Exception as _e:
                logger.debug("Auto summary after orchestration failed: %s", _e)
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
            try:
                self.call_from_thread(self._try_process_queue)
            except Exception:
                pass

    def _process_parallel(self: SagoApp, agent_tasks: list[tuple[str, str]]) -> None:
        """Run multiple agents in parallel, each with its own task."""
        agents = [a for a, _ in agent_tasks]
        logger.info("parallel requested: agents=%s", agents)
        self.is_thinking = True
        t = threading.Thread(target=self._process_parallel_thread, args=(agent_tasks,), daemon=True)
        t.start()

    def _process_parallel_thread(self: SagoApp, agent_tasks: list[tuple[str, str]]) -> None:
        """Runs in a background thread."""
        agents = [a for a, _ in agent_tasks]
        logger.info("parallel thread started: agents=%s", agents)

        # Set callbacks in context so spawned agents inherit UI updates (per-agent distinct, sequential)
        from sago.engine.simple_executor import set_execution_callbacks

        def _on_tool_call(n, a, ag=""):
            self.call_from_thread(self._update_spinner, f"Running: {n}")

        def _on_tool_result(n, a, r, s, ag=""):
            _ag = ag or getattr(self, "current_agent", "")
            try:
                self.call_from_thread(self._add_tool_call, n, a, r, s, _ag)
            except TypeError:
                self.call_from_thread(self._add_tool_call, n, a, r, s)

        def _on_thinking(t, ag=""):
            self.call_from_thread(self._update_spinner, t)
            low = t.strip().lower() if t else ""
            if low.startswith("planning...") or low.startswith("working...") or ("step " in low and "intent:" in low):
                return
            if t and len(t.strip()) >= 20:
                _ag2 = ag or getattr(self, "current_agent", "") or "sago"
                try:
                    self.call_from_thread(self._add_thinking_card, t, _ag2)
                except TypeError:
                    self.call_from_thread(self._add_thinking_card, t)
                try:
                    from sago.tracking.dev_tracer import get_dev_tracer

                    get_dev_tracer().record_thinking(
                        source=f"agent.{_ag2}", model=getattr(self, "current_model", ""), thinking_content=t
                    )
                except Exception:
                    pass

        set_execution_callbacks(
            on_tool_call=_on_tool_call,
            on_tool_result=_on_tool_result,
            on_thinking=_on_thinking,
        )

        tm = self._task_manager or get_task_manager()

        # Create task entries for each agent with their own task
        task_infos = []
        for agent_name, agent_task in agent_tasks:
            info = tm.create_task(agent_name, agent_task)
            info.status = AgentStatus.RUNNING
            task_infos.append(info)

        # Show parallel bar
        try:
            self.call_from_thread(self._show_parallel_bar, agents)
            self.call_from_thread(self._update_dashboard)
        except Exception as e:
            logger.debug("parallel bar setup failed: %s", e)

        try:
            from sago.agents.handoff import create_fresh_guard
            from sago.tools.file.spawn_agent import SpawnAgentTool

            # Create fresh guard for this parallel execution context
            _parallel_guard = create_fresh_guard()

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

                    # Share recursion guard explicitly; tolerate mocks that don't accept `guard`
                    try:
                        result = tool.run(
                            task=subtask, agent_name=agent_name, guard=_parallel_guard
                        )
                    except TypeError:
                        result = tool.run(task=subtask, agent_name=agent_name)
                    elapsed = _time.time() - start
                    info.elapsed = elapsed

                    # Detect errors using shared helper (avoids false positives on prose)
                    result_is_error = "could not be spawned" in result or _is_error_result(result)

                    if result_is_error:
                        info.status = AgentStatus.FAILED
                        info.error = result
                        self.call_from_thread(self._update_dashboard)
                        self.call_from_thread(
                            self._update_parallel_agent_status,
                            agent_name,
                            f"✗ Failed ({elapsed:.1f}s)",
                        )
                        self.call_from_thread(
                            self._add_parallel_result,
                            agent_name,
                            result,
                            elapsed,
                            False,
                        )
                        return {
                            "agent": agent_name,
                            "result": result,
                            "elapsed": elapsed,
                            "success": False,
                        }

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
            agent_task_map = {a: t for a, t in agent_tasks}
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(agents)) as executor:
                futures = {}
                for info in task_infos:
                    agent_task = agent_task_map.get(info.agent_name, "")
                    future = executor.submit(execute_agent, info.agent_name, agent_task, info)
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
            # Auto summary card by agent for parallel
            try:
                _pa = ""
                try:
                    _pa_path = __import__("pathlib").Path.cwd() / "PROJECT_ANALYSIS.md"
                    if _pa_path.exists():
                        _pa = _pa_path.read_text(encoding="utf-8", errors="replace")[:8000]
                except Exception:
                    _pa = ""
                self.call_from_thread(self._add_summary_by_agent_card, None, _pa)
            except Exception as _e:
                logger.debug("Auto summary after parallel failed: %s", _e)

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
            try:
                self.call_from_thread(self._try_process_queue)
            except Exception:
                pass

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
        try:
            self.query_one("#parallel-bar").remove_class("visible")
        except Exception:
            pass  # Parallel bar may not exist
