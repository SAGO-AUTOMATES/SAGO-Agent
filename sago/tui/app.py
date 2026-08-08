"""Sago TUI - Clean Terminal Interface with Autocomplete."""

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
    "/help": "Show this help",
    "/h": "Show help",
    "/agents": "List all agents",
    "/a": "List agents",
    "/clear": "Clear chat",
    "/c": "Clear chat",
    "/status": "System status",
    "/s": "System status",
    "/export": "Export session to markdown",
    "/e": "Export session",
    "/sessions": "List recent sessions",
    "/session": "Switch session",
    "/history": "Show chat history",
    "/model": "Show current model",
    "/provider": "Show current provider",
    "/version": "Show version",
    "/exit": "Quit",
    "/q": "Quit",
    "/quit": "Quit",
}


class SuggestionList(Static):
    """Popup suggestion list."""

    def __init__(self, items: list[str], **kwargs) -> None:
        self.items = items
        self.selected = 0
        super().__init__(**kwargs)

    def render(self) -> str:
        lines = []
        for i, item in enumerate(self.items[:10]):
            if i == self.selected:
                lines.append(f"▸ {item}")
            else:
                lines.append(f"  {item}")
        return "\n".join(lines)


class SagoApp(App):
    """Clean Sago TUI with autocomplete."""

    CSS = """
    Screen {
        background: #0d1117;
    }

    #messages {
        height: 1fr;
        padding: 1 2;
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
        padding: 1 2;
        background: #161b22;
        border: tall #30363d;
        margin: 0 1;
    }

    #msg-input {
        background: #0d1117;
        border: tall #30363d;
        color: #c9d1d9;
    }

    #msg-input:focus {
        border: tall #58a6ff;
    }

    #suggestions {
        display: none;
        max-height: 12;
        overflow-y: auto;
        background: #161b22;
        border: tall #30363d;
        margin: 0 1;
        padding: 1;
    }

    #suggestions.visible {
        display: block;
    }

    .suggestion-item {
        color: #c9d1d9;
        padding: 0 1;
    }

    .suggestion-item.selected {
        color: #58a6ff;
        text-style: bold;
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

    .error {
        color: #f85149;
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
    messages: reactive[list[dict]] = reactive(list)
    show_suggestions: reactive[bool] = reactive(False)
    suggestion_items: reactive[list[str]] = reactive(list)
    suggestion_index: reactive[int] = reactive(0)
    suggestion_mode: reactive[str] = reactive("")  # "command", "agent", "file"

    def compose(self) -> ComposeResult:
        yield ScrollableContainer(id="messages")
        yield Vertical(id="suggestions")
        with Vertical(id="input-area"):
            yield Input(
                placeholder="Message... (/, @, # for autocomplete)",
                id="msg-input",
            )

    def on_mount(self) -> None:
        self._add_system_message("Sago v0.1.0 — /help for commands, @ for agents, # for files")
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

    def _show_command_suggestions(self, prefix: str) -> None:
        matches = [cmd for cmd in COMMANDS if cmd.startswith(prefix.lower())]
        if matches:
            items = [f"{cmd} — {COMMANDS[cmd]}" for cmd in matches]
            self._show_suggestions(items, "command")
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
                self._show_suggestions(items, "agent")
            else:
                self._hide_suggestions()
        except Exception:
            self._hide_suggestions()

    def _show_file_suggestions(self, prefix: str) -> None:
        search = prefix[1:].lower()
        items = []

        try:
            cwd = Path.cwd()
            for p in sorted(cwd.iterdir()):
                if search in p.name.lower():
                    if p.is_dir():
                        items.append(f"# {p.name}/")
                    else:
                        items.append(f"# {p.name}")
                if len(items) >= 15:
                    break

            if items:
                self._show_suggestions(items, "file")
            else:
                self._hide_suggestions()
        except Exception:
            self._hide_suggestions()

    def _show_suggestions(self, items: list[str], mode: str) -> None:
        self.suggestion_items = items
        self.suggestion_mode = mode
        self.suggestion_index = 0
        self.show_suggestions = True

        container = self.query_one("#suggestions")
        container.remove_children()
        container.add_class("visible")
        for i, item in enumerate(items):
            cls = "suggestion-item selected" if i == 0 else "suggestion-item"
            container.mount(Static(item, classes=cls))

    def _hide_suggestions(self) -> None:
        self.show_suggestions = False
        self.suggestion_items = []
        container = self.query_one("#suggestions")
        container.remove_children()
        container.remove_class("visible")

    def action_dismiss_suggestions(self) -> None:
        if self.show_suggestions:
            self._hide_suggestions()
        else:
            self.exit()

    def _handle_command(self, command: str) -> None:
        cmd = command.lower().strip()

        if cmd in ("/help", "/h"):
            lines = "\n".join(f"  {cmd}" for cmd in sorted(COMMANDS.keys()))
            self._add_system_message(f"Commands:\n{lines}")
        elif cmd in ("/agents", "/a"):
            self._show_agents()
        elif cmd in ("/clear", "/c"):
            self.action_clear_chat()
        elif cmd in ("/status", "/s"):
            self._show_status()
        elif cmd in ("/export", "/e"):
            self._export_session()
        elif cmd in ("/sessions",):
            self._show_sessions()
        elif cmd in ("/session",):
            self._add_system_message("Usage: /session <id>")
        elif cmd in ("/history",):
            self._show_history()
        elif cmd in ("/model",):
            self._add_system_message("Model: openrouter/free")
        elif cmd in ("/provider",):
            self._add_system_message("Provider: OpenRouter")
        elif cmd in ("/version",):
            self._add_system_message("Sago v0.1.0")
        elif cmd in ("/exit", "/q", "/quit"):
            self.exit()
        else:
            self._add_system_message(f"Unknown command: {cmd}")

    def _show_agents(self) -> None:
        try:
            from sago.agents.registry import list_agents
            agents = list_agents()
            lines = "\n".join(f"  {a['name']}" for a in agents[:30])
            self._add_system_message(f"Agents ({len(agents)} total):\n{lines}")
        except Exception as e:
            self._add_system_message(f"Error: {e}")

    def _show_status(self) -> None:
        try:
            from sago.agents.registry import list_agents
            agents = list_agents()
            self._add_system_message(
                f"Sago v0.1.0\n"
                f"  Agents: {len(agents)}\n"
                f"  Model: openrouter/free\n"
                f"  Messages: {len(self.messages)}"
            )
        except Exception as e:
            self._add_system_message(f"Error: {e}")

    def _show_sessions(self) -> None:
        try:
            from sago.database import Database
            db = Database()
            sessions = db.get_recent_sessions(limit=10)
            if sessions:
                lines = "\n".join(
                    f"  {s.get('id', '?')[:8]} — {s.get('title', 'Untitled')}"
                    for s in sessions
                )
                self._add_system_message(f"Recent sessions:\n{lines}")
            else:
                self._add_system_message("No sessions found")
        except Exception as e:
            self._add_system_message(f"Sessions: {e}")

    def _show_history(self) -> None:
        if self.messages:
            lines = []
            for msg in self.messages[-10:]:
                role = msg.get("role", "?")
                content = msg.get("content", "")[:60]
                lines.append(f"  [{role}] {content}")
            self._add_system_message("Recent messages:\n" + "\n".join(lines))
        else:
            self._add_system_message("No history yet")

    def _export_session(self) -> None:
        export = "# Sago Session\n\n"
        for msg in self.messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            export += f"[{role.upper()}]\n{content}\n\n"
        filename = f"sago_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(filename, "w") as f:
            f.write(export)
        self._add_system_message(f"Exported to {filename}")

    def _add_user_message(self, content: str) -> None:
        msg = {"role": "user", "content": content}
        self.messages.append(msg)
        container = self.query_one("#messages")
        container.mount(Static(f"> {content}", classes="msg-user"))
        container.scroll_end()

    def _add_assistant_message(self, content: str, meta: str = "") -> None:
        msg = {"role": "assistant", "content": content}
        self.messages.append(msg)
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
                lang = lang or "text"
                try:
                    syntax = Syntax(code.strip(), lang, theme="monokai", word_wrap=True)
                    container.mount(Static(syntax, classes="code-block"))
                except Exception:
                    container.mount(Static(code.strip(), classes="code-block"))
        container.scroll_end()

    def _add_system_message(self, content: str) -> None:
        container = self.query_one("#messages")
        container.mount(Static(content, classes="msg-system"))
        container.scroll_end()

    def _add_tool_message(self, tool: str, result: str) -> None:
        container = self.query_one("#messages")
        container.mount(Static(f"  {tool}: {result[:120]}", classes="tool-call"))
        container.scroll_end()

    @work(thread=True)
    def _process_message(self, message: str) -> None:
        import os
        try:
            api_key = os.environ.get("OPENROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
            if not api_key:
                self.call_from_thread(self._add_system_message, "No API key. Set OPENROUTER_API_KEY.")
                return

            from sago.engine.simple_executor import execute_agent_task

            agent_role = self.current_agent.replace("-", " ").title()
            result = execute_agent_task(
                task=message,
                agent_role=agent_role,
                api_key=api_key,
                model="openrouter/free",
                max_tokens=2048,
                max_iterations=3,
            )

            output = result.get("output", "No response")
            tool_calls = result.get("tool_calls", [])
            for tc in tool_calls:
                self.call_from_thread(self._add_tool_message, tc.get("tool", ""), tc.get("result", ""))
            self.call_from_thread(self._add_assistant_message, output)

        except Exception as e:
            self.call_from_thread(self._add_system_message, f"Error: {e}")

    def action_clear_chat(self) -> None:
        container = self.query_one("#messages")
        container.remove_children()
        self.messages.clear()
        self._add_system_message("Chat cleared.")


def main():
    SagoApp().run()


if __name__ == "__main__":
    main()
