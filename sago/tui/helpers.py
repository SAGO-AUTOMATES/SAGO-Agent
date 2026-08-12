"""TUI Helpers - Extended UI helper methods with agent-tagged messages."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from rich.syntax import Syntax
from textual.containers import Vertical
from textual.widgets import Collapsible, Static

from sago.tui.widgets import AgentStatus, get_agent_color, get_task_manager

if TYPE_CHECKING:
    from sago.tui.app import SagoApp


def _render_markdown(content: str) -> str:
    """Render markdown content to a plain-text approximation with formatting hints."""
    text = content

    # Bold: **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)

    # Italic: *text* or _text_ (but not inside words)
    text = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"\1", text)

    # Inline code: `code`
    text = re.sub(r"`(.+?)`", r"\1", text)

    # Headers: ### text → text
    text = re.sub(r"^#{1,6}\s+(.+)$", r"\1", text, flags=re.MULTILINE)

    # Unordered list: - item → • item
    text = re.sub(r"^(\s*)[-*]\s+", r"\1• ", text, flags=re.MULTILINE)

    # Links: [text](url) → text (url)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1 (\2)", text)

    return text


class UIHelpers:
    """Mixin class providing UI helper methods for SagoApp."""

    def _add_user_message(self: SagoApp, content: str) -> None:
        self.messages.append({"role": "user", "content": content})
        self.query_one("#messages").mount(Static(f"> {content}", classes="msg-user"))
        self.query_one("#messages").scroll_end()
        self._save_message("user", content)

    def _add_assistant_message(
        self: SagoApp, content: str, meta: str = "", agent_name: str = ""
    ) -> None:
        self.messages.append({"role": "assistant", "content": content, "agent": agent_name})
        container = self.query_one("#messages")

        display = content
        if meta:
            display += f"\n\n{meta}"

        # Prepend agent tag if specified
        agent_prefix = ""
        if agent_name:
            color = get_agent_color(agent_name)
            agent_prefix = f"[{color}]({agent_name})[/{color}] "

        if "```" not in display:
            # Plain text — render markdown formatting
            rendered = _render_markdown(display)
            container.mount(Static(f"{agent_prefix}{rendered}", classes="msg-assistant"))
        else:
            # Has code blocks — render each part
            parts = display.split("```")
            first_text = True
            for i, part in enumerate(parts):
                if i % 2 == 0:
                    # Text outside code blocks
                    rendered = _render_markdown(part.strip())
                    if rendered.strip():
                        prefix = agent_prefix if first_text else ""
                        first_text = False
                        container.mount(Static(f"{prefix}{rendered}", classes="msg-assistant"))
                else:
                    # Inside code block
                    lines = part.split("\n", 1)
                    lang = ""
                    code = lines[0]
                    if len(lines) > 1:
                        lang = lines[0].strip()
                        code = lines[1]
                    else:
                        code = lines[0]

                    # Strip trailing backticks from code
                    code = code.rstrip().removesuffix("```").rstrip()

                    if not code.strip():
                        continue

                    # Try rich syntax highlighting
                    try:
                        syntax = Syntax(
                            code,
                            lang or "text",
                            theme="monokai",
                            line_numbers=True,
                            word_wrap=True,
                        )
                        container.mount(
                            Collapsible(
                                Static(syntax),
                                title=f"Code ({lang or 'text'})",
                                collapsed=False,
                            )
                        )
                    except Exception:
                        container.mount(Static(code, classes="code-block"))

        container.scroll_end()
        self._save_message("assistant", content)

    def _add_agent_message(self: SagoApp, agent_name: str, content: str) -> None:
        """Add a message with explicit agent tagging."""
        self._add_assistant_message(content, agent_name=agent_name)

    def _add_system_message(self: SagoApp, content: str) -> None:
        self.query_one("#messages").mount(Static(content, classes="msg-system"))
        self.query_one("#messages").scroll_end()

    def _add_tool_call(
        self: SagoApp, tool_name: str, args: dict, result: str, success: bool = True
    ) -> None:
        args_str = "\n".join(f"  {k}: {str(v)[:200]}" for k, v in args.items())
        status = "OK" if success else "ERROR"
        title = f"[{status}] {tool_name}"
        body = f"Input:\n{args_str}\n\nOutput:\n{result[:1000]}"
        if len(result) > 1000:
            body += f"\n... ({len(result)} chars total)"

        c = self.query_one("#messages")
        c.mount(Collapsible(Static(body, classes="msg-system"), title=title, collapsed=True))
        c.scroll_end()

    def _add_parallel_result(
        self: SagoApp, agent_name: str, result: str, elapsed: float, success: bool
    ) -> None:
        """Add a result from a parallel agent execution."""
        color = get_agent_color(agent_name)
        status_icon = "✓" if success else "✗"
        header = f"[{color}]{status_icon} {agent_name}[/{color}] ({elapsed:.1f}s)"

        container = self.query_one("#messages")
        if "```" in result:
            parts = result.split("```")
            for i, part in enumerate(parts):
                if i % 2 == 0:
                    rendered = _render_markdown(part.strip())
                    if rendered.strip():
                        if i == 0:
                            container.mount(
                                Static(f"{header}\n{rendered}", classes="msg-assistant")
                            )
                        else:
                            container.mount(Static(rendered, classes="msg-assistant"))
                else:
                    lines = part.split("\n", 1)
                    lang = lines[0].strip() if len(lines) > 1 else ""
                    code = lines[1] if len(lines) > 1 else lines[0]
                    code = code.rstrip().removesuffix("```").rstrip()
                    if code.strip():
                        try:
                            syntax = Syntax(
                                code, lang or "text", theme="monokai", line_numbers=True
                            )
                            container.mount(
                                Collapsible(
                                    Static(syntax),
                                    title=f"{agent_name} - Code ({lang or 'text'})",
                                    collapsed=False,
                                )
                            )
                        except Exception:
                            container.mount(Static(code, classes="code-block"))
        else:
            rendered = _render_markdown(result)
            container.mount(Static(f"{header}\n{rendered}", classes="msg-assistant"))
        container.scroll_end()

    def _add_summary(
        self: SagoApp,
        tool_calls: list[dict],
        output: str,
        elapsed: float,
        tokens: dict,
    ) -> None:
        n_tools = len(tool_calls)
        n_ok = sum(1 for t in tool_calls if t.get("success", False))
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

        # Build summary line
        parts = []
        if n_tools > 0:
            parts.append(f"{n_tools} tool{'s' if n_tools != 1 else ''} ({n_ok} ok, {n_fail} fail)")
        if t_in > 0 or t_out > 0:
            parts.append(f"{t_in:,}+{t_out:,} tokens")
        if elapsed > 0:
            parts.append(f"{elapsed:.1f}s")

        if not parts:
            parts.append("Done")

        lines = ["Summary: " + " | ".join(parts)]

        if cache_hit > 0:
            lines.append(f"Cache: {cache_hit:,} hit, {cache_miss:,} miss")

        files = [
            t["args"].get("file_path", "")
            for t in tool_calls
            if t.get("tool") == "write_file" and t.get("success", False)
        ]
        files = [f for f in files if f]
        if files:
            lines.append(f"Files: {', '.join(files)}")

        box = Static("\n".join(lines), classes="summary-box")
        self.query_one("#messages").mount(box)
        self.query_one("#messages").scroll_end()

    def _update_dashboard(self: SagoApp) -> None:
        """Update the agent dashboard with current task states."""
        dashboard = self.query_one("#agent-dashboard")
        if not dashboard or not self._dashboard_visible:
            return
        tm = get_task_manager()
        tasks = tm.get_all_tasks()

        # Clear and rebuild dashboard content
        dashboard.remove_children()
        dashboard.mount(Static("Agent Dashboard", classes="dashboard-title"))

        active = sum(1 for t in tasks if t.status == AgentStatus.RUNNING)
        completed = sum(1 for t in tasks if t.status == AgentStatus.COMPLETED)
        failed = sum(1 for t in tasks if t.status == AgentStatus.FAILED)

        for info in tasks:
            color = get_agent_color(info.agent_id)
            status_icon = {
                AgentStatus.IDLE: "○",
                AgentStatus.RUNNING: "⟳",
                AgentStatus.WAITING: "◎",
                AgentStatus.COMPLETED: "✓",
                AgentStatus.FAILED: "✗",
                AgentStatus.CANCELLED: "⊘",
            }.get(info.status, "?")

            entry = Vertical(classes="agent-entry")
            entry.mount(
                Static(
                    f"[{color}]{status_icon} {info.agent_name}[/{color}]",
                    classes="agent-name",
                )
            )
            if info.task:
                entry.mount(Static(f"  {info.task[:50]}", classes="agent-task"))
            if info.current_tool and info.status == AgentStatus.RUNNING:
                entry.mount(Static(f"  -> {info.current_tool}", classes="agent-tools"))
            if info.elapsed > 0:
                entry.mount(Static(f"  {info.elapsed:.1f}s", classes="agent-tools"))
            dashboard.mount(entry)

        dashboard.mount(Static("---" * 15, classes="dashboard-separator"))
        parts = []
        if active:
            parts.append(f"{active} active")
        if completed:
            parts.append(f"{completed} done")
        if failed:
            parts.append(f"{failed} failed")
        if not parts:
            parts.append("No agents")
        dashboard.mount(Static(f"Total: {', '.join(parts)}", classes="dashboard-stats"))

    def _save_message(self: SagoApp, role: str, content: str) -> None:
        if self.current_session_id and self.current_session_id != "local":
            try:
                from sago.database import MessageStore

                ms = MessageStore(self.current_session_id)
                ms.add(role=role, content=content, agent_name=self.current_agent)
                ms.close()
            except Exception:
                pass
