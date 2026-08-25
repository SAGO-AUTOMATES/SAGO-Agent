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
from sago.utils.safe import log_exception


def _safe_static(text: str, classes: str = "", markup: bool = True) -> Static:
    """Create Static that never crashes on MarkupError (lazy render).

    Textual's Content.from_markup is evaluated lazily during render/layout.
    If dynamic content produces invalid markup (e.g. "'][/white]"), the
    exception surfaces in get_content_height and kills the TUI. This helper
    pre-validates markup and falls back to markup=False + escaped text.
    """
    if not markup:
        return Static(text, classes=classes, markup=False)
    try:
        # Pre-validate: this is what Static will do during render
        from textual.content import Content

        Content.from_markup(text)
        return Static(text, classes=classes, markup=True)
    except Exception:
        # Fallback: render as plain text (still with markup=False, no crash)
        try:
            from rich.markup import escape as _esc

            return Static(_esc(text), classes=classes, markup=False)
        except Exception:
            return Static(text, classes=classes, markup=False)


if TYPE_CHECKING:
    from sago.tui.app import SagoApp


def _render_markdown(content: str) -> str:
    """Format markdown content cleanly into Rich terminal markup."""
    from rich.markup import escape as _escape

    # Escape any Rich markup in the raw content first to prevent LLM output
    # from being interpreted as style tags (e.g. [c8caa51e] -> \[c8caa51e\])
    text = _escape(content)

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


def _render_markdown_rich(content: str) -> Any:
    """Render markdown content as a Rich renderable (for proper formatting).

    Escapes Rich markup in the raw content first to prevent LLM output
    from being interpreted as style tags, then renders as Markdown.
    """
    from rich.markdown import Markdown as RichMarkdown

    text = escape(content)
    return RichMarkdown(text)


def _make_code_copy_button(code: str) -> Button:
    """Create a copy button that stores code for clipboard handler in app.py."""
    btn = Button("📋 Copy Code", classes="btn-copy-code")
    btn._code_content = code  # type: ignore[attr-defined]
    return btn


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
        self._response_container: Vertical | None = None

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
            from rich.markdown import Markdown as RichMarkdown

            body_header = (
                "User Prompt:" if self.card_type == "user" else f"{self.tag_label.title()} Target:"
            )
            yield Static(
                f"[bold {self.tag_color}]{body_header}[/bold {self.tag_color}]",
                classes="exchange-user-prompt-header",
                markup=True,
            )
            yield Static(RichMarkdown(self.prompt), classes="exchange-user-prompt markdown-body")
            yield Static("─" * 40, classes="exchange-divider", markup=False)
            # Response container - hidden until content mounts
            self._response_container = Vertical(classes="exchange-response")
            self._response_container.display = False
            yield self._response_container

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
        except Exception as e:
            log_exception(e, "toggle exchange turn collapse")

    def mount_child(self, widget: Any) -> None:
        """Mount child widget inside exchange body."""
        try:
            body = self.query_one(".exchange-body")
            body.mount(widget)
        except Exception as e:
            log_exception(e, "fallback mount exchange turn widget")
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
        except Exception as e:
            log_exception(e, "toggle collapsible output card")


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
        except Exception as e:
            log_exception(e, "toggle shell escape card collapse")

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
        except Exception as e:
            log_exception(e, "update shell escape card result")


def _summarize_tool_result(result: str) -> str:
    """Create a smart summary of tool result output instead of naive truncation."""
    from rich.markup import escape as _escape

    if not result or not result.strip():
        return "[dim](empty)[/dim]"

    lines = result.strip().split("\n")
    total_chars = len(result)
    total_lines = len(lines)

    # Short results: show as-is
    if total_chars <= 1500:
        return _escape(result)

    # Smart summary based on content detection
    summary_parts: list[str] = []

    # Detect content type
    is_file_listing = any(
        line.strip().startswith(("sago/", "src/", "lib/", "tests/", "./"))
        or line.strip().startswith("- ")
        for line in lines[:20]
    )
    is_json = result.strip().startswith(("{", "["))
    is_code = any(
        kw in result[:500]
        for kw in ("def ", "class ", "function ", "import ", "from ", "const ", "let ", "var ")
    )
    is_error = any(
        kw in result[:500].lower()
        for kw in ("error", "traceback", "exception", "failed", "warning")
    )
    is_search_result = any(
        kw in result[:500].lower() for kw in ("match", "found", "results", "grep", "search")
    )

    # Header with metadata
    if is_file_listing:
        file_count = sum(1 for line in lines if "." in line and "/" not in line.lstrip()[:1])
        summary_parts.append(f"[dim]File listing: {total_lines} lines, ~{file_count} files[/dim]")
    elif is_json:
        summary_parts.append(f"[dim]JSON response: {total_chars} chars, {total_lines} lines[/dim]")
    elif is_code:
        summary_parts.append(f"[dim]Code output: {total_lines} lines[/dim]")
    elif is_error:
        summary_parts.append(f"[dim]Error output: {total_lines} lines[/dim]")
    elif is_search_result:
        match_count = sum(
            1 for line in lines if line.strip().startswith(("sago/", "src/", "tests/"))
        )
        summary_parts.append(
            f"[dim]Search results: {match_count} matches in {total_lines} lines[/dim]"
        )
    else:
        summary_parts.append(f"[dim]Output: {total_lines} lines, {total_chars} chars[/dim]")

    # Show first ~30 lines (most tools put important output first)
    head_lines = lines[:30]
    summary_parts.append(_escape("\n".join(head_lines)))

    if total_lines > 30:
        # Show last ~10 lines (often contains summary/summary info)
        tail_start = max(0, total_lines - 10)
        tail_lines = lines[tail_start:]
        summary_parts.append(f"\n[dim]... ({total_lines - 30} lines omitted) ...[/dim]")
        summary_parts.append(_escape("\n".join(tail_lines)))

    # Footer with stats
    summary_parts.append(f"\n[dim]── Total: {total_lines} lines, {total_chars:,} chars ──[/dim]")

    return "\n".join(summary_parts)


class UIHelpers:
    """Mixin class providing UI helper methods for SagoApp."""

    def _add_user_message(self: SagoApp, content: str) -> None:
        self._hide_welcome_screen()
        self.messages.append({"role": "user", "content": content})
        self._save_message("user", content)

        # Synthesize smart one-liner session title (only for new sessions without a title)
        from sago.engine.prompt_enhancer import generate_session_title

        current_title = getattr(self, "current_session_title", "")
        if not current_title or current_title in ("TUI Session", "Interactive Session"):
            self.current_session_title = generate_session_title(content)
            try:
                from sago.database import Session

                s = Session(self.current_session_id)
                s.update(title=self.current_session_title)
                s.close()
            except Exception as e:
                log_exception(e, "update session title in database")

        # Create unified ExchangeTurnCard
        turn_card = ExchangeTurnCard(prompt=content, card_type="user")
        self._active_exchange_card = turn_card
        msg_container = self.query_one("#messages")
        msg_container.mount(turn_card)
        msg_container.scroll_end(animate=False)

    def _update_last_user_message_metadata(self: SagoApp, metadata: dict) -> None:
        """Update the last user message's metadata in the database."""
        if getattr(self, "_loading_session", False):
            return
        if self.current_session_id and self.current_session_id != "local":
            try:
                from sago.database import MessageStore

                if not hasattr(self, "_message_store") or self._message_store is None:
                    self._message_store = MessageStore(self.current_session_id)
                # Update the last user message with enhancement metadata
                self._message_store.update_last_user_metadata(
                    agent_name=self.current_agent,
                    metadata=metadata,
                )
            except Exception as e:
                log_exception(e, "update user message metadata")

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

        from rich.markup import escape
        from textual.widgets import Collapsible

        raw_tags = getattr(enhancement, "improvements", [])[:4]
        tags = " • ".join(escape(str(t)) for t in raw_tags)
        intent_summary = escape(str(getattr(enhancement, "intent_summary", "")))
        enhanced_prompt = escape(str(getattr(enhancement, "enhanced_prompt", "")))
        original_prompt = escape(str(getattr(enhancement, "original_prompt", "")))
        raw_crit = getattr(enhancement, "acceptance_criteria", [])
        crit_lines = "\n".join(f"  {i + 1}. {escape(str(c))}" for i, c in enumerate(raw_crit))
        raw_targets = getattr(enhancement, "target_scope", [])
        targets = ", ".join(escape(str(t)) for t in raw_targets)

        card_lines = []
        if original_prompt:
            card_lines.append(f"[dim]Original:[/] [white]{original_prompt}[/white]")
        card_lines.append(f"[bold #58a6ff]Goal:[/] [white]{intent_summary}[/white]")
        if targets:
            card_lines.append(f"[dim]Targets:[/] [cyan]{targets}[/cyan]")
        if tags:
            card_lines.append(f"[dim]Additions:[/] [green]{tags}[/green]")
        if crit_lines:
            card_lines.append(f"\n[bold]Acceptance Criteria:[/]\n{crit_lines}")

        card_lines.append(
            f"\n[dim]── Enhanced Prompt Sent to Agent ──[/dim]\n[white]{enhanced_prompt}[/white]"
        )

        title = (
            f"✨ Enhanced Prompt: {intent_summary[:80]}" if intent_summary else "✨ Enhanced Prompt"
        )

        target_card = getattr(self, "_active_exchange_card", None)
        resp_container = None
        if target_card is not None:
            try:
                resp_container = target_card.query_one(".exchange-response")
            except Exception:
                pass

        # Single collapsed card only — the previous inline one-liner + card was duplicate
        # Keep just the collapsible (contains the one-liner as its title summary)
        # Use safe static: pre-validates markup, falls back to plaintext on stray "'][/white]"
        card = Collapsible(
            _safe_static("\n".join(card_lines), markup=True),
            title=title,
            collapsed=True,
        )

        if resp_container is not None:
            try:
                target_card.query_one(".exchange-body").mount(card, before=resp_container)
            except Exception:
                target_card.mount(card)
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
            """Mount into response container with fallback to #messages."""
            try:
                if target_card is not None:
                    resp = getattr(target_card, "_response_container", None)
                    if resp is not None:
                        resp.display = True
                        resp.mount(elem)
                        return
                    target_card.mount(elem)
                    return
            except Exception as mount_err:
                log_exception(mount_err, "mount into response container")
            # Ultimate fallback: mount directly on #messages
            try:
                self.query_one("#messages").mount(elem)
            except Exception as fallback_err:
                log_exception(fallback_err, "fallback mount on #messages")

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
            # Escape agent_name to prevent markup injection like "'][/white]"
            agent_prefix = f"[{color}][AGENT: {escape(agent_name)}][/{color}]\n"
        else:
            agent_prefix = "[bold green][SAGO][/bold green]\n"

        try:
            if "```" not in display:
                # Use Rich Markdown renderer for proper formatting
                from rich.markdown import Markdown as RichMarkdown

                md = RichMarkdown(display)
                _mount_element(
                    _safe_static(agent_prefix, classes="exchange-assistant agent-tag", markup=True)
                )
                _mount_element(Static(md, classes="exchange-assistant markdown-body"))
            else:
                parts = display.split("```")
                first_text = True
                for i, part in enumerate(parts):
                    if i % 2 == 0:
                        text_content = part.strip()
                        if text_content:
                            prefix = agent_prefix if first_text else ""
                            first_text = False
                            if prefix:
                                _mount_element(
                                    _safe_static(
                                        prefix, classes="exchange-assistant agent-tag", markup=True
                                    )
                                )
                            from rich.markdown import Markdown as RichMarkdown

                            md = RichMarkdown(text_content)
                            _mount_element(Static(md, classes="exchange-assistant markdown-body"))
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
                                    collapsed=True,
                                )
                            )
                            # Copy button for easy clipboard access (Textual captures mouse otherwise)
                            try:
                                copy_bar = Horizontal(classes="code-action-bar")
                                copy_btn = _make_code_copy_button(code)
                                _mount_element(copy_bar)
                                copy_bar.mount(Static("", classes="spacer"))
                                copy_bar.mount(copy_btn)
                            except Exception:
                                pass
                        except Exception as e:
                            log_exception(e, "render code syntax highlighting")
                            _mount_element(
                                Collapsible(
                                    Static(code, classes="code-block", markup=False),
                                    title=f"Code snippet ({lang or 'text'})",
                                    collapsed=True,
                                )
                            )
                            try:
                                copy_bar = Horizontal(classes="code-action-bar")
                                copy_btn = _make_code_copy_button(code)
                                _mount_element(copy_bar)
                                copy_bar.mount(Static("", classes="spacer"))
                                copy_bar.mount(copy_btn)
                            except Exception:
                                pass
        except Exception as e:
            # Last resort: mount raw content as plain text
            log_exception(e, "mount assistant message content")
            try:
                _mount_element(Static(f"{agent_prefix}{display}", markup=False))
            except Exception as final_err:
                log_exception(final_err, "final fallback mount assistant message")

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
                    args=(
                        self.current_session_id,
                        list(self.messages),
                        Path.cwd(),
                        getattr(self, "session_tool_calls", None),
                    ),
                    daemon=True,
                ).start()
            except Exception as e:
                log_exception(e, "export session dev artifacts in background")

        # Turn finished -> clear active exchange card
        self._active_exchange_card = None
        self.query_one("#messages").scroll_end(animate=False)

    def _add_thinking_card(self: SagoApp, reasoning_text: str) -> None:
        """Add/update a single technical reasoning card inside active turn box.

        Spawns at TOP of exchange (between divider and response), not bottom.
        Dedupes per-turn: appends to existing card instead of creating 3 duplicates.
        Ignores synthetic spam like 'Step 1/30...' / 'Synthesized reasoning'.
        """
        # Filter synthetic BS - only real LLM reasoning should be visible
        low = reasoning_text.strip().lower()
        if not reasoning_text.strip():
            return
        # Ignore our own synthetic placeholders
        if low.startswith("thinking: step ") or low.startswith("synthesized reasoning"):
            return
        # Ignore super-short spinner text
        if len(reasoning_text.strip()) < 20:
            return

        target_card = getattr(self, "_active_exchange_card", None)
        if target_card is None:
            self.query_one("#messages").mount(
                Collapsible(
                    Static(reasoning_text, classes="thinking-text", markup=False),
                    title="● Technical Reasoning & Analysis",
                    collapsed=False,
                )
            )
            self.query_one("#messages").scroll_end(animate=False)
            return

        # Try to reuse existing thinking card for this turn (append, don't duplicate)
        try:
            # Check if we already have a thinking card for this exchange
            existing = getattr(target_card, "_thinking_card", None)
            if existing is not None:
                try:
                    # static inside collapsible
                    static = existing.query_one(".thinking-text", Static)
                    current = getattr(static, "_sago_thinking_text", "") or ""
                    # dedupe - don't append identical block
                    if reasoning_text.strip() in current:
                        return
                    new_text = (
                        current + "\n\n" + reasoning_text.strip()
                        if current
                        else reasoning_text.strip()
                    )
                    static.update(new_text)
                    static._sago_thinking_text = new_text  # type: ignore[attr-defined]
                    # Expand if it was collapsed
                    try:
                        existing.is_collapsed = False
                        existing.query_one(".card-body").display = True  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    self.query_one("#messages").scroll_end(animate=False)
                    return
                except Exception:
                    pass
        except Exception:
            pass

        # Create new card - mount at TOP (before response container)
        static_widget = Static(reasoning_text, classes="thinking-text", markup=False)
        static_widget._sago_thinking_text = reasoning_text.strip()  # type: ignore[attr-defined]
        card = Collapsible(
            static_widget,
            title="● Technical Reasoning & Analysis",
            collapsed=False,
        )
        # Remember for dedupe/append
        try:
            target_card._thinking_card = card  # type: ignore[attr-defined]
        except Exception:
            pass

        # Mount before exchange-response so it appears at top, not bottom
        try:
            body_widget = target_card.query_one(".exchange-body")
            try:
                resp = target_card.query_one(".exchange-response")
                body_widget.mount(card, before=resp)
            except Exception:
                body_widget.mount(card)
        except Exception:
            try:
                target_card.mount(card)
            except Exception:
                self.query_one("#messages").mount(card)
        self.query_one("#messages").scroll_end(animate=False)

    def _add_plan_card(self: SagoApp, plan_text: str, step_count: int = 0) -> None:
        """Add a dedicated collapsible plan card inside active turn box."""
        from rich.markup import escape as _escape

        target_card = getattr(self, "_active_exchange_card", None)
        title = f"● Execution Plan ({step_count} steps)" if step_count else "● Execution Plan"
        # Store the plan card reference for in-place updates
        card = Collapsible(
            _safe_static(_escape(plan_text), classes="plan-text", markup=True),
            title=title,
            collapsed=False,
        )
        # Keep reference for progress updates
        self._current_plan_card = card  # type: ignore[attr-defined]
        self._current_plan_steps = step_count  # type: ignore[attr-defined]
        if target_card is not None and hasattr(target_card, "mount_child"):
            target_card.mount_child(card)
        elif target_card is not None:
            target_card.mount(card)
        else:
            self.query_one("#messages").mount(card)
        self.query_one("#messages").scroll_end(animate=False)

    def _update_plan_progress(
        self: SagoApp, plan: Any, completed_idx: int, status: str = "completed"
    ) -> None:
        """Update the Execution Plan card in place (progress %, checkmarks)."""
        try:
            card = getattr(self, "_current_plan_card", None)
            if card is None:
                return
            # Find the plan-text Static inside the Collapsible
            try:
                static = card.query_one(".plan-text", Static)
            except Exception:
                return
            # Re-render with updated progress
            from sago.tasks import get_task_manager

            tm = get_task_manager()
            # Use the plan object to format, but update the static directly
            new_text = tm.format_plan(plan)
            # Update title to show progress
            try:
                card.title = (
                    f"● Execution Plan ({len(plan.todos)} steps) — {plan.progress:.0%} {status}"
                )
            except Exception:
                pass
            static.update(new_text)
            # Also update the collapsible title if needed
            try:
                card.query_one(Collapsible).title = f"Execution Plan — {plan.progress:.0%}"
            except Exception:
                pass
        except Exception as e:
            from sago.utils.safe import log_exception

            log_exception(e, "update plan progress in place")

    def _add_agent_message(self: SagoApp, agent_name: str, content: str) -> None:
        """Add a message with explicit agent tagging."""
        self._add_assistant_message(content, agent_name=agent_name)

    def _add_system_message(self: SagoApp, content: str | Any) -> None:
        self._hide_welcome_screen()
        from rich.text import Text

        if isinstance(content, Text):
            renderable = content
        else:
            clean_text = content.strip()
            has_prefix = (
                clean_text.startswith("⚡")
                or clean_text.startswith("●")
                or clean_text.startswith("\\[")
                or clean_text.startswith("[STOP]")
            )

            if has_prefix:
                renderable = Text.from_markup(clean_text)
            else:
                renderable = Text()
                renderable.append("● ", style="dim yellow")
                renderable.append_text(Text.from_markup(clean_text, style="dim"))

        try:
            self.query_one("#messages").mount(
                Static(
                    renderable,
                    classes="msg-system",
                )
            )
            self.query_one("#messages").scroll_end(animate=False)
        except Exception as e:
            log_exception(e, "mount system message")

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

        target_card = getattr(self, "_active_exchange_card", None)
        if target_card is None:
            return

        try:
            from rich.markup import escape as _escape

            status_tag = (
                "[bold green]● OK[/bold green]" if success else "[bold red]✗ FAILED[/bold red]"
            )
            title = f"{status_tag} Tool: [bold cyan]{_escape(tool_name)}[/bold cyan]"

            param_lines = []
            for k, v in args.items():
                val_str = str(v)
                if len(val_str) > 300:
                    val_str = val_str[:300] + "..."
                param_lines.append(
                    f"  [bold cyan]{_escape(k)}[/bold cyan]: [white]{_escape(val_str)}[/white]"
                )
            args_str = "\n".join(param_lines) if param_lines else "  [dim](no parameters)[/dim]"

            preview_res = _summarize_tool_result(result)

            body = (
                f"[bold yellow]Parameters:[/bold yellow]\n{args_str}\n\n"
                f"[bold green]Result Output:[/bold green]\n{preview_res}"
            )

            # Use safe static that pre-validates markup; body contains escaped
            # dynamic tool output like "|agents=339', 'path': '/mnt/ramdisk/sago]"
            # and would otherwise fail lazily during get_content_height.
            card = Collapsible(
                _safe_static(body, classes="msg-system", markup=True),
                title=title,
                collapsed=True,
            )

            # Insert into exchange body BEFORE response container so it appears
            # between the user prompt divider and the assistant text
            try:
                body_widget = target_card.query_one(".exchange-body")
                try:
                    resp = target_card.query_one(".exchange-response")
                    body_widget.mount(card, before=resp)
                except Exception:
                    body_widget.mount(card)
            except Exception:
                resp = getattr(target_card, "_response_container", None)
                if resp is not None:
                    try:
                        first_child = resp.children[0] if resp.children else None
                        if first_child is not None:
                            resp.mount(card, before=first_child)
                        else:
                            resp.mount(card)
                    except Exception:
                        resp.mount(card)
                else:
                    target_card.mount(card)
        except Exception as e:
            log_exception(e, "mount tool call")

        self.query_one("#messages").scroll_end(animate=False)

    def _add_parallel_result(
        self: SagoApp, agent_name: str, result: str, elapsed: float, success: bool
    ) -> None:
        """Add a result from a parallel agent execution with copy button & code syntax."""
        color = get_agent_color(agent_name)
        status_icon = "✓" if success else "✗"
        header = f"[{color}][bold]{status_icon} [AGENT: {agent_name}][/bold][/{color}] [dim](completed in {elapsed:.1f}s)[/dim]"

        # Mount into exchange card if available, otherwise fall back to #messages
        target_card = getattr(self, "_active_exchange_card", None)
        container = None
        if target_card is not None:
            container = getattr(target_card, "_response_container", None)
        if container is None:
            container = self.query_one("#messages")
        else:
            container.display = True

        try:
            if "```" in result:
                parts = result.split("```")
                for i, part in enumerate(parts):
                    if i % 2 == 0:
                        text_content = part.strip()
                        if text_content:
                            from rich.markdown import Markdown as RichMarkdown

                            md = RichMarkdown(text_content)
                            if i == 0:
                                container.mount(
                                    Static(
                                        header,
                                        classes="msg-assistant agent-tag",
                                        markup=True,
                                    )
                                )
                                container.mount(Static(md, classes="msg-assistant markdown-body"))
                            else:
                                container.mount(Static(md, classes="msg-assistant markdown-body"))
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
                                        collapsed=True,
                                    )
                                )
                                try:
                                    bar = Horizontal(classes="code-action-bar")
                                    btn = _make_code_copy_button(code)
                                    container.mount(bar)
                                    bar.mount(Static("", classes="spacer"))
                                    bar.mount(btn)
                                except Exception:
                                    pass
                            except Exception as e:
                                log_exception(e, "render code syntax in parallel result")
                                container.mount(
                                    Collapsible(
                                        Static(code, classes="code-block", markup=False),
                                        title=f"{agent_name} - Code ({lang or 'text'})",
                                        collapsed=True,
                                    )
                                )
                                try:
                                    bar = Horizontal(classes="code-action-bar")
                                    btn = _make_code_copy_button(code)
                                    container.mount(bar)
                                    bar.mount(Static("", classes="spacer"))
                                    bar.mount(btn)
                                except Exception:
                                    pass
            else:
                from rich.markdown import Markdown as RichMarkdown

                md = RichMarkdown(result)
                container.mount(Static(header, classes="msg-assistant agent-tag", markup=True))
                container.mount(Static(md, classes="msg-assistant markdown-body"))
            container.scroll_end()
        except Exception as e:
            log_exception(e, "mount parallel result")

    def _add_orchestrate_step(
        self: SagoApp,
        step_num: int,
        total_steps: int,
        agent_name: str,
        task: str,
        result: str,
        tools_used: list[str],
        success: bool,
        elapsed: float = 0.0,
    ) -> None:
        """Mount a single orchestration step result into the exchange card."""
        color = get_agent_color(agent_name)
        status_icon = "✓" if success else "✗"

        # Header with agent name, step number, elapsed — escape agent_name to avoid markup injection
        from rich.markup import escape as _escape

        header_parts = [
            f"[{color}][bold]{status_icon} Step {step_num}/{total_steps}: {_escape(agent_name)}[/bold][/{color}]",
        ]
        if elapsed > 0:
            header_parts.append(f"[dim]({elapsed:.1f}s)[/dim]")
        header = " ".join(header_parts)

        # Task line
        task_line = f"[dim]Task:[/] [white]{_escape(task[:120])}[/white]"

        # Tools used line
        tools_line = ""
        if tools_used:
            tool_names = ", ".join(tools_used[:5])
            tools_line = f"[dim]Tools:[/] [cyan]{_escape(tool_names)}[/cyan]"

        target_card = getattr(self, "_active_exchange_card", None)
        container = None
        if target_card is not None:
            container = getattr(target_card, "_response_container", None)
        if container is None:
            container = self.query_one("#messages")
        else:
            container.display = True

        try:
            # Mount header
            container.mount(Static(header, classes="msg-assistant agent-tag", markup=True))
            # Mount task
            container.mount(Static(task_line, classes="msg-assistant", markup=True))
            # Mount tools if any
            if tools_line:
                container.mount(Static(tools_line, classes="msg-assistant", markup=True))

            # Mount result content with code blocks
            if result and "```" in result:
                parts = result.split("```")
                for i, part in enumerate(parts):
                    if i % 2 == 0:
                        text_content = part.strip()
                        if text_content:
                            from rich.markdown import Markdown as RichMarkdown

                            md = RichMarkdown(text_content)
                            container.mount(Static(md, classes="msg-assistant markdown-body"))
                    else:
                        lines = part.split("\n", 1)
                        lang = lines[0].strip() if len(lines) > 1 else ""
                        code = lines[1] if len(lines) > 1 else lines[0]
                        code = code.rstrip().removesuffix("```").rstrip()
                        if code.strip():
                            try:
                                from rich.syntax import Syntax

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
                                        title=f"{agent_name} code ({lang or 'text'})",
                                        collapsed=True,
                                    )
                                )
                                try:
                                    bar = Horizontal(classes="code-action-bar")
                                    btn = _make_code_copy_button(code)
                                    container.mount(bar)
                                    bar.mount(Static("", classes="spacer"))
                                    bar.mount(btn)
                                except Exception:
                                    pass
                            except Exception:
                                container.mount(
                                    Static(
                                        f"[dim]{code[:500]}[/dim]",
                                        classes="msg-assistant",
                                        markup=False,
                                    )
                                )
                                try:
                                    bar = Horizontal(classes="code-action-bar")
                                    btn = _make_code_copy_button(code)
                                    container.mount(bar)
                                    bar.mount(Static("", classes="spacer"))
                                    bar.mount(btn)
                                except Exception:
                                    pass
            elif result:
                from rich.markdown import Markdown as RichMarkdown

                md = RichMarkdown(result[:3000])
                container.mount(Static(md, classes="msg-assistant markdown-body"))

            # Divider between steps
            container.mount(Static("[dim]─[/dim]", classes="msg-assistant", markup=True))
            container.scroll_end()
        except Exception as e:
            log_exception(e, "mount orchestrate step")

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
            except Exception as e:
                log_exception(e, "fetch active tasks for dashboard")

            content_widget.update("\n".join(lines))
        except Exception as e:
            log_exception(e, "update agent dashboard")

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
        # Skip saving during session load
        if getattr(self, "_loading_session", False):
            return
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
                    except Exception as e:
                        log_exception(e, "update session title on user message")
            except Exception as e:
                log_exception(e, "save message to database")
