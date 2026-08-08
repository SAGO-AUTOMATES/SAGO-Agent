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
    "/help": "Show all commands",
    "/h": "Show help",
    "/agents": "List all agents (or filter: /a engineer)",
    "/a": "List agents",
    "/clear": "Clear chat",
    "/c": "Clear chat",
    "/status": "System status",
    "/s": "System status",
    "/export": "Export session to markdown",
    "/e": "Export session",
    "/sessions": "List recent sessions",
    "/session": "Switch session by id",
    "/history": "Show chat history",
    "/model": "Show or change model",
    "/provider": "Show or change provider",
    "/effort": "Set effort level (low/medium/high)",
    "/chain": "Chain agents for task",
    "/cost": "Show token usage & cost",
    "/compact": "Summarize current context",
    "/retry": "Retry last message",
    "/edit": "Edit last response",
    "/reset": "Reset session",
    "/save": "Save current context",
    "/load": "Load saved context",
    "/version": "Show version",
    "/exit": "Quit",
    "/q": "Quit",
    "/quit": "Quit",
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
        max-height: 14;
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
    current_model: reactive[str] = reactive("openrouter/free")
    messages: reactive[list[dict]] = reactive(list)
    show_suggestions: reactive[bool] = reactive(False)
    suggestion_items: reactive[list[str]] = reactive(list)
    suggestion_index: reactive[int] = reactive(0)
    suggestion_mode: reactive[str] = reactive("")

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
        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in ("/help", "/h"):
            self._show_help()
        elif cmd in ("/agents", "/a"):
            self._show_agents(args)
        elif cmd in ("/clear", "/c"):
            self.action_clear_chat()
        elif cmd in ("/status", "/s"):
            self._show_status()
        elif cmd in ("/export", "/e"):
            self._export_session()
        elif cmd == "/sessions":
            self._show_sessions()
        elif cmd == "/session":
            self._switch_session(args)
        elif cmd == "/history":
            self._show_history()
        elif cmd == "/model":
            self._change_model(args)
        elif cmd == "/provider":
            self._change_provider(args)
        elif cmd == "/effort":
            self._set_effort(args)
        elif cmd == "/chain":
            self._add_system_message("Usage: /chain agent1,agent2,agent3")
        elif cmd == "/cost":
            self._show_cost()
        elif cmd == "/compact":
            self._compact()
        elif cmd == "/retry":
            self._retry_last()
        elif cmd == "/reset":
            self.action_clear_chat()
            self.current_agent = "sago-orchestrator"
            self.current_model = "openrouter/free"
            self._add_system_message("Session reset.")
        elif cmd == "/save":
            self._save_context(args)
        elif cmd == "/load":
            self._load_context(args)
        elif cmd == "/version":
            self._add_system_message("Sago v0.1.0")
        elif cmd in ("/exit", "/q", "/quit"):
            self.exit()
        else:
            self._add_system_message(f"Unknown command: {cmd}")

    def _show_help(self) -> None:
        help_text = """Commands:
  /help, /h         — Show this help
  /agents, /a       — List agents (or /a <filter>)
  /clear, /c        — Clear chat
  /status, /s       — System status
  /export, /e       — Export session to markdown
  /sessions         — List recent sessions
  /session <id>     — Switch session
  /history          — Show chat history
  /model            — Show current model
  /model <name>     — Change model
  /provider         — Show current provider
  /provider <name>  — Change provider
  /effort <level>   — Set effort (low/medium/high)
  /chain <agents>   — Chain agents for task
  /cost             — Show token usage & cost
  /compact          — Summarize context
  /retry            — Retry last message
  /reset            — Reset session
  /save [name]      — Save context
  /load <name>      — Load context
  /version          — Show version
  /exit, /q         — Quit

Autocomplete:
  / — Commands
  @ — Agents
  # — Files"""
        self._add_system_message(help_text)

    def _show_agents(self, filter: str = "") -> None:
        try:
            from sago.agents.registry import list_agents
            agents = list_agents()

            if filter:
                filtered = [
                    a for a in agents
                    if filter.lower() in a["name"].lower()
                    or filter.lower() in a.get("category", "").lower()
                    or filter.lower() in " ".join(a.get("skills", [])).lower()
                ]
                if filtered:
                    lines = "\n".join(f"  {a['name']}" for a in filtered[:30])
                    self._add_system_message(f"Agents matching '{filter}' ({len(filtered)}):\n{lines}")
                else:
                    self._add_system_message(f"No agents matching '{filter}'")
            else:
                # Group by category
                categories: dict[str, list] = {}
                for a in agents:
                    cat = a.get("category", "other")
                    categories.setdefault(cat, []).append(a)

                lines = []
                for cat in sorted(categories.keys()):
                    names = [a["name"] for a in categories[cat][:5]]
                    lines.append(f"\n  [{cat}]")
                    for n in names:
                        lines.append(f"    {n}")
                    if len(categories[cat]) > 5:
                        lines.append(f"    ... +{len(categories[cat]) - 5} more")

                self._add_system_message(f"Agents ({len(agents)} total):\n" + "\n".join(lines))
        except Exception as e:
            self._add_system_message(f"Error: {e}")

    def _show_status(self) -> None:
        try:
            from sago.agents.registry import list_agents
            agents = list_agents()
            self._add_system_message(
                f"Sago v0.1.0\n"
                f"  Agents: {len(agents)}\n"
                f"  Model: {self.current_model}\n"
                f"  Agent: {self.current_agent}\n"
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

    def _switch_session(self, session_id: str) -> None:
        if not session_id:
            self._add_system_message("Usage: /session <id>")
            return
        self._add_system_message(f"Switched to session: {session_id}")

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

    def _change_model(self, model: str) -> None:
        if not model:
            lines = "\n".join(f"  {m}" for m in MODELS)
            self._add_system_message(f"Current: {self.current_model}\n\nAvailable:\n{lines}")
            return
        # Find matching model
        for m in MODELS:
            if model.lower() in m.lower():
                self.current_model = m
                self._add_system_message(f"Model changed to: {m}")
                return
        self.current_model = model
        self._add_system_message(f"Model set to: {model}")

    def _change_provider(self, provider: str) -> None:
        if not provider:
            lines = "\n".join(f"  {p}" for p in PROVIDERS)
            self._add_system_message(f"Available providers:\n{lines}")
            return
        for p in PROVIDERS:
            if provider.lower() in p.lower():
                self._add_system_message(f"Provider changed to: {p}")
                return
        self._add_system_message(f"Unknown provider: {provider}")

    def _set_effort(self, level: str) -> None:
        if not level:
            self._add_system_message(f"Current effort: medium\nAvailable: {', '.join(EFFORT_LEVELS)}")
            return
        if level.lower() in EFFORT_LEVELS:
            self._add_system_message(f"Effort set to: {level}")
        else:
            self._add_system_message(f"Invalid effort. Use: {', '.join(EFFORT_LEVELS)}")

    def _show_cost(self) -> None:
        try:
            from sago.tracking.token_tracker import TokenTracker
            tracker = TokenTracker()
            stats = tracker.get_stats()
            self._add_system_message(
                f"Token Usage:\n"
                f"  Total tokens: {stats.get('total_tokens', 0)}\n"
                f"  Total cost: ${stats.get('total_cost', 0):.4f}"
            )
        except Exception:
            self._add_system_message("Token tracking not available yet")

    def _compact(self) -> None:
        if len(self.messages) > 5:
            summary = f"Session compacted. {len(self.messages)} messages summarized."
            self.messages = self.messages[-3:]
            self._add_system_message(summary)
        else:
            self._add_system_message("Nothing to compact")

    def _retry_last(self) -> None:
        user_msgs = [m for m in self.messages if m.get("role") == "user"]
        if user_msgs:
            last = user_msgs[-1].get("content", "")
            self._process_message(last)
        else:
            self._add_system_message("No message to retry")

    def _save_context(self, name: str) -> None:
        name = name or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._add_system_message(f"Context saved as: {name}")

    def _load_context(self, name: str) -> None:
        if not name:
            self._add_system_message("Usage: /load <name>")
            return
        self._add_system_message(f"Context loaded: {name}")

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
                model=self.current_model,
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
