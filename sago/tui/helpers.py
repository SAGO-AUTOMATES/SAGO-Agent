"""TUI Helpers - Extended UI helper methods with agent-tagged messages."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from rich.markup import escape
from rich.syntax import Syntax
from textual import events, on
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Collapsible, Static

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


def create_collapsible(
    *content: Any,
    title: str = "",
    collapsed: bool = False,
) -> Collapsible:
    """Create a native Textual Collapsible."""
    return Collapsible(*content, title=title, collapsed=collapsed)


class ExchangeTurnCard(Vertical):
    """Container for a single unified conversational turn (Prompt, Reasoning, Tools, Response)."""

    def __init__(
        self,
        prompt: str,
        card_type: str = "user",
        tag_label: str = "",
        tag_color: str = "",
        meta_info: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(classes=f"exchange-box exchange-box--{card_type}", **kwargs)
        self.prompt = prompt
        self.card_type = card_type
        self.tag_label = tag_label or ("USER" if card_type == "user" else card_type.upper())
        self.tag_color = tag_color or (
            "#58a6ff"
            if card_type == "user"
            else (
                "#bc8cff"
                if card_type == "delegate"
                else (
                    "#79c0ff"
                    if card_type == "chain"
                    else (
                        "#3fb950"
                        if card_type == "orchestrate"
                        else ("#d29922" if card_type == "plan" else "#58a6ff")
                    )
                )
            )
        )
        self.meta_info = meta_info
        self.response_text: str = ""
        self.is_turn_collapsed = False

    def compose(self):
        preview = self.prompt.replace("\n", " ").strip()
        title_snippet = f"{preview[:120]}..." if len(preview) > 120 else preview
        icon = "▶" if self.is_turn_collapsed else "▼"
        meta_str = f"  [bold white]{escape(self.meta_info)}[/bold white]" if self.meta_info else ""
        yield Static(
            f"[bold {self.tag_color}]{icon} {self.tag_label}[/bold {self.tag_color}]{meta_str}  {escape(title_snippet)}",
            classes="exchange-prompt-header",
            markup=True,
        )
        with Vertical(classes="exchange-body"):
            rendered_prompt = _render_markdown(self.prompt)
            body_header = (
                "User Prompt:" if self.card_type == "user" else f"{self.tag_label.title()} Target:"
            )
            yield Static(
                f"[bold {self.tag_color}]{body_header}[/bold {self.tag_color}]\n{rendered_prompt}",
                classes="exchange-user-prompt",
                markup=True,
            )
            yield Static("─" * 40, classes="exchange-divider", markup=False)

    @on(events.Click, ".exchange-prompt-header")
    def on_header_clicked(self, event: events.Click) -> None:
        event.stop()
        self.toggle_collapse()

    def toggle_collapse(self) -> None:
        """Toggle collapsed state of entire exchange body."""
        try:
            body = self.query_one(".exchange-body")
            hdr = self.query_one(".exchange-prompt-header", Static)
            self.is_turn_collapsed = not self.is_turn_collapsed
            body.display = not self.is_turn_collapsed

            preview = self.prompt.replace("\n", " ").strip()
            title_snippet = f"{preview[:120]}..." if len(preview) > 120 else preview
            icon = "▶" if self.is_turn_collapsed else "▼"
            meta_str = (
                f"  [bold white]{escape(self.meta_info)}[/bold white]" if self.meta_info else ""
            )

            if self.is_turn_collapsed:
                hdr.update(
                    f"[bold {self.tag_color}]{icon} {self.tag_label}[/bold {self.tag_color}]{meta_str}  {escape(title_snippet)}  [dim]─ (click to expand)[/dim]"
                )
            else:
                hdr.update(
                    f"[bold {self.tag_color}]{icon} {self.tag_label}[/bold {self.tag_color}]{meta_str}  {escape(title_snippet)}"
                )
        except Exception:
            pass

    def mount_child(self, widget: Any) -> None:
        """Mount child widget inside exchange body."""
        try:
            body = self.query_one(".exchange-body")
            body.mount(widget)
        except Exception:
            self.mount(widget)


class CollapsibleOutputCard(Vertical):
    """Universal collapsible card for command outputs with clickable top header."""

    def __init__(
        self,
        content_widget: Any,
        title: str,
        collapsed: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(classes="collapsible-card-box", **kwargs)
        self.card_title = title
        self.is_collapsed = collapsed
        self._content_widget = content_widget

    def compose(self):
        icon = "▶" if self.is_collapsed else "▼"
        safe_title = escape(self.card_title)
        yield Static(
            f"[dim]{icon}[/dim]  {safe_title}",
            classes="card-header",
            markup=True,
        )
        with Vertical(classes="card-body"):
            yield self._content_widget

    @on(events.Click, ".card-header")
    def on_header_clicked(self, event: events.Click) -> None:
        event.stop()
        self.toggle_collapse()

    def toggle_collapse(self) -> None:
        try:
            body = self.query_one(".card-body")
            hdr = self.query_one(".card-header", Static)
            self.is_collapsed = not self.is_collapsed
            body.display = not self.is_collapsed
            safe_title = escape(self.card_title)
            icon = "▶" if self.is_collapsed else "▼"
            hdr.update(f"[dim]{icon}[/dim]  {safe_title}")
        except Exception:
            pass


class ShellEscapeCard(Vertical):
    """Clean collapsible terminal card for !<command> shell executions."""

    def __init__(self, command: str, **kwargs: Any) -> None:
        super().__init__(classes="shell-escape-card", **kwargs)
        self.command = command
        self.is_collapsed = False
        self._status_tag = "[dim](running...)[/dim]"

    def compose(self):
        icon = "▶" if self.is_collapsed else "▼"
        yield Static(
            f"[dim]{icon}[/dim]  [bold white]$ {escape(self.command)}[/bold white]  {self._status_tag}",
            classes="shell-card-header",
            markup=True,
        )
        with Vertical(classes="shell-card-body"):
            yield Static("Executing command in workspace shell...", classes="shell-output-text")

    @on(events.Click, ".shell-card-header")
    def on_header_clicked(self, event: events.Click) -> None:
        event.stop()
        self.toggle_collapse()

    def toggle_collapse(self) -> None:
        try:
            body = self.query_one(".shell-card-body")
            hdr = self.query_one(".shell-card-header", Static)
            self.is_collapsed = not self.is_collapsed
            body.display = not self.is_collapsed
            icon = "▶" if self.is_collapsed else "▼"
            hdr.update(
                f"[dim]{icon}[/dim]  [bold white]$ {escape(self.command)}[/bold white]  {self._status_tag}"
            )
        except Exception:
            pass

    def update_result(self, output: str, returncode: int, duration_s: float) -> None:
        try:
            hdr = self.query_one(".shell-card-header", Static)
            body = self.query_one(".shell-output-text", Static)
            self._status_tag = (
                f"[bold #3fb950]✓ exit 0[/bold #3fb950] [dim]({duration_s:.2f}s)[/dim]"
                if returncode == 0
                else f"[bold #f85149]✗ exit {returncode}[/bold #f85149] [dim]({duration_s:.2f}s)[/dim]"
            )
            icon = "▶" if self.is_collapsed else "▼"
            hdr.update(
                f"[dim]{icon}[/dim]  [bold white]$ {escape(self.command)}[/bold white]  {self._status_tag}"
            )
            clean_out = output.strip() if output.strip() else "[dim](no output)[/dim]"
            body.update(clean_out)
        except Exception:
            pass


class UIHelpers:
    """Mixin class providing UI helper methods for SagoApp."""

    def _add_user_message(self: SagoApp, content: str) -> None:
        self._hide_welcome_screen()
        self.messages.append({"role": "user", "content": content})
        self._save_message("user", content)

        # Synthesize smart one-liner session title
        from sago.engine.prompt_enhancer import generate_session_title

        current_title = getattr(self, "current_session_title", "")
        if not current_title or current_title in ("TUI Session", "Interactive Session"):
            self.current_session_title = generate_session_title(content)
            try:
                from sago.database import Session

                s = Session(self.current_session_id)
                s.update(title=self.current_session_title)
                s.close()
            except Exception:
                pass

        # Create unified ExchangeTurnCard
        turn_card = ExchangeTurnCard(prompt=content, card_type="user")
        self._active_exchange_card = turn_card
        msg_container = self.query_one("#messages")
        msg_container.mount(turn_card)
        msg_container.scroll_end(animate=False)

    def _add_command_turn(
        self: SagoApp,
        cmd_type: str,
        content: str,
        meta: str = "",
        tag_label: str = "",
        tag_color: str = "",
    ) -> None:
        """Create a dedicated command turn card with unique border color and tag."""
        self._hide_welcome_screen()
        self.messages.append({"role": "user", "content": f"/{cmd_type} {content}".strip()})
        self._save_message("user", f"/{cmd_type} {content}".strip())

        turn_card = ExchangeTurnCard(
            prompt=content,
            card_type=cmd_type,
            tag_label=tag_label,
            tag_color=tag_color,
            meta_info=meta,
        )
        self._active_exchange_card = turn_card
        msg_container = self.query_one("#messages")
        msg_container.mount(turn_card)
        msg_container.scroll_end(animate=False)

    def _add_prompt_enhancement_card(self: SagoApp, enhancement: Any) -> None:
        """Display clean collapsible Prompt Enhancement section directly inside active exchange turn."""
        if not enhancement or not getattr(enhancement, "was_modified", False):
            return

        from textual.widgets import Collapsible, Static

        tags = " • ".join(getattr(enhancement, "improvements", [])[:4])
        intent_summary = getattr(enhancement, "intent_summary", "")
        enhanced_prompt = getattr(enhancement, "enhanced_prompt", "")
        crit_lines = "\n".join(
            f"  {i + 1}. {c}" for i, c in enumerate(getattr(enhancement, "acceptance_criteria", []))
        )
        targets = ", ".join(getattr(enhancement, "target_scope", []))

        card_lines = [
            f"[bold #58a6ff]Goal:[/] [white]{intent_summary}[/white]",
        ]
        if targets:
            card_lines.append(f"[dim]Targets:[/] [cyan]{targets}[/cyan]")
        if tags:
            card_lines.append(f"[dim]Additions:[/] [green]{tags}[/green]")
        if crit_lines:
            card_lines.append(f"\n[bold]Acceptance Criteria:[/]\n{crit_lines}")

        card_lines.append(
            f"\n[dim]── Injected Structured Prompt ──[/dim]\n[white]{enhanced_prompt}[/white]"
        )

        title_preview = intent_summary[:55] if intent_summary else "Goal Synthesized"
        title = f"✨ Enhanced Prompt: [bold]{title_preview}[/bold]"
        card = Collapsible(
            Static("\n".join(card_lines), markup=True),
            title=title,
            collapsed=False,
        )

        target_card = getattr(self, "_active_exchange_card", None)
        if target_card is not None and hasattr(target_card, "mount_child"):
            target_card.mount_child(card)
        elif target_card is not None:
            target_card.mount(card)
        else:
            self.query_one("#messages").mount(card)
        self.query_one("#messages").scroll_end(animate=False)

    def _add_assistant_message(
        self: SagoApp, content: str, meta: str = "", agent_name: str = ""
    ) -> None:
        self._hide_welcome_screen()
        self.messages.append({"role": "assistant", "content": content, "agent_name": agent_name})
        self._save_message("assistant", content)

        target_card = getattr(self, "_active_exchange_card", None)

        def _mount_element(elem: Any) -> None:
            if target_card is not None and hasattr(target_card, "mount_child"):
                target_card.mount_child(elem)
            elif target_card is not None:
                target_card.mount(elem)
            else:
                self.query_one("#messages").mount(elem)

        display = content

        # Extract and contain thinking / reasoning blocks
        thinking_match = re.search(
            r"<(?:thinking|thought)>(.*?)</(?:thinking|thought)>", display, re.DOTALL
        )
        if thinking_match:
            thinking_content = thinking_match.group(1).strip()
            if thinking_content:
                _mount_element(
                    Collapsible(
                        Static(thinking_content, classes="thinking-text", markup=False),
                        title="● Technical Reasoning & Analysis",
                        collapsed=True,
                    )
                )
            display = re.sub(
                r"<(?:thinking|thought)>.*?</(?:thinking|thought)>", "", display, flags=re.DOTALL
            ).strip()

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
            _mount_element(
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
                        _mount_element(
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
                        _mount_element(
                            Collapsible(
                                Static(syntax),
                                title=f"Code snippet ({lang or 'text'})",
                                collapsed=False,
                            )
                        )
                    except Exception:
                        _mount_element(
                            Collapsible(
                                Static(code, classes="code-block", markup=False),
                                title=f"Code snippet ({lang or 'text'})",
                                collapsed=False,
                            )
                        )

        if target_card is not None and hasattr(target_card, "response_text"):
            if target_card.response_text:
                target_card.response_text += f"\n{content}"
            else:
                target_card.response_text = content

        # If developer mode is active, mount a per-turn trace bar with a "View Trace" button
        if getattr(self, "developer_mode", False):
            from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer

            tracer = get_dev_tracer()
            traces = tracer.get_recent_traces(limit=500) if tracer.is_enabled else []
            if traces:
                llm_count = sum(
                    1
                    for t in traces
                    if t.event_type in (TraceEventType.LLM_PAYLOAD, TraceEventType.LLM_RAW_RESPONSE)
                )
                tool_count = sum(1 for t in traces if t.event_type == TraceEventType.TOOL_DISPATCH)
                route_count = sum(1 for t in traces if t.event_type == TraceEventType.AGENT_ROUTING)
                thinking_count = sum(
                    1 for t in traces if t.event_type == TraceEventType.LLM_THINKING
                )
                err_count = sum(1 for t in traces if t.event_type.value == "ERROR")

                # Build the stats label
                parts = [f"⚡ {len(traces)} events"]
                if llm_count:
                    parts.append(f"{llm_count} LLM")
                if tool_count:
                    parts.append(f"{tool_count} tools")
                if route_count:
                    parts.append(f"{route_count} routes")
                if thinking_count:
                    parts.append(f"{thinking_count} thinking")
                if err_count:
                    parts.append(f"{err_count} errors")

                badge_text = "  ·  ".join(parts)

                # Snapshot the events for the button closure
                captured_events = list(traces)

                bar = Horizontal(classes="trace-action-bar")

                badge_static = Static(
                    f"[dim]{badge_text}[/dim]",
                    classes="trace-badge",
                    markup=True,
                )
                view_btn = Button(
                    "View Trace ⚡",
                    id=f"btn-view-trace-{id(traces)}",
                    classes="btn-view-trace",
                )
                # Store the snapshot on the widget so the app-level handler can pick it up
                setattr(view_btn, "_trace_events", captured_events)
                setattr(view_btn, "_trace_label", badge_text)

                def _mount_trace_bar() -> None:
                    if target_card is not None and hasattr(target_card, "mount_child"):
                        target_card.mount_child(bar)
                    else:
                        container = self.query_one("#messages")
                        container.mount(bar)
                    bar.mount(badge_static)
                    bar.mount(view_btn)

                self.call_after_refresh(_mount_trace_bar)

        # If developer mode is active, continuously and automatically update session dev artifacts
        if getattr(self, "developer_mode", False):
            try:
                import threading
                from pathlib import Path

                from sago.tracking.dev_tracer import export_session_dev_artifacts

                threading.Thread(
                    target=export_session_dev_artifacts,
                    args=(self.current_session_id, list(self.messages), Path.cwd()),
                    daemon=True,
                ).start()
            except Exception:
                pass

        # Turn finished -> clear active exchange card
        self._active_exchange_card = None
        self.query_one("#messages").scroll_end(animate=False)

    def _add_thinking_card(self: SagoApp, reasoning_text: str) -> None:
        """Add a dedicated collapsible technical reasoning card inside active turn box."""
        target_card = getattr(self, "_active_exchange_card", None)
        card = Collapsible(
            Static(reasoning_text, classes="thinking-text", markup=False),
            title="● Technical Reasoning & Analysis",
            collapsed=True,
        )
        if target_card is not None and hasattr(target_card, "mount_child"):
            target_card.mount_child(card)
        elif target_card is not None:
            target_card.mount(card)
        else:
            self.query_one("#messages").mount(card)
        self.query_one("#messages").scroll_end(animate=False)

    def _add_plan_card(self: SagoApp, plan_text: str, step_count: int = 0) -> None:
        """Add a dedicated collapsible plan card inside active turn box."""
        target_card = getattr(self, "_active_exchange_card", None)
        title = f"● Execution Plan ({step_count} steps)" if step_count else "● Execution Plan"
        card = Collapsible(
            Static(plan_text, classes="plan-text", markup=True),
            title=title,
            collapsed=True,
        )
        if target_card is not None and hasattr(target_card, "mount_child"):
            target_card.mount_child(card)
        elif target_card is not None:
            target_card.mount(card)
        else:
            self.query_one("#messages").mount(card)
        self.query_one("#messages").scroll_end(animate=False)

    def _add_agent_message(self: SagoApp, agent_name: str, content: str) -> None:
        """Add a message with explicit agent tagging."""
        self._add_assistant_message(content, agent_name=agent_name)

    def _add_system_message(self: SagoApp, content: str) -> None:
        self._hide_welcome_screen()
        clean_text = content.strip()
        self.query_one("#messages").mount(
            Static(
                f"[dim yellow]●[/dim yellow] [dim]{clean_text}[/dim]",
                classes="msg-system",
                markup=True,
            )
        )
        self.query_one("#messages").scroll_end(animate=False)

    def _add_error_inline(self: SagoApp, content: str, hint: str = "") -> None:
        """Mount an error inline inside the active exchange card, or fall back to msg-system."""
        self._hide_welcome_screen()
        from rich.markup import escape as _escape

        clean = content.strip()
        hint_part = f"\n[dim]{_escape(hint)}[/dim]" if hint else ""
        widget = Static(
            f"[bold #f85149]✗ Error:[/bold #f85149] {_escape(clean)}{hint_part}",
            classes="msg-error-inline",
            markup=True,
        )
        target_card = getattr(self, "_active_exchange_card", None)
        if target_card is not None and hasattr(target_card, "mount_child"):
            target_card.mount_child(widget)
        else:
            # No active card — render as a standalone system notice
            self.query_one("#messages").mount(widget)
        self.query_one("#messages").scroll_end(animate=False)

    def _add_notice_inline(self: SagoApp, content: str) -> None:
        """Mount an informational notice inline inside the active exchange card."""
        self._hide_welcome_screen()
        from rich.markup import escape as _escape

        widget = Static(
            f"[dim]ℹ {_escape(content.strip())}[/dim]",
            classes="msg-notice-inline",
            markup=True,
        )
        target_card = getattr(self, "_active_exchange_card", None)
        if target_card is not None and hasattr(target_card, "mount_child"):
            target_card.mount_child(widget)
        else:
            self.query_one("#messages").mount(widget)
        self.query_one("#messages").scroll_end(animate=False)

    def _add_tool_call(
        self: SagoApp, tool_name: str, args: dict, result: str, success: bool = True
    ) -> None:
        if not hasattr(self, "session_tool_calls"):
            self.session_tool_calls = []
        self.session_tool_calls.append({"tool": tool_name, "success": success})

        status_tag = "[bold green]● OK[/bold green]" if success else "[bold red]✗ FAILED[/bold red]"
        title = f"{status_tag} Tool: [bold cyan]{tool_name}[/bold cyan]"

        param_lines = []
        for k, v in args.items():
            val_str = str(v)
            if len(val_str) > 300:
                val_str = val_str[:300] + "..."
            param_lines.append(f"  [bold cyan]{k}[/bold cyan]: [white]{val_str}[/white]")
        args_str = "\n".join(param_lines) if param_lines else "  [dim](no parameters)[/dim]"

        preview_res = result[:2000] if result else "(empty)"
        if len(result) > 2000:
            preview_res += f"\n... [dim]({len(result)} characters total)[/dim]"

        body = (
            f"[bold yellow]Parameters:[/bold yellow]\n{args_str}\n\n"
            f"[bold green]Result Output:[/bold green]\n{preview_res}"
        )

        card = Collapsible(
            Static(body, classes="msg-system", markup=True),
            title=title,
            collapsed=True,
        )

        target_card = getattr(self, "_active_exchange_card", None)
        if target_card is not None and hasattr(target_card, "mount_child"):
            target_card.mount_child(card)
        elif target_card is not None:
            target_card.mount(card)
        else:
            self.query_one("#messages").mount(card)

        self.query_one("#messages").scroll_end(animate=False)

    def _add_parallel_result(
        self: SagoApp, agent_name: str, result: str, elapsed: float, success: bool
    ) -> None:
        """Add a result from a parallel agent execution with copy button & code syntax."""
        color = get_agent_color(agent_name)
        status_icon = "✓" if success else "✗"
        header = f"[{color}][bold]{status_icon} [AGENT: {agent_name}][/bold][/{color}] [dim](completed in {elapsed:.1f}s)[/dim]"

        container = self.query_one("#messages")

        if "```" in result:
            parts = result.split("```")
            for i, part in enumerate(parts):
                if i % 2 == 0:
                    rendered = _render_markdown(part.strip())
                    if rendered.strip():
                        if i == 0:
                            container.mount(
                                Static(
                                    f"{header}\n\n{rendered}",
                                    classes="msg-assistant",
                                    markup=True,
                                )
                            )
                        else:
                            container.mount(Static(rendered, classes="msg-assistant", markup=True))
                else:
                    lines = part.split("\n", 1)
                    lang = lines[0].strip() if len(lines) > 1 else ""
                    code = lines[1] if len(lines) > 1 else lines[0]
                    code = code.rstrip().removesuffix("```").rstrip()
                    if code.strip():
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
                                    title=f"{agent_name} - Code ({lang or 'text'})",
                                    collapsed=False,
                                )
                            )
                        except Exception:
                            container.mount(
                                Collapsible(
                                    Static(code, classes="code-block", markup=False),
                                    title=f"{agent_name} - Code ({lang or 'text'})",
                                    collapsed=False,
                                )
                            )
        else:
            rendered = _render_markdown(result)
            container.mount(Static(f"{header}\n\n{rendered}", classes="msg-assistant", markup=True))
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

        title = f"📊 Turn Summary ({elapsed:.1f}s)" if elapsed > 0 else "📊 Turn Summary"
        card = Collapsible(
            Static("\n".join(lines), classes="summary-box", markup=False),
            title=title,
            collapsed=True,
        )
        target_card = getattr(self, "_active_exchange_card", None)
        if target_card is not None and hasattr(target_card, "mount_child"):
            target_card.mount_child(card)
        elif target_card is not None:
            target_card.mount(card)
        else:
            self.query_one("#messages").mount(card)
        self.query_one("#messages").scroll_end(animate=False)

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
                from sago.database import MessageStore, Session

                if not hasattr(self, "_message_store") or self._message_store is None:
                    self._message_store = MessageStore(self.current_session_id)
                self._message_store.add(
                    role=role,
                    content=content,
                    agent_name=self.current_agent,
                    metadata=metadata,
                )
                self._message_store.flush()

                # Automatically update session title with first real user prompt (ignoring slash commands)
                if role == "user" and content and not content.strip().startswith("/"):
                    try:
                        s = Session(self.current_session_id)
                        curr_session = s.get()
                        if curr_session and (
                            not curr_session.get("title")
                            or curr_session.get("title") == "TUI Session"
                        ):
                            prompt_title = content.strip().split("\n")[0][:45]
                            s.update(title=prompt_title)
                    except Exception:
                        pass
            except Exception:
                pass
