"""TUI Helpers - Extended UI helper methods with agent-tagged messages."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from rich.syntax import Syntax
from textual.containers import Vertical
from textual.widgets import Collapsible, Static

from sago.tui.widgets import AgentStatus, get_agent_color

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
        self._hide_welcome_screen()
        self.messages.append({"role": "user", "content": content})
        self.query_one("#messages").mount(Static(f"> {content}", classes="msg-user", markup=False))
        self.query_one("#messages").scroll_end()
        self._save_message("user", content)

    def _add_assistant_message(
        self: SagoApp, content: str, meta: str = "", agent_name: str = ""
    ) -> None:
        self._hide_welcome_screen()
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

        from rich.markup import escape

        if "```" not in display:
            # Plain text — render markdown formatting
            rendered = _render_markdown(display)
            container.mount(
                Static(f"{agent_prefix}{escape(rendered)}", classes="msg-assistant")
            )
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
                        container.mount(
                            Static(f"{prefix}{escape(rendered)}", classes="msg-assistant")
                        )
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
                        container.mount(Static(code, classes="code-block", markup=False))

        container.scroll_end()
        self._save_message("assistant", content)

    def _add_agent_message(self: SagoApp, agent_name: str, content: str) -> None:
        """Add a message with explicit agent tagging."""
        self._add_assistant_message(content, agent_name=agent_name)

    def _add_system_message(self: SagoApp, content: str) -> None:
        self.query_one("#messages").mount(Static(content, classes="msg-system", markup=False))
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
        c.mount(
            Collapsible(
                Static(body, classes="msg-system", markup=False),
                title=title,
                collapsed=True,
            )
        )
        c.scroll_end()

    def _add_parallel_result(
        self: SagoApp, agent_name: str, result: str, elapsed: float, success: bool
    ) -> None:
        """Add a result from a parallel agent execution."""
        color = get_agent_color(agent_name)
        status_icon = "✓" if success else "✗"
        header = f"[{color}]{status_icon} {agent_name}[/{color}] ({elapsed:.1f}s)"

        container = self.query_one("#messages")
        from rich.markup import escape

        if "```" in result:
            parts = result.split("```")
            for i, part in enumerate(parts):
                if i % 2 == 0:
                    rendered = _render_markdown(part.strip())
                    if rendered.strip():
                        if i == 0:
                            container.mount(
                                Static(
                                    f"{header}\n{escape(rendered)}",
                                    classes="msg-assistant",
                                )
                            )
                        else:
                            container.mount(Static(escape(rendered), classes="msg-assistant"))
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
                            container.mount(Static(code, classes="code-block", markup=False))
        else:
            from rich.markup import escape
            rendered = _render_markdown(result)
            container.mount(Static(f"{header}\n{escape(rendered)}", classes="msg-assistant"))
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

        # Don't show summary box unless enabled
        if not getattr(self, "show_summary", False):
            return

        # Build summary line
        parts = []
        if n_tools > 0:
            parts.append(f"{n_tools} tool{'s' if n_tools != 1 else ''} ({n_ok} ok, {n_fail} fail)")
        cum = tokens.get("cumulative", 0)
        if cum > 0:
            parts.append(f"{cum:,} tokens")
        elif t_in > 0 or t_out > 0:
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

        box = Static("\n".join(lines), classes="summary-box", markup=False)
        self.query_one("#messages").mount(box)
        self.query_one("#messages").scroll_end()

    def _update_dashboard(self: SagoApp) -> None:
        """Update the agent dashboard with current status."""
        dashboard = self.query_one("#agent-dashboard")
        if not dashboard or not self._dashboard_visible:
            return

        # Try to update in-place; fall back to rebuild if structure changed
        existing_entries = dashboard.query(".agent-entry")

        # Build current status entries
        status_items = []

        # Always show current agent info
        status_items.append(("agent", self.current_agent, "active"))
        status_items.append(("model", f"{self.current_provider}/{self.current_model}", "info"))
        status_items.append(("effort", self.current_effort, "info"))
        status_items.append(("session", self.current_session_id[:8] if self.current_session_id else "none", "info"))

        # Show YOLO mode
        yolo_status = "ON" if self.yolo_mode else "OFF"
        status_items.append(("yolo", yolo_status, "active" if self.yolo_mode else "idle"))

        # Show message count
        status_items.append(("messages", str(len(self.messages)), "info"))

        # Show background tasks if any
        try:
            from sago.tui.widgets import AgentStatus, get_task_manager
            tm = get_task_manager()
            tasks = tm.get_all_tasks()
            running = [t for t in tasks if t.status == AgentStatus.RUNNING]
            if running:
                for t in running:
                    status_items.append(("task", f"{t.agent_name}: {t.task[:30]}", "running"))
        except Exception:
            pass

        # Show if thinking
        if self.is_thinking:
            status_items.append(("status", "Thinking...", "running"))

        # Rebuild dashboard if structure changed
        if len(existing_entries) != len(status_items):
            dashboard.remove_children()
            dashboard.mount(Static("Agent Dashboard", classes="dashboard-title", markup=False))
            for key, value, status in status_items:
                entry = Vertical(classes="agent-entry")
                color_class = f"{status}-color"
                entry.mount(
                    Static(
                        f"{key}: {value}",
                        classes=f"agent-name {color_class}",
                        markup=False,
                    )
                )
                dashboard.mount(entry)
            dashboard.mount(Static("---" * 15, classes="dashboard-separator", markup=False))
        else:
            # Update in-place
            for idx, (key, value, status) in enumerate(status_items):
                entry = existing_entries[idx]
                entry.remove_children()
                color_class = f"{status}-color"
                entry.mount(
                    Static(
                        f"{key}: {value}",
                        classes=f"agent-name {color_class}",
                        markup=False,
                    )
                )

        # Update stats
        stats_widgets = dashboard.query(".dashboard-stats")
        if stats_widgets:
            parts = []
            if self.is_thinking:
                parts.append("active")
            try:
                from sago.tui.widgets import AgentStatus, get_task_manager
                tm = get_task_manager()
                tasks = tm.get_all_tasks()
                running = sum(1 for t in tasks if t.status == AgentStatus.RUNNING)
                if running:
                    parts.append(f"{running} tasks")
            except Exception:
                pass
            if not parts:
                parts.append("idle")
            stats_widgets[0].update(f"Status: {', '.join(parts)}")

    def _render_agent_entry(self, entry: Vertical, info: Any) -> None:
        """Render a single agent entry into a container."""
        status_icon = {
            AgentStatus.IDLE: "○",
            AgentStatus.RUNNING: "⟳",
            AgentStatus.WAITING: "◎",
            AgentStatus.COMPLETED: "✓",
            AgentStatus.FAILED: "✗",
            AgentStatus.CANCELLED: "⊘",
        }.get(info.status, "?")

        entry.mount(
            Static(
                f"{status_icon} {info.agent_name}",
                classes="agent-name",
                markup=False,
            )
        )
        if info.task:
            entry.mount(Static(f"  {info.task[:50]}", classes="agent-task", markup=False))
        if info.current_tool and info.status == AgentStatus.RUNNING:
            entry.mount(
                Static(f"  -> {info.current_tool}", classes="agent-tools", markup=False)
            )
        if info.elapsed > 0:
            entry.mount(Static(f"  {info.elapsed:.1f}s", classes="agent-tools", markup=False))

    def _save_message(self: SagoApp, role: str, content: str, metadata: dict | None = None) -> None:
        if self.current_session_id and self.current_session_id != "local":
            try:
                from sago.database import MessageStore

                # Reuse MessageStore instance for batched writes
                if not hasattr(self, "_message_store") or self._message_store is None:
                    self._message_store = MessageStore(self.current_session_id)
                self._message_store.add(
                    role=role,
                    content=content,
                    agent_name=self.current_agent,
                    metadata=metadata,
                )
            except Exception:
                pass
