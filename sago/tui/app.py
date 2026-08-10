"""Sago TUI - Production Terminal Interface with all features working."""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from rich.syntax import Syntax
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widgets import Collapsible, Input, Static


COMMANDS = {
    "/help": "Show all commands",
    "/agents": "List agents (or /agents <filter>)",
    "/agent": "Set current agent (/agent <name>)",
    "/delegate": "Delegate task to specialist (/delegate <agent> <task>)",
    "/chain": "Chain agents (/chain <agent1,agent2> <task>)",
    "/orchestrate": "Multi-agent orchestration (auto-delegates to specialists)",
    "/clear": "Clear chat",
    "/status": "System status",
    "/export": "Export to markdown",
    "/sessions": "List sessions",
    "/session": "Switch session (/session <id>)",
    "/history": "Chat history",
    "/model": "Change model (/model <name>)",
    "/provider": "Change provider",
    "/effort": "Set effort: low/medium/high/max",
    "/cost": "Token usage and costs",
    "/compact": "Summarize and compress context",
    "/retry": "Retry last message",
    "/reset": "Reset session",
    "/save": "Save session to file (/save [name])",
    "/load": "Load session from file (/load <name>)",
    "/git": "Git status",
    "/diff": "Show diff (/diff [file])",
    "/commit": "Commit (/commit <message>)",
    "/approve": "Approve pending action",
    "/deny": "Deny pending action",
    "/version": "Version info",
    "/undo": "Undo last file change",
    "/changes": "Show file changes this session",
    "/exit": "Quit",
}

MODELS = [
    "openrouter/free",
    "openrouter/deepseek/deepseek-chat",
    "openrouter/meta-llama/llama-3.1-70b-instruct",
    "openrouter/qwen/qwen-2.5-72b-instruct",
    "openrouter/google/gemini-2.0-flash-001",
]

EFFORT_LEVELS = {
    "low": {"max_iterations": 3, "max_tokens": 8192, "desc": "Quick answers, minimal tool use"},
    "medium": {"max_iterations": 6, "max_tokens": 16384, "desc": "Balanced approach"},
    "high": {"max_iterations": 10, "max_tokens": 32768, "desc": "Thorough analysis, complex tasks"},
    "max": {"max_iterations": 15, "max_tokens": 65536, "desc": "Maximum depth, full context utilization"},
}

# Pricing per 1M tokens (approximate) - with cache pricing
MODEL_COSTS = {
    "openrouter/free": {"input": 0, "output": 0, "cache_hit": 0, "cache_miss": 0},
    "openrouter/deepseek/deepseek-chat": {"input": 0.14, "output": 0.28, "cache_hit": 0.014, "cache_miss": 0.14},
    "openrouter/meta-llama/llama-3.1-70b-instruct": {"input": 0.52, "output": 0.75, "cache_hit": 0.052, "cache_miss": 0.52},
    "openrouter/qwen/qwen-2.5-72b-instruct": {"input": 0.50, "output": 0.75, "cache_hit": 0.05, "cache_miss": 0.50},
    "openrouter/google/gemini-2.0-flash-001": {"input": 0.10, "output": 0.40, "cache_hit": 0.025, "cache_miss": 0.10},
    "anthropic/claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00, "cache_hit": 0.30, "cache_miss": 3.00},
    "anthropic/claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00, "cache_hit": 0.30, "cache_miss": 3.00},
    "openai/gpt-4o": {"input": 2.50, "output": 10.00, "cache_hit": 1.25, "cache_miss": 2.50},
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60, "cache_hit": 0.075, "cache_miss": 0.15},
}

SPINNERS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

SAVE_DIR = Path.home() / ".sago" / "sessions"


class Spinner(Static):
    def __init__(self, text: str = "Thinking", **kwargs) -> None:
        self.frame = 0
        self.spin_text = text
        super().__init__(**kwargs)

    def render(self) -> str:
        return f" {SPINNERS[self.frame % len(SPINNERS)]} {self.spin_text}..."

    def advance(self) -> None:
        self.frame += 1
        self.refresh()


class SagoApp(App):
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
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+l", "clear_chat", "Clear"),
        Binding("escape", "dismiss_suggestions", "Dismiss"),
    ]

    TITLE = "Sago"

    current_agent: reactive[str] = reactive("sago-orchestrator")
    current_model: reactive[str] = reactive("openrouter/free")
    current_effort: reactive[str] = reactive("medium")
    current_session_id: reactive[str] = reactive("")
    messages: reactive[list[dict]] = reactive(list)
    show_suggestions: reactive[bool] = reactive(False)
    suggestion_items: reactive[list[str]] = reactive(list)
    suggestion_values: reactive[list[str]] = reactive(list)
    suggestion_index: reactive[int] = reactive(0)
    is_thinking: reactive[bool] = reactive(False)
    pending_action: reactive[dict] = reactive(dict)
    command_history: reactive[list[str]] = reactive(list)
    history_index: reactive[int] = reactive(-1)
    total_input_tokens: reactive[int] = reactive(0)
    total_output_tokens: reactive[int] = reactive(0)
    total_cache_hit_tokens: reactive[int] = reactive(0)
    total_cache_miss_tokens: reactive[int] = reactive(0)
    total_cost: reactive[float] = reactive(0.0)
    # Pause/resume mechanism for todo confirmations
    _executor_pause_event: object = None  # threading.Event
    _executor_thread: object = None  # running thread reference

    def compose(self) -> ComposeResult:
        yield ScrollableContainer(id="messages")
        yield Vertical(id="suggestions")
        with Vertical(id="input-area"):
            yield Input(placeholder="/, @, # for autocomplete", id="msg-input")

    def on_mount(self) -> None:
        self._spinner = None
        self._spinner_timer = None
        self._init_db()
        self._init_session()
        self._add_system_message("Sago v0.1.0 — /help for commands")
        self.query_one("#msg-input").focus()

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
            event.input.value = val + " "
            event.input.cursor_position = len(event.input.value)
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
            elif event.key in ("right", "tab"):
                event.prevent_default()
                self._select_current()
        elif event.key in ("up", "down"):
            event.prevent_default()
            self._navigate_history(event.key)

    def _move_sel(self, d: int) -> None:
        if self.suggestion_items:
            self.suggestion_index = (self.suggestion_index + d) % len(self.suggestion_items)
            self._update_highlight()

    def _select_current(self) -> None:
        if self.suggestion_values:
            v = self.suggestion_values[self.suggestion_index]
            inp = self.query_one("#msg-input")
            inp.value = v + " "
            inp.cursor_position = len(inp.value)
            self._hide_suggestions()

    def _update_highlight(self) -> None:
        for i, child in enumerate(self.query_one("#suggestions").children):
            child.set_class(i == self.suggestion_index, "highlighted")

    def _add_to_history(self, cmd: str) -> None:
        if self.command_history and self.command_history[-1] == cmd:
            return
        self.command_history.append(cmd)
        if len(self.command_history) > 50:
            self.command_history = self.command_history[-50:]

    def _navigate_history(self, key: str) -> None:
        if not self.command_history:
            return
        inp = self.query_one("#msg-input")
        if key == "up":
            idx = self.history_index + 1
            if idx < len(self.command_history):
                self.history_index = idx
                inp.value = self.command_history[-1 - idx]
                inp.cursor_position = len(inp.value)
        elif key == "down":
            if self.history_index > 0:
                self.history_index -= 1
                inp.value = self.command_history[-1 - self.history_index]
                inp.cursor_position = len(inp.value)
            else:
                self.history_index = -1
                inp.value = ""
                inp.cursor_position = 0

    def on_mouse_scroll_down(self, event) -> None:
        self.query_one("#messages").scroll_down()

    def on_mouse_scroll_up(self, event) -> None:
        self.query_one("#messages").scroll_up()

    def on_click(self, event) -> None:
        if self.show_suggestions:
            for i, child in enumerate(self.query_one("#suggestions").children):
                if child.hovered:
                    self.suggestion_index = i
                    self._select_current()
                    break

    def _show_cmd_suggestions(self, prefix: str) -> None:
        full_commands = {k: v for k, v in COMMANDS.items() if len(k) > 2}
        matches = [(c, d) for c, d in full_commands.items() if c.startswith(prefix.lower())]
        if matches:
            self._show_suggestions([f"{c} — {d}" for c, d in matches], [c for c, _ in matches])
        else:
            self._hide_suggestions()

    def _show_agent_suggestions(self, prefix: str) -> None:
        try:
            from sago.agents.registry import list_agents
            search = prefix[1:].lower()
            matches = [a["name"] for a in list_agents() if search in a["name"].lower()][:15]
            if matches:
                self._show_suggestions([f"@{n}" for n in matches], matches)
            else:
                self._hide_suggestions()
        except Exception:
            self._hide_suggestions()

    def _show_file_suggestions(self, prefix: str) -> None:
        search = prefix[1:].lower()
        items, vals = [], []
        try:
            for p in Path(".").iterdir():
                if p.name.startswith(".") or p.name.startswith("_"):
                    continue
                if search in p.name.lower():
                    items.append(f"#  {p.name}")
                    vals.append(p.name)
                    if len(items) >= 10:
                        break
        except Exception:
            pass
        if items:
            self._show_suggestions(items, vals)
        else:
            self._hide_suggestions()

    def _show_suggestions(self, items: list[str], values: list[str]) -> None:
        container = self.query_one("#suggestions")
        container.remove_children()
        for item in items:
            container.mount(Static(item, classes="suggestion-item"))
        self.suggestion_items = items
        self.suggestion_values = values
        self.suggestion_index = 0
        self.show_suggestions = True
        container.add_class("visible")
        self._update_highlight()

    def _hide_suggestions(self) -> None:
        self.show_suggestions = False
        self.suggestion_items = []
        self.suggestion_values = []
        self.query_one("#suggestions").remove_class("visible")

    def action_dismiss_suggestions(self) -> None:
        self._hide_suggestions()

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
            self._spinner.spin_text = text
            self._spinner.refresh()

    def _hide_spinner(self) -> None:
        if hasattr(self, "_spinner_timer") and self._spinner_timer:
            self._spinner_timer.stop()
            self._spinner_timer = None
        if hasattr(self, "_spinner") and self._spinner:
            try:
                self._spinner.remove()
            except Exception:
                pass
            self._spinner = None

    def _handle_command(self, command: str) -> None:
        parts = command.strip().split(maxsplit=1)
        cmd, args = parts[0].lower(), parts[1] if len(parts) > 1 else ""

        h = {
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
            "/version": lambda: self._add_system_message("Sago v0.1.0"),
            "/exit": lambda: self.exit(),
        }
        fn = h.get(cmd)
        if fn:
            fn()
        else:
            self._add_system_message(f"Unknown: {cmd}")

    def _show_help(self) -> None:
        self._add_system_message(
            "Commands:\n"
            "\n"
            "  /help             Show this help\n"
            "  /agents [filter]  List agents\n"
            "  /agent <name>     Set current agent\n"
            "  /delegate <a> <t> Delegate task to specialist\n"
            "  /chain <a1,a2> <t> Chain agents\n"
            "  /orchestrate <t>  Auto-delegate to specialists\n"
            "  /clear            Clear chat\n"
            "  /status           System status\n"
            "  /export           Export to markdown\n"
            "  /sessions         List sessions\n"
            "  /session <id>     Switch session\n"
            "  /history          Chat history\n"
            "  /model [name]     Change model\n"
            "  /effort <level>   Set effort: low/medium/high/max\n"
            "  /cost             Token usage and costs\n"
            "  /compact          Summarize context\n"
            "  /save [name]      Save session to file\n"
            "  /load <name>      Load session from file\n"
            "  /retry            Retry last message\n"
            "  /reset            Reset session\n"
            "  /git              Git status\n"
            "  /diff [file]      Show diff\n"
            "  /commit <msg>     Commit\n"
            "  /approve          Approve action\n"
            "  /deny             Deny action\n"
            "  /permissions      Show tool permissions\n"
            "  /allow <tool>     Allow a tool\n"
            "  /block <tool>     Block a tool\n"
            "  /plan             Show active task plan\n"
            "  /todo             Show current todo\n"
            "  /todos            Show all todos in plan\n"
            "  /done [id]        Mark todo as done\n"
            "  /ask <msg>        Ask for user input\n"
            "  /exit             Quit"
        )

    def _show_agents(self, f: str = "") -> None:
        try:
            from sago.agents.registry import list_agents
            agents = list_agents()
            if f:
                filtered = [a for a in agents if f.lower() in a["name"].lower()]
                lines = "\n".join(f"  {a['name']}" for a in filtered[:30])
                self._add_system_message(f"Agents matching '{f}' ({len(filtered)}):\n{lines}")
            else:
                lines = "\n".join(f"  {a['name']}" for a in agents[:30])
                self._add_system_message(f"Agents ({len(agents)} total, use /agents <filter>):\n{lines}")
        except Exception as e:
            self._add_system_message(f"Error: {e}")

    def _set_agent(self, name: str) -> None:
        if not name:
            self._add_system_message(f"Current: {self.current_agent}\nUse /agents to see available")
            return
        from sago.agents.registry import get_agent
        agent = get_agent(name)
        if agent:
            self.current_agent = name
            self._add_system_message(f"Agent: {name} ({agent.role})")
        else:
            self._add_system_message(f"Unknown agent: {name}")

    def _delegate_task(self, args: str) -> None:
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            self._add_system_message("Usage: /delegate <agent-name> <task>")
            return
        agent_name, task = parts[0], parts[1]
        self._add_user_message(f"/delegate {args}")
        self._process_delegation(agent_name, task)

    def _chain_agents(self, args: str) -> None:
        parts = args.split(maxsplit=1)
        if len(parts) < 2:
            self._add_system_message("Usage: /chain <agent1,agent2,...> <task>")
            return
        agent_chain, task = parts[0], parts[1]
        agents = [a.strip() for a in agent_chain.split(",")]
        self._add_user_message(f"/chain {args}")
        self._process_chain(agents, task)

    def _orchestrate_task(self, task: str) -> None:
        if not task:
            self._add_system_message("Usage: /orchestrate <task>")
            return
        self._add_user_message(f"/orchestrate {task}")
        self._process_orchestration(task)

    def _show_status(self) -> None:
        try:
            from sago.agents.registry import list_agents
            n = len(list_agents())
        except Exception:
            n = 0
        sid = self.current_session_id[:8] if self.current_session_id else "none"
        effort = EFFORT_LEVELS.get(self.current_effort, {})
        self._add_system_message(
            f"Sago v0.1.0\n"
            f"  Agent:    {self.current_agent}\n"
            f"  Model:    {self.current_model}\n"
            f"  Effort:   {self.current_effort} ({effort.get('desc', '')})\n"
            f"  Session:  {sid}\n"
            f"  Agents:   {n} available\n"
            f"  Messages: {len(self.messages)}"
        )

    def _show_sessions(self) -> None:
        try:
            from sago.database import Session, init_db
            init_db()
            s = Session()
            sessions = s.list_all(limit=15)
            s.close()
            if sessions:
                lines = []
                for ses in sessions:
                    sid = ses["id"][:8]
                    title = ses.get("title", "Untitled")[:30]
                    date = ses.get("created_at", "?")[:10]
                    lines.append(f"  {sid}  {title:<30} {date}")
                self._add_system_message("Sessions (use /session <id> to load):\n" + "\n".join(lines))
            else:
                self._add_system_message("No sessions")
        except Exception as e:
            self._add_system_message(f"Sessions: {e}")

    def _switch_session(self, sid: str) -> None:
        if not sid:
            self._add_system_message("Usage: /session <id>")
            return
        try:
            from sago.database import Session, MessageStore, init_db
            init_db()
            s = Session()
            sessions = s.list_all(limit=100)
            s.close()

            matched = None
            for ses in sessions:
                if ses["id"] == sid or ses["id"].startswith(sid):
                    matched = ses
                    break

            if not matched:
                self._add_system_message(f"Not found: {sid}")
                return

            full_id = matched["id"]
            self.current_session_id = full_id

            ms = MessageStore(full_id)
            history = ms.get_history(limit=100)
            ms.close()

            self.messages.clear()
            self.query_one("#messages").remove_children()
            self._add_system_message(f"Loaded: {matched.get('title', 'Untitled')} [{full_id[:8]}] ({len(history)} msgs)")
            for msg in history:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user":
                    self.messages.append({"role": "user", "content": content})
                    self.query_one("#messages").mount(Static(f"> {content}", classes="msg-user"))
                elif role == "assistant":
                    self.messages.append({"role": "assistant", "content": content})
                    self.query_one("#messages").mount(Static(content, classes="msg-assistant"))
            self.query_one("#messages").scroll_end()
        except Exception as e:
            self._add_system_message(f"Error: {e}")

    def _show_history(self) -> None:
        if self.messages:
            lines = [f"  [{m.get('role','?')}] {m.get('content','')[:50]}" for m in self.messages[-10:]]
            self._add_system_message("History:\n" + "\n".join(lines))
        else:
            self._add_system_message("No history")

    def _change_model(self, m: str) -> None:
        if not m:
            self._add_system_message(f"Current: {self.current_model}\n" + "\n".join(f"  {x}" for x in MODELS))
            return
        for model in MODELS:
            if m.lower() in model.lower():
                self.current_model = model
                self._add_system_message(f"Model: {model}")
                return
        self._add_system_message(f"Unknown: {m}\nAvailable: {', '.join(MODELS)}")

    def _change_provider(self, p: str) -> None:
        self.current_model = f"{p}/free" if "/" not in p else p
        self._add_system_message(f"Provider: {self.current_model}")

    def _set_effort(self, level: str) -> None:
        if not level:
            current = EFFORT_LEVELS.get(self.current_effort, {})
            lines = [f"Current: {self.current_effort} - {current.get('desc', '')}"]
            for k, v in EFFORT_LEVELS.items():
                marker = " *" if k == self.current_effort else ""
                lines.append(f"  {k:8} {v['desc']}{marker}")
            self._add_system_message("\n".join(lines))
            return

        level = level.lower().strip()
        if level in EFFORT_LEVELS:
            self.current_effort = level
            config = EFFORT_LEVELS[level]
            self._add_system_message(
                f"Effort: {level}\n"
                f"  Max iterations: {config['max_iterations']}\n"
                f"  Max tokens: {config['max_tokens']}\n"
                f"  {config['desc']}"
            )
        else:
            self._add_system_message(f"Unknown level: {level}\nUse: low, medium, high, max")

    def _show_cost(self) -> None:
        cost_config = MODEL_COSTS.get(self.current_model, {"input": 0, "output": 0, "cache_hit": 0, "cache_miss": 0})

        # Calculate costs with cache pricing
        cache_hit_cost = (self.total_cache_hit_tokens / 1_000_000) * cost_config.get("cache_hit", 0)
        cache_miss_cost = (self.total_cache_miss_tokens / 1_000_000) * cost_config.get("cache_miss", cost_config["input"])
        output_cost = (self.total_output_tokens / 1_000_000) * cost_config["output"]
        total = cache_hit_cost + cache_miss_cost + output_cost

        # Cache savings
        full_input_cost = ((self.total_cache_hit_tokens + self.total_cache_miss_tokens) / 1_000_000) * cost_config["input"]
        savings = full_input_cost - (cache_hit_cost + cache_miss_cost)
        savings_pct = (savings / full_input_cost * 100) if full_input_cost > 0 else 0

        total_input = self.total_cache_hit_tokens + self.total_cache_miss_tokens

        lines = [
            f"Token Usage ({self.current_model}):",
            f"  Input:     {total_input:,} tokens",
            f"    Cache hit:  {self.total_cache_hit_tokens:,} tokens (${cache_hit_cost:.4f})" if self.total_cache_hit_tokens else "",
            f"    Cache miss: {self.total_cache_miss_tokens:,} tokens (${cache_miss_cost:.4f})" if self.total_cache_miss_tokens else "",
            f"  Output:    {self.total_output_tokens:,} tokens (${output_cost:.4f})",
            f"  ─────────────────────────────",
            f"  Total:     ${total:.4f}",
        ]

        if savings > 0:
            lines.append(f"  Saved:     ${savings:.4f} ({savings_pct:.0f}% via cache)")

        lines.append(f"  Messages:  {len(self.messages)}")

        self._add_system_message("\n".join(l for l in lines if l))

    def _compact(self) -> None:
        if not self.messages:
            self._add_system_message("Nothing to compact")
            return

        # Build summary of conversation
        user_msgs = [m for m in self.messages if m.get("role") == "user"]
        asst_msgs = [m for m in self.messages if m.get("role") == "assistant"]

        summary_parts = []
        for m in user_msgs[-5:]:
            summary_parts.append(f"User: {m['content'][:100]}")
        for m in asst_msgs[-3:]:
            summary_parts.append(f"Assistant: {m['content'][:200]}")

        summary = "\n".join(summary_parts)

        # Keep only last few messages
        self.messages = self.messages[-6:]

        self.query_one("#messages").remove_children()
        self._add_system_message(f"[Context compacted - {len(user_msgs)} messages summarized]")
        self._add_system_message(f"Recent context:\n{summary}")

    def _retry_last(self) -> None:
        user_msgs = [m for m in self.messages if m.get("role") == "user"]
        if user_msgs:
            last = user_msgs[-1]["content"]
            self._process_message(last)
        else:
            self._add_system_message("Nothing to retry")

    def _reset(self) -> None:
        self.messages.clear()
        self.query_one("#messages").remove_children()
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cache_hit_tokens = 0
        self.total_cache_miss_tokens = 0
        self.total_cost = 0.0
        self._init_session()
        self._add_system_message("Session reset")

    def _save_session(self, name: str) -> None:
        name = name.strip() or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        filepath = SAVE_DIR / f"{name}.json"

        data = {
            "name": name,
            "created_at": datetime.now().isoformat(),
            "model": self.current_model,
            "effort": self.current_effort,
            "agent": self.current_agent,
            "messages": self.messages,
            "tokens": {
                "input": self.total_input_tokens,
                "output": self.total_output_tokens,
                "cache_hit": self.total_cache_hit_tokens,
                "cache_miss": self.total_cache_miss_tokens,
            },
        }

        filepath.write_text(json.dumps(data, indent=2))
        self._add_system_message(f"Saved: {filepath}")

    def _load_session(self, name: str) -> None:
        if not name:
            # List saved sessions
            if SAVE_DIR.exists():
                files = list(SAVE_DIR.glob("*.json"))
                if files:
                    lines = [f"  {f.stem}" for f in sorted(files)[-10:]]
                    self._add_system_message(f"Saved sessions (use /load <name>):\n" + "\n".join(lines))
                else:
                    self._add_system_message("No saved sessions")
            else:
                self._add_system_message("No saved sessions")
            return

        filepath = SAVE_DIR / f"{name}.json"
        if not filepath.exists():
            self._add_system_message(f"Not found: {name}")
            return

        try:
            data = json.loads(filepath.read_text())
            self.messages = data.get("messages", [])
            self.current_model = data.get("model", self.current_model)
            self.current_effort = data.get("effort", self.current_effort)
            self.current_agent = data.get("agent", self.current_agent)
            tokens = data.get("tokens", {})
            self.total_input_tokens = tokens.get("input", 0)
            self.total_output_tokens = tokens.get("output", 0)
            self.total_cache_hit_tokens = tokens.get("cache_hit", 0)
            self.total_cache_miss_tokens = tokens.get("cache_miss", 0)

            self.query_one("#messages").remove_children()
            self._add_system_message(f"Loaded: {name}")
            for msg in self.messages:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user":
                    self.query_one("#messages").mount(Static(f"> {content}", classes="msg-user"))
                elif role == "assistant":
                    self.query_one("#messages").mount(Static(content, classes="msg-assistant"))
            self.query_one("#messages").scroll_end()
        except Exception as e:
            self._add_system_message(f"Error loading: {e}")

    def _export_session(self) -> None:
        export = "\n".join(f"[{m.get('role','?').upper()}]\n{m.get('content','')}\n" for m in self.messages)
        fn = f"sago_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        Path(fn).write_text(f"# Sago Session\n\n{export}")
        self._add_system_message(f"Exported: {fn}")

    def _git_status(self) -> None:
        try:
            r = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                files = r.stdout.strip()
                self._add_system_message(f"Git changes:\n{files}" if files else "Git: clean")
            else:
                self._add_system_message("Not a git repo")
        except Exception:
            self._add_system_message("Git unavailable")

    def _git_diff(self, file: str) -> None:
        try:
            args = ["git", "diff"]
            if file:
                args.extend(["--", file])
            r = subprocess.run(args, capture_output=True, text=True, timeout=5)
            if r.stdout:
                self._add_assistant_message(f"```diff\n{r.stdout[:2000]}\n```")
            else:
                self._add_system_message("No changes")
        except Exception:
            self._add_system_message("Diff failed")

    def _git_commit(self, msg: str) -> None:
        if not msg:
            self._add_system_message("Usage: /commit <message>")
            return
        self.pending_action = {"type": "git_commit", "message": msg}
        self._add_system_message(f"Commit: \"{msg}\"?\nType /approve or /deny")

    def _approve_action(self) -> None:
        import threading
        action = self.pending_action
        if not action:
            # Check for pending orchestration plan
            if hasattr(self, 'pending_orchestration') and self.pending_orchestration:
                plan = self.pending_orchestration.get("plan")
                if plan:
                    self.pending_orchestration = None
                    self._execute_orchestration_plan(plan)
                    return
            # Check if executor is paused (waiting for user confirmation)
            if self._executor_pause_event and isinstance(self._executor_pause_event, threading.Event):
                self._executor_pause_event.clear()  # Resume executor
                self._add_system_message("Approved - continuing execution")
                return
            self._add_system_message("Nothing to approve")
            return
        if action["type"] == "git_commit":
            try:
                subprocess.run(["git", "add", "-A"], capture_output=True, timeout=5)
                r = subprocess.run(["git", "commit", "-m", action["message"]], capture_output=True, text=True, timeout=5)
                self._add_system_message(f"Committed: {r.stdout.strip()[:100]}")
            except Exception as e:
                self._add_system_message(f"Failed: {e}")
        elif action["type"] == "user_input":
            plan_id = action.get("plan_id")
            todo_id = action.get("todo_id")
            if plan_id and todo_id:
                from sago.tasks import get_task_manager
                tm = get_task_manager()
                user_input = action.get("input", "")
                if user_input:
                    tm.provide_input(plan_id, todo_id, user_input)
                    self._add_system_message(f"Input provided for todo {todo_id}")
        self.pending_action = {}

    def _deny_action(self) -> None:
        import threading
        # Check for pending orchestration plan
        if hasattr(self, 'pending_orchestration') and self.pending_orchestration:
            self.pending_orchestration = None
            self._add_system_message("Orchestration plan denied")
            return
        # Check if executor is paused - resume with skip
        if self._executor_pause_event and isinstance(self._executor_pause_event, threading.Event):
            self._executor_pause_event.clear()  # Resume executor (it will skip the current step)
            self._add_system_message("Skipped - continuing execution")
            return
        self.pending_action = {}
        self._add_system_message("Denied")

    def _show_permissions(self, args: str) -> None:
        from sago.permissions import get_permission_manager, TOOL_RISK_LEVELS, RiskLevel
        pm = get_permission_manager()

        if args == "blocked":
            if pm.config.blocked_tools:
                lines = "\n".join(f"  - {t}" for t in pm.config.blocked_tools)
                self._add_system_message(f"Blocked tools:\n{lines}")
            else:
                self._add_system_message("No blocked tools")
        elif args == "allowed":
            if pm.config.allowed_tools:
                lines = "\n".join(f"  - {t}" for t in pm.config.allowed_tools)
                self._add_system_message(f"Allowed tools:\n{lines}")
            else:
                self._add_system_message("No explicit allowed list (all tools available)")
        else:
            lines = []
            for name, risk in sorted(TOOL_RISK_LEVELS.items()):
                blocked = "BLOCKED" if pm.is_blocked(name) else "ok"
                lines.append(f"  {name:<25} {risk.value:<10} {blocked}")
            self._add_system_message("Tool permissions:\n" + "\n".join(lines))

    def _allow_tool(self, tool_name: str) -> None:
        if not tool_name:
            self._add_system_message("Usage: /allow <tool_name>")
            return
        from sago.permissions import get_permission_manager
        pm = get_permission_manager()
        if tool_name in pm.config.blocked_tools:
            pm.config.blocked_tools.remove(tool_name)
            pm._save_config()
            self._add_system_message(f"Unblocked: {tool_name}")
        else:
            self._add_system_message(f"Not blocked: {tool_name}")

    def _block_tool(self, tool_name: str) -> None:
        if not tool_name:
            self._add_system_message("Usage: /block <tool_name>")
            return
        from sago.permissions import get_permission_manager
        pm = get_permission_manager()
        if tool_name not in pm.config.blocked_tools:
            pm.config.blocked_tools.append(tool_name)
            pm._save_config()
            self._add_system_message(f"Blocked: {tool_name}")
        else:
            self._add_system_message(f"Already blocked: {tool_name}")

    def _show_plan(self, args: str) -> None:
        from sago.tasks import get_task_manager
        tm = get_task_manager()
        plan = tm.get_active_plan()
        if plan:
            self._add_system_message(tm.format_plan(plan))
        else:
            self._add_system_message("No active plan. Complex tasks auto-create plans.")

    def _show_todo(self, args: str) -> None:
        from sago.tasks import get_task_manager
        tm = get_task_manager()
        plan = tm.get_active_plan()
        if not plan:
            self._add_system_message("No active plan")
            return
        current = plan.current_todo
        if current:
            self._add_system_message(
                f"Current todo [{current.id}]: {current.description}\n"
                f"Status: {current.status.value}\n"
                f"Use /done {current.id} when complete"
            )
        else:
            self._add_system_message("All todos completed! ✅")

    def _show_all_todos(self) -> None:
        from sago.tasks import get_task_manager
        tm = get_task_manager()
        plan = tm.get_active_plan()
        if not plan:
            self._add_system_message("No active plan")
            return
        self._add_system_message(tm.format_plan(plan))

    def _mark_todo_done(self, todo_id: str) -> None:
        from sago.tasks import get_task_manager
        tm = get_task_manager()
        plan = tm.get_active_plan()
        if not plan:
            self._add_system_message("No active plan")
            return
        if not todo_id:
            # Mark current todo as done
            current = plan.current_todo
            if current:
                todo_id = current.id
            else:
                self._add_system_message("No pending todo to mark as done")
                return
        if tm.complete_todo(plan.id, todo_id, result="Completed by user"):
            self._add_system_message(f"Todo {todo_id} marked as done ✅")
            # Show next todo
            next_todo = plan.current_todo
            if next_todo:
                self._add_system_message(f"Next: [{next_todo.id}] {next_todo.description}")
            else:
                self._add_system_message("All todos completed! 🎉")
        else:
            self._add_system_message(f"Todo {todo_id} not found")

    def _ask_user(self, message: str) -> None:
        if not message:
            self._add_system_message("Usage: /ask <question for user>")
            return
        from sago.tasks import get_task_manager
        tm = get_task_manager()
        plan = tm.get_active_plan()
        if plan:
            current = plan.current_todo
            if current:
                tm.wait_for_input(plan.id, current.id, message)
                self._add_system_message(f"⏳ Waiting for input: {message}")
                self.pending_action = {"type": "user_input", "plan_id": plan.id, "todo_id": current.id}
        else:
            self._add_system_message(f"❓ {message}")

    def _undo_change(self) -> None:
        """Undo the last file change."""
        from sago.memory.change_tracker import get_change_tracker
        tracker = get_change_tracker()
        undone_path = tracker.undo_last()
        if undone_path:
            self._add_system_message(f"Undid change to: {undone_path}")
        else:
            self._add_system_message("No changes to undo")

    def _show_changes(self) -> None:
        """Show all file changes this session."""
        from sago.memory.change_tracker import get_change_tracker
        tracker = get_change_tracker()
        summary = tracker.get_diff_summary()
        self._add_system_message(summary)

    def _add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})
        self.query_one("#messages").mount(Static(f"> {content}", classes="msg-user"))
        self.query_one("#messages").scroll_end()
        self._save_message("user", content)

    def _add_assistant_message(self, content: str, meta: str = "") -> None:
        self.messages.append({"role": "assistant", "content": content})
        c = self.query_one("#messages")
        if meta:
            c.mount(Static(meta, classes="msg-meta"))
        code_blocks = re.findall(r"```(\w+)?\n(.*?)```", content, re.DOTALL)
        parts = re.split(r"```\w*\n.*?```", content, flags=re.DOTALL)
        for i, part in enumerate(parts):
            part = part.strip()
            if part:
                c.mount(Static(part, classes="msg-assistant"))
            if i < len(code_blocks):
                lang, code = code_blocks[i]
                try:
                    syntax = Syntax(code.strip(), lang or "text", theme="monokai", word_wrap=True)
                    c.mount(Static(syntax, classes="code-block"))
                except Exception:
                    c.mount(Static(code.strip(), classes="code-block"))
        c.scroll_end()
        self._save_message("assistant", content)

    def _add_system_message(self, content: str) -> None:
        self.query_one("#messages").mount(Static(content, classes="msg-system"))
        self.query_one("#messages").scroll_end()

    def _add_tool_call(self, tool_name: str, args: dict, result: str, success: bool = True) -> None:
        args_str = "\n".join(f"  {k}: {str(v)[:200]}" for k, v in args.items())
        status = "OK" if success else "ERROR"
        title = f"[{status}] {tool_name}"
        body = f"Input:\n{args_str}\n\nOutput:\n{result[:1000]}"
        if len(result) > 1000:
            body += f"\n... ({len(result)} chars total)"

        c = self.query_one("#messages")
        c.mount(Collapsible(
            Static(body, classes="msg-system"),
            title=title,
            collapsed=True,
        ))
        c.scroll_end()

    def _add_summary(self, tool_calls: list[dict], output: str, elapsed: float, tokens: dict) -> None:
        n_tools = len(tool_calls)
        n_ok = sum(1 for t in tool_calls if t.get("success", True))
        n_fail = n_tools - n_ok
        t_in = tokens.get("input", 0)
        t_out = tokens.get("output", 0)
        cache_hit = tokens.get("cache_hit", 0)
        cache_miss = tokens.get("cache_miss", 0)

        # Update totals
        self.total_input_tokens += t_in
        self.total_output_tokens += t_out
        self.total_cache_hit_tokens += cache_hit
        self.total_cache_miss_tokens += cache_miss

        lines = [f"Summary: {n_tools} calls ({n_ok} ok, {n_fail} fail) | {t_in}+{t_out} tokens | {elapsed:.1f}s"]

        if cache_hit > 0:
            lines.append(f"Cache: {cache_hit:,} hit, {cache_miss:,} miss")

        files = [t["args"].get("file_path", "") for t in tool_calls if t.get("tool") == "write_file" and t.get("success", True)]
        files = [f for f in files if f]
        if files:
            lines.append(f"Files: {', '.join(files)}")

        box = Static("\n".join(lines), classes="summary-box")
        self.query_one("#messages").mount(box)
        self.query_one("#messages").scroll_end()

    def _save_message(self, role: str, content: str) -> None:
        if self.current_session_id and self.current_session_id != "local":
            try:
                from sago.database import MessageStore
                ms = MessageStore(self.current_session_id)
                ms.add(role=role, content=content, agent_name=self.current_agent)
                ms.close()
            except Exception:
                pass

    @work(thread=True)
    def _process_delegation(self, agent_name: str, task: str) -> None:
        self.is_thinking = True
        self.call_from_thread(self._show_spinner, f"Delegating to {agent_name}...")
        try:
            api_key = os.environ.get("OPENROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
            if not api_key:
                self.call_from_thread(self._hide_spinner)
                self.call_from_thread(self._add_system_message,
                    "No API key. Set OPENROUTER_API_KEY or OPENAI_API_KEY.\n"
                    "You can still use Sago without agent delegation.")
                return

            from sago.tools.file.spawn_agent import SpawnAgentTool
            tool = SpawnAgentTool()
            result = tool.run(task=task, agent_name=agent_name)

            self.call_from_thread(self._hide_spinner)

            # If agent spawning failed, offer fallback
            if "could not be spawned" in result or "Error:" in result:
                self.call_from_thread(self._add_system_message,
                    f"{result}\n\n"
                    f"Would you like to:\n"
                    f"  1. Run the task directly (type the task again without /delegate)\n"
                    f"  2. Try a different agent"
                )
            else:
                self.call_from_thread(self._add_assistant_message, result)
        except Exception as e:
            self.call_from_thread(self._hide_spinner)
            self.call_from_thread(self._add_system_message,
                f"Delegation error: {e}\n"
                f"Try running the task directly instead.")
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
                self.call_from_thread(self._update_spinner, f"Step {i+1}/{len(agents)}: {agent}")
                result = tool.run(task=current_input, agent_name=agent)
                current_input = f"Previous agent ({agent}) said:\n\n{result}\n\nNow continue with the next step."

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
                self.call_from_thread(self._add_system_message, "No API key. Set OPENROUTER_API_KEY or OPENAI_API_KEY.")
                return

            from openai import OpenAI
            from sago.agents.registry import list_agents

            client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1", timeout=30.0)
            agents = list_agents()
            agent_list_str = "\n".join([
                f"- {a['name']}: {a.get('role', '')} | Skills: {', '.join(a.get('skills', [])[:3])}"
                for a in agents[:50]
            ])

            try:
                response = client.chat.completions.create(
                    model=self.current_model,
                    messages=[
                        {"role": "system", "content": (
                            "You are a task orchestrator. Analyze the task and break it into steps.\n"
                            "For each step, specify which agent should handle it.\n"
                            "Reply with a JSON list of steps: [{\"agent\": \"agent-name\", \"task\": \"what to do\"}]\n\n"
                            f"Available agents:\n{agent_list_str}"
                        )},
                        {"role": "user", "content": task},
                    ],
                    max_tokens=1024,
                )
            except Exception as api_err:
                self.call_from_thread(self._hide_spinner)
                self.call_from_thread(self._add_system_message,
                    f"Failed to create orchestration plan: {api_err}\n"
                    f"Try running the task directly instead of using /orchestrate."
                )
                return

            plan_text = response.choices[0].message.content or "[]"
            import json
            try:
                json_match = re.search(r'\[.*\]', plan_text, re.DOTALL)
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
                plan_lines.append(f"  {i+1}. {agent}: {step_task}")
            plan_msg = "Proposed plan:\n" + "\n".join(plan_lines) + "\n\nUse /approve or /deny"
            self.call_from_thread(self._hide_spinner)
            self.call_from_thread(self._add_system_message, plan_msg)

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
            failed_steps = []

            for i, step in enumerate(plan):
                agent = step.get("agent", "python-engineer")
                step_task = step.get("task", "")
                self.call_from_thread(self._update_spinner, f"Step {i+1}/{len(plan)}: {agent}")
                result = tool.run(task=step_task, agent_name=agent)

                # Check if step failed
                if result.startswith("Agent '") and "could not be spawned" in result:
                    failed_steps.append((i+1, agent, result))
                    results.append(f"**{agent}** (FAILED): {result[:300]}")
                else:
                    results.append(f"**{agent}**: {result[:500]}")

            self.call_from_thread(self._hide_spinner)

            # Show results with failure summary
            final = f"Orchestration complete ({len(plan)} steps):\n\n" + "\n\n".join(results)
            if failed_steps:
                final += f"\n\n**{len(failed_steps)} step(s) failed** — you can retry those steps or run the task directly."
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
            api_key = os.environ.get("OPENROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
            if not api_key:
                self.call_from_thread(self._hide_spinner)
                self.call_from_thread(self._add_system_message, "No API key.")
                return

            effort = EFFORT_LEVELS.get(self.current_effort, EFFORT_LEVELS["medium"])

            def on_tool(name, args):
                args_str = ", ".join(f"{k}={str(v)[:20]}" for k, v in list(args.items())[:2])
                self.call_from_thread(self._update_spinner, f"{name}({args_str})")

            def on_thinking(text):
                self.call_from_thread(self._update_spinner, text)

            # Try streaming first
            try:
                from openai import OpenAI
                from sago.engine.simple_executor import (
                    _discover_tools, _get_context, _detect_task_type,
                    PROMPTS, _TOOL_DESCRIPTIONS, _extract_tool_calls,
                    _load_agent_profile, _is_complex_task, _generate_plan_with_llm,
                )
                import json
                import time as _time
                import threading

                tools = _discover_tools()
                client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1", timeout=90.0)
                start_time = _time.time()

                # Detect project context (languages, frameworks)
                from sago.engine.simple_executor import _detect_project_context
                project_context = _detect_project_context()
                project_ctx = _get_context()

                # Enrich context with detected info
                if project_context["languages"]:
                    project_ctx += f"\nDetected languages: {', '.join(project_context['languages'])}"
                if project_context["frameworks"]:
                    project_ctx += f"\nDetected frameworks: {', '.join(project_context['frameworks'])}"

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
                    tool_count=len(tools),
                    tool_list=_TOOL_DESCRIPTIONS,
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

                # Inject project instructions (CLAUDE.md / .sago/instructions.md)
                try:
                    from sago.memory.project_instructions import get_project_instructions
                    pi = get_project_instructions()
                    instructions_prompt = pi.get_for_prompt()
                    if instructions_prompt:
                        system_prompt += instructions_prompt
                except Exception:
                    pass

                # Inject framework context
                if project_context["frameworks"]:
                    system_prompt += (
                        f"\n\n=== EXISTING PROJECT DETECTED ===\n"
                        f"This project uses: {', '.join(project_context['frameworks'])}\n"
                        f"Match the existing style and conventions."
                    )

                # === TODO SYSTEM: Auto-create plan for complex tasks ===
                task_plan = None
                current_todo_index = 0
                todo_tool_counts: dict[str, int] = {}

                if _is_complex_task(message) and api_key:
                    try:
                        from sago.tasks import get_task_manager, TaskStatus
                        tm = get_task_manager()
                        steps = _generate_plan_with_llm(message, client, self.current_model, _TOOL_DESCRIPTIONS)
                        task_plan = tm.create_plan(goal=message, todos=steps)
                        # Mark todos that need confirmation
                        confirm_keywords = ["confirm", "approve", "review", "check", "verify", "validate"]
                        for todo in task_plan.todos:
                            if any(kw in todo.description.lower() for kw in confirm_keywords):
                                todo.requires_confirmation = True
                                todo.confirmation_message = f"Please confirm: {todo.description}"
                        # Show plan in TUI
                        self.call_from_thread(self._add_system_message, f"📋 Created plan with {len(task_plan.todos)} steps:")
                        self.call_from_thread(self._add_system_message, tm.format_plan(task_plan))
                        # Start first todo
                        if task_plan.todos:
                            tm.start_todo(task_plan.id, task_plan.todos[0].id)
                            self.call_from_thread(self._update_spinner, f"Step 1/{len(task_plan.todos)}: {task_plan.todos[0].description[:50]}")
                    except Exception:
                        task_plan = None
                # === END TODO SYSTEM ===

                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ]

                tool_history = []
                files_created = []
                total_tokens_in = 0
                total_tokens_out = 0
                content = ""
                tool_call_counts: dict[str, int] = {}
                failed_calls: set[str] = set()

                for iteration in range(effort["max_iterations"]):
                    # Update spinner with todo progress
                    todo_info = ""
                    if task_plan and current_todo_index < len(task_plan.todos):
                        todo = task_plan.todos[current_todo_index]
                        todo_info = f" | Step {current_todo_index + 1}/{len(task_plan.todos)}: {todo.description[:40]}"
                    self.call_from_thread(self._update_spinner, f"Step {iteration+1}/{effort['max_iterations']}{todo_info}...")

                    stream = client.chat.completions.create(
                        model=self.current_model,
                        messages=messages,
                        max_tokens=effort["max_tokens"],
                        temperature=0.3,
                        stream=True,
                        stream_options={"include_usage": True},
                    )

                    content = ""
                    for chunk in stream:
                        # Get usage from final chunk
                        if hasattr(chunk, 'usage') and chunk.usage:
                            total_tokens_in = chunk.usage.prompt_tokens or 0
                            total_tokens_out = chunk.usage.completion_tokens or 0
                        if chunk.choices and chunk.choices[0].delta.content:
                            token = chunk.choices[0].delta.content
                            content += token

                    if not content and hasattr(stream, 'choices') and stream.choices:
                        if hasattr(stream.choices[0].message, 'reasoning'):
                            content = stream.choices[0].message.reasoning or ""

                    messages.append({"role": "assistant", "content": content})

                    # Check for tool calls
                    tool_calls = _extract_tool_calls(content)
                    if not tool_calls:
                        # No tool calls - mark current todo as complete
                        if task_plan and current_todo_index < len(task_plan.todos):
                            from sago.tasks import get_task_manager, TaskStatus
                            tm = get_task_manager()
                            todo = task_plan.todos[current_todo_index]
                            if todo.status == TaskStatus.IN_PROGRESS:
                                tm.complete_todo(task_plan.id, todo.id, result=content[:200])
                                self.call_from_thread(self._add_system_message, f"✅ Step {current_todo_index + 1} completed: {todo.description[:60]}")
                                current_todo_index += 1
                                # Continue to next todo
                                if current_todo_index < len(task_plan.todos):
                                    next_todo = task_plan.todos[current_todo_index]
                                    tm.start_todo(task_plan.id, next_todo.id)
                                    self.call_from_thread(self._update_spinner, f"Step {current_todo_index + 1}/{len(task_plan.todos)}: {next_todo.description[:50]}")
                                    messages.append({"role": "user", "content": (
                                        f"Moving to next step: {next_todo.description}\n"
                                        f"Execute this step now. Use the appropriate tools."
                                    )})
                                    continue
                        break

                    # Execute tools
                    results_for_llm = []
                    tools_used_in_iteration = []

                    for call_str in tool_calls:
                        try:
                            call = json.loads(call_str)
                            name = call.get("name", "")
                            args = call.get("args", {})

                            if name not in tools:
                                results_for_llm.append(f"Unknown tool: {name}")
                                continue

                            # Loop protection
                            call_key = f"{name}:{json.dumps(args, sort_keys=True)}"
                            if call_key in failed_calls:
                                results_for_llm.append(f"[SKIP] Already failed: {name} with same args")
                                continue

                            # Check permissions before execution
                            from sago.permissions import get_permission_manager, RiskLevel
                            pm = get_permission_manager()
                            risk = pm.get_risk_level(name)
                            allowed, reason = pm.check_permission(name, args, self.current_session_id)

                            if not allowed:
                                if risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                                    # For high/critical risk, ask user in TUI
                                    self.call_from_thread(self._add_system_message,
                                        f"Tool '{name}' requires approval (risk: {risk.value})")
                                    # Auto-deny for now - can add interactive prompt later
                                    results_for_llm.append(f"Permission denied: {name} requires approval")
                                    continue
                                else:
                                    results_for_llm.append(f"Permission denied: {reason}")
                                    continue

                            # No hard limits - let LLM self-regulate
                            # But detect circular behavior and warn
                            tool_call_counts[name] = tool_call_counts.get(name, 0) + 1
                            recent_calls = [f"{c['tool']}:{json.dumps(c['args'], sort_keys=True)[:50]}" for c in tool_history[-5:]]
                            if len(recent_calls) >= 3:
                                unique_recent = set(recent_calls[-3:])
                                if len(unique_recent) == 1:
                                    results_for_llm.append(
                                        f"[HINT] You've called {name} with similar args 3 times in a row. "
                                        f"If this isn't working, try a completely different approach or finish the task."
                                    )

                            self.call_from_thread(on_tool, name, args)
                            tool_instance = tools[name]()
                            result = tool_instance.run(**args)
                            result_str = str(result)[:4000]

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

                            tools_used_in_iteration.append(name)

                            display = result_str[:1500] + "..." if len(result_str) > 1500 else result_str
                            results_for_llm.append(f"[{'ERROR' if is_error else 'OK'}] {name}:\n{display}")

                        except json.JSONDecodeError:
                            results_for_llm.append("Invalid JSON format")
                        except Exception as e:
                            results_for_llm.append(f"Tool error: {e}")

                    # === TODO SYSTEM: Update progress ===
                    if task_plan:
                        try:
                            from sago.tasks import get_task_manager, TaskStatus
                            tm = get_task_manager()

                            if current_todo_index < len(task_plan.todos):
                                todo = task_plan.todos[current_todo_index]

                                # Track tools for this todo
                                if todo.id not in todo_tool_counts:
                                    todo_tool_counts[todo.id] = 0
                                todo_tool_counts[todo.id] += len(tools_used_in_iteration)

                                # Check if todo needs confirmation before proceeding
                                if todo.requires_confirmation and todo.status == TaskStatus.IN_PROGRESS:
                                    self.call_from_thread(self._add_system_message, f"⏳ Waiting for confirmation: {todo.confirmation_message or todo.description}")
                                    # Set up pause event and wait
                                    pause_event = threading.Event()
                                    pause_event.set()  # Start paused
                                    self._executor_pause_event = pause_event
                                    self.call_from_thread(self._hide_spinner)
                                    self.call_from_thread(self._add_system_message, "Type /approve to continue or /deny to skip this step")
                                    pause_event.wait()  # Block until user responds
                                    self._executor_pause_event = None
                                    self.call_from_thread(self._show_spinner)

                                # Auto-complete todo after sufficient work
                                successful_tools = [t["tool"] for t in tool_history if t.get("success") and t["tool"] in tools_used_in_iteration]
                                tools_for_todo = todo_tool_counts.get(todo.id, 0)
                                if (tools_for_todo >= 3 and len(successful_tools) >= 2) or (tools_for_todo >= 2 and len(tools_used_in_iteration) >= 1):
                                    tm.complete_todo(task_plan.id, todo.id, result=f"Completed: {', '.join(successful_tools[:3])}")
                                    self.call_from_thread(self._add_system_message, f"✅ Step {current_todo_index + 1} completed: {todo.description[:60]}")
                                    current_todo_index += 1

                                    if current_todo_index < len(task_plan.todos):
                                        next_todo = task_plan.todos[current_todo_index]
                                        tm.start_todo(task_plan.id, next_todo.id)
                                        self.call_from_thread(self._update_spinner, f"Step {current_todo_index + 1}/{len(task_plan.todos)}: {next_todo.description[:50]}")
                                        results_for_llm.append(
                                            f"\n[PROGRESS] Step completed. Next step: {next_todo.description}\n"
                                            f"Execute this step now."
                                        )
                                    else:
                                        results_for_llm.append("\n[PROGRESS] All steps completed. Provide final summary.")
                        except Exception:
                            pass
                    # === END TODO SYSTEM ===

                    combined = "\n\n".join(results_for_llm)
                    messages.append({"role": "user", "content": combined})

                # === POST-EXECUTION: Test → Fix → Retry loop ===
                if files_created:
                    self.call_from_thread(self._update_spinner, "Running tests...")
                    from sago.engine.simple_executor import _auto_install_deps, _run_tests_if_exist

                    # Auto-install dependencies
                    _auto_install_deps(files_created)

                    test_fix_attempts = 0
                    max_test_fix_attempts = 3

                    while test_fix_attempts < max_test_fix_attempts:
                        test_result = _run_tests_if_exist(files_created, tools)
                        if test_result is None:
                            break  # No tests found

                        test_passed, test_output = test_result
                        if test_passed:
                            self.call_from_thread(self._add_system_message, "✅ All tests passed!")
                            break

                        test_fix_attempts += 1
                        if test_fix_attempts >= max_test_fix_attempts:
                            self.call_from_thread(self._add_system_message, f"❌ Tests still failing after {max_test_fix_attempts} attempts")
                            break

                        self.call_from_thread(self._update_spinner, f"Tests failed (attempt {test_fix_attempts}/{max_test_fix_attempts}), fixing...")

                        # Feed test errors back to LLM for fixing
                        try:
                            fix_stream = client.chat.completions.create(
                                model=self.current_model,
                                messages=messages + [
                                    {"role": "user", "content": (
                                        f"The tests are failing. Fix the failing tests.\n\n"
                                        f"Test output:\n{test_output[:3000]}\n\n"
                                        f"Files you created: {', '.join(files_created)}\n"
                                        f"Fix the issues and make the tests pass. Use edit_file or write_file to fix."
                                    )},
                                ],
                                max_tokens=effort["max_tokens"],
                                temperature=0.3,
                                stream=True,
                                stream_options={"include_usage": True},
                            )
                            fix_content = ""
                            for chunk in fix_stream:
                                if chunk.choices and chunk.choices[0].delta.content:
                                    fix_content += chunk.choices[0].delta.content

                            if fix_content:
                                messages.append({"role": "assistant", "content": fix_content})
                                fix_tool_calls = _extract_tool_calls(fix_content)
                                for call_str in fix_tool_calls:
                                    try:
                                        call = json.loads(call_str)
                                        name = call.get("name", "")
                                        args = call.get("args", {})
                                        if name in tools:
                                            tool_instance = tools[name]()
                                            result = tool_instance.run(**args)
                                            result_str = str(result)[:4000]
                                            is_error = result_str.lower().startswith("error")
                                            tool_history.append({
                                                "tool": name,
                                                "args": args,
                                                "result": result_str[:500],
                                                "success": not is_error,
                                            })
                                            if name == "write_file" and not is_error:
                                                fp = args.get("file_path", "")
                                                if fp and fp not in files_created:
                                                    files_created.append(fp)
                                    except Exception:
                                        pass
                        except Exception:
                            break
                # === END TEST → FIX LOOP ===

                # Final todo cleanup
                if task_plan:
                    try:
                        from sago.tasks import get_task_manager, TaskStatus
                        tm = get_task_manager()
                        for idx in range(current_todo_index, len(task_plan.todos)):
                            todo = task_plan.todos[idx]
                            if todo.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS):
                                tm.complete_todo(task_plan.id, todo.id, result="Task completed")
                        self.call_from_thread(self._add_system_message, tm.format_plan(task_plan))
                    except Exception:
                        pass

                elapsed = _time.time() - start_time

                self.call_from_thread(self._hide_spinner)

                for tc in tool_history:
                    self.call_from_thread(
                        self._add_tool_call,
                        tc.get("tool", ""),
                        tc.get("args", {}),
                        tc.get("result", ""),
                        tc.get("success", True),
                    )

                self.call_from_thread(
                    self._add_summary,
                    tool_history,
                    content,
                    elapsed,
                    {"input": total_tokens_in, "output": total_tokens_out},
                )

                # Show change summary if files were modified
                if files_created:
                    try:
                        from sago.memory.change_tracker import get_change_tracker
                        tracker = get_change_tracker()
                        change_summary = tracker.get_diff_summary()
                        if change_summary and "No changes" not in change_summary:
                            self.call_from_thread(self._add_system_message, f"📝 {change_summary}")
                    except Exception:
                        pass

                # Record learning
                try:
                    from sago.learning import get_learning_store
                    ls = get_learning_store()
                    successful_tools = [t["tool"] for t in tool_history if t.get("success")]
                    if successful_tools:
                        ls.record_success(task_type, successful_tools, f"Used {', '.join(set(successful_tools[:5]))}")
                    for tool_record in tool_history:
                        ls.record_tool_effectiveness(tool_record["tool"], tool_record.get("success", False))
                except Exception:
                    pass

                self.call_from_thread(self._add_assistant_message, content)

            except ImportError:
                # Fallback to non-streaming
                from sago.engine.simple_executor import execute_agent_task

                def on_todo_created(plan):
                    self.call_from_thread(self._add_system_message, f"📋 Created plan with {len(plan.todos)} steps:")
                    from sago.tasks import get_task_manager
                    tm = get_task_manager()
                    self.call_from_thread(self._add_system_message, tm.format_plan(plan))

                def on_todo_update(plan, todo_index, status):
                    if todo_index < len(plan.todos):
                        todo = plan.todos[todo_index]
                        if status == "started":
                            self.call_from_thread(self._update_spinner, f"Step {todo_index + 1}/{len(plan.todos)}: {todo.description[:50]}")
                        elif status == "completed":
                            self.call_from_thread(self._add_system_message, f"✅ Step {todo_index + 1} completed: {todo.description[:60]}")

                result = execute_agent_task(
                    task=message,
                    agent_role=self.current_agent.replace("-", " ").title(),
                    api_key=api_key,
                    model=self.current_model,
                    max_tokens=effort["max_tokens"],
                    max_iterations=effort["max_iterations"],
                    on_tool_call=on_tool,
                    on_thinking=on_thinking,
                    on_todo_created=on_todo_created,
                    on_todo_update=on_todo_update,
                )

                # Show task plan if created
                if result.get("task_plan"):
                    from sago.tasks import get_task_manager
                    tm = get_task_manager()
                    plan = tm.get_active_plan()
                    if plan:
                        self.call_from_thread(self._add_system_message, tm.format_plan(plan))

                self.call_from_thread(self._hide_spinner)

                for tc in result.get("tool_calls", []):
                    self.call_from_thread(
                        self._add_tool_call,
                        tc.get("tool", ""),
                        tc.get("args", {}),
                        tc.get("result", ""),
                        tc.get("success", True),
                    )

                self.call_from_thread(
                    self._add_summary,
                    result.get("tool_calls", []),
                    result.get("output", ""),
                    result.get("elapsed", 0),
                    result.get("tokens", {}),
                )

                output = result.get("output", "No response")
                self.call_from_thread(self._add_assistant_message, output)

        except Exception as e:
            self.call_from_thread(self._hide_spinner)
            self.call_from_thread(self._add_system_message, f"Error: {e}")
        finally:
            self.is_thinking = False

    def action_clear_chat(self) -> None:
        self.query_one("#messages").remove_children()
        self.messages.clear()
        self._add_system_message("Cleared.")


def main():
    SagoApp().run()
