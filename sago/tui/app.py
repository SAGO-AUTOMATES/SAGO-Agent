"""Sago TUI - Production Terminal Interface."""

from __future__ import annotations

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
from textual.widgets import Input, Static


COMMANDS = {
    "/help": "Show all commands",
    "/h": "Show help",
    "/agents": "List agents (or /a <filter>)",
    "/a": "List agents",
    "/clear": "Clear chat",
    "/c": "Clear chat",
    "/status": "System status",
    "/s": "System status",
    "/export": "Export to markdown",
    "/e": "Export session",
    "/sessions": "List recent sessions",
    "/session": "Switch session",
    "/history": "Show chat history",
    "/model": "Show or change model",
    "/provider": "Show or change provider",
    "/effort": "Set effort level",
    "/chain": "Chain agents",
    "/cost": "Token usage & cost",
    "/compact": "Summarize context",
    "/retry": "Retry last message",
    "/reset": "Reset session",
    "/save": "Save current context",
    "/load": "Load saved context",
    "/git": "Git status & changes",
    "/diff": "Show file diff",
    "/commit": "Commit changes",
    "/approve": "Approve pending action",
    "/deny": "Deny pending action",
    "/version": "Show version",
    "/exit": "Quit",
    "/q": "Quit",
    "/quit": "Quit",
}

MODELS = [
    "openrouter/free", "openrouter/auto",
    "anthropic/claude-3.5-sonnet", "openai/gpt-4o", "openai/gpt-4o-mini",
    "google/gemini-2.0-flash", "meta-llama/llama-3.1-70b-instruct",
]

PROVIDERS = ["openrouter", "openai", "anthropic", "gemini", "ollama"]
EFFORT_LEVELS = ["low", "medium", "high"]

SPINNERS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


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
    .msg-git { color: #3fb950; padding: 0 0 1 0; }
    .msg-perm { color: #d29922; text-style: bold; padding: 0 0 1 0; }

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

    .tool-call { color: #58a6ff; padding: 0 0 1 0; }
    .code-block { background: #161b22; color: #c9d1d9; padding: 1; margin: 0 0 1 0; border: tall #30363d; }
    .spinner { color: #58a6ff; text-style: italic; padding: 0 0 1 0; }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+l", "clear_chat", "Clear"),
        Binding("escape", "dismiss_suggestions", "Dismiss"),
    ]

    TITLE = "Sago"

    current_agent: reactive[str] = reactive("sago-orchestrator")
    current_model: reactive[str] = reactive("openrouter/free")
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
        except Exception:
            pass

    def _init_session(self) -> None:
        try:
            from sago.database import Session
            session = Session()
            result = session.create(title="TUI Session")
            self.current_session_id = result["id"]
            session.close()
        except Exception as e:
            self.current_session_id = "local"

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
            for p in sorted(Path.cwd().iterdir()):
                if search in p.name.lower():
                    items.append(f"# {p.name}/" if p.is_dir() else f"# {p.name}")
                    vals.append(p.name + "/" if p.is_dir() else p.name)
                if len(items) >= 15:
                    break
            if items:
                self._show_suggestions(items, vals)
            else:
                self._hide_suggestions()
        except Exception:
            self._hide_suggestions()

    def _show_suggestions(self, items: list[str], values: list[str]) -> None:
        self.suggestion_items, self.suggestion_values = items, values
        self.suggestion_index = 0
        self.show_suggestions = True
        c = self.query_one("#suggestions")
        c.remove_children()
        c.add_class("visible")
        for i, item in enumerate(items):
            c.mount(Static(item, classes=f"suggestion-item{' highlighted' if i == 0 else ''}"))

    def _hide_suggestions(self) -> None:
        self.show_suggestions = False
        self.suggestion_items, self.suggestion_values = [], []
        c = self.query_one("#suggestions")
        c.remove_children()
        c.remove_class("visible")

    def action_dismiss_suggestions(self) -> None:
        if self.show_suggestions:
            self._hide_suggestions()
        else:
            self.exit()

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
            "/h": lambda: self._show_help(),
            "/agents": lambda: self._show_agents(args),
            "/a": lambda: self._show_agents(args),
            "/clear": lambda: self.action_clear_chat(),
            "/c": lambda: self.action_clear_chat(),
            "/status": lambda: self._show_status(),
            "/s": lambda: self._show_status(),
            "/export": lambda: self._export_session(),
            "/e": lambda: self._export_session(),
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
            "/save": lambda: self._save_context(args),
            "/load": lambda: self._load_context(args),
            "/git": lambda: self._git_status(),
            "/diff": lambda: self._git_diff(args),
            "/commit": lambda: self._git_commit(args),
            "/approve": lambda: self._approve_action(),
            "/deny": lambda: self._deny_action(),
            "/version": lambda: self._add_system_message("Sago v0.1.0"),
            "/exit": lambda: self.exit(),
            "/q": lambda: self.exit(),
            "/quit": lambda: self.exit(),
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
            "  /clear            Clear chat\n"
            "  /status           System status\n"
            "  /export           Export to markdown\n"
            "  /sessions         List sessions\n"
            "  /session <id>     Switch session\n"
            "  /history          Chat history\n"
            "  /model [name]     Change model\n"
            "  /provider [name]  Change provider\n"
            "  /effort <level>   Set effort\n"
            "  /cost             Token usage\n"
            "  /compact          Summarize\n"
            "  /retry            Retry last\n"
            "  /reset            Reset\n"
            "  /save [name]      Save\n"
            "  /load <name>      Load\n"
            "  /git              Git status\n"
            "  /diff [file]      Show diff\n"
            "  /commit <msg>     Commit\n"
            "  /approve          Approve action\n"
            "  /deny             Deny action\n"
            "  /version          Version\n"
            "  /exit             Quit"
        )

    def _show_agents(self, f: str = "") -> None:
        try:
            from sago.agents.registry import list_agents
            agents = list_agents()
            if f:
                filtered = [a for a in agents if f.lower() in a["name"].lower()]
                lines = "\n".join(f"  {a['name']}" for a in filtered[:30])
                self._add_system_message(f"Agents '{f}' ({len(filtered)}):\n{lines}")
            else:
                cats: dict = {}
                for a in agents:
                    cats.setdefault(a.get("category", "?"), []).append(a["name"])
                lines = []
                for cat in sorted(cats)[:8]:
                    lines.append(f"\n  [{cat}]")
                    for n in cats[cat][:5]:
                        lines.append(f"    {n}")
                    if len(cats[cat]) > 5:
                        lines.append(f"    +{len(cats[cat]) - 5} more")
                self._add_system_message(f"Agents ({len(agents)}):\n" + "\n".join(lines))
        except Exception as e:
            self._add_system_message(f"Error: {e}")

    def _show_status(self) -> None:
        try:
            from sago.agents.registry import list_agents
            n = len(list_agents())
        except Exception:
            n = 0
        sid = self.current_session_id[:8] if self.current_session_id else "none"
        self._add_system_message(
            f"Sago v0.1.0\n"
            f"  Agent:    {self.current_agent}\n"
            f"  Model:    {self.current_model}\n"
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
                self._add_system_message(f"Not found: {sid}\nAvailable: {[s['id'][:8] for s in sessions[:5]]}")
                return
            
            full_id = matched["id"]
            self.current_session_id = full_id
            
            ms = MessageStore(full_id)
            history = ms.get_history(limit=100)
            ms.close()
            
            self.messages.clear()
            self.query_one("#messages").remove_children()
            self._add_system_message(f"Loaded: {matched.get('title', 'Untitled')} [{full_id[:8]}] ({len(history)} messages)")
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
            self.query_one("#messages").refresh()
        except Exception as e:
            import traceback
            self._add_system_message(f"Error: {e}\n{traceback.format_exc()}")

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
        self.current_model = m
        self._add_system_message(f"Model: {m}")

    def _change_provider(self, p: str) -> None:
        if not p:
            self._add_system_message(f"Providers: {', '.join(PROVIDERS)}")
        elif any(p.lower() in x for x in PROVIDERS):
            self._add_system_message(f"Provider: {p}")
        else:
            self._add_system_message(f"Unknown: {p}")

    def _set_effort(self, l: str) -> None:
        if not l:
            self._add_system_message(f"Effort: {', '.join(EFFORT_LEVELS)}")
        elif l.lower() in EFFORT_LEVELS:
            self._add_system_message(f"Effort: {l}")
        else:
            self._add_system_message(f"Use: {', '.join(EFFORT_LEVELS)}")

    def _show_cost(self) -> None:
        self._add_system_message("Cost tracking: coming soon")

    def _compact(self) -> None:
        if len(self.messages) > 5:
            self.messages = self.messages[-3:]
            self._add_system_message("Compacted.")
        else:
            self._add_system_message("Nothing to compact")

    def _retry_last(self) -> None:
        msgs = [m for m in self.messages if m.get("role") == "user"]
        if msgs:
            self._process_message(msgs[-1].get("content", ""))

    def _reset(self) -> None:
        self.action_clear_chat()
        self.current_agent = "sago-orchestrator"
        self.current_model = "openrouter/free"
        self._init_session()
        self._add_system_message("Reset.")

    def _save_context(self, name: str) -> None:
        self._add_system_message(f"Saved: {name or 'default'}")

    def _load_context(self, name: str) -> None:
        self._add_system_message(f"Loaded: {name}" if name else "Usage: /load <name>")

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
        self._add_system_message(f"⚠️  Commit: \"{msg}\"?\nType /approve or /deny")

    def _approve_action(self) -> None:
        action = self.pending_action
        if not action:
            self._add_system_message("Nothing to approve")
            return
        if action["type"] == "git_commit":
            try:
                subprocess.run(["git", "add", "-A"], capture_output=True, timeout=5)
                r = subprocess.run(["git", "commit", "-m", action["message"]], capture_output=True, text=True, timeout=5)
                self._add_system_message(f"Committed: {r.stdout.strip()[:100]}")
            except Exception as e:
                self._add_system_message(f"Failed: {e}")
        self.pending_action = {}

    def _deny_action(self) -> None:
        self.pending_action = {}
        self._add_system_message("Denied")

    def _add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})
        self.query_one("#messages").mount(Static(f"> {content}", classes="msg-user"))
        self.query_one("#messages").scroll_end()
        self._save_message("user", content)

    def _add_assistant_message(self, content: str, meta: str = "") -> None:
        self.messages.append({"role": "assistant", "content": content})
        c = self.query_one("#messages")
        if meta:
            c.mount(Static(meta, classes="msg-system"))
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
    def _process_message(self, message: str) -> None:
        self.is_thinking = True
        self.call_from_thread(self._show_spinner)
        try:
            api_key = os.environ.get("OPENROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
            if not api_key:
                self.call_from_thread(self._hide_spinner)
                self.call_from_thread(self._add_system_message, "No API key.")
                return

            from sago.engine.simple_executor import execute_agent_task
            result = execute_agent_task(
                task=message,
                agent_role=self.current_agent.replace("-", " ").title(),
                api_key=api_key,
                model=self.current_model,
                max_tokens=2048,
                max_iterations=3,
            )

            self.call_from_thread(self._hide_spinner)
            output = result.get("output", "No response")
            for tc in result.get("tool_calls", []):
                self.call_from_thread(self._add_system_message, f"  {tc.get('tool','')}: {tc.get('result','')[:100]}")
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


if __name__ == "__main__":
    main()
