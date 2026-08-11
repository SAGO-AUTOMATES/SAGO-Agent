"""TUI Helpers - UI helper methods for displaying messages and tool calls."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from rich.syntax import Syntax
from textual.widgets import Collapsible, Static

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

    # Ordered list: 1. item → 1. item (keep as-is)
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

    def _add_assistant_message(self: SagoApp, content: str, meta: str = "") -> None:
        self.messages.append({"role": "assistant", "content": content})
        container = self.query_one("#messages")

        display = content
        if meta:
            display += f"\n\n{meta}"

        if "```" not in display:
            # Plain text — render markdown formatting
            rendered = _render_markdown(display)
            container.mount(Static(rendered, classes="msg-assistant"))
        else:
            # Has code blocks — render each part
            parts = display.split("```")
            for i, part in enumerate(parts):
                if i % 2 == 0:
                    # Text outside code blocks
                    rendered = _render_markdown(part.strip())
                    if rendered.strip():
                        container.mount(Static(rendered, classes="msg-assistant"))
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
                        # Mount syntax-highlighted code block
                        container.mount(
                            Collapsible(
                                Static(syntax),
                                title=f"Code ({lang or 'text'})",
                                collapsed=False,
                            )
                        )
                    except Exception:
                        # Fallback to plain code block
                        container.mount(Static(code, classes="code-block"))

        container.scroll_end()
        self._save_message("assistant", content)

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

    def _save_message(self: SagoApp, role: str, content: str) -> None:
        if self.current_session_id and self.current_session_id != "local":
            try:
                from sago.database import MessageStore

                ms = MessageStore(self.current_session_id)
                ms.add(role=role, content=content, agent_name=self.current_agent)
                ms.close()
            except Exception:
                pass
