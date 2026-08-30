"""Interactive Modals for SAGO TUI.

Provides full-screen modal overlays accessible via function keys:
- F3: Interactive Diff Inspector & File Changes (DiffViewerScreen)
- F4: Workspace File Tree Explorer with Rich Syntax Highlighting (FileExplorerScreen)
- F5: Session Manager with Message Preview & Instant Switcher (SessionManagerScreen)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from rich.markup import escape
from rich.syntax import Syntax
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, DirectoryTree, Label, OptionList, Static
from textual.widgets.option_list import Option

logger = logging.getLogger("sago.tui.modals")


# ─── F3: Interactive Diff Inspector ───────────────────────────────────────────


class DiffViewerScreen(ModalScreen):
    """Interactive workspace diff and change viewer modal (F3)."""

    DEFAULT_CSS = """
    DiffViewerScreen {
        align: center middle;
        background: rgba(5, 7, 10, 0.85);
    }
    #diff-dialog {
        width: 92%;
        height: 88%;
        background: #0d1117;
        border: solid #30363d;
        border-top: solid #58a6ff;
        padding: 1 2;
    }
    #diff-header {
        height: 3;
        dock: top;
        border-bottom: solid #21262d;
        layout: horizontal;
    }
    #diff-title {
        color: #58a6ff;
        text-style: bold;
        width: 1fr;
    }
    #diff-actions {
        width: auto;
        layout: horizontal;
    }
    #diff-body {
        height: 1fr;
        layout: horizontal;
    }
    #diff-file-list {
        width: 32%;
        height: 100%;
        border-right: solid #21262d;
        padding-right: 1;
    }
    #diff-content-scroll {
        width: 68%;
        height: 100%;
        padding-left: 1;
    }
    #diff-content {
        color: #e6edf3;
    }
    .modal-btn {
        margin-left: 1;
        min-width: 12;
        height: 3;
        background: #21262d;
        color: #c9d1d9;
    }
    .modal-btn:hover {
        background: #30363d;
        color: #ffffff;
    }
    .modal-btn-primary {
        background: #1f6feb;
        color: #ffffff;
        text-style: bold;
    }
    .modal-btn-primary:hover {
        background: #388bfd;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("r", "refresh_diff", "Refresh"),
    ]

    def __init__(self, target_file: str = "") -> None:
        super().__init__()
        self.target_file = target_file
        self._diff_map: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="diff-dialog"):
            with Horizontal(id="diff-header"):
                yield Label("🔍 Workspace Diff Inspector (F3)", id="diff-title")
                with Horizontal(id="diff-actions"):
                    yield Button("↻ Refresh (r)", id="btn-diff-refresh", classes="modal-btn")
                    yield Button("✕ Close (Esc)", id="btn-diff-close", classes="modal-btn")
            with Horizontal(id="diff-body"):
                with Vertical(id="diff-file-list"):
                    yield Label("[bold cyan]Changed Files:[/bold cyan]")
                    yield OptionList(id="diff-options")
                with VerticalScroll(id="diff-content-scroll"):
                    yield Static("[dim]Loading workspace diff...[/dim]", id="diff-content")

    def on_mount(self) -> None:
        self.action_refresh_diff()

    def action_refresh_diff(self) -> None:
        """Fetch git status and diffs."""
        import subprocess

        try:
            res = subprocess.run(
                ["git", "status", "--short"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            files = []
            if res.returncode == 0 and res.stdout.strip():
                for line in res.stdout.strip().splitlines():
                    parts = line.strip().split(None, 1)
                    if len(parts) >= 2:
                        status, fpath = parts[0], parts[1]
                        files.append((status, fpath))

            option_list = self.query_one("#diff-options", OptionList)
            option_list.clear_options()
            self._diff_map.clear()

            if not files:
                option_list.add_option(Option("No modified files"))
                self.query_one("#diff-content", Static).update(
                    "[bold green]✨ Clean Working Tree[/bold green]\n\n"
                    "No unstaged or staged changes detected in workspace."
                )
                return

            for status, fpath in files:
                diff_proc = subprocess.run(
                    ["git", "diff", "HEAD", "--", fpath],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                raw_diff = diff_proc.stdout if diff_proc.returncode == 0 else ""
                if not raw_diff:
                    raw_diff = f"[Untracked / New file: {fpath}]"
                self._diff_map[fpath] = raw_diff
                tag_col = "green" if status == "A" else ("yellow" if status == "M" else "red")
                option_list.add_option(
                    Option(f"[{tag_col}]{status:<2}[/{tag_col}] {fpath}", id=fpath)
                )

            initial_file = self.target_file if self.target_file in self._diff_map else files[0][1]
            self._display_file_diff(initial_file)

        except Exception as e:
            self.query_one("#diff-content", Static).update(f"[red]Error fetching diff: {e}[/red]")

    def _display_file_diff(self, file_path: str) -> None:
        diff_text = self._diff_map.get(file_path, "No diff available")
        formatted = []
        adds = sum(
            1
            for line in diff_text.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        dels = sum(
            1
            for line in diff_text.splitlines()
            if line.startswith("-") and not line.startswith("---")
        )

        header = (
            f"[bold cyan]File:[/] [bold white]{escape(file_path)}[/]  "
            f"[bold green]+{adds}[/] [bold red]-{dels}[/]\n"
            f"[dim]{'─' * 60}[/dim]\n"
        )
        formatted.append(header)

        for line in diff_text.splitlines():
            if line.startswith("diff --git") or line.startswith("index "):
                formatted.append(f"[bold yellow]{escape(line)}[/bold yellow]")
            elif line.startswith("--- ") or line.startswith("+++ "):
                formatted.append(f"[bold dim]{escape(line)}[/bold dim]")
            elif line.startswith("+"):
                formatted.append(f"[bold green]+ {escape(line[1:])}[/bold green]")
            elif line.startswith("-"):
                formatted.append(f"[bold red]- {escape(line[1:])}[/bold red]")
            elif line.startswith("@@"):
                formatted.append(f"[bold magenta]{escape(line)}[/bold magenta]")
            else:
                formatted.append(f"  {escape(line)}")
        self.query_one("#diff-content", Static).update("\n".join(formatted))

    @on(OptionList.OptionSelected, "#diff-options")
    def on_file_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id:
            self._display_file_diff(str(event.option.id))

    @on(Button.Pressed, "#btn-diff-refresh")
    def on_refresh_pressed(self) -> None:
        self.action_refresh_diff()

    @on(Button.Pressed, "#btn-diff-close")
    def on_close_pressed(self) -> None:
        self.dismiss()


# ─── F4: Workspace File Tree Explorer with Rich Syntax Highlighting ───────────


class FileExplorerScreen(ModalScreen):
    """Interactive workspace file tree and code inspection modal with syntax highlighting (F4)."""

    DEFAULT_CSS = """
    FileExplorerScreen {
        align: center middle;
        background: rgba(5, 7, 10, 0.85);
    }
    #file-dialog {
        width: 92%;
        height: 88%;
        background: #0d1117;
        border: solid #30363d;
        border-top: solid #3fb950;
        padding: 1 2;
    }
    #file-header {
        height: 3;
        dock: top;
        border-bottom: solid #21262d;
        layout: horizontal;
    }
    #file-title {
        color: #3fb950;
        text-style: bold;
        width: 1fr;
    }
    #file-body {
        height: 1fr;
        layout: horizontal;
    }
    #tree-container {
        width: 32%;
        height: 100%;
        border-right: solid #21262d;
        padding-right: 1;
    }
    #preview-container {
        width: 68%;
        height: 100%;
        padding-left: 1;
    }
    #file-preview {
        color: #e6edf3;
    }
    .modal-btn {
        margin-left: 1;
        min-width: 12;
        height: 3;
        background: #21262d;
        color: #c9d1d9;
    }
    .modal-btn:hover {
        background: #30363d;
        color: #ffffff;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
    ]

    _LEXER_MAP: dict[str, str] = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "jsx",
        ".tsx": "tsx",
        ".rs": "rust",
        ".go": "go",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".md": "markdown",
        ".sh": "bash",
        ".bash": "bash",
        ".html": "html",
        ".css": "css",
        ".sql": "sql",
        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
        ".hpp": "cpp",
        ".java": "java",
        ".rb": "ruby",
        ".php": "php",
    }

    def compose(self) -> ComposeResult:
        cwd = Path.cwd()
        with Vertical(id="file-dialog"):
            with Horizontal(id="file-header"):
                yield Label(f"📁 Workspace Explorer (F4) — {cwd.name}", id="file-title")
                yield Button("✕ Close (Esc)", id="btn-file-close", classes="modal-btn")
            with Horizontal(id="file-body"):
                with Vertical(id="tree-container"):
                    yield DirectoryTree(str(cwd), id="dir-tree")
                with VerticalScroll(id="preview-container"):
                    yield Static(
                        "[dim]Select a file from the workspace tree to view...[/dim]",
                        id="file-preview",
                    )

    @on(DirectoryTree.FileSelected, "#dir-tree")
    def on_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        path = event.path
        try:
            if path.stat().st_size > 500_000:
                self.query_one("#file-preview", Static).update(
                    f"[yellow]File is too large ({path.stat().st_size / 1024:.1f} KB) to preview inline.[/yellow]"
                )
                return

            text = path.read_text(encoding="utf-8", errors="replace")
            lexer = self._LEXER_MAP.get(path.suffix.lower(), "text")

            # Use Rich Syntax highlighting
            syntax = Syntax(
                text[:30000],
                lexer,
                theme="monokai",
                line_numbers=True,
                word_wrap=True,
            )
            self.query_one("#file-preview", Static).update(syntax)
        except Exception as e:
            self.query_one("#file-preview", Static).update(f"[red]Could not read file: {e}[/red]")

    @on(Button.Pressed, "#btn-file-close")
    def on_close_pressed(self) -> None:
        self.dismiss()


# ─── F5: Session Manager & Instant Switcher ───────────────────────────────────


class SessionManagerScreen(ModalScreen):
    """Interactive session switcher & history manager modal (F5)."""

    DEFAULT_CSS = """
    SessionManagerScreen {
        align: center middle;
        background: rgba(5, 7, 10, 0.85);
    }
    #session-dialog {
        width: 88%;
        height: 82%;
        background: #0d1117;
        border: solid #30363d;
        border-top: solid #d2a8ff;
        padding: 1 2;
    }
    #session-header {
        height: 3;
        dock: top;
        border-bottom: solid #21262d;
        layout: horizontal;
    }
    #session-title {
        color: #d2a8ff;
        text-style: bold;
        width: 1fr;
    }
    #session-body {
        height: 1fr;
        layout: horizontal;
    }
    #session-list-col {
        width: 42%;
        height: 100%;
        border-right: solid #21262d;
        padding-right: 1;
    }
    #session-detail-col {
        width: 58%;
        height: 100%;
        padding-left: 1;
    }
    .modal-btn {
        margin-left: 1;
        min-width: 12;
        height: 3;
        background: #21262d;
        color: #c9d1d9;
    }
    .modal-btn:hover {
        background: #30363d;
        color: #ffffff;
    }
    .modal-btn-primary {
        background: #8957e5;
        color: #ffffff;
        text-style: bold;
    }
    .modal-btn-primary:hover {
        background: #ab7df8;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("enter", "switch_selected_session", "Switch"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._sessions: list[dict[str, Any]] = []
        self._selected_sid: str = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="session-dialog"):
            with Horizontal(id="session-header"):
                yield Label("🔄 Session History & Switcher (F5)", id="session-title")
                with Horizontal(id="session-actions"):
                    yield Button(
                        "▶ Switch (Enter)",
                        id="btn-session-switch",
                        classes="modal-btn modal-btn-primary",
                    )
                    yield Button("✕ Close (Esc)", id="btn-session-close", classes="modal-btn")
            with Horizontal(id="session-body"):
                with Vertical(id="session-list-col"):
                    yield Label("[bold cyan]Saved Sessions:[/bold cyan]")
                    yield OptionList(id="session-options")
                with VerticalScroll(id="session-detail-col"):
                    yield Static(
                        "[dim]Select a session from the list to view chat preview...[/dim]",
                        id="session-details",
                    )

    def on_mount(self) -> None:
        self._load_sessions()

    def _load_sessions(self) -> None:
        from sago.database import Session

        option_list = self.query_one("#session-options", OptionList)
        option_list.clear_options()
        self._sessions = []

        try:
            with Session() as s:
                all_s = s.list_all(limit=50)
                self._sessions = all_s
                if not all_s:
                    option_list.add_option(Option("No saved sessions"))
                    self.query_one("#session-details", Static).update(
                        "[dim]No saved sessions found in database.[/dim]"
                    )
                    return

                for entry in all_s:
                    sid = entry.get("id", "unknown")
                    title = entry.get("title") or "Untitled Session"
                    created = entry.get("created_at", "")[:16].replace("T", " ")
                    option_list.add_option(Option(f"{title} [dim]({created})[/dim]", id=sid))

                if all_s:
                    self._selected_sid = str(all_s[0].get("id", ""))
                    self._show_details(all_s[0])
        except Exception as e:
            self.query_one("#session-details", Static).update(
                f"[red]Error loading sessions: {e}[/red]"
            )

    def _show_details(self, entry: dict[str, Any]) -> None:
        sid = entry.get("id", "")
        self._selected_sid = sid
        title = entry.get("title", "Untitled")
        created = entry.get("created_at", "")[:19].replace("T", " ")
        status = entry.get("status", "active")

        # Parse workspace path
        workspace_cwd = ""
        raw_meta = entry.get("metadata")
        if raw_meta:
            try:
                import json

                meta = json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta
                workspace_cwd = meta.get("workspace_cwd", "")
            except Exception:
                pass

        # Load recent messages preview for this session
        msg_preview_lines = []
        try:
            from sago.database import MessageStore

            ms = MessageStore(sid)
            history = ms.get_history(limit=6)
            ms.close()
            if history:
                msg_preview_lines.append(
                    "\n[bold yellow]Recent Conversation Highlights:[/bold yellow]"
                )
                for m in history:
                    r = m.get("role", "user")
                    c = (m.get("content") or "").strip()
                    c_short = c[:100] + ("..." if len(c) > 100 else "")
                    if r == "user":
                        msg_preview_lines.append(f"  [cyan]User:[/] {escape(c_short)}")
                    else:
                        msg_preview_lines.append(f"  [green]Assistant:[/] {escape(c_short)}")
        except Exception:
            pass

        lines = [
            f"[bold magenta]Session Title:[/] [bold white]{escape(title)}[/bold white]",
            f"[bold cyan]Session ID:[/] `{sid}`",
            f"[bold cyan]Status:[/] {status}    [bold cyan]Created:[/] {created}",
        ]
        if workspace_cwd:
            lines.append(f"[bold cyan]Workspace Root:[/] `{escape(workspace_cwd)}`")

        if msg_preview_lines:
            lines.extend(msg_preview_lines)

        lines.extend(
            [
                "",
                "[bold green]▶ Click 'Switch' or press Enter to resume this conversation.[/bold green]",
            ]
        )
        self.query_one("#session-details", Static).update("\n".join(lines))

    def action_switch_selected_session(self) -> None:
        """Switch to currently selected session."""
        if self._selected_sid:
            app = self.app
            self.dismiss()
            if hasattr(app, "_load_session"):
                app._load_session(self._selected_sid)

    @on(OptionList.OptionSelected, "#session-options")
    def on_session_selected(self, event: OptionList.OptionSelected) -> None:
        sid = str(event.option.id) if event.option.id else ""
        for s in self._sessions:
            if s.get("id") == sid:
                self._show_details(s)
                break

    @on(Button.Pressed, "#btn-session-switch")
    def on_switch_pressed(self) -> None:
        self.action_switch_selected_session()

    @on(Button.Pressed, "#btn-session-close")
    def on_close_pressed(self) -> None:
        self.dismiss()
