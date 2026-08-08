"""Sago TUI - Clean Terminal Interface."""

from __future__ import annotations

import os
import re
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
    "/agents": "List agents (or /a <filter>)",
    "/clear": "Clear chat",
    "/status": "System status",
    "/export": "Export to markdown",
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
    "/save": "Save context",
    "/load": "Load context",
    "/version": "Show version",
    "/exit": "Quit",
}

MODELS = [
    "openrouter/free",
    "openrouter/auto",
    "anthropic/claude-3.5-sonnet",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "google/gemini-2.0-flash",
    "google/gemini-2.0-flash-lite",
    "meta-llama/llama-3.1-8b-instruct:free",
    "meta-llama/llama-3.1-70b-instruct",
    "mistralai/mistral-7b-instruct:free",
    "qwen/qwen-2-72b-instruct",
]

PROVIDERS = ["openrouter", "openai", "anthropic", "gemini", "ollama"]
EFFORT_LEVELS = ["low", "medium", "high"]

SPINNERS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class Spinner(Static):
    """Animated spinner widget."""

    def __init__(self, **kwargs) -> None:
        self.frame = 0
        super().__init__(**kwargs)

    def render(self) -> str:
        return f" {SPINNERS[self.frame % len(SPINNERS)]} Thinking..."

    def advance(self) -> None:
        self.frame += 1
        self.refresh()


class SagoApp(App):
    """Clean Sago TUI."""

    CSS = """
    Screen {
        background: #0d1117;
    }

    #messages {
        height: 1fr;
        padding: 0 2;
        overflow-y: auto;
    }

    .msg-user {
        color: #58a6ff;
        padding: 0 0 1 0;
    }

    .msg-assistant {
        color: #c9d1d9;
        padding: 0 0 1 0;
    }

    .msg-system {
        color: #8b949e;
        text-style: italic;
        padding: 0 0 1 0;
    }

    .msg-meta {
        color: #8b949e;
        text-style: italic;
        padding: 0 0 1 0;
    }

    #input-area {
        height: auto;
        padding: 0 2 1 2;
        background: #161b22;
        border-top: solid #30363d;
    }

    #msg-input {
        background: #0d1117;
        border: tall #30363d;
        color: #c9d1d9;
        margin: 0;
    }

    #msg-input:focus {
        border: tall #58a6ff;
    }

    #suggestions {
        display: none;
        max-height: 14;
        overflow-y: auto;
        background: #161b22;
        border-top: solid #30363d;
        padding: 0 2;
    }

    #suggestions.visible {
        display: block;
    }

    .suggestion-item {
        color: #c9d1d9;
        padding: 0 0;
    }

    .suggestion-item.highlighted {
        color: #ffffff;
        background: #1f6feb;
    }

    .tool-call {
        color: #58a6ff;
        padding: 0 0 1 0;
    }

    .code-block {
        background: #161b22;
        color: #c9d1d9;
        padding: 1;
        margin: 0 0 1 0;
        border: tall #30363d;
    }

    .spinner {
        color: #58a6ff;
        text-style: italic;
        padding: 0 0 1 0;
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
    messages: reactive[list[dict]] = reactive(list)
    show_suggestions: reactive[bool] = reactive(False)
    suggestion_items: reactive[list[str]] = reactive(list)
    suggestion_values: reactive[list[str]] = reactive(list)
    suggestion_index: reactive[int] = reactive(0)
    is_thinking: reactive[bool] = reactive(False)

    def compose(self) -> ComposeResult:
        yield ScrollableContainer(id="messages")
        yield Vertical(id="suggestions")
        with Vertical(id="input-area"):
            yield Input(
                placeholder="/, @, # for autocomplete",
                id="msg-input",
            )

    def on_mount(self) -> None:
        self._add_system_message("Sago v0.1.0 — /help for commands")
        self.query_one("#msg-input").focus()

    @on(Input.Changed, "#msg-input")
    def on_input_changed(self, event: Input.Changed) -> None:
        value = event.value
        if value.startswith("/"):
            self._show_command_suggestions(value)
        elif value.startswith("@"):
            self._show_agent_suggestions(value)
        elif value.startswith("#"):
            self._show_file_suggestions(value)
        else:
            self._hide_suggestions()

    @on(Input.Submitted, "#msg-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        message = event.value.strip()
        if not message:
            return
        event.input.value = ""
        self._hide_suggestions()
        if message.startswith("/"):
            self._handle_command(message)
            return
        self._add_user_message(message)
        self._process_message(message)

    def on_key(self, event) -> None:
        if not self.show_suggestions:
            return
        if event.key == "down":
            event.prevent_default()
            self._move_selection(1)
        elif event.key == "up":
            event.prevent_default()
            self._move_selection(-1)
        elif event.key in ("right", "tab"):
            event.prevent_default()
            self._select_current()

    def _move_selection(self, delta: int) -> None:
        if not self.suggestion_items:
            return
        self.suggestion_index = (self.suggestion_index + delta) % len(self.suggestion_items)
        self._update_highlight()

    def _select_current(self) -> None:
        if not self.suggestion_values:
            return
        value = self.suggestion_values[self.suggestion_index]
        inp = self.query_one("#msg-input")
        inp.value = value + " "
        inp.cursor_position = len(inp.value)
        self._hide_suggestions()

    def _update_highlight(self) -> None:
        container = self.query_one("#suggestions")
        for i, child in enumerate(container.children):
            if i == self.suggestion_index:
                child.add_class("highlighted")
            else:
                child.remove_class("highlighted")

    def _show_command_suggestions(self, prefix: str) -> None:
        matches = [(cmd, desc) for cmd, desc in COMMANDS.items() if cmd.startswith(prefix.lower())]
        if matches:
            items = [f"{cmd} — {desc}" for cmd, desc in matches]
            values = [cmd for cmd, _ in matches]
            self._show_suggestions(items, values)
        else:
            self._hide_suggestions()

    def _show_agent_suggestions(self, prefix: str) -> None:
        try:
            from sago.agents.registry import list_agents
            agents = list_agents()
            search = prefix[1:].lower()
            matches = [a["name"] for a in agents if search in a["name"].lower()]
            if matches:
                items = [f"@{name}" for name in matches[:15]]
                values = [name for name in matches[:15]]
                self._show_suggestions(items, values)
            else:
                self._hide_suggestions()
        except Exception:
            self._hide_suggestions()

    def _show_file_suggestions(self, prefix: str) -> None:
        search = prefix[1:].lower()
        items, values = [], []
        try:
            for p in sorted(Path.cwd().iterdir()):
                if search in p.name.lower():
                    items.append(f"# {p.name}/" if p.is_dir() else f"# {p.name}")
                    values.append(p.name + "/" if p.is_dir() else p.name)
                if len(items) >= 15:
                    break
            if items:
                self._show_suggestions(items, values)
            else:
                self._hide_suggestions()
        except Exception:
            self._hide_suggestions()

    def _show_suggestions(self, items: list[str], values: list[str]) -> None:
        self.suggestion_items = items
        self.suggestion_values = values
        self.suggestion_index = 0
        self.show_suggestions = True
        container = self.query_one("#suggestions")
        container.remove_children()
        container.add_class("visible")
        for i, item in enumerate(items):
            cls = "suggestion-item highlighted" if i == 0 else "suggestion-item"
            container.mount(Static(item, classes=cls))

    def _hide_suggestions(self) -> None:
        self.show_suggestions = False
        self.suggestion_items = []
        self.suggestion_values = []
        container = self.query_one("#suggestions")
        container.remove_children()
        container.remove_class("visible")

    def action_dismiss_suggestions(self) -> None:
        if self.show_suggestions:
            self._hide_suggestions()
        else:
            self.exit()

    def _show_spinner(self) -> None:
        container = self.query_one("#messages")
        spinner = Spinner(classes="spinner")
        container.mount(spinner)
        container.scroll_end()
        self.spinner_widget = spinner

    def _hide_spinner(self) -> None:
        if hasattr(self, "spinner_widget") and self.spinner_widget:
            try:
                self.spinner_widget.remove()
            except Exception:
                pass
            self.spinner_widget = None

    def _handle_command(self, command: str) -> None:
        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        handlers = {
            "/help": lambda: self._show_help(),
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
            "/version": lambda: self._add_system_message("Sago v0.1.0"),
            "/exit": lambda: self.exit(),
            "/q": lambda: self.exit(),
            "/quit": lambda: self.exit(),
        }

        handler = handlers.get(cmd)
        if handler:
            handler()
        else:
            self._add_system_message(f"Unknown: {cmd}")

    def _show_help(self) -> None:
        self._add_system_message("""Commands:
  /help             Show this help
  /agents [filter]  List agents
  /clear            Clear chat
  /status           System status
  /export           Export to markdown
  /sessions         List sessions
  /session <id>     Switch session
  /history          Chat history
  /model [name]     Change model
  /provider [name]  Change provider
  /effort <level>   Set effort
  /cost             Token usage
  /compact          Summarize
  /retry            Retry last
  /reset            Reset
  /save [name]      Save
  /load <name>      Load
  /version          Version
  /exit             Quit""")

    def _show_agents(self, filter: str = "") -> None:
        try:
            from sago.agents.registry import list_agents
            agents = list_agents()
            if filter:
                filtered = [a for a in agents if filter.lower() in a["name"].lower()]
                lines = "\n".join(f"  {a['name']}" for a in filtered[:30])
                self._add_system_message(f"Agents '{filter}' ({len(filtered)}):\n{lines}")
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
            agents = list_agents()
            self._add_system_message(
                f"Sago v0.1.0 | {len(agents)} agents | {self.current_model} | {len(self.messages)} msgs"
            )
        except Exception:
            self._add_system_message("Sago v0.1.0")

    def _show_sessions(self) -> None:
        self._add_system_message("Sessions: coming soon")

    def _switch_session(self, sid: str) -> None:
        self._add_system_message(f"Session: {sid}" if sid else "Usage: /session <id>")

    def _show_history(self) -> None:
        if self.messages:
            lines = [f"  [{m.get('role','?')}] {m.get('content','')[:50]}" for m in self.messages[-10:]]
            self._add_system_message("History:\n" + "\n".join(lines))
        else:
            self._add_system_message("No history")

    def _change_model(self, model: str) -> None:
        if not model:
            lines = "\n".join(f"  {m}" for m in MODELS)
            self._add_system_message(f"Current: {self.current_model}\n{lines}")
            return
        for m in MODELS:
            if model.lower() in m.lower():
                self.current_model = m
                self._add_system_message(f"Model: {m}")
                return
        self.current_model = model
        self._add_system_message(f"Model: {model}")

    def _change_provider(self, p: str) -> None:
        if not p:
            self._add_system_message(f"Providers: {', '.join(PROVIDERS)}")
            return
        for prov in PROVIDERS:
            if p.lower() in prov.lower():
                self._add_system_message(f"Provider: {prov}")
                return
        self._add_system_message(f"Unknown: {p}")

    def _set_effort(self, level: str) -> None:
        if not level:
            self._add_system_message(f"Effort: {', '.join(EFFORT_LEVELS)}")
        elif level.lower() in EFFORT_LEVELS:
            self._add_system_message(f"Effort: {level}")
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

    def _add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})
        self.query_one("#messages").mount(Static(f"> {content}", classes="msg-user"))
        self.query_one("#messages").scroll_end()

    def _add_assistant_message(self, content: str, meta: str = "") -> None:
        self.messages.append({"role": "assistant", "content": content})
        container = self.query_one("#messages")
        if meta:
            container.mount(Static(meta, classes="msg-meta"))
        code_blocks = re.findall(r"```(\w+)?\n(.*?)```", content, re.DOTALL)
        parts = re.split(r"```\w*\n.*?```", content, flags=re.DOTALL)
        for i, part in enumerate(parts):
            part = part.strip()
            if part:
                container.mount(Static(part, classes="msg-assistant"))
            if i < len(code_blocks):
                lang, code = code_blocks[i]
                try:
                    syntax = Syntax(code.strip(), lang or "text", theme="monokai", word_wrap=True)
                    container.mount(Static(syntax, classes="code-block"))
                except Exception:
                    container.mount(Static(code.strip(), classes="code-block"))
        container.scroll_end()

    def _add_system_message(self, content: str) -> None:
        self.query_one("#messages").mount(Static(content, classes="msg-system"))
        self.query_one("#messages").scroll_end()

    @work(thread=True)
    def _process_message(self, message: str) -> None:
        self.is_thinking = True
        self.call_from_thread(self._show_spinner)
        try:
            api_key = os.environ.get("OPENROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
            if not api_key:
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
