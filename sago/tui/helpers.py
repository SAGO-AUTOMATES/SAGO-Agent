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
    """Format markdown content cleanly into Rich terminal markup."""
    text = content

    # Headers: ### text -> [bold yellow]text[/bold yellow]
    text = re.sub(r"^###\s+(.+)$", r"[bold yellow]\1[/bold yellow]", text, flags=re.MULTILINE)
    text = re.sub(r"^##\s+(.+)$", r"[bold cyan]\1[/bold cyan]", text, flags=re.MULTILINE)
    text = re.sub(
        r"^#\s+(.+)$", r"[bold underline cyan]\1[/bold underline cyan]", text, flags=re.MULTILINE
    )

    # Bold: **text** -> [bold]text[/bold]
    text = re.sub(r"\*\*(.+?)\*\*", r"[bold]\1[/bold]", text)

    # Italic: *text* -> [italic]text[/italic]
    text = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"[italic]\1[/italic]", text)

    # Inline code: `code` -> [cyan]`code`[/cyan]
    text = re.sub(r"`(.+?)`", r"[cyan]`\1`[/cyan]", text)

    # Unordered list: - item ->   [cyan]•[/cyan] item
    text = re.sub(r"^(\s*)[-*]\s+", r"\1[cyan]•[/cyan] ", text, flags=re.MULTILINE)

    # Numbered list: 1. item ->   [bold cyan]1.[/bold cyan] item
    text = re.sub(r"^(\s*)(\d+\.)\s+", r"\1[bold cyan]\2[/bold cyan] ", text, flags=re.MULTILINE)

    return text


class UIHelpers:
    """Mixin class providing UI helper methods for SagoApp."""

    def _add_user_message(self: SagoApp, content: str) -> None:
        self._hide_welcome_screen()
        self.messages.append({"role": "user", "content": content})
        self._save_message("user", content)

        # Create a unified turn container (exchange-box)
        exchange_box = Vertical(classes="exchange-box")
        exchange_box.mount(
            Static(
                f"[bold cyan]● PROMPT[/bold cyan]  [bold white]{content}[/bold white]",
                classes="exchange-prompt",
                markup=True,
            )
        )
        self._active_exchange_card = exchange_box
        self.query_one("#messages").mount(exchange_box)
        self.query_one("#messages").scroll_end()

    def _add_assistant_message(
        self: SagoApp, content: str, meta: str = "", agent_name: str = ""
    ) -> None:
        self._hide_welcome_screen()
        self.messages.append({"role": "assistant", "content": content, "agent": agent_name})
        self._save_message("assistant", content)

        target = getattr(self, "_active_exchange_card", None)
        if target is None:
            target = self.query_one("#messages")

        display = content
        if meta:
            display += f"\n\n[dim]{meta}[/dim]"

        # Prepend agent tag if specified
        if agent_name:
            color = get_agent_color(agent_name)
            agent_prefix = f"[{color}][AGENT: {agent_name}][/{color}]\n"
        else:
            agent_prefix = "[bold green][SAGO][/bold green]\n"

        if "```" not in display:
            rendered = _render_markdown(display)
            target.mount(
                Static(f"{agent_prefix}{rendered}", classes="exchange-assistant", markup=True)
            )
        else:
            parts = display.split("```")
            first_text = True
            for i, part in enumerate(parts):
                if i % 2 == 0:
                    rendered = _render_markdown(part.strip())
                    if rendered.strip():
                        prefix = agent_prefix if first_text else ""
                        first_text = False
                        target.mount(
                            Static(f"{prefix}{rendered}", classes="exchange-assistant", markup=True)
                        )
                else:
                    lines = part.split("\n", 1)
                    lang = lines[0].strip() if len(lines) > 1 else "text"
                    code = lines[1] if len(lines) > 1 else lines[0]
                    code = code.rstrip().removesuffix("```").rstrip()

                    if not code.strip():
                        continue

                    try:
                        syntax = Syntax(
                            code,
                            lang or "text",
                            theme="monokai",
                            line_numbers=True,
                            word_wrap=True,
                        )
                        target.mount(
                            Collapsible(
                                Static(syntax),
                                title=f"Code snippet ({lang or 'text'})",
                                collapsed=False,
                            )
                        )
                    except Exception:
                        target.mount(Static(code, classes="code-block", markup=False))

        # Turn finished -> clear active exchange card
        self._active_exchange_card = None
        self.query_one("#messages").scroll_end()

    def _add_agent_message(self: SagoApp, agent_name: str, content: str) -> None:
        """Add a message with explicit agent tagging."""
        self._add_assistant_message(content, agent_name=agent_name)

    def _add_system_message(self: SagoApp, content: str) -> None:
        self.query_one("#messages").mount(
            Static(
                f"[bold yellow][SYSTEM][/bold yellow] {content}", classes="msg-system", markup=True
            )
        )
        self.query_one("#messages").scroll_end()

    def _add_tool_call(
        self: SagoApp, tool_name: str, args: dict, result: str, success: bool = True
    ) -> None:
        status_tag = "[bold green]● OK[/bold green]" if success else "[bold red]✗ FAILED[/bold red]"
        title = f"{status_tag} Tool: [bold cyan]{tool_name}[/bold cyan]"

        args_str = "\n".join(f"  [cyan]{k}[/cyan]: {str(v)[:200]}" for k, v in args.items())
        preview_res = result[:1500] if result else "(empty)"
        if len(result) > 1500:
            preview_res += f"\n... [dim]({len(result)} characters total)[/dim]"

        body = f"[bold]Parameters:[/bold]\n{args_str}\n\n[bold]Output:[/bold]\n{preview_res}"

        target = getattr(self, "_active_exchange_card", None)
        if target is None:
            target = self.query_one("#messages")

        target.mount(
            Collapsible(
                Static(body, classes="msg-system", markup=True),
                title=title,
                collapsed=True,
            )
        )
        self.query_one("#messages").scroll_end()

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
        """Update the agent dashboard safely with Rich formatted markup."""
        try:
            dashboards = self.query("#agent-dashboard")
            if not dashboards or not getattr(self, "_dashboard_visible", False):
                return

            content_widgets = self.query("#agent-dashboard-content")
            if not content_widgets:
                return
            content_widget = content_widgets[0]

            lines = []
            cur_agent = getattr(self, "current_agent", "sago")
            prov = getattr(self, "current_provider", "openrouter")
            model = getattr(self, "current_model", "openrouter/free")
            effort = getattr(self, "current_effort", "medium")
            yolo = getattr(self, "yolo_mode", False)
            thinking = getattr(self, "is_thinking", False)
            session_id = getattr(self, "current_session_id", "local")

            lines.append(f"[bold cyan]Agent:[/] [white]{cur_agent}[/]")
            lines.append(f"[bold cyan]Model:[/] [yellow]{prov}/{model}[/]")
            lines.append(f"[bold cyan]Effort:[/] [magenta]{effort}[/]")
            lines.append(
                f"[bold cyan]YOLO:[/] [{'green' if yolo else 'dim'}]{'ON' if yolo else 'OFF'}[/]"
            )
            lines.append(
                f"[bold cyan]Session:[/] [dim]{session_id[:8] if session_id else 'none'}[/]"
            )
            lines.append(f"[bold cyan]Messages:[/] [white]{len(getattr(self, 'messages', []))}[/]")

            status_text = "[bold green]● Thinking[/]" if thinking else "[dim]○ Idle[/]"
            lines.append(f"[bold cyan]Status:[/] {status_text}")
            lines.append("\n[dim]────────────────────────────[/dim]\n")

            # Background Tasks
            try:
                from sago.tui.widgets import AgentStatus, get_task_manager

                tm = get_task_manager()
                tasks = tm.get_all_tasks()
                running = [t for t in tasks if t.status == AgentStatus.RUNNING]
                lines.append(f"[bold]Active Tasks ({len(running)}):[/bold]")
                if running:
                    for t in running[:5]:
                        lines.append(
                            f"  [green]●[/] [cyan]{t.agent_name}[/]: [dim]{t.task[:18]}...[/dim]"
                        )
                else:
                    lines.append("  [dim]No running tasks[/dim]")
            except Exception:
                pass

            content_widget.update("\n".join(lines))
        except Exception:
            pass

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
            entry.mount(Static(f"  -> {info.current_tool}", classes="agent-tools", markup=False))
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
