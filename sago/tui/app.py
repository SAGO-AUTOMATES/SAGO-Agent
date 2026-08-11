"""Sago TUI - Production Terminal Interface with all features working."""

from __future__ import annotations

import json
import os
import re
import threading
import time as _time

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widgets import Button, Footer, Input, Static

from sago.tui.commands import CommandHandlers
from sago.tui.helpers import UIHelpers
from sago.tui.models import COMMANDS, EFFORT_LEVELS
from sago.tui.widgets import Spinner


class SagoApp(App, CommandHandlers, UIHelpers):
    CSS = """
    Screen { background: #0d1117; }

    #messages {
        height: 1fr;
        padding: 1 2 2 2;
        overflow-y: auto;
        scrollbar-size: 0 0;
    }

    .msg-user { color: #58a6ff; padding: 0 0 1 0; }
    .msg-assistant { color: #c9d1d9; padding: 0 0 1 0; }
    .msg-system { color: #8b949e; text-style: italic; padding: 0 0 1 0; }
    .msg-meta { color: #484f58; padding: 0 0 0 0; }

    Collapsible {
        background: #0d1117;
        border: solid #21262d;
        margin: 0 0 1 0;
        padding: 0;
    }
    Collapsible .collapsible-title { background: #161b22; color: #58a6ff; padding: 0 1; }
    Collapsible .collapsible-body { background: #0d1117; color: #8b949e; padding: 0 1; }

    #input-area {
        height: auto;
        padding: 1 2;
        background: #161b22;
        border: solid #30363d;
        margin: 0 1 1 1;
    }

    #msg-input {
        background: #0d1117;
        border: tall #30363d;
        color: #c9d1d9;
        margin: 0;
    }
    #msg-input:focus { border: tall #58a6ff; }

    #suggestions {
        display: none;
        max-height: 14;
        overflow-y: auto;
        background: #161b22;
        border: solid #30363d;
        margin: 0 1 0 1;
        padding: 0;
        scrollbar-size: 0 0;
    }
    #suggestions.visible { display: block; }

    .suggestion-item { color: #c9d1d9; padding: 0 1; }
    .suggestion-item.highlighted { color: #ffffff; background: #1f6feb; }

    .code-block {
        background: #161b22;
        color: #c9d1d9;
        padding: 1;
        margin: 0 0 1 0;
        border: tall #30363d;
    }

    .spinner { color: #58a6ff; text-style: italic; padding: 0 0 1 0; }

    .summary-box {
        background: #161b22;
        border: solid #1f6feb;
        color: #c9d1d9;
        padding: 1;
        margin: 0 0 1 0;
    }

    #approval-bar {
        display: none;
        height: auto;
        background: #161b22;
        border: solid #f0883e;
        margin: 0 1 0 1;
        padding: 1;
    }
    #approval-bar.visible { display: block; }

    #approval-bar .approval-label {
        color: #f0883e;
        text-style: bold;
        padding: 0 0 1 0;
    }

    #approval-bar .approval-buttons {
        layout: horizontal;
        height: 3;
    }

    #approval-bar Button {
        margin: 0 1 0 0;
        min-width: 12;
    }

    .approve-btn { background: #238636; color: #ffffff; border: solid #2ea043; }
    .approve-btn:hover { background: #2ea043; }
    .approve-btn:focus { border: solid #ffffff; }

    .deny-btn { background: #da3633; color: #ffffff; border: solid #f85149; }
    .deny-btn:hover { background: #f85149; }
    .deny-btn:focus { border: solid #ffffff; }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+l", "clear_chat", "Clear"),
        Binding("escape", "dismiss_suggestions", "Dismiss"),
        Binding("y", "approve_action", "Approve", show=True, priority=True),
        Binding("n", "deny_action", "Deny", show=True, priority=True),
        Binding("ctrl+y", "approve_action", "Approve", show=False),
        Binding("ctrl+n", "deny_action", "Deny", show=False),
    ]

    TITLE = "Sago"

    current_agent: reactive[str] = reactive("sago-orchestrator")
    current_model: reactive[str] = reactive("openrouter/free")
    current_provider: reactive[str] = reactive("openrouter")
    current_effort: reactive[str] = reactive("medium")
    current_session_id: reactive[str] = reactive("")
    messages: reactive[list[dict]] = reactive(list)
    show_suggestions: reactive[bool] = reactive(False)
    suggestion_items: reactive[list[str]] = reactive(list)
    suggestion_values: reactive[list[str]] = reactive(list)
    suggestion_index: reactive[int] = reactive(0)
    is_thinking: reactive[bool] = reactive(False)
    pending_action: reactive[dict] = reactive(dict)
    pending_orchestration: dict | None = None
    approval_message: reactive[str] = reactive("")
    yolo_mode: reactive[bool] = reactive(False)
    # Pause/resume mechanism for todo confirmations
    _executor_pause_event: object = None  # threading.Event
    _executor_thread: object = None  # running thread reference
    _tool_approved: bool = False
    command_history: list[str] = []
    history_index: int = -1
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_hit_tokens: int = 0
    total_cache_miss_tokens: int = 0

    def compose(self) -> ComposeResult:
        yield ScrollableContainer(id="messages")
        yield Vertical(id="suggestions")
        with Vertical(id="approval-bar"):
            yield Static("Pending action", id="approval-label", classes="approval-label")
            with Horizontal(id="approval-buttons"):
                yield Button(
                    "Approve [Y]",
                    id="btn-approve",
                    variant="success",
                    classes="approve-btn",
                )
                yield Button("Deny [N]", id="btn-deny", variant="error", classes="deny-btn")
        with Vertical(id="input-area"):
            yield Input(placeholder="/, @, # for autocomplete", id="msg-input")
        yield Footer()

    def on_mount(self) -> None:
        self._spinner = None
        self._spinner_timer = None
        self._pending_resume = getattr(self, "_pending_resume", None)
        self._init_db()
        self._init_session()
        self._load_settings()
        self._add_system_message("Sago v0.1.0 — /help for commands")
        # Auto-resume if --resume flag was passed
        if self._pending_resume:
            self._load_session(self._pending_resume)
            self._pending_resume = None
        # Auto-refresh models if stale
        self._auto_refresh_models()
        self.query_one("#msg-input").focus()

    def _load_settings(self) -> None:
        """Load persisted settings (model, provider, effort, yolo, agent)."""
        try:
            from sago.settings import load_setting

            self.current_model = load_setting("model", self.current_model)
            self.current_provider = load_setting("provider", self.current_provider)
            self.current_effort = load_setting("effort", self.current_effort)
            self.current_agent = load_setting("agent", self.current_agent)
            self.yolo_mode = load_setting("yolo", self.yolo_mode)
        except Exception:
            pass

    def _save_settings(self) -> None:
        """Persist current settings."""
        try:
            from sago.settings import save_setting

            save_setting("model", self.current_model)
            save_setting("provider", self.current_provider)
            save_setting("effort", self.current_effort)
            save_setting("agent", self.current_agent)
            save_setting("yolo", self.yolo_mode)
        except Exception:
            pass

    def _auto_refresh_models(self) -> None:
        """Refresh model list from OpenRouter if cache is stale."""
        import os

        try:
            from sago.tui.models import auto_refresh_if_stale

            api_key = os.environ.get("OPENROUTER_API_KEY", "")
            msg = auto_refresh_if_stale(api_key)
            if msg:
                self._add_system_message(f"[auto-refresh] {msg}")
        except Exception:
            pass

    def _resolve_api_model(self) -> str:
        """Strip provider prefix for API calls. google/gemini-2.0-flash -> gemini-2.0-flash."""
        m = self.current_model
        p = self.current_provider
        if p == "google" and m.startswith("google/"):
            return m[len("google/") :]
        if p == "openai" and m.startswith("openai/"):
            return m[len("openai/") :]
        return m

    def watch_current_model(self, value: str) -> None:
        """Auto-save model when changed."""
        self._save_settings()

    def watch_current_provider(self, value: str) -> None:
        """Auto-save provider when changed."""
        self._save_settings()

    def watch_current_effort(self, value: str) -> None:
        """Auto-save effort when changed."""
        self._save_settings()

    def watch_current_agent(self, value: str) -> None:
        """Auto-save agent when changed."""
        self._save_settings()

    def watch_yolo_mode(self, value: bool) -> None:
        """Auto-save yolo mode when changed."""
        self._save_settings()

    def _init_db(self) -> None:
        try:
            from sago.database import init_db

            init_db()
        except Exception as e:
            import logging

            logging.getLogger("sago.tui").debug(f"DB init failed: {e}")

    def _init_session(self) -> None:
        try:
            from sago.database import Session, init_db

            init_db()
            session = Session()
            result = session.create(title="TUI Session")
            self.current_session_id = result["id"]
            session.close()
        except Exception as e:
            import logging

            logging.getLogger("sago.tui").debug(f"Session init failed: {e}")
            self.current_session_id = "local"

    @on(Input.Changed, "#msg-input")
    def on_input_changed(self, event: Input.Changed) -> None:
        v = event.value
        if v.startswith("/"):
            self._show_cmd_suggestions(v)
        elif v.startswith("@"):
            self._show_agent_suggestions(v)
        elif v.startswith("#"):
            self._show_file_suggestions(v)
        else:
            self._hide_suggestions()

    @on(Input.Submitted, "#msg-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        msg = event.value.strip()
        if not msg:
            return

        if self.show_suggestions and self.suggestion_values:
            val = self.suggestion_values[self.suggestion_index]
            # If exact match on a command, submit it directly
            if val in COMMANDS and msg.strip() == val:
                self._hide_suggestions()
                event.input.value = ""
                self._handle_command(val)
                return
            # Otherwise just autocomplete
            event.input.value = val + " "
            event.input.cursor_position = len(event.input.value)
            # If selecting a model suggestion, set provider too
            if (
                val.startswith("/model ")
                and not val.startswith("/model add")
                and not val.startswith("/model remove")
                and not val.startswith("/model refresh")
            ):
                model_id = val[7:].strip()
                provider = model_id.split("/")[0]
                self.current_provider = provider
                self.current_model = model_id
            self._hide_suggestions()
            return

        event.input.value = ""
        self._hide_suggestions()
        self.history_index = -1

        if msg.startswith("/"):
            if msg != "/history":
                self._add_to_history(msg)
            self._handle_command(msg)
        else:
            self._add_to_history(msg)
            self._add_user_message(msg)
            self._process_message(msg)

    def on_key(self, event) -> None:
        if self.show_suggestions:
            if event.key == "down":
                event.prevent_default()
                self._move_sel(1)
            elif event.key == "up":
                event.prevent_default()
                self._move_sel(-1)
            elif event.key == "escape":
                self._hide_suggestions()
        else:
            # Command history navigation when no suggestions visible
            inp = self.query_one("#msg-input")
            if inp.cursor_position == 0 and not inp.value:
                if event.key == "up":
                    self._navigate_history("up")
                elif event.key == "down":
                    self._navigate_history("down")

    def _move_sel(self, d: int) -> None:
        n = len(self.suggestion_values)
        if n == 0:
            return
        self.suggestion_index = (self.suggestion_index + d) % n
        self._update_highlight()

    def _select_current(self) -> None:
        if self.suggestion_values:
            val = self.suggestion_values[self.suggestion_index]
            inp = self.query_one("#msg-input")
            inp.value = val + " "
            inp.cursor_position = len(inp.value)
            # If selecting a model suggestion, set provider too
            if (
                val.startswith("/model ")
                and not val.startswith("/model add")
                and not val.startswith("/model remove")
                and not val.startswith("/model refresh")
            ):
                model_id = val[7:].strip()
                provider = model_id.split("/")[0]
                self.current_provider = provider
                self.current_model = model_id
            self._hide_suggestions()

    def _update_highlight(self) -> None:
        items = self.query(".suggestion-item")
        for i, item in enumerate(items):
            is_highlighted = i == self.suggestion_index
            item.set_class(is_highlighted, "highlighted")
            # Auto-scroll highlighted item into view
            if is_highlighted:
                item.scroll_visible()

    def _add_to_history(self, cmd: str) -> None:
        if cmd and (not self.command_history or self.command_history[-1] != cmd):
            self.command_history.append(cmd)
        self.history_index = len(self.command_history)

    def _navigate_history(self, key: str) -> None:
        if not self.command_history:
            return
        if key == "up":
            self.history_index = max(0, self.history_index - 1)
        else:
            self.history_index = min(len(self.command_history) - 1, self.history_index + 1)
        if 0 <= self.history_index < len(self.command_history):
            self.query_one("#msg-input").value = self.command_history[self.history_index]

    def on_mouse_scroll_down(self, event) -> None:
        self.query_one("#messages").scroll_down()

    def on_mouse_scroll_up(self, event) -> None:
        self.query_one("#messages").scroll_up()

    def on_click(self, event) -> None:
        self.query_one("#msg-input").focus()

    def _show_cmd_suggestions(self, prefix: str) -> None:
        # "/model provider query" — show filtered models for that provider
        if prefix.startswith("/model "):
            parts = prefix[7:].split(None, 1)
            if len(parts) == 2:
                # "/model google gemini" → filter google models by "gemini"
                provider_filter, query = parts
                self._show_model_suggestions(query, provider_filter)
            elif len(parts) == 1:
                # "/model google" → show all google models
                self._show_model_suggestions("", parts[0])
            else:
                # "/model " → show all models
                self._show_model_suggestions("", "")
            return
        # "/model" with no space yet — show command
        if prefix == "/model":
            matches = ["/model"]
            items = ["/model - Change model"]
            self._show_suggestions(items, matches)
            return
        # Other commands
        matches = [cmd for cmd in COMMANDS if cmd.startswith(prefix)]
        values = matches
        items = [f"{cmd} - {COMMANDS[cmd]}" for cmd in matches]
        self._show_suggestions(items, values)

    def _show_model_suggestions(self, query: str, provider_filter: str = "") -> None:
        from sago.tui.models import get_all_models

        models = get_all_models()
        if provider_filter:
            # Filter by provider prefix
            models = [m for m in models if m.startswith(f"{provider_filter}/")]
        if query:
            models = [m for m in models if query.lower() in m.lower()]

        items = [f"  {m}" for m in models[:30]]
        values = [f"/model {m}" for m in models[:30]]
        self._show_suggestions(items, values)

    def _show_agent_suggestions(self, prefix: str) -> None:
        try:
            from sago.agents.registry import list_agents

            agents = list_agents()
            matches = [a["name"] for a in agents if a["name"].startswith(prefix[1:])]
            self._show_suggestions(matches, [f"@{m}" for m in matches])
        except Exception:
            pass

    def _show_file_suggestions(self, prefix: str) -> None:
        from pathlib import Path

        files = [f.name for f in Path(".").glob("*") if f.is_file()][:10]
        self._show_suggestions(files, [f"#{f}" for f in files])

    def _show_suggestions(self, items: list[str], values: list[str]) -> None:
        self.suggestion_items = items
        self.suggestion_values = values
        self.suggestion_index = 0
        self.show_suggestions = True
        container = self.query_one("#suggestions")
        container.remove_children()
        for i, item in enumerate(items):
            container.mount(Static(item, classes="suggestion-item"))
        container.add_class("visible")
        self._update_highlight()

    def _hide_suggestions(self) -> None:
        self.show_suggestions = False
        self.suggestion_items = []
        self.suggestion_values = []
        self.query_one("#suggestions").remove_class("visible")

    def action_dismiss_suggestions(self) -> None:
        self._hide_suggestions()

    def action_approve_action(self) -> None:
        """Handle Y key or Approve button click."""
        if self.approval_message:
            self._approve_action()

    def action_deny_action(self) -> None:
        """Handle N key or Deny button click."""
        if self.approval_message:
            self._deny_action()

    @on(Button.Pressed, "#btn-approve")
    def on_approve_pressed(self, event: Button.Pressed) -> None:
        """Handle Approve button click."""
        self._approve_action()

    @on(Button.Pressed, "#btn-deny")
    def on_deny_pressed(self, event: Button.Pressed) -> None:
        """Handle Deny button click."""
        self._deny_action()

    def _show_approval_bar(self, message: str) -> None:
        """Show the approval bar with a message."""
        self.approval_message = message
        label = self.query_one("#approval-label", Static)
        label.update(f"  {message}")
        self.query_one("#approval-bar").add_class("visible")

    def _hide_approval_bar(self) -> None:
        """Hide the approval bar."""
        self.approval_message = ""
        self.query_one("#approval-bar").remove_class("visible")

    def _approve_action(self) -> None:
        """Handle Y key or Approve button click."""
        self._tool_approved = True
        self._hide_approval_bar()
        if self._executor_pause_event:
            self._executor_pause_event.set()

    def _deny_action(self) -> None:
        """Handle N key or Deny button click."""
        self._tool_approved = False
        self._hide_approval_bar()
        if self._executor_pause_event:
            self._executor_pause_event.set()

    def _show_spinner(self, text: str = "Thinking") -> None:
        self._hide_spinner()
        s = Spinner(text, classes="spinner")
        self.query_one("#messages").mount(s)
        self.query_one("#messages").scroll_end()
        self._spinner = s
        self._spinner_timer = self.set_interval(0.1, self._advance_spinner)

    def _advance_spinner(self) -> None:
        if self._spinner:
            self._spinner.advance()

    def _update_spinner(self, text: str) -> None:
        if self._spinner:
            self._spinner.text = text
            self._spinner.refresh()

    def _hide_spinner(self) -> None:
        if self._spinner_timer:
            self._spinner_timer.stop()
            self._spinner_timer = None
        if self._spinner:
            try:
                self._spinner.remove()
            except Exception:
                pass
            self._spinner = None

    def _handle_command(self, command: str) -> None:
        parts = command.strip().split(None, 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        handlers = {
            "/help": lambda: self._show_help(),
            "/agents": lambda: self._show_agents(args),
            "/agent": lambda: self._set_agent(args),
            "/delegate": lambda: self._delegate_task(args),
            "/chain": lambda: self._chain_agents(args),
            "/orchestrate": lambda: self._orchestrate_task(args),
            "/clear": lambda: self.action_clear_chat(),
            "/status": lambda: self._show_status(),
            "/export": lambda: self._export_session(),
            "/sessions": lambda: self._show_sessions(),
            "/session": lambda: self._switch_session(args),
            "/history": lambda: self._show_history(),
            "/model": lambda: self._change_model(args),
            "/provider": lambda: self._change_provider(args),
            "/effort": lambda: self._set_effort(args),
            "/cost": lambda: self._show_cost(),
            "/compact": lambda: self._compact(),
            "/retry": lambda: self._retry_last(),
            "/reset": lambda: self._reset(),
            "/save": lambda: self._save_session(args),
            "/load": lambda: self._load_session(args),
            "/git": lambda: self._git_status(),
            "/diff": lambda: self._git_diff(args),
            "/commit": lambda: self._git_commit(args),
            "/approve": lambda: self._approve_action(),
            "/deny": lambda: self._deny_action(),
            "/version": lambda: self._show_version(),
            "/yolo": lambda: self._toggle_yolo(),
            "/permissions": lambda: self._show_permissions(args),
            "/allow": lambda: self._allow_tool(args),
            "/block": lambda: self._block_tool(args),
            "/todo": lambda: self._show_todo(args),
            "/todos": lambda: self._show_all_todos(),
            "/done": lambda: self._mark_todo_done(args),
            "/ask": lambda: self._ask_user(args),
            "/plan": lambda: self._show_plan(args),
            "/undo": lambda: self._undo_change(),
            "/changes": lambda: self._show_changes(),
            "/exit": lambda: self._exit_session(),
            "/resume": lambda: self._list_sessions(),
        }

        if cmd in handlers:
            handlers[cmd]()
        else:
            self._add_system_message(f"Unknown: {cmd}\nType /help for commands")

    def action_quit(self) -> None:
        """Save session and exit."""
        self._exit_session()

    def action_clear_chat(self) -> None:
        self.query_one("#messages").remove_children()
        self.messages.clear()
        self._add_system_message("Cleared.")

    @work(thread=True)
    def _process_delegation(self, agent_name: str, task: str) -> None:
        self.is_thinking = True
        self.call_from_thread(self._show_spinner, f"Delegating to {agent_name}...")
        try:
            api_key = os.environ.get("OPENROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
            if not api_key:
                self.call_from_thread(self._hide_spinner)
                self.call_from_thread(
                    self._add_system_message,
                    "No API key. Set OPENROUTER_API_KEY or OPENAI_API_KEY.",
                )
                return

            from sago.tools.file.spawn_agent import SpawnAgentTool

            tool = SpawnAgentTool()
            result = tool.run(task=task, agent_name=agent_name)

            self.call_from_thread(self._hide_spinner)
            if "could not be spawned" in result or "Error:" in result:
                self.call_from_thread(
                    self._add_system_message,
                    f"{result}\n\nTry running the task directly.",
                )
            else:
                self.call_from_thread(self._add_assistant_message, result)
        except Exception as e:
            self.call_from_thread(self._hide_spinner)
            self.call_from_thread(self._add_system_message, f"Delegation error: {e}")
        finally:
            self.is_thinking = False

    @work(thread=True)
    def _process_chain(self, agents: list[str], task: str) -> None:
        self.is_thinking = True
        self.call_from_thread(self._show_spinner, f"Chain: {' → '.join(agents)}")
        try:
            api_key = os.environ.get("OPENROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
            if not api_key:
                self.call_from_thread(self._hide_spinner)
                self.call_from_thread(self._add_system_message, "No API key.")
                return

            from sago.tools.file.spawn_agent import SpawnAgentTool

            tool = SpawnAgentTool()
            current_input = task
            for i, agent in enumerate(agents):
                self.call_from_thread(self._update_spinner, f"Step {i + 1}/{len(agents)}: {agent}")
                result = tool.run(task=current_input, agent_name=agent)
                current_input = f"Previous agent ({agent}) said:\n\n{result}\n\nNow continue."
            self.call_from_thread(self._hide_spinner)
            self.call_from_thread(self._add_assistant_message, current_input)
        except Exception as e:
            self.call_from_thread(self._hide_spinner)
            self.call_from_thread(self._add_system_message, f"Chain error: {e}")
        finally:
            self.is_thinking = False

    @work(thread=True)
    def _process_orchestration(self, task: str) -> None:
        self.is_thinking = True
        self.call_from_thread(self._show_spinner, "Analyzing task for delegation...")
        try:
            api_key = os.environ.get("OPENROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
            if not api_key:
                self.call_from_thread(self._hide_spinner)
                self.call_from_thread(self._add_system_message, "No API key.")
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

            try:
                response = client.chat.completions.create(
                    model=self.current_model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a task orchestrator. Analyze the task and break it into steps.\n"
                                "For each step, specify which agent should handle it.\n"
                                'Reply with a JSON list of steps: [{"agent": "agent-name", "task": "what to do"}]\n\n'
                                f"Available agents:\n{agent_list_str}"
                            ),
                        },
                        {"role": "user", "content": task},
                    ],
                    max_tokens=1024,
                )
            except Exception as api_err:
                self.call_from_thread(self._hide_spinner)
                self.call_from_thread(
                    self._add_system_message,
                    f"Failed to create plan: {api_err}",
                )
                return

            plan_text = response.choices[0].message.content or "[]"
            try:
                json_match = re.search(r"\[.*\]", plan_text, re.DOTALL)
                if json_match:
                    plan = json.loads(json_match.group())
                else:
                    plan = [{"agent": "python-engineer", "task": task}]
            except json.JSONDecodeError:
                plan = [{"agent": "python-engineer", "task": task}]

            # Show plan and ask for confirmation
            plan_lines = []
            for i, step in enumerate(plan):
                agent = step.get("agent", "python-engineer")
                step_task = step.get("task", "")[:80]
                plan_lines.append(f"  {i + 1}. {agent}: {step_task}")
            plan_summary = f"Orchestration plan ({len(plan)} steps):\n" + "\n".join(plan_lines)
            self.call_from_thread(self._hide_spinner)
            self.call_from_thread(self._add_system_message, plan_summary)

            # Show approval bar with buttons
            approval_msg = f"Execute {len(plan)} steps?  Press [Y] Approve or [N] Deny"
            self.call_from_thread(self._show_approval_bar, approval_msg)

            # Store plan for /approve command
            self.pending_orchestration = {"task": task, "plan": plan}

        except Exception as e:
            self.call_from_thread(self._hide_spinner)
            self.call_from_thread(self._add_system_message, f"Orchestration error: {e}")
        finally:
            self.is_thinking = False

    def _execute_orchestration_plan(self, plan: list[dict]) -> None:
        """Execute an approved orchestration plan."""
        self.is_thinking = True
        self.call_from_thread(self._show_spinner, f"Executing {len(plan)} steps...")
        try:
            from sago.tools.file.spawn_agent import SpawnAgentTool

            tool = SpawnAgentTool()
            results = []
            for i, step in enumerate(plan):
                agent = step.get("agent", "python-engineer")
                step_task = step.get("task", "")
                self.call_from_thread(self._update_spinner, f"Step {i + 1}/{len(plan)}: {agent}")
                result = tool.run(task=step_task, agent_name=agent)
                results.append(f"**{agent}**: {result[:500]}")

            self.call_from_thread(self._hide_spinner)
            final = f"Orchestration complete ({len(plan)} steps):\n\n" + "\n\n".join(results)
            self.call_from_thread(self._add_assistant_message, final)
        except Exception as e:
            self.call_from_thread(self._hide_spinner)
            self.call_from_thread(self._add_system_message, f"Execution error: {e}")
        finally:
            self.is_thinking = False

    @work(thread=True)
    def _process_message(self, message: str) -> None:
        self.is_thinking = True
        self.call_from_thread(self._show_spinner)
        try:
            effort = EFFORT_LEVELS.get(self.current_effort, EFFORT_LEVELS["medium"])

            def on_tool(name, args):
                args_str = ", ".join(f"{k}={str(v)[:30]}" for k, v in list(args.items())[:3])
                self.call_from_thread(self._update_spinner, f"Running: {name}({args_str})")

            def on_tool_result(name, args, result, success):
                self.call_from_thread(self._add_tool_call, name, args, result, success)

            def on_thinking(text):
                self.call_from_thread(self._update_spinner, text)

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

                # Get provider client (handles google, openai, openrouter, etc.)
                try:
                    client, api_model = get_tui_client(self.current_provider, self.current_model)
                    use_native_gemini = self.current_provider == "google"
                    gemini_client = client if use_native_gemini else None
                except ValueError as e:
                    self.call_from_thread(self._hide_spinner)
                    self.call_from_thread(self._add_system_message, str(e))
                    return

                start_time = _time.time()

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

                # Load learning suggestions
                learning_suggestion = None
                try:
                    from sago.learning import get_learning_store

                    ls = get_learning_store()
                    learning_suggestion = ls.suggest_approach("general", list(tools.keys()))
                except Exception:
                    pass

                # Load profile and build prompt
                profile = _load_agent_profile(self.current_agent.replace("-", " ").title())
                task_type = _detect_task_type(message)
                template = PROMPTS.get(task_type, PROMPTS["create"])
                system_prompt = template.format(
                    agent_role=self.current_agent.replace("-", " ").title(),
                    project_ctx=project_ctx,
                )

                if profile and profile.get("system_prompt"):
                    system_prompt = profile["system_prompt"]

                # Inject learning suggestion
                if learning_suggestion:
                    system_prompt += (
                        f"\n\n=== PAST SUCCESSFUL APPROACH ===\n"
                        f"Based on past similar tasks, this approach worked:\n"
                        f"{learning_suggestion}\n"
                        f"Consider using a similar approach, but adapt to the current context."
                    )

                # Inject project instructions
                try:
                    from sago.memory.project_instructions import (
                        get_project_instructions,
                    )

                    pi = get_project_instructions()
                    instructions_prompt = pi.get_for_prompt()
                    if instructions_prompt:
                        system_prompt += instructions_prompt
                except Exception:
                    pass

                # TODO system
                task_plan = None
                current_todo_index = 0
                todo_tool_counts: dict[str, int] = {}

                if _is_complex_task(message):
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
                                todo.confirmation_message = f"Please confirm: {todo.description}"
                        self.call_from_thread(
                            self._add_system_message,
                            f"📋 Created plan with {len(task_plan.todos)} steps:",
                        )
                        self.call_from_thread(self._add_system_message, tm.format_plan(task_plan))
                        if task_plan.todos:
                            tm.start_todo(task_plan.id, task_plan.todos[0].id)
                            self.call_from_thread(
                                self._update_spinner,
                                f"Step 1/{len(task_plan.todos)}: {task_plan.todos[0].description[:50]}",
                            )
                    except Exception:
                        task_plan = None

                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ]

                # Build OpenAI function calling tool definitions
                openai_tools = _build_openai_tools(tools)

                tool_history = []
                files_created = []
                total_tokens_in = 0
                total_tokens_out = 0
                content = ""
                tool_call_counts: dict[str, int] = {}
                failed_calls: set[str] = set()

                for iteration in range(effort["max_iterations"]):
                    # Update spinner
                    todo_info = ""
                    if task_plan and current_todo_index < len(task_plan.todos):
                        todo = task_plan.todos[current_todo_index]
                        todo_info = f" | Step {current_todo_index + 1}/{len(task_plan.todos)}: {todo.description[:40]}"
                    self.call_from_thread(
                        self._update_spinner,
                        f"Step {iteration + 1}/{effort['max_iterations']}{todo_info}...",
                    )

                    # Call LLM — native Gemini or OpenAI-compatible with function calling
                    native_tool_calls: list[dict] = []

                    if use_native_gemini:
                        # Convert messages to Google format with tools
                        sys_msg = ""
                        contents = []
                        for msg in messages:
                            if msg["role"] == "system":
                                sys_msg = msg["content"]
                            elif msg["role"] in ("user", "assistant"):
                                contents.append(msg["content"])
                        if not contents:
                            contents = ["Hello"]
                        from google.genai import types as google_types

                        # Convert tools to Google format
                        google_tools = []
                        for tool in openai_tools:
                            func = tool["function"]
                            google_tools.append(
                                google_types.FunctionDeclaration(
                                    name=func["name"],
                                    description=func.get("description", ""),
                                    parameters=google_types.Schema(
                                        type_=google_types.Type.OBJECT,
                                        properties={
                                            k: google_types.Schema(
                                                type_=google_types.Type.STRING,
                                                description=v.get("description", ""),
                                            )
                                            for k, v in func.get("parameters", {})
                                            .get("properties", {})
                                            .items()
                                        },
                                        required=func.get("parameters", {}).get("required", []),
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

                        response = gemini_client.models.generate_content(
                            model=api_model,
                            contents=contents,
                            config=google_config,
                        )
                        content = response.text or ""
                        # Extract tool calls from Gemini response
                        if response.candidates:
                            for part in response.candidates[0].content.parts:
                                if part.function_call:
                                    native_tool_calls.append(
                                        {
                                            "id": f"gemini_{len(native_tool_calls)}",
                                            "name": part.function_call.name,
                                            "args": dict(part.function_call.args)
                                            if part.function_call.args
                                            else {},
                                        }
                                    )
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

                        stream = client.chat.completions.create(**api_kwargs)

                        content = ""
                        tool_call_deltas: dict[int, dict] = {}

                        for chunk in stream:
                            if hasattr(chunk, "usage") and chunk.usage:
                                total_tokens_in = chunk.usage.prompt_tokens or 0
                                total_tokens_out = chunk.usage.completion_tokens or 0
                            if not chunk.choices:
                                continue
                            delta = chunk.choices[0].delta
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
                            native_tool_calls.append(tc)

                    # Handle empty content with no tool calls
                    if not content and not native_tool_calls:
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
                        ]
                        content_lower = content.lower() if content else ""
                        is_fabrication = not tool_history and any(
                            phrase in content_lower for phrase in fabrication_phrases
                        )

                        if is_fabrication and iteration < effort["max_iterations"] - 1:
                            messages.append(
                                {
                                    "role": "user",
                                    "content": (
                                        "STOP. You are fabricating results without calling tools. "
                                        "You MUST use a tool to interact with the system. Do it NOW."
                                    ),
                                }
                            )
                            continue

                        # Handle todo completion
                        if task_plan and current_todo_index < len(task_plan.todos):
                            from sago.tasks import TaskStatus, get_task_manager

                            tm = get_task_manager()
                            todo = task_plan.todos[current_todo_index]
                            if todo.status == TaskStatus.IN_PROGRESS:
                                tm.complete_todo(
                                    task_plan.id, todo.id, result=content[:200] if content else ""
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
                                            "content": f"Moving to next step: {next_todo.description}\nExecute this step now.",
                                        }
                                    )
                                    continue
                        break

                    # ---- Execute native tool calls ----
                    tools_used_in_iteration = []

                    for tc in native_tool_calls:
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

                        # Loop protection
                        call_key = f"{name}:{json.dumps(args, sort_keys=True)}"
                        if call_key in failed_calls:
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc_id,
                                    "content": f"[SKIP] Already failed: {name} with same args",
                                }
                            )
                            continue

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
                            if risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                                self.call_from_thread(
                                    self._show_approval_bar,
                                    f"Allow {name}? (risk: {risk.value}) -- Press [Y] or [N]",
                                )
                                pause_event = threading.Event()
                                self._executor_pause_event = pause_event
                                self._pending_tool_approval = {"name": name, "args": args}
                                pause_event.wait()
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

                        # Detect circular behavior
                        tool_call_counts[name] = tool_call_counts.get(name, 0) + 1
                        recent_calls = [
                            f"{c['tool']}:{json.dumps(c['args'], sort_keys=True)[:50]}"
                            for c in tool_history[-5:]
                        ]
                        if len(recent_calls) >= 3:
                            unique_recent = set(recent_calls[-3:])
                            if len(unique_recent) == 1:
                                messages.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": tc_id,
                                        "content": f"[HINT] You've called {name} with similar args 3 times. Try a different approach.",
                                    }
                                )
                                continue

                        self.call_from_thread(on_tool, name, args)
                        tool_instance = tools[name]()
                        result = tool_instance.run(**args)
                        result_str = str(result)

                        is_error = (
                            result_str.lower().startswith("error")
                            or "traceback" in result_str.lower()
                        )
                        if is_error:
                            failed_calls.add(call_key)

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
                        tools_used_in_iteration.append(name)
                        self.call_from_thread(on_tool_result, name, args, result_str, not is_error)

                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "content": result_str,
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
                                    pause_event.wait()
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
                        except Exception:
                            pass

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

                        test_fix_attempts += 1
                        if test_fix_attempts >= max_test_fix_attempts:
                            self.call_from_thread(
                                self._add_system_message,
                                f"❌ Tests still failing after {max_test_fix_attempts} attempts",
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
                                                    "arguments": tc["arguments"],
                                                },
                                            }
                                            for tc in fix_tcs
                                        ],
                                    }
                                )
                                for tc in fix_tcs:
                                    try:
                                        fix_args = (
                                            json.loads(tc["arguments"]) if tc["arguments"] else {}
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
                        except Exception:
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
                    except Exception:
                        pass

                elapsed = _time.time() - start_time
                self.call_from_thread(self._hide_spinner)

                # Show summary
                self.call_from_thread(
                    self._add_summary,
                    tool_history,
                    content,
                    elapsed,
                    {"input": total_tokens_in, "output": total_tokens_out},
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
                    except Exception:
                        pass

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
                except Exception:
                    pass

                # Show response — if tools were executed, show results not raw JSON
                if tool_history:
                    # Tools were executed — show a summary of what happened
                    last_results = []
                    for t in tool_history[-3:]:
                        status = "✓" if t.get("success") else "✗"
                        last_results.append(f"{status} {t['tool']}: {t.get('result', '')[:200]}")
                    summary = "\n".join(last_results)
                    if content and content.strip() and not content.strip().startswith("{"):
                        # LLM also produced text output (not just tool calls)
                        self.call_from_thread(self._add_assistant_message, content)
                    else:
                        self.call_from_thread(self._add_assistant_message, summary)
                elif content and content.strip():
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

                # Get API key for the current provider
                provider_key = os.environ.get(
                    {"google": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY"}.get(
                        self.current_provider, "OPENROUTER_API_KEY"
                    ),
                    "",
                )
                provider_base_url = {
                    "google": None,
                    "openai": "https://api.openai.com/v1",
                    "openrouter": "https://openrouter.ai/api/v1",
                }.get(self.current_provider, "https://openrouter.ai/api/v1")

                result = execute_agent_task(
                    task=message,
                    agent_role=self.current_agent.replace("-", " ").title(),
                    api_key=provider_key,
                    model=self.current_model,
                    base_url=provider_base_url,
                    max_tokens=effort["max_tokens"],
                    max_iterations=effort["max_iterations"],
                    on_tool_call=on_tool,
                    on_tool_result=on_tool_result,
                    on_thinking=on_thinking,
                    on_todo_created=on_todo_created,
                    on_todo_update=on_todo_update,
                )

                if result.get("task_plan"):
                    from sago.tasks import get_task_manager

                    tm = get_task_manager()
                    plan = tm.get_active_plan()
                    if plan:
                        self.call_from_thread(self._add_system_message, tm.format_plan(plan))

                self.call_from_thread(self._hide_spinner)

                output = result.get("output", "")
                tool_calls = result.get("tool_calls", [])
                if output and output.strip():
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
            if "429" in error_msg or "rate" in error_msg.lower():
                provider_urls = {
                    "google": "https://console.cloud.google.com/billing",
                    "openai": "https://platform.openai.com/settings/organization/billing",
                    "openrouter": "https://openrouter.ai/settings/credits",
                }
                url = provider_urls.get(self.current_provider, "your provider's dashboard")
                error_msg = f"Rate limited. Wait or check credits at {url}"
            elif "401" in error_msg or "auth" in error_msg.lower():
                error_msg = f"Authentication failed. Check your {self.current_provider} API key."
            elif "404" in error_msg:
                error_msg = f"Model '{self.current_model}' not found. Try a different model."
            self.call_from_thread(self._add_system_message, f"Error: {error_msg}")
        finally:
            self.is_thinking = False


def main():
    SagoApp().run()
