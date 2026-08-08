"""Sago TUI - Clean Terminal Interface."""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import TYPE_CHECKING

from rich.syntax import Syntax
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Input, Static


class SagoApp(App):
    """Clean Sago TUI."""

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
    ]

    TITLE = "Sago"

    current_agent: reactive[str] = reactive("sago-orchestrator")
    messages: reactive[list[dict]] = reactive(list)

    def compose(self) -> ComposeResult:
        yield ScrollableContainer(id="messages")
        with Vertical(id="input-area"):
            yield Input(
                placeholder="Message... (/help for commands)",
                id="msg-input",
            )
        yield Footer()

    def on_mount(self) -> None:
        self._add_system_message("Sago v0.1.0 — Type /help for commands")
        self.query_one("#msg-input").focus()

    @on(Input.Submitted, "#msg-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        message = event.value.strip()
        if not message:
            return

        event.input.value = ""

        if message.startswith("/"):
            self._handle_command(message)
            return

        self._add_user_message(message)
        self._process_message(message)

    def _handle_command(self, command: str) -> None:
        cmd = command.lower().strip()

        if cmd in ("/help", "/h"):
            self._add_system_message(
                "Commands:\n"
                "  /help, /h    — Show this help\n"
                "  /agents, /a  — List agents\n"
                "  /clear, /c   — Clear chat\n"
                "  /status, /s  — System status\n"
                "  /export, /e  — Export session\n"
                "  /exit, /q    — Quit"
            )
        elif cmd in ("/agents", "/a"):
            self._show_agents()
        elif cmd in ("/clear", "/c"):
            self.action_clear_chat()
        elif cmd in ("/status", "/s"):
            self._show_status()
        elif cmd in ("/export", "/e"):
            self._export_session()
        elif cmd in ("/exit", "/q", "/quit"):
            self.exit()
        else:
            self._add_system_message(f"Unknown command: {cmd}")

    def _show_agents(self) -> None:
        try:
            from sago.agents.registry import list_agents
            agents = list_agents()
            lines = "\n".join(f"  {a['name']}" for a in agents[:20])
            self._add_system_message(f"Agents:\n{lines}")
        except Exception as e:
            self._add_system_message(f"Error: {e}")

    def _show_status(self) -> None:
        try:
            from sago.agents.registry import list_agents
            agents = list_agents()
            self._add_system_message(
                f"Sago v0.1.0\n"
                f"  Agents: {len(agents)}\n"
                f"  Model: openrouter/free"
            )
        except Exception as e:
            self._add_system_message(f"Error: {e}")

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
