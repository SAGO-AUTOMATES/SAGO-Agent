"""Message Processor and LLM Streaming Worker for Sago TUI."""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sago.tui.models import EFFORT_LEVELS

if TYPE_CHECKING:
    from sago.tui.app import SagoApp

logger = logging.getLogger("sago.tui.processor")
_time = time


class MessageProcessorMixin:
    """Mixin class for processing user chat messages, LLM streaming, function execution, and post-verification."""

    def _process_message(self: SagoApp, message: str) -> None:
        """Entry point — runs on main thread, dispatches work to a background thread."""
        logger.info(
            "Message processing started (agent=%s, model=%s, provider=%s, prompt_length=%d)",
            self.current_agent,
            self.current_model,
            self.current_provider,
            len(message),
        )
        self.is_thinking = True
        self._active_cancel_event = threading.Event()
        self._show_spinner()
        t = threading.Thread(target=self._process_message_thread, args=(message,), daemon=True)
        t.start()

    def _process_message_thread(self: SagoApp, message: str) -> None:
        """Runs in a background thread — all call_from_thread calls are safe here."""
        thread_start = _time.time()
        # Direct shell execution escape (!command)
        clean_msg = message.strip()
        if clean_msg.startswith("!") and len(clean_msg) > 1:
            cmd = clean_msg[1:].strip()
            self.call_from_thread(self._update_spinner, f"Executing: {cmd}")
            try:
                import subprocess

                res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
                out = (res.stdout or "") + ("\n" + res.stderr if res.stderr else "")
                output_str = f"```bash\n$ {cmd}\n{out.strip()}\n```"
                self.call_from_thread(self._add_assistant_message, output_str)
            except Exception as e:
                self.call_from_thread(self._add_system_message, f"Shell command failed: {e}")
            finally:
                self.call_from_thread(self._hide_spinner)
                self.is_thinking = False
                # Drain queued messages if any — serialized execution
                try:
                    self.call_from_thread(self._try_process_queue)
                except Exception:
                    pass
            return

        try:
            cancel_ev = getattr(self, "_active_cancel_event", None)
            effort = EFFORT_LEVELS.get(self.current_effort, EFFORT_LEVELS["medium"])

            def on_tool(name, args):
                args_str = ", ".join(f"{k}={str(v)[:30]}" for k, v in list(args.items())[:3])
                self.call_from_thread(self._update_spinner, f"Running: {name}({args_str})")

            def on_tool_result(name, args, result, success):
                self.call_from_thread(self._add_tool_call, name, args, result, success)

            def on_thinking(text):
                self.call_from_thread(self._update_spinner, text)
                # For delegated engine tasks, real LLM <thinking> comes via this callback.
                # Spinner text like "Planning... (step 1/30)" is NOT real reasoning - filter it.
                low = text.strip().lower() if text else ""
                if (
                    low.startswith("planning...")
                    or low.startswith("working...")
                    or "step " in low
                    and "intent:" in low
                ):
                    return
                if text and text.strip() and len(text.strip()) >= 20:
                    clean = re.sub(r"\[/?[^\]]*\]", "", text).strip()
                    # Skip synthetic placeholders still
                    cl = clean.lower()
                    if cl.startswith("thinking: step ") or cl.startswith("synthesized reasoning"):
                        return
                    try:
                        from sago.tracking.dev_tracer import get_dev_tracer

                        get_dev_tracer().record_thinking(
                            source=f"tui.llm.{self.current_provider}",
                            model=self.current_model,
                            thinking_content=clean,
                        )
                    except Exception:
                        pass
                    try:
                        self.call_from_thread(self._add_thinking_card, clean)
                    except Exception:
                        pass

            # Propagate callbacks into context so spawned agents inherit them
            from sago.engine.simple_executor import set_execution_callbacks

            set_execution_callbacks(
                on_tool_call=on_tool,
                on_tool_result=on_tool_result,
                on_thinking=on_thinking,
            )

            # Try streaming first
            try:
                import sago.engine.simple_executor as _se
                from sago.llm.tui_providers import get_tui_client

                _se._discover_tools()  # Ensure tools are loaded
                from sago.engine.simple_executor import (
                    PROMPTS,
                    _build_openai_tools,
                    _detect_project_context,
                    _detect_task_type,
                    _discover_tools,
                    _generate_plan_with_llm,
                    _get_context,
                    _is_complex_task,
                    _load_agent_profile,
                )

                tools = _discover_tools()
                logger.info(
                    "LLM request starting: model=%s, provider=%s, tools_available=%d, prompt_length=%d",
                    self.current_model,
                    self.current_provider,
                    len(tools),
                    len(message),
                )

                # Get provider client (handles google, openai, openrouter, etc.)
                try:
                    client, api_model = get_tui_client(self.current_provider, self.current_model)
                    use_native_gemini = self.current_provider == "google"
                    gemini_client = client if use_native_gemini else None
                except ValueError as e:
                    self.call_from_thread(self._hide_spinner)
                    # Detailed provider error with actionable next steps
                    err_detail = str(e)
                    provider_hint = (
                        f"Provider `{self.current_provider}` / Model `{self.current_model}`"
                    )
                    hint = (
                        f"❌ Provider error ({provider_hint}): {err_detail}\n"
                        f"→ Check API key: `echo ${self._get_provider_key_name()}`\n"
                        f"→ Switch model: `/model openrouter/free` or `/provider openrouter`\n"
                        f"→ Retry: `/retry` or `/continue` after fixing key\n"
                        f"→ Status: `/status` to see current provider/model"
                    )
                    self.call_from_thread(self._add_error_inline, hint, "Provider setup failed")
                    return

                start_time = _time.time()

                from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer

                get_dev_tracer().record(
                    event_type=TraceEventType.FUNCTION_CALL,
                    source="sago.tui.app",
                    action=f"process_message({self.current_agent})",
                    data={
                        "task": message[:120],
                        "model": self.current_model,
                        "provider": self.current_provider,
                    },
                )

                # Assemble rich tri-partite context (AST symbols, hybrid search, learning patterns, previous sessions)
                task_type = _detect_task_type(message)
                try:
                    from sago.engine.context_assembler import get_context_assembler

                    assembler = get_context_assembler(cwd=str(Path.cwd()))
                    agent_slug = (
                        self.current_agent.lower().replace(" ", "-") if self.current_agent else None
                    )
                    assembled = assembler.assemble(
                        task=message,
                        task_type=task_type,
                        agent_name=agent_slug,
                        available_tools=list(tools.keys()),
                        session_id=self.current_session_id or "default",
                    )
                except Exception as ctx_err:
                    logger.debug("Context assembler failed: %s", ctx_err)
                    assembled = None

                # Detect project context
                project_context = _detect_project_context()
                project_ctx = _get_context()

                if project_context["languages"]:
                    project_ctx += (
                        f"\nDetected languages: {', '.join(project_context['languages'])}"
                    )
                if project_context["frameworks"]:
                    project_ctx += (
                        f"\nDetected frameworks: {', '.join(project_context['frameworks'])}"
                    )

                # Extract file references from message and add as context
                file_context = self._extract_file_context(message)
                if file_context:
                    project_ctx += f"\n\nReferenced files:\n{file_context}"

                from sago.agents.registry import resolve_specialist_agent

                active_agent = self.current_agent or "full-stack-engineer"
                if active_agent in (
                    "python-engineer",
                    "developer",
                    "general-assistant",
                    "assistant",
                ):
                    resolved = resolve_specialist_agent(task=message, default_agent=active_agent)
                    if resolved and resolved != "general-assistant":
                        active_agent = resolved

                # Load profile and build prompt
                profile = _load_agent_profile(active_agent.replace("-", " ").title())
                _is_lightweight = task_type == "chat"
                if _is_lightweight:
                    template = PROMPTS.get(task_type, PROMPTS.get("chat", PROMPTS["create"]))
                    system_prompt = template.format(
                        agent_role=active_agent.replace("-", " ").title(),
                        project_ctx="",
                    )
                else:
                    template = PROMPTS.get(task_type, PROMPTS["create"])
                    system_prompt = template.format(
                        agent_role=active_agent.replace("-", " ").title(),
                        project_ctx=project_ctx,
                    )
                    if profile and profile.get("system_prompt"):
                        system_prompt = profile["system_prompt"]

                # Inject system-level enhancements (learning approach, known fixes, instructions)
                if assembled and not _is_lightweight:
                    enhancements = assembled.format_system_enhancements()
                    if enhancements:
                        system_prompt += f"\n\n{enhancements}"
                elif not _is_lightweight:
                    try:
                        from sago.learning import get_learning_store

                        ls = get_learning_store()
                        learning_suggestion = ls.suggest_approach(task_type, list(tools.keys()))
                        if learning_suggestion:
                            system_prompt += (
                                f"\n\n=== PAST SUCCESSFUL APPROACH ===\n"
                                f"Based on past similar tasks, this approach worked:\n"
                                f"{learning_suggestion}\n"
                                f"Consider using a similar approach, but adapt to the current context."
                            )
                    except Exception as e:
                        logger.debug("Learning suggestion failed: %s", e)

                    try:
                        from sago.memory.project_instructions import (
                            get_project_instructions,
                        )

                        pi = get_project_instructions()
                        instructions_prompt = pi.get_for_prompt()
                        if instructions_prompt:
                            system_prompt += instructions_prompt
                    except Exception as e:
                        logger.debug("Project instructions failed: %s", e)

                # TODO system
                task_plan = None
                current_todo_index = 0
                todo_tool_counts: dict[str, int] = {}

                if _is_complex_task(message) and not _is_lightweight:
                    try:
                        from sago.tasks import TaskStatus, get_task_manager

                        tm = get_task_manager()
                        steps = _generate_plan_with_llm(message, client, self.current_model, "")
                        task_plan = tm.create_plan(goal=message, todos=steps)
                        confirm_keywords = [
                            "confirm",
                            "approve",
                            "review",
                            "check",
                            "verify",
                            "validate",
                        ]
                        for todo in task_plan.todos:
                            if any(kw in todo.description.lower() for kw in confirm_keywords):
                                todo.requires_confirmation = True
                        self.call_from_thread(
                            self._add_plan_card,
                            tm.format_plan(task_plan),
                            len(task_plan.todos),
                        )
                        if task_plan.todos:
                            tm.start_todo(task_plan.id, task_plan.todos[0].id)
                            self.call_from_thread(
                                self._update_spinner,
                                f"Step 1/{len(task_plan.todos)}: {task_plan.todos[0].description[:50]}",
                            )
                    except Exception as e:
                        logger.debug("Task plan creation failed: %s", e)
                        task_plan = None

                # Assemble multi-turn conversational history from prior messages
                history: list[dict[str, Any]] = []
                for m in self.messages[:-1]:
                    r = m.get("role")
                    c = m.get("content")
                    if r in ("user", "assistant") and c:
                        # Clean out reasoning tags from context history
                        cleaned_c = re.sub(
                            r"<(?:thinking|thought)>.*?</(?:thinking|thought)>",
                            "",
                            c,
                            flags=re.DOTALL,
                        ).strip()
                        if cleaned_c:
                            history.append({"role": r, "content": cleaned_c})

                from sago.engine.prompt_enhancer import enhance_prompt

                enhancement = enhance_prompt(
                    task=message,
                    agent_role=self.current_agent,
                    llm_client=client,
                    llm_model=api_model,
                )
                if enhancement.was_modified and not _is_lightweight:
                    self.call_from_thread(
                        self._update_spinner,
                        f"✨ Enhanced: {enhancement.intent_summary}",
                    )
                    self.call_from_thread(
                        self._add_prompt_enhancement_card,
                        enhancement,
                    )
                    # Store enhancement data on the user message for export/resume
                    if self.messages and self.messages[-1].get("role") == "user":
                        enhancement_dict = enhancement.to_dict()
                        self.messages[-1]["enhancement"] = enhancement_dict
                        self.call_from_thread(
                            self._update_last_user_message_metadata,
                            {"enhancement": enhancement_dict},
                        )

                # Use enhanced structured prompt for engineering requests
                user_msg_content = (
                    enhancement.enhanced_prompt
                    if (not _is_lightweight and enhancement.was_modified)
                    else message
                )

                # Inject assembled context (AST symbols, project graph, RAG) into user message
                if assembled and not _is_lightweight:
                    context_block = assembled.format_user_context_block()
                    if context_block:
                        user_msg_content = (
                            f"## Reference Context (read-only workspace data)\n"
                            f"{context_block}\n\n"
                            f"## Task & Plan\n{user_msg_content}"
                        )

                messages = (
                    [{"role": "system", "content": system_prompt}]
                    + history
                    + [{"role": "user", "content": user_msg_content}]
                )

                # Build OpenAI function calling tool definitions
                openai_tools = _build_openai_tools(tools)

                tool_history = []
                files_created = []
                total_tokens_in = 0
                total_tokens_out = 0
                cumulative_tokens = 0
                content = ""
                tool_call_counts: dict[str, int] = {}
                failed_calls: set[str] = set()
                executed_calls: set[str] = set()
                MAX_CUMULATIVE_TOKENS = 40000  # hard cap per message
                has_created_checkpoint = False

                # Initialize DB stores for this session
                _tool_usage_store = None
                _token_tracker = None
                if self.current_session_id:
                    try:
                        from sago.database import ToolUsageStore, init_db

                        init_db()
                        _tool_usage_store = ToolUsageStore(self.current_session_id)
                    except Exception as e:
                        logger.debug("ToolUsageStore init failed: %s", e)
                try:
                    from sago.tracking.token_tracker import get_token_tracker

                    _token_tracker = get_token_tracker()
                except Exception as e:
                    logger.debug("Token tracker init failed: %s", e)

                for iteration in range(effort["max_iterations"]):
                    if cancel_ev and cancel_ev.is_set():
                        self.call_from_thread(self._hide_spinner)
                        return

                    # Hard token cap — stop if budget exceeded
                    if cumulative_tokens >= MAX_CUMULATIVE_TOKENS:
                        self.call_from_thread(
                            self._add_system_message,
                            f"[STOP] Token budget exhausted ({cumulative_tokens:,} tokens used). Finishing up.",
                        )
                        break

                    # Update spinner
                    todo_info = ""
                    if task_plan and current_todo_index < len(task_plan.todos):
                        todo = task_plan.todos[current_todo_index]
                        todo_info = f" | Step {current_todo_index + 1}/{len(task_plan.todos)}: {todo.description[:40]}"
                    _spinner_text = f"Step {iteration + 1}/{effort['max_iterations']}{todo_info}..."
                    self.call_from_thread(self._update_spinner, _spinner_text)

                    # Call LLM — native Gemini or OpenAI-compatible with function calling
                    native_tool_calls: list[dict] = []

                    if use_native_gemini:
                        from google.genai import types as google_types

                        sys_msg = ""
                        contents = []
                        for msg in messages:
                            role = msg.get("role")
                            c_text = msg.get("content")
                            if role == "system":
                                sys_msg = c_text or ""
                                continue

                            if role == "user":
                                if c_text:
                                    contents.append(
                                        google_types.Content(
                                            role="user",
                                            parts=[google_types.Part(text=c_text)],
                                        )
                                    )
                            elif role == "assistant":
                                if msg.get("_google_parts"):
                                    contents.append(
                                        google_types.Content(
                                            role="model",
                                            parts=list(msg["_google_parts"]),
                                        )
                                    )
                                else:
                                    parts = []
                                    if c_text:
                                        parts.append(google_types.Part(text=c_text))
                                    for tc in msg.get("tool_calls", []):
                                        fn = tc.get("function", {})
                                        fname = fn.get("name", "")
                                        fargs = fn.get("arguments", {})
                                        if isinstance(fargs, str):
                                            try:
                                                fargs = json.loads(fargs) if fargs else {}
                                            except (json.JSONDecodeError, TypeError) as parse_err:
                                                logger.debug(
                                                    "Failed to parse function args: %s", parse_err
                                                )
                                                fargs = {}
                                        parts.append(
                                            google_types.Part(
                                                function_call=google_types.FunctionCall(
                                                    name=fname,
                                                    args=fargs if isinstance(fargs, dict) else {},
                                                )
                                            )
                                        )
                                    if parts:
                                        contents.append(
                                            google_types.Content(role="model", parts=parts)
                                        )
                            elif role == "tool":
                                tname = msg.get("name") or "tool"
                                contents.append(
                                    google_types.Content(
                                        role="user",
                                        parts=[
                                            google_types.Part(
                                                function_response=google_types.FunctionResponse(
                                                    name=tname,
                                                    response={"result": str(c_text or "")},
                                                )
                                            )
                                        ],
                                    )
                                )

                        if not contents:
                            contents = [
                                google_types.Content(
                                    role="user", parts=[google_types.Part(text="Hello")]
                                )
                            ]

                        # Convert tools to Google format
                        google_tools = []
                        for tool in openai_tools:
                            func = tool["function"]
                            params = func.get("parameters", {})
                            properties = {
                                k: google_types.Schema(
                                    type=google_types.Type.STRING,
                                    description=v.get("description", ""),
                                )
                                for k, v in params.get("properties", {}).items()
                            }
                            google_tools.append(
                                google_types.FunctionDeclaration(
                                    name=func["name"],
                                    description=func.get("description", ""),
                                    parameters=google_types.Schema(
                                        type=google_types.Type.OBJECT,
                                        properties=properties,
                                        required=params.get("required", []),
                                    ),
                                )
                            )

                        google_config = google_types.GenerateContentConfig(
                            system_instruction=sys_msg or None,
                            max_output_tokens=effort["max_tokens"],
                            temperature=0.3,
                        )
                        if google_tools:
                            google_config.tools = [
                                google_types.Tool(function_declarations=google_tools)
                            ]
                        # Enable native Gemini thinking (gemini-2.5-flash part.thought)
                        try:
                            if hasattr(google_types, "ThinkingConfig"):
                                _tc = google_types.ThinkingConfig(thinking_budget=1024)  # type: ignore[attr-defined]
                                if hasattr(_tc, "include_thoughts"):
                                    _tc.include_thoughts = True  # type: ignore[attr-defined]
                                google_config.thinking_config = _tc  # type: ignore[attr-defined]
                        except Exception:
                            pass

                        # Deep trace: record raw request
                        from sago.tracking.dev_tracer import get_dev_tracer as _gdt

                        _tracer = _gdt()
                        if _tracer.is_enabled:
                            _tracer.record_llm_request(
                                source=f"tui.llm.{self.current_provider}",
                                model=api_model,
                                messages=messages,
                                tools=openai_tools,
                                max_tokens=effort["max_tokens"],
                                temperature=0.3,
                            )

                        _llm_start_time = time.time()
                        logger.info(
                            "Streaming start: provider=google, model=%s, contents=%d parts, tools=%d",
                            api_model,
                            len(contents),
                            len(google_tools),
                        )
                        response = gemini_client.models.generate_content(
                            model=api_model,
                            contents=contents,
                            config=google_config,
                        )
                        content = response.text or ""

                        # Usage metadata from Gemini response if available
                        if hasattr(response, "usage_metadata") and response.usage_metadata:
                            total_tokens_in = (
                                getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                            )
                            total_tokens_out = (
                                getattr(response.usage_metadata, "candidates_token_count", 0) or 0
                            )
                            cumulative_tokens += total_tokens_out
                            logger.info(
                                "LLM response received: model=%s, content_length=%d, tokens_in=%d, tokens_out=%d",
                                api_model,
                                len(content),
                                total_tokens_in,
                                total_tokens_out,
                            )
                        else:
                            logger.info(
                                "LLM response received: model=%s, content_length=%d (no usage metadata)",
                                api_model,
                                len(content),
                            )

                        # Extract tool calls and reasoning from Gemini response
                        _gemini_raw_parts = []
                        _gemini_thinking = ""
                        if response.candidates and response.candidates[0].content:
                            _gemini_raw_parts = list(response.candidates[0].content.parts or [])
                            for part in _gemini_raw_parts:
                                if getattr(part, "thought", None):
                                    t_val = getattr(part, "text", "") or ""
                                    if t_val:
                                        _gemini_thinking += t_val + "\n"
                                elif part.function_call:
                                    native_tool_calls.append(
                                        {
                                            "id": f"gemini_{len(native_tool_calls)}",
                                            "name": part.function_call.name,
                                            "args": dict(part.function_call.args)
                                            if part.function_call.args
                                            else {},
                                        }
                                    )
                                elif part.text and not content:
                                    content = part.text
                    else:
                        # OpenAI-compatible with native function calling (streaming)
                        api_kwargs = {
                            "model": api_model,
                            "messages": messages,
                            "max_tokens": effort["max_tokens"],
                            "temperature": 0.3,
                            "stream": True,
                            "stream_options": {"include_usage": True},
                        }
                        if openai_tools:
                            api_kwargs["tools"] = openai_tools
                            api_kwargs["tool_choice"] = "auto"

                        # --- Deep trace: capture raw LLM request ---
                        from sago.tracking.dev_tracer import get_dev_tracer as _gdt

                        _tracer = _gdt()
                        if _tracer.is_enabled:
                            _tracer.record_llm_request(
                                source=f"tui.llm.{self.current_provider}",
                                model=api_model,
                                messages=messages,
                                tools=openai_tools,
                                max_tokens=effort["max_tokens"],
                                temperature=0.3,
                            )

                        _llm_start_time = time.time()
                        logger.info(
                            "Streaming start: provider=%s, model=%s, messages=%d, tools=%d, stream=True",
                            self.current_provider,
                            api_model,
                            len(messages),
                            len(openai_tools),
                        )
                        stream = client.chat.completions.create(**api_kwargs)

                        content = ""
                        tool_call_deltas: dict[int, dict] = {}
                        # Accumulate reasoning/thinking for OpenRouter/Ollama and other providers
                        _stream_reasoning = ""

                        for chunk in stream:
                            if hasattr(chunk, "usage") and chunk.usage:
                                total_tokens_in = chunk.usage.prompt_tokens or 0
                                total_tokens_out = chunk.usage.completion_tokens or 0
                                cumulative_tokens += total_tokens_out
                            if not chunk.choices:
                                continue
                            delta = chunk.choices[0].delta
                            # Capture reasoning/thinking deltas (OpenRouter: delta.reasoning, Ollama: delta.thinking)
                            for _rfield in (
                                "reasoning",
                                "reasoning_content",
                                "thinking",
                                "thought",
                                "reasoning_details",
                            ):
                                if hasattr(delta, _rfield):
                                    _rval = getattr(delta, _rfield)
                                    if _rval:
                                        if isinstance(_rval, list):
                                            _rval = " ".join(
                                                str(
                                                    v.get("text", "")
                                                    if isinstance(v, dict)
                                                    else str(v)
                                                )
                                                for v in _rval
                                            )
                                        _stream_reasoning += str(_rval)
                            if delta.content:
                                content += delta.content
                            # Accumulate streaming tool calls
                            if delta.tool_calls:
                                for tc_delta in delta.tool_calls:
                                    idx = tc_delta.index
                                    if idx not in tool_call_deltas:
                                        tool_call_deltas[idx] = {
                                            "id": "",
                                            "name": "",
                                            "arguments": "",
                                        }
                                    if tc_delta.id:
                                        tool_call_deltas[idx]["id"] = tc_delta.id
                                    if tc_delta.function:
                                        if tc_delta.function.name:
                                            tool_call_deltas[idx]["name"] = tc_delta.function.name
                                        if tc_delta.function.arguments:
                                            tool_call_deltas[idx]["arguments"] += (
                                                tc_delta.function.arguments
                                            )

                        # Convert accumulated deltas to tool calls
                        for idx in sorted(tool_call_deltas.keys()):
                            tc = tool_call_deltas[idx]
                            try:
                                parsed_args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                            except json.JSONDecodeError:
                                parsed_args = {}
                            native_tool_calls.append(
                                {
                                    "id": tc["id"],
                                    "name": tc["name"],
                                    "args": parsed_args,
                                }
                            )

                    from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer

                    _llm_latency_ms = (time.time() - _llm_start_time) * 1000
                    logger.info(
                        "LLM response received: provider=%s, model=%s, content_length=%d, tool_calls=%d, latency_ms=%.0f, tokens_in=%d, tokens_out=%d",
                        self.current_provider,
                        api_model,
                        len(content),
                        len(native_tool_calls),
                        _llm_latency_ms,
                        total_tokens_in,
                        total_tokens_out,
                    )

                    # Extract thinking content if present (<thinking> tags, native Gemini, or OpenRouter/Ollama reasoning)
                    _thinking_content = (
                        _gemini_thinking.strip() if use_native_gemini and _gemini_thinking else ""
                    )
                    # Streaming reasoning captured for OpenRouter / Ollama
                    try:
                        _sr = locals().get("_stream_reasoning", "") or ""
                        if not _thinking_content and _sr.strip():
                            _thinking_content = _sr.strip()
                    except Exception:
                        pass
                    if not _thinking_content:
                        _thinking_match = re.search(
                            r"<(?:thinking|thought)>(.*?)</(?:thinking|thought)>",
                            content,
                            re.DOTALL,
                        )
                        if _thinking_match:
                            _thinking_content = _thinking_match.group(1).strip()
                    # No synthetic TUI card — only real LLM thinking is shown in UI (prevents BS "Intent: ... step 1/30")
                    # Fallback is recorded to tracer for non-zero but not mounted to avoid TUI BS
                    is_synthetic = False
                    if not _thinking_content and iteration == 0:
                        _intent2 = (
                            message[:80].replace("\n", " ").strip()
                            if isinstance(message, str)
                            else ""
                        )
                        is_synthetic = True
                        _thinking_content = f"Considering: {message[:120].replace(chr(10), ' ').strip()[:100]} — planning next step to align with intent."
                    if _thinking_content:
                        get_dev_tracer().record_thinking(
                            source=f"tui.llm.{self.current_provider}",
                            model=api_model,
                            thinking_content=_thinking_content,
                        )
                        # Only mount real thinking to TUI; synthetic stays in tracer only (no BS card)
                        if not is_synthetic:
                            try:
                                self.call_from_thread(self._add_thinking_card, _thinking_content)
                            except Exception:
                                pass

                    # Raw response trace (deep debug)
                    get_dev_tracer().record_llm_response(
                        source=f"tui.llm.{self.current_provider}",
                        model=api_model,
                        response_content=content[:10000] if content else "",
                        thinking=_thinking_content[:10000] if _thinking_content else "",
                        tool_calls=[
                            {"name": tc["name"], "args": tc["args"]} for tc in native_tool_calls
                        ],
                        usage={"tokens_in": total_tokens_in, "tokens_out": total_tokens_out},
                        latency_ms=_llm_latency_ms,
                    )

                    # Summary trace (compact)
                    get_dev_tracer().record(
                        event_type=TraceEventType.LLM_PAYLOAD,
                        source=f"tui.llm.{self.current_provider}",
                        action=f"generate_content({api_model})"
                        if use_native_gemini
                        else f"chat.completions.create({api_model})",
                        data={
                            "model": api_model,
                            "provider": self.current_provider,
                            "messages_count": len(messages),
                            "tokens_in": total_tokens_in,
                            "tokens_out": total_tokens_out,
                            "tool_calls_generated": len(native_tool_calls),
                            "latency_ms": _llm_latency_ms,
                        },
                    )

                    # Handle empty content with no tool calls
                    if not content and not native_tool_calls:
                        logger.debug(
                            "Empty response received: iteration=%d/%d",
                            iteration + 1,
                            effort["max_iterations"],
                        )
                        if iteration < effort["max_iterations"] - 1:
                            messages.append(
                                {
                                    "role": "user",
                                    "content": "You returned an empty response. Please use the available tools to complete the task.",
                                }
                            )
                            continue
                        else:
                            content = "I wasn't able to generate a response. Please try again."

                    # Build assistant message
                    assistant_msg: dict = {"role": "assistant", "content": content or None}
                    if use_native_gemini and _gemini_raw_parts:
                        assistant_msg["_google_parts"] = _gemini_raw_parts
                    if native_tool_calls:
                        assistant_msg["tool_calls"] = [
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": json.dumps(tc["args"])
                                    if isinstance(tc["args"], dict)
                                    else tc["args"],
                                },
                            }
                            for tc in native_tool_calls
                        ]
                    messages.append(assistant_msg)

                    # If no tool calls, check for fabrication or finish
                    if not native_tool_calls:
                        fabrication_phrases = [
                            "the file contains",
                            "the contents are",
                            "i read the file",
                            "the file has",
                            "i can see that",
                            "looking at the file",
                            "the code shows",
                            "i opened the file",
                            "the file shows",
                            "successfully created",
                            "i saved the file",
                            "the file was created",
                            "i have created",
                            "i've created",
                            "done! the file",
                            "i've updated",
                            "i have updated",
                            "i've added",
                            "i have added",
                            "i've removed",
                            "i have removed",
                            "i've deleted",
                            "i have deleted",
                            "i've modified",
                            "i have modified",
                            "the updated file",
                            "the modified file",
                            "after修改ing",
                            "the fix involves",
                            "the issue is",
                            "the problem is",
                            "the solution is",
                            "here's the fix",
                            "here is the fix",
                            "the error occurs because",
                            "the bug is in",
                            "i've written",
                            "i have written",
                            "the code below",
                            "here's the code",
                            "here is the code",
                            "as shown in",
                            "as we can see",
                            "based on the file",
                            "after reviewing",
                            "i've tested",
                            "i have tested",
                            "all tests pass",
                            "the test passes",
                            "everything works",
                            "it's working",
                            "it works now",
                            "fixed by",
                            "resolved by",
                        ]
                        content_lower = content.lower() if content else ""

                        # Detect fabrication:
                        # 1. No tool calls at all + claims to have done things
                        # 2. Tool calls exist but response claims MORE than was actually done
                        is_fabrication = False
                        if not tool_history:
                            # No tools called at all - any fabrication phrase is suspicious
                            is_fabrication = any(
                                phrase in content_lower for phrase in fabrication_phrases
                            )
                        else:
                            # Tools were called - check if response claims actions beyond what tools did
                            tools_called = {tc.get("tool", "") for tc in tool_history}
                            # If agent claims file operations but no write/edit tool was called
                            file_claim_phrases = [
                                "successfully created",
                                "i saved the file",
                                "the file was created",
                                "i've created",
                                "i have created",
                                "i've updated",
                                "i have updated",
                                "i've modified",
                                "i have modified",
                                "done! the file",
                                "i've written",
                                "i have written",
                            ]
                            claims_file_ops = any(
                                phrase in content_lower for phrase in file_claim_phrases
                            )
                            made_file_ops = any(
                                t in tools_called
                                for t in ("write_file", "edit_file", "create_file")
                            )
                            if claims_file_ops and not made_file_ops:
                                is_fabrication = True

                        if is_fabrication and iteration < effort["max_iterations"] - 1:
                            # Build specific guidance based on what was claimed
                            guidance = []
                            if any(
                                p in content_lower
                                for p in ["file contains", "i read", "the code shows", "i can see"]
                            ):
                                guidance.append(
                                    "Use read_file tool to actually read the file first."
                                )
                            if any(
                                p in content_lower
                                for p in ["created", "saved", "written", "updated", "modified"]
                            ):
                                guidance.append(
                                    "Use write_file or edit_file tool to actually create/modify the file."
                                )
                            if any(p in content_lower for p in ["tested", "tests pass", "works"]):
                                guidance.append("Use execute_shell tool to actually run the tests.")

                            guidance_text = (
                                " ".join(guidance)
                                if guidance
                                else "Use the available tools to complete the task."
                            )

                            messages.append(
                                {
                                    "role": "user",
                                    "content": (
                                        "STOP. You are fabricating results without actually using tools. "
                                        f"{guidance_text} "
                                        "Do NOT claim file contents, file creation, or test results "
                                        "without actually calling the corresponding tool. Do it NOW."
                                    ),
                                }
                            )
                            continue

                        # Handle todo completion — update Execution Plan widget in place
                        if task_plan and current_todo_index < len(task_plan.todos):
                            from sago.tasks import TaskStatus, get_task_manager

                            tm = get_task_manager()
                            todo = task_plan.todos[current_todo_index]
                            if todo.status == TaskStatus.IN_PROGRESS:
                                tm.complete_todo(
                                    task_plan.id, todo.id, result=content[:200] if content else ""
                                )
                                # Update the plan card in place instead of dumping a new message below
                                try:
                                    self.call_from_thread(
                                        self._update_plan_progress,
                                        task_plan,
                                        current_todo_index,
                                        "completed",
                                    )
                                except Exception:
                                    # Fallback to old system message if update fails
                                    self.call_from_thread(
                                        self._add_system_message,
                                        f"Step {current_todo_index + 1} completed: {todo.description[:60]}",
                                    )
                                current_todo_index += 1
                                if current_todo_index < len(task_plan.todos):
                                    next_todo = task_plan.todos[current_todo_index]
                                    tm.start_todo(task_plan.id, next_todo.id)
                                    try:
                                        self.call_from_thread(
                                            self._update_plan_progress,
                                            task_plan,
                                            current_todo_index,
                                            "in_progress",
                                        )
                                    except Exception:
                                        pass
                                    messages.append(
                                        {
                                            "role": "user",
                                            "content": f"Moving to next step: {next_todo.description}\nExecute this step now.",
                                        }
                                    )
                                    continue
                        break

                    # ---- Execute native tool calls ----
                    tools_used_in_iteration = []
                    logger.info(
                        "Tool calls detected: %s",
                        [(tc["name"], len(str(tc["args"]))) for tc in native_tool_calls],
                    )

                    for tc in native_tool_calls:
                        if cancel_ev and cancel_ev.is_set():
                            self.call_from_thread(self._hide_spinner)
                            return

                        tc_id = tc["id"]
                        name = tc["name"]
                        args = tc["args"] if isinstance(tc["args"], dict) else {}

                        if name not in tools:
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc_id,
                                    "content": f"Unknown tool: {name}",
                                }
                            )
                            continue

                        # Loop protection — skip duplicate successful calls
                        call_key = f"{name}:{json.dumps(args, sort_keys=True)}"
                        if call_key in executed_calls:
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc_id,
                                    "content": f"[SKIP] Already executed: {name} with identical args. Do not repeat the same call.",
                                }
                            )
                            continue
                        if call_key in failed_calls:
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc_id,
                                    "content": f"[SKIP] Already failed: {name} with same args. Try a different approach.",
                                }
                            )
                            continue

                        # Per-tool call limit (max 3 per tool name, ask_question max 1 to avoid stuck loop)
                        tool_call_counts[name] = tool_call_counts.get(name, 0) + 1
                        if name == "ask_question" and tool_call_counts[name] > 1:
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc_id,
                                    "content": "[SKIP] ask_question already asked — waiting for user reply, do not repeat. Answer directly or proceed.",
                                }
                            )
                            continue
                        if tool_call_counts[name] > 3:
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc_id,
                                    "content": f"[SKIP] Tool '{name}' has been called {tool_call_counts[name] - 1} times already. Stop calling it and provide a final answer.",
                                }
                            )
                            continue

                        def _make_tool_approval_message(tool_name: str, risk_level: str) -> Any:
                            from rich.text import Text

                            msg = Text()
                            msg.append("⚡ Tool '", style="bold")
                            msg.append(tool_name, style="bold yellow")
                            msg.append(f"' ({risk_level} risk) requires approval.\n", style="bold")
                            msg.append("Press ", style="bold")
                            msg.append("[Y]", style="bold green")
                            msg.append(" Approve / ", style="bold")
                            msg.append("[N]", style="bold red")
                            msg.append(" Deny or type 'y' / 'n'.", style="bold")
                            return msg

                        def _make_approval_bar_text(
                            tool_name: str, risk_level: str, args: Any = None
                        ) -> str:
                            """Build a concise approval bar message."""
                            arg_summary = ""
                            if args and isinstance(args, dict):
                                # Show first arg value truncated
                                first_val = next(iter(args.values()), "")
                                if isinstance(first_val, str) and len(first_val) > 40:
                                    first_val = first_val[:40] + "..."
                                arg_summary = f" → {first_val}" if first_val else ""
                            return f"{tool_name}{arg_summary} ({risk_level} risk) — [Y] Approve / [N] Deny"

                        # Check permissions
                        from sago.permissions import RiskLevel, get_permission_manager

                        pm = get_permission_manager()
                        risk = pm.get_risk_level(name)

                        if self.yolo_mode:
                            allowed = True
                            reason = "YOLO mode"
                        else:
                            allowed, reason = pm.check_permission(
                                name, args, self.current_session_id
                            )

                        if not allowed:
                            if risk in (
                                RiskLevel.MEDIUM,
                                RiskLevel.HIGH,
                                RiskLevel.CRITICAL,
                            ):
                                self._tool_approved = False
                                approval_msg = _make_approval_bar_text(name, risk.value, args)
                                # Approval bar at bottom is the immersive prompt; don't also spam
                                # a separate breaking-immersion system message (tool call already visible).
                                self.call_from_thread(
                                    self._show_approval_bar,
                                    approval_msg,
                                )
                                pause_event = threading.Event()
                                self._executor_pause_event = pause_event
                                self._pending_tool_approval = {"name": name, "args": args}
                                pause_event.wait(timeout=300)
                                self._executor_pause_event = None
                                self._pending_tool_approval = None
                                if not self._tool_approved:
                                    messages.append(
                                        {
                                            "role": "tool",
                                            "tool_call_id": tc_id,
                                            "content": f"Permission denied: {name} requires approval",
                                        }
                                    )
                                    continue
                                # Remember session approval
                                pm.approve_tool(name, self.current_session_id)
                                self._tool_approved = False
                            else:
                                messages.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": tc_id,
                                        "content": f"Permission denied: {reason}",
                                    }
                                )
                                continue

                        on_tool(name, args)
                        t_tool_start = time.perf_counter()
                        logger.debug(
                            "Tool execution started: name=%s, args_length=%d", name, len(str(args))
                        )
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

                                # Proactive pre-modification workspace checkpointing with user notification
                                if not has_created_checkpoint and name in (
                                    "write_file",
                                    "edit_file",
                                    "multi_edit_file",
                                    "apply_patch",
                                    "delete_file",
                                ):
                                    try:
                                        from sago.engine.checkpoint import (
                                            get_checkpoint_manager,
                                        )

                                        mgr = get_checkpoint_manager()
                                        target_fp = clean_args.get("file_path") or clean_args.get(
                                            "path"
                                        )
                                        target_list = (
                                            [target_fp]
                                            if target_fp and os.path.exists(target_fp)
                                            else None
                                        )
                                        cp_meta = mgr.create_checkpoint(
                                            description=f"Snapshot before {name}",
                                            files=target_list,
                                        )
                                        self.call_from_thread(
                                            self._add_system_message,
                                            f"🛡️ [bold green]Workspace Snapshot Saved[/bold green]: `{cp_meta.checkpoint_id}` ({len(cp_meta.file_paths)} files)\n"
                                            f"[dim]Rollback at any time with: `/checkpoint restore {cp_meta.checkpoint_id}` or `/undo`[/dim]",
                                        )
                                        has_created_checkpoint = True
                                    except Exception as e:
                                        logger.debug("Auto checkpoint failed: %s", e)

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

                        tool_dur_ms = (time.perf_counter() - t_tool_start) * 1000.0

                        is_error = (
                            result_str.lower().startswith("error")
                            or "traceback" in result_str.lower()
                        )
                        if is_error:
                            failed_calls.add(call_key)
                            logger.error(
                                "Tool execution failed: name=%s, duration_ms=%.0f, error=%s",
                                name,
                                tool_dur_ms,
                                result_str[:200],
                            )
                        else:
                            executed_calls.add(call_key)
                            logger.debug(
                                "Tool execution completed: name=%s, duration_ms=%.0f, result_length=%d",
                                name,
                                tool_dur_ms,
                                len(result_str),
                            )

                        from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer

                        get_dev_tracer().record(
                            event_type=TraceEventType.TOOL_DISPATCH,
                            source="tui.tool_dispatcher",
                            action=f"run({name})",
                            data={
                                "tool_name": name,
                                "arguments": args,
                                "result_preview": result_str[:250],
                                "risk_level": risk.value if "risk" in locals() else "SAFE",
                            },
                            status="FAILED" if is_error else "OK",
                            duration_ms=tool_dur_ms,
                        )

                        if name in ("write_file", "edit_file", "file_operations") and not is_error:
                            fp = (
                                args.get("file_path", "")
                                or args.get("target_file", "")
                                or args.get("path", "")
                            )
                            if fp and fp not in files_created:
                                files_created.append(fp)
                            try:
                                from sago.engine.verifier import get_continuous_verifier

                                get_continuous_verifier().enqueue_files([fp] if fp else [])
                            except Exception as e:
                                logger.debug("Failed to enqueue files for verification: %s", e)

                        if name == "write_file" and not is_error:
                            # Nudge LLM to stop after successful file write
                            if iteration < effort["max_iterations"] - 1:
                                messages.append(
                                    {
                                        "role": "user",
                                        "content": (
                                            "[SYSTEM] File operation succeeded. "
                                            "Do NOT call any more tools. Provide your final answer now."
                                        ),
                                    }
                                )

                        if name == "edit_file" and not is_error:
                            # Nudge LLM to stop after successful edit
                            if iteration < effort["max_iterations"] - 1:
                                messages.append(
                                    {
                                        "role": "user",
                                        "content": (
                                            "[SYSTEM] Edit succeeded. "
                                            "Do NOT call any more tools. Provide your final answer now."
                                        ),
                                    }
                                )

                        tool_history.append(
                            {
                                "tool": name,
                                "args": args,
                                "result": result_str[:2000],
                                "success": not is_error,
                            }
                        )
                        tools_used_in_iteration.append(name)
                        on_tool_result(name, args, result_str, not is_error)

                        # Log tool usage to DB
                        if _tool_usage_store:
                            try:
                                _tool_usage_store.log(
                                    tool_name=name,
                                    arguments=args,
                                    result=result_str[:2000],
                                    duration_ms=int(tool_dur_ms),
                                    success=not is_error,
                                )
                            except Exception as e:
                                logger.debug("Failed to log tool usage: %s", e)

                        messages.append(
                            {
                                "role": "tool",
                                "name": name,
                                "tool_call_id": tc_id,
                                "content": result_str[:500]
                                if len(result_str) > 500
                                else result_str,
                            }
                        )

                    # TODO progress
                    if task_plan:
                        try:
                            from sago.tasks import TaskStatus, get_task_manager

                            tm = get_task_manager()
                            if current_todo_index < len(task_plan.todos):
                                todo = task_plan.todos[current_todo_index]
                                if todo.id not in todo_tool_counts:
                                    todo_tool_counts[todo.id] = 0
                                todo_tool_counts[todo.id] += len(tools_used_in_iteration)

                                if (
                                    todo.requires_confirmation
                                    and todo.status == TaskStatus.IN_PROGRESS
                                ):
                                    self.call_from_thread(
                                        self._show_approval_bar,
                                        f"Confirm: {todo.confirmation_message or todo.description}",
                                    )
                                    pause_event = threading.Event()
                                    self._executor_pause_event = pause_event
                                    pause_event.wait(timeout=300)
                                    self._executor_pause_event = None

                                successful_tools = [
                                    t["tool"]
                                    for t in tool_history
                                    if t.get("success") and t["tool"] in tools_used_in_iteration
                                ]
                                tools_for_todo = todo_tool_counts.get(todo.id, 0)
                                if (tools_for_todo >= 5 and len(successful_tools) >= 3) or (
                                    tools_for_todo >= 4 and len(tools_used_in_iteration) >= 1
                                ):
                                    tm.complete_todo(
                                        task_plan.id,
                                        todo.id,
                                        result=f"Completed: {', '.join(successful_tools[:3])}",
                                    )
                                    self.call_from_thread(
                                        self._add_system_message,
                                        f"Step {current_todo_index + 1} completed: {todo.description[:60]}",
                                    )
                                    current_todo_index += 1
                                    if current_todo_index < len(task_plan.todos):
                                        next_todo = task_plan.todos[current_todo_index]
                                        tm.start_todo(task_plan.id, next_todo.id)
                                        messages.append(
                                            {
                                                "role": "user",
                                                "content": f"[PROGRESS] Step completed. Next step: {next_todo.description}\nExecute this step now.",
                                            }
                                        )
                                    else:
                                        messages.append(
                                            {
                                                "role": "user",
                                                "content": "[PROGRESS] All steps completed. Provide final summary.",
                                            }
                                        )
                        except Exception as e:
                            logger.debug("TODO progress update failed: %s", e)

                    continue  # Loop back for next LLM call with tool results as role:tool messages

                # Post-execution: test → fix → retry
                if files_created:
                    self.call_from_thread(self._update_spinner, "Running tests...")
                    from sago.engine.simple_executor import (
                        _auto_install_deps,
                        _run_tests_if_exist,
                    )

                    _auto_install_deps(files_created)
                    test_fix_attempts = 0
                    max_test_fix_attempts = 3

                    while test_fix_attempts < max_test_fix_attempts:
                        test_result = _run_tests_if_exist(files_created, tools)
                        if test_result is None:
                            break

                        test_passed, test_output = test_result
                        if test_passed:
                            self.call_from_thread(self._add_system_message, "✅ All tests passed!")
                            break

                        logger.info(
                            "Post-verification LLM call: reason=tests_failed, attempt=%d/%d, test_output_length=%d",
                            test_fix_attempts,
                            max_test_fix_attempts,
                            len(test_output),
                        )
                        test_fix_attempts += 1
                        if test_fix_attempts >= max_test_fix_attempts:
                            self.call_from_thread(
                                self._add_system_message,
                                f"❌ Tests still failing after {max_test_fix_attempts} attempts. Use `/undo` or `/checkpoint restore` to safely roll back changes.",
                            )
                            break

                        self.call_from_thread(
                            self._update_spinner,
                            f"Tests failed (attempt {test_fix_attempts}/{max_test_fix_attempts}), fixing...",
                        )

                        try:
                            fix_msgs = messages + [
                                {
                                    "role": "user",
                                    "content": (
                                        f"The tests are failing. Fix them.\n\n"
                                        f"Test output:\n{test_output[:3000]}\n\n"
                                        f"Files: {', '.join(files_created)}\n"
                                        f"Fix the issues. Use edit_file or write_file."
                                    ),
                                },
                            ]
                            fix_api_kwargs = {
                                "model": api_model,
                                "messages": fix_msgs,
                                "max_tokens": effort["max_tokens"],
                                "temperature": 0.3,
                                "stream": True,
                                "stream_options": {"include_usage": True},
                            }
                            if openai_tools:
                                fix_api_kwargs["tools"] = openai_tools
                                fix_api_kwargs["tool_choice"] = "auto"

                            fix_stream = client.chat.completions.create(**fix_api_kwargs)
                            fix_content = ""
                            fix_tc_deltas: dict[int, dict] = {}
                            for chunk in fix_stream:
                                if not chunk.choices:
                                    continue
                                delta = chunk.choices[0].delta
                                if delta.content:
                                    fix_content += delta.content
                                if delta.tool_calls:
                                    for tc_delta in delta.tool_calls:
                                        idx = tc_delta.index
                                        if idx not in fix_tc_deltas:
                                            fix_tc_deltas[idx] = {
                                                "id": "",
                                                "name": "",
                                                "arguments": "",
                                            }
                                        if tc_delta.id:
                                            fix_tc_deltas[idx]["id"] = tc_delta.id
                                        if tc_delta.function:
                                            if tc_delta.function.name:
                                                fix_tc_deltas[idx]["name"] = tc_delta.function.name
                                            if tc_delta.function.arguments:
                                                fix_tc_deltas[idx]["arguments"] += (
                                                    tc_delta.function.arguments
                                                )

                            # Process accumulated fix tool calls
                            if fix_tc_deltas:
                                fix_tcs = [fix_tc_deltas[k] for k in sorted(fix_tc_deltas.keys())]
                                messages.append(
                                    {
                                        "role": "assistant",
                                        "content": fix_content or None,
                                        "tool_calls": [
                                            {
                                                "id": tc["id"],
                                                "type": "function",
                                                "function": {
                                                    "name": tc["name"],
                                                    "arguments": json.dumps(tc["arguments"])
                                                    if isinstance(tc["arguments"], dict)
                                                    else tc["arguments"],
                                                },
                                            }
                                            for tc in fix_tcs
                                        ],
                                    }
                                )
                                for tc in fix_tcs:
                                    try:
                                        fix_args = (
                                            json.loads(tc["arguments"])
                                            if isinstance(tc["arguments"], str)
                                            else (tc["arguments"] or {})
                                        )
                                    except json.JSONDecodeError:
                                        fix_args = {}
                                    fix_name = tc["name"]
                                    if fix_name in tools:
                                        tool_instance = tools[fix_name]()
                                        result = tool_instance.run(**fix_args)
                                        result_str = str(result)
                                        is_error = result_str.lower().startswith("error")
                                        tool_history.append(
                                            {
                                                "tool": fix_name,
                                                "args": fix_args,
                                                "result": result_str[:2000],
                                                "success": not is_error,
                                            }
                                        )
                                        if fix_name == "write_file" and not is_error:
                                            fp = fix_args.get("file_path", "")
                                            if fp and fp not in files_created:
                                                files_created.append(fp)
                                        messages.append(
                                            {
                                                "role": "tool",
                                                "tool_call_id": tc["id"],
                                                "content": result_str,
                                            }
                                        )
                            elif fix_content:
                                messages.append({"role": "assistant", "content": fix_content})
                        except Exception as e:
                            logger.debug("Test-fix loop failed: %s", e)
                            break

                # Final todo cleanup
                if task_plan:
                    try:
                        from sago.tasks import TaskStatus, get_task_manager

                        tm = get_task_manager()
                        for idx in range(current_todo_index, len(task_plan.todos)):
                            todo = task_plan.todos[idx]
                            if todo.status in (
                                TaskStatus.PENDING,
                                TaskStatus.IN_PROGRESS,
                            ):
                                tm.complete_todo(
                                    task_plan.id,
                                    todo.id,
                                    result="Task completed",
                                )
                        self.call_from_thread(self._add_system_message, tm.format_plan(task_plan))
                    except Exception as e:
                        logger.debug("Final todo cleanup failed: %s", e)

                elapsed = _time.time() - start_time
                self.call_from_thread(self._hide_spinner)

                # Record token usage to tracker
                if _token_tracker and (total_tokens_in > 0 or total_tokens_out > 0):
                    try:
                        _token_tracker.record(
                            provider=self.current_provider,
                            model=self.current_model,
                            input_tokens=total_tokens_in,
                            output_tokens=total_tokens_out,
                            latency_ms=elapsed * 1000,
                            metadata={"session_id": self.current_session_id},
                        )
                        _token_tracker.save()
                    except Exception as e:
                        logger.debug("Token tracker save failed: %s", e)

                # Flush tool usage store
                if _tool_usage_store:
                    try:
                        _tool_usage_store.flush()
                    except Exception as e:
                        logger.debug("Tool usage store flush failed: %s", e)

                # Show summary
                self.call_from_thread(
                    self._add_summary,
                    tool_history,
                    content,
                    elapsed,
                    {
                        "input": total_tokens_in,
                        "output": total_tokens_out,
                        "cumulative": cumulative_tokens,
                    },
                )

                # Show change summary
                if files_created:
                    try:
                        from sago.memory.change_tracker import get_change_tracker

                        tracker = get_change_tracker()
                        change_summary = tracker.get_diff_summary()
                        if change_summary and "No changes" not in change_summary:
                            self.call_from_thread(
                                self._add_system_message,
                                f"📝 {change_summary}",
                            )
                    except Exception as e:
                        logger.debug("Change tracker failed: %s", e)

                # Record learning
                try:
                    from sago.learning import get_learning_store

                    ls = get_learning_store()
                    successful_tools = [t["tool"] for t in tool_history if t.get("success")]
                    if successful_tools:
                        ls.record_success(
                            task_type,
                            successful_tools,
                            f"Used {', '.join(set(successful_tools[:5]))}",
                        )
                    for tool_record in tool_history:
                        ls.record_tool_effectiveness(
                            tool_record["tool"], tool_record.get("success", False)
                        )
                except Exception as e:
                    logger.debug("Learning record failed: %s", e)

                # Show response — if tools were executed, show results not raw JSON
                if tool_history:
                    # Tools were executed — show a summary of what happened
                    last_results = []
                    for t in tool_history[-3:]:
                        status = "✓" if t.get("success") else "✗"
                        last_results.append(f"{status} {t['tool']}: {t.get('result', '')[:200]}")
                    summary = "\n".join(last_results)
                    if content and content.strip() and not content.strip().startswith("{"):
                        # Run shared hallucination verifier on the content
                        try:
                            from sago.engine.hallucination_verifier import get_verifier

                            verifier = get_verifier()
                            verification = verifier.verify(
                                content, tool_history=tool_history, task_type=task_type
                            )
                            if verification.has_hallucinations:
                                content = verification.cleaned_content
                        except Exception as e:
                            logger.debug("Hallucination verification failed: %s", e)
                        self.call_from_thread(self._add_assistant_message, content)
                    else:
                        self.call_from_thread(self._add_assistant_message, summary)

                    # Show verification and confidence indicator (dev mode only)
                    try:
                        from sago.engine.hallucination_verifier import get_verifier

                        verifier = get_verifier()
                        verification = verifier.verify(
                            content or "",
                            tool_history=tool_history,
                            task_type=task_type,
                        )
                        confidence = verification.confidence
                        all_issues = verification.all_issues
                        logger.info(
                            "hallucination_check: confidence=%d issues=%d model=%s",
                            confidence,
                            len(all_issues),
                            self.current_model,
                        )
                        # Silent — no Confidence banner (user says it breaks immersion, alignment off)
                        # Logged at INFO above; UI no longer shows "Confidence: 100/100" line
                    except Exception as e:
                        logger.debug("Verification confidence check failed: %s", e)
                elif content and content.strip():
                    # Run shared hallucination verifier on content without tools
                    try:
                        from sago.engine.hallucination_verifier import get_verifier

                        verifier = get_verifier()
                        verification = verifier.verify(
                            content, tool_history=[], task_type=task_type
                        )
                        if verification.has_hallucinations:
                            content = verification.cleaned_content
                    except Exception as e:
                        logger.debug("Hallucination verification failed: %s", e)
                    self.call_from_thread(self._add_assistant_message, content)
                elif tool_history:
                    tools_done = [t["tool"] for t in tool_history]
                    self.call_from_thread(
                        self._add_assistant_message,
                        f"Completed using: {', '.join(tools_done)}",
                    )
                else:
                    self.call_from_thread(
                        self._add_assistant_message,
                        "I wasn't able to process your request. Please try rephrasing.",
                    )

            except ImportError:
                # Fallback to non-streaming
                from sago.engine.simple_executor import execute_agent_task

                def on_todo_created(plan):
                    self.call_from_thread(
                        self._add_system_message,
                        f"📋 Created plan with {len(plan.todos)} steps:",
                    )
                    from sago.tasks import get_task_manager

                    tm = get_task_manager()
                    self.call_from_thread(self._add_system_message, tm.format_plan(plan))

                def on_todo_update(plan, todo_index, status):
                    if todo_index < len(plan.todos):
                        todo = plan.todos[todo_index]
                        if status == "started":
                            self.call_from_thread(
                                self._update_spinner,
                                f"Step {todo_index + 1}/{len(plan.todos)}: {todo.description[:50]}",
                            )
                        elif status == "completed":
                            self.call_from_thread(
                                self._add_system_message,
                                f"✅ Step {todo_index + 1} completed: {todo.description[:60]}",
                            )

                # Get API key for the current provider (registry-driven)
                from sago.llm.registry import (
                    get_provider_spec,
                    normalize_provider,
                    resolve_base_url,
                )

                _spec = get_provider_spec(normalize_provider(self.current_provider))
                provider_key = (
                    os.environ.get(_spec.api_key_env, "")
                    if _spec and _spec.api_key_env
                    else os.environ.get("OPENROUTER_API_KEY", "")
                )
                provider_base_url = resolve_base_url(normalize_provider(self.current_provider))

                exec_result: dict[str, Any] = execute_agent_task(
                    task=message,
                    agent_role=self.current_agent.replace("-", " ").title(),
                    api_key=provider_key,
                    model=self.current_model,
                    base_url=provider_base_url,
                    max_tokens=int(effort["max_tokens"]),
                    max_iterations=int(effort["max_iterations"]),
                    on_tool_call=on_tool,
                    on_tool_result=on_tool_result,
                    on_thinking=on_thinking,
                    on_todo_created=on_todo_created,
                    on_todo_update=on_todo_update,
                )

                if exec_result.get("task_plan"):
                    from sago.tasks import get_task_manager

                    tm = get_task_manager()
                    plan = tm.get_active_plan()
                    if plan:
                        self.call_from_thread(self._add_system_message, tm.format_plan(plan))

                self.call_from_thread(self._hide_spinner)

                is_success = exec_result.get("success", True)
                err = exec_result.get("error")
                output = exec_result.get("output", "")
                tool_calls = exec_result.get("tool_calls", [])

                if not is_success or err:
                    err_text = err or output or "Unknown execution failure"
                    self.call_from_thread(
                        self._add_assistant_message,
                        f"❌ **Execution Error:** {err_text}",
                    )
                elif output and output.strip():
                    self.call_from_thread(self._add_assistant_message, output)
                elif tool_calls:
                    tools_done = [t.get("tool", "unknown") for t in tool_calls]
                    self.call_from_thread(
                        self._add_assistant_message,
                        f"Completed using: {', '.join(tools_done)}",
                    )
                else:
                    self.call_from_thread(
                        self._add_assistant_message,
                        "I wasn't able to process your request. Please try rephrasing.",
                    )

        except Exception as e:
            self.call_from_thread(self._hide_spinner)
            error_msg = str(e)
            logger.error(
                "Error during message processing: %s (model=%s, provider=%s, elapsed=%.1fs)",
                error_msg,
                self.current_model,
                self.current_provider,
                _time.time() - thread_start,
            )

            try:
                from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer

                get_dev_tracer().record(
                    event_type=TraceEventType.ERROR,
                    source="sago.tui.app",
                    action=f"process_message_failed({self.current_provider})",
                    data={"error": error_msg, "model": self.current_model},
                    status="FAILED",
                )
            except Exception as tracer_err:
                logger.debug("Dev tracer record failed in error handler: %s", tracer_err)

            if "429" in error_msg or "rate" in error_msg.lower():
                from sago.llm.registry import get_provider_spec, normalize_provider

                _spec = get_provider_spec(normalize_provider(self.current_provider))
                url = (
                    _spec.billing_url
                    if _spec and _spec.billing_url
                    else "your provider's dashboard"
                )
                error_msg = (
                    f"Rate limited. Wait a few seconds or check credits at {url}.\n"
                    f"💡 *Tip:* Type `/continue` to resume this task without losing previous tool results, or switch model with `/model`."
                )
            elif "401" in error_msg or "auth" in error_msg.lower():
                error_msg = f"Authentication failed. Check your {self.current_provider} API key."
            elif "404" in error_msg:
                error_msg = (
                    f"Model '{self.current_model}' not found. Try a different model with `/model`."
                )
            try:
                self.call_from_thread(self._add_assistant_message, f"❌ **Error:** {error_msg}")
            except Exception as msg_err:
                logger.debug("Failed to display error via _add_assistant_message: %s", msg_err)
                # Absolute last resort: try to mount directly on #messages
                try:

                    def _fallback_error() -> None:
                        try:
                            from textual.widgets import Static

                            self.query_one("#messages").mount(
                                Static(f"❌ Error: {error_msg}", markup=False)
                            )
                            self.query_one("#messages").scroll_end(animate=False)
                        except Exception as fb_err:
                            logger.debug("Final fallback error mount failed: %s", fb_err)

                    self.call_from_thread(_fallback_error)
                except Exception as thread_err:
                    logger.debug("call_from_thread fallback failed: %s", thread_err)
        finally:
            self.is_thinking = False
            logger.info("Message processing ended (elapsed=%.1fs)", _time.time() - thread_start)
            # Serialized queue: if user typed while we were thinking, run next
            try:
                self.call_from_thread(self._try_process_queue)
            except Exception:
                pass
