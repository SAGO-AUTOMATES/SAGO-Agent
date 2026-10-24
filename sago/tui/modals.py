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
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, DirectoryTree, Input, Label, OptionList, Select, Static
from textual.widgets.option_list import Option

from sago.tui.helpers import _get_syntax_theme

logger = logging.getLogger("sago.tui.modals")

_THEMES = [
    "obsidian",
    "nord",
    "dracula",
    "monokai",
    "tokyo-night",
    "solarized-dark",
    "cyberpunk",
    "catppuccin-mocha",
    "gruvbox-dark",
    "rose-pine",
]


def _apply_theme(screen: ModalScreen) -> None:
    """Apply the current app theme class to a modal screen."""
    try:
        theme = getattr(screen.app, "sago_theme", "obsidian")
        for t in _THEMES:
            screen.remove_class(f"theme-{t}")
        if theme and theme != "obsidian":
            screen.add_class(f"theme-{theme}")
    except Exception:
        pass


# ─── F3: Interactive Diff Inspector ───────────────────────────────────────────


class DiffViewerScreen(ModalScreen):
    """Interactive workspace diff and change viewer modal (F3)."""

    DEFAULT_CSS = """
    DiffViewerScreen {
        align: center middle;
        background: rgba(1, 4, 9, 0.88);
    }
    #diff-dialog {
        width: 94%;
        height: 90%;
        background: #0d1117;
        border: solid #1c2128;
        border-top: solid #58a6ff;
        padding: 0 1 1 1;
    }
    #diff-header {
        height: 3;
        dock: top;
        padding: 0 1;
        border-bottom: solid #1c2128;
    }
    #diff-title {
        text-style: bold;
        width: 1fr;
        padding: 0 0 0 1;
        color: #58a6ff;
    }
    #diff-hints {
        color: #484f58;
        width: auto;
        padding: 0 1 0 0;
        content-align: right middle;
    }
    #diff-body {
        height: 1fr;
        layout: horizontal;
    }
    #diff-file-list {
        width: 32%;
        height: 100%;
        border-right: solid #1c2128;
        padding: 1 1 0 0;
    }
    #diff-file-label {
        color: #8b949e;
        text-style: bold;
        padding: 0 0 1 0;
    }
    #diff-options {
        background: #0d1117;
        border: none;
        overflow-y: scroll;
        scrollbar-gutter: stable;
        scrollbar-size-vertical: 1;
        scrollbar-size-horizontal: 0;
        scrollbar-color: #388bfd #161b22;
        scrollbar-color-hover: #79c0ff #161b22;
    }
    #diff-content-scroll {
        width: 68%;
        height: 100%;
        padding: 0 0 0 1;
        overflow-y: scroll;
        scrollbar-gutter: stable;
        scrollbar-size-vertical: 1;
        scrollbar-size-horizontal: 0;
        scrollbar-color: #388bfd #161b22;
        scrollbar-color-hover: #79c0ff #161b22;
    }
    #diff-content {
        color: #c9d1d9;
        padding: 1 0 0 0;
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
                yield Label("± Workspace Diff", id="diff-title")
                yield Static("[dim]R Refresh · Esc Close[/dim]", id="diff-hints")
            with Horizontal(id="diff-body"):
                with Vertical(id="diff-file-list"):
                    yield Label("CHANGED FILES", id="diff-file-label")
                    yield OptionList(id="diff-options")
                with VerticalScroll(id="diff-content-scroll"):
                    yield Static("[dim]Select a file to view its diff...[/dim]", id="diff-content")

    def on_mount(self) -> None:
        _apply_theme(self)
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

            try:
                option_list = self.query_one("#diff-options", OptionList)
                option_list.clear_options()
            except Exception:
                return
            self._diff_map.clear()

            if not files:
                option_list.add_option(Option("No modified files"))
                try:
                    self.query_one("#diff-content", Static).update(
                        "[bold green]Clean Working Tree[/bold green]\n\n"
                        "No unstaged or staged changes detected."
                    )
                except Exception:
                    pass
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
                    raw_diff = f"[Untracked: {fpath}]"
                self._diff_map[fpath] = raw_diff
                tag_col = "green" if status == "A" else ("yellow" if status == "M" else "red")
                option_list.add_option(
                    Option(f"[{tag_col}]{status:<2}[/{tag_col}] {escape(fpath)}", id=fpath)
                )

            initial_file = self.target_file if self.target_file in self._diff_map else files[0][1]
            self._display_file_diff(initial_file)

        except Exception as e:
            try:
                self.query_one("#diff-content", Static).update(
                    f"[red]Error fetching diff: {e}[/red]"
                )
            except Exception:
                pass

    def _display_file_diff(self, file_path: str) -> None:
        diff_text = self._diff_map.get(file_path, "No diff available")

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

        styled = Text()
        styled.append(f"  {file_path}\n", style="bold white")
        styled.append(f"  +{adds} ", style="bold green")
        styled.append(f"-{dels}\n\n", style="bold red")

        for line in diff_text.splitlines():
            if line.startswith("diff --git") or line.startswith("index "):
                styled.append(line + "\n", style="bold yellow")
            elif line.startswith("--- ") or line.startswith("+++ "):
                styled.append(line + "\n", style="dim")
            elif line.startswith("+"):
                styled.append("+ " + line[1:] + "\n", style="green")
            elif line.startswith("-"):
                styled.append("- " + line[1:] + "\n", style="red")
            elif line.startswith("@@"):
                styled.append(line + "\n", style="bold magenta")
            elif line.startswith("Binary"):
                styled.append(line + "\n", style="dim italic")
            else:
                styled.append(line + "\n")

        self.query_one("#diff-content", Static).update(styled)

    @on(OptionList.OptionSelected, "#diff-options")
    def on_file_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id:
            self._display_file_diff(str(event.option.id))


# ─── F4: Workspace File Tree Explorer with Rich Syntax Highlighting ───────────


class FileExplorerScreen(ModalScreen):
    """Interactive workspace file tree and code inspection modal with syntax highlighting (F4)."""

    DEFAULT_CSS = """
    FileExplorerScreen {
        align: center middle;
        background: rgba(1, 4, 9, 0.88);
    }
    #file-dialog {
        width: 94%;
        height: 90%;
        background: #0d1117;
        border: solid #1c2128;
        border-top: solid #3fb950;
        padding: 0 1 1 1;
    }
    #file-header {
        height: 3;
        dock: top;
        padding: 0 1;
        border-bottom: solid #1c2128;
    }
    #file-title {
        text-style: bold;
        width: 1fr;
        padding: 0 0 0 1;
        color: #3fb950;
    }
    #file-hints {
        color: #484f58;
        width: auto;
        padding: 0 1 0 0;
        content-align: right middle;
    }
    #file-body {
        height: 1fr;
        layout: horizontal;
    }
    #tree-container {
        width: 32%;
        height: 100%;
        border-right: solid #1c2128;
        padding-right: 1;
    }
    DirectoryTree {
        background: #0d1117;
        border: none;
        overflow-y: scroll;
        scrollbar-gutter: stable;
        scrollbar-size-vertical: 1;
        scrollbar-size-horizontal: 0;
        scrollbar-color: #388bfd #161b22;
        scrollbar-color-hover: #79c0ff #161b22;
    }
    #preview-container {
        width: 68%;
        height: 100%;
        padding-left: 1;
        overflow-y: scroll;
        scrollbar-gutter: stable;
        scrollbar-size-vertical: 1;
        scrollbar-size-horizontal: 0;
        scrollbar-color: #388bfd #161b22;
        scrollbar-color-hover: #79c0ff #161b22;
    }
    #file-preview {
        color: #c9d1d9;
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

    _BINARY_EXTS = frozenset(
        {
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".bmp",
            ".ico",
            ".svg",
            ".webp",
            ".mp3",
            ".mp4",
            ".wav",
            ".ogg",
            ".flac",
            ".m4a",
            ".wma",
            ".zip",
            ".tar",
            ".gz",
            ".bz2",
            ".xz",
            ".7z",
            ".rar",
            ".pdf",
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            ".ppt",
            ".pptx",
            ".exe",
            ".dll",
            ".so",
            ".dylib",
            ".bin",
            ".dat",
            ".pyc",
            ".pyo",
            ".class",
            ".o",
            ".a",
        }
    )

    def compose(self) -> ComposeResult:
        cwd = Path.cwd()
        with Vertical(id="file-dialog"):
            with Horizontal(id="file-header"):
                yield Label(f"▤ Workspace Explorer — {cwd.name}", id="file-title")
                yield Static("[dim]Esc Close[/dim]", id="file-hints")
            with Horizontal(id="file-body"):
                with Vertical(id="tree-container"):
                    yield DirectoryTree(str(cwd), id="dir-tree")
                with VerticalScroll(id="preview-container"):
                    yield Static(
                        "[dim]Select a file from the workspace tree to view...[/dim]",
                        id="file-preview",
                    )

    def on_mount(self) -> None:
        _apply_theme(self)

    @on(DirectoryTree.FileSelected, "#dir-tree")
    def on_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        path = event.path
        try:
            if path.is_dir():
                return

            ext = path.suffix.lower()
            size = path.stat().st_size

            if size > 500_000:
                self.query_one("#file-preview", Static).update(
                    f"[yellow]File too large ({size / 1024:.1f} KB) to preview inline.[/yellow]"
                )
                return

            if ext in self._BINARY_EXTS or size == 0:
                kind = ext.lstrip(".").upper() if ext else "UNKNOWN"
                self.query_one("#file-preview", Static).update(
                    f"[dim]{kind} binary file[/dim]\n\n"
                    f"  Size: {size:,} bytes ({size / 1024:.1f} KB)\n"
                    f"  Path: {path}"
                )
                return

            raw = path.read_bytes()
            if b"\x00" in raw[:8192]:
                self.query_one("#file-preview", Static).update(
                    f"[dim]Binary file detected[/dim]\n\n"
                    f"  Size: {size:,} bytes ({size / 1024:.1f} KB)\n"
                    f"  Path: {path}"
                )
                return

            text = raw.decode("utf-8", errors="replace")
            lexer = self._LEXER_MAP.get(ext, "text")
            syntax = Syntax(
                text[:30000],
                lexer,
                theme=_get_syntax_theme(self.app),
                line_numbers=True,
                word_wrap=True,
                padding=1,
            )
            self.query_one("#file-preview", Static).update(syntax)
        except Exception as e:
            self.query_one("#file-preview", Static).update(f"[red]Could not read file: {e}[/red]")


# ─── F5: Session Manager & Instant Switcher ───────────────────────────────────


class SessionManagerScreen(ModalScreen):
    """Interactive session switcher & history manager modal (F5)."""

    DEFAULT_CSS = """
    SessionManagerScreen {
        align: center middle;
        background: rgba(1, 4, 9, 0.88);
    }
    #session-dialog {
        width: 90%;
        height: 86%;
        background: #0d1117;
        border: solid #1c2128;
        border-top: solid #d2a8ff;
        padding: 0 1 1 1;
    }
    #session-header {
        height: 3;
        dock: top;
        padding: 0 1;
        border-bottom: solid #1c2128;
    }
    #session-title {
        text-style: bold;
        width: 1fr;
        padding: 0 0 0 1;
        color: #d2a8ff;
    }
    #session-hints {
        color: #484f58;
        width: auto;
        padding: 0 1 0 0;
        content-align: right middle;
    }
    #session-body {
        height: 1fr;
        layout: horizontal;
    }
    #session-list-col {
        width: 40%;
        height: 100%;
        border-right: solid #1c2128;
        padding: 1 1 0 0;
    }
    #session-list-label {
        color: #8b949e;
        text-style: bold;
        padding: 0 0 1 0;
    }
    #session-options {
        background: #0d1117;
        border: none;
        overflow-y: scroll;
        scrollbar-gutter: stable;
        scrollbar-size-vertical: 1;
        scrollbar-size-horizontal: 0;
        scrollbar-color: #388bfd #161b22;
        scrollbar-color-hover: #79c0ff #161b22;
    }
    #session-detail-col {
        width: 60%;
        height: 100%;
        padding: 1 0 0 1;
        overflow-y: scroll;
        scrollbar-gutter: stable;
        scrollbar-size-vertical: 1;
        scrollbar-size-horizontal: 0;
        scrollbar-color: #388bfd #161b22;
        scrollbar-color-hover: #79c0ff #161b22;
    }
    #session-details {
        color: #c9d1d9;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("enter", "switch_selected_session", "Switch", priority=True),
        Binding("r", "refresh_sessions", "Refresh"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._sessions: list[dict[str, Any]] = []
        self._selected_sid: str = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="session-dialog"):
            with Horizontal(id="session-header"):
                yield Label("↻ Session History & Switcher", id="session-title")
                yield Static("[dim]Enter Switch · R Refresh · Esc Close[/dim]", id="session-hints")
            with Horizontal(id="session-body"):
                with Vertical(id="session-list-col"):
                    yield Label("SAVED SESSIONS", id="session-list-label")
                    yield OptionList(id="session-options")
                with VerticalScroll(id="session-detail-col"):
                    yield Static(
                        "[dim]Select a session to view details...[/dim]",
                        id="session-details",
                    )

    def on_mount(self) -> None:
        _apply_theme(self)
        self._load_sessions()

    def _load_sessions(self) -> None:
        from sago.database import Session

        try:
            option_list = self.query_one("#session-options", OptionList)
            option_list.clear_options()
        except Exception:
            return
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

        workspace_cwd = ""
        raw_meta = entry.get("metadata")
        if raw_meta:
            try:
                import json

                meta = json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta
                workspace_cwd = meta.get("workspace_cwd", "")
            except Exception:
                pass

        styled = Text()
        styled.append(f"  {title}\n", style="bold white")
        styled.append(f"  {sid}\n\n", style="dim")

        styled.append("  Status  ", style="bold")
        styled.append(f"{status}\n", style="cyan" if status == "active" else "yellow")

        styled.append("  Created ", style="bold")
        styled.append(f"{created}\n", style="cyan")

        if workspace_cwd:
            styled.append("  Root    ", style="bold")
            styled.append(f"{workspace_cwd}\n", style="cyan")

        try:
            from sago.database import MessageStore

            ms = MessageStore(sid)
            history = ms.get_history(limit=6)
            ms.close()
            if history:
                styled.append("\n  Recent Messages\n", style="bold yellow")
                for m in history:
                    r = m.get("role", "user")
                    c = (m.get("content") or "").strip()
                    c_short = c[:120] + ("..." if len(c) > 120 else "")
                    if r == "user":
                        styled.append("    User ", style="bold cyan")
                        styled.append(f"{c_short}\n")
                    else:
                        styled.append("    Assistant ", style="bold green")
                        styled.append(f"{c_short}\n")
        except Exception:
            pass

        styled.append("\n  Press Enter to switch to this session.\n", style="dim")

        self.query_one("#session-details", Static).update(styled)

    def action_refresh_sessions(self) -> None:
        """Reload session list from database."""
        self._load_sessions()

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
                self._selected_sid = sid
                break


# ─── F6 / Ctrl+M: Model & Provider Switcher ──────────────────────────────────


class ModelSwitcherScreen(ModalScreen[dict[str, str] | None]):
    """Interactive model & provider switcher modal (F6 / Ctrl+M / /model)."""

    DEFAULT_CSS = """
    ModelSwitcherScreen {
        align: center middle;
        background: rgba(1, 4, 9, 0.88);
    }
    #model-dialog {
        width: 94%;
        height: 90%;
        background: #0d1117;
        border: solid #1c2128;
        border-top: solid #58a6ff;
        padding: 0 1 1 1;
    }
    #model-header {
        height: 3;
        dock: top;
        padding: 0 1;
        border-bottom: solid #1c2128;
    }
    #model-title {
        text-style: bold;
        width: 1fr;
        padding: 0 0 0 1;
        color: #58a6ff;
    }
    #model-hints {
        color: #8b949e;
        width: auto;
        padding: 0 1 0 0;
        content-align: right middle;
    }
    #model-filter-bar {
        height: auto;
        padding: 0 0 1 0;
        margin-bottom: 1;
        border-bottom: solid #1c2128;
    }
    #model-search-input {
        width: 100%;
        height: 1;
        border: none;
        background: #161b22;
        color: #f0f6fc;
        padding: 0 1;
        margin-bottom: 1;
    }
    #model-search-input:focus {
        border: none;
        background: #1c2128;
        color: #ffffff;
    }
    #model-provider-tabs {
        height: 1;
        layout: horizontal;
        overflow-x: auto;
        overflow-y: hidden;
        scrollbar-size: 0 0;
    }
    Button.provider-pill {
        height: 1;
        min-width: 5;
        width: auto;
        border: none !important;
        background: #161b22;
        color: #8b949e;
        padding: 0 1;
        margin-right: 1;
    }
    Button.provider-pill:hover {
        background: #21262d;
        color: #f0f6fc;
        border: none !important;
    }
    Button.provider-pill:focus {
        border: none !important;
        text-style: none;
    }
    Button.provider-pill.-active {
        background: #388bfd !important;
        color: #ffffff !important;
        text-style: bold;
        border: none !important;
        tint: transparent !important;
    }
    #model-body {
        height: 1fr;
        layout: horizontal;
    }
    #model-list-col {
        width: 50%;
        height: 100%;
        border-right: solid #1c2128;
        padding: 1 1 0 0;
    }
    #model-options {
        background: #0d1117;
        border: none !important;
        padding: 0;
        overflow-y: scroll;
        scrollbar-gutter: stable;
        scrollbar-size-vertical: 1;
        scrollbar-size-horizontal: 0;
        scrollbar-color: #388bfd #161b22;
        scrollbar-color-hover: #79c0ff #161b22;
    }
    #model-options:focus {
        border: none !important;
        background-tint: transparent;
    }
    #model-options > .option-list--option-highlighted {
        background: #1f6feb;
        color: #ffffff;
        text-style: bold;
    }
    #model-options:focus > .option-list--option-highlighted {
        background: #1f6feb;
        color: #ffffff;
        text-style: bold;
    }
    #model-options > .option-list--option-hover {
        background: #161b22;
    }
    #model-detail-col {
        width: 50%;
        height: 100%;
        padding: 1 1 0 1;
    }
    #btn-select-model {
        margin-bottom: 1;
        width: 100%;
        height: 1;
        background: #238636;
        color: #ffffff;
        text-style: bold;
        border: none !important;
        padding: 0 1;
    }
    #btn-select-model:hover {
        background: #2ea043;
        color: #ffffff;
        border: none !important;
    }
    #btn-select-model:focus {
        background: #2ea043;
        color: #ffffff;
        border: none !important;
    }
    #btn-select-model.-active {
        background: #2ea043 !important;
        border: none !important;
        tint: transparent !important;
    }
    #model-detail-scroll {
        height: 1fr;
        overflow-y: scroll;
        scrollbar-gutter: stable;
        scrollbar-size-vertical: 1;
        scrollbar-size-horizontal: 0;
        scrollbar-color: #388bfd #161b22;
        scrollbar-color-hover: #79c0ff #161b22;
    }
    #model-details {
        padding: 1;
        background: #161b22;
        border: solid #21262d;
        color: #c9d1d9;
        margin-bottom: 1;
    }
    #model-custom-section {
        margin-top: 1;
        padding: 1;
        border: solid #30363d;
        background: #161b22;
    }
    #custom-model-input {
        margin-bottom: 1;
        border: solid #30363d;
        background: #0d1117;
        color: #f0f6fc;
    }
    #custom-provider-select {
        margin-bottom: 1;
        border: solid #30363d;
    }
    #btn-use-custom {
        margin-top: 1;
        width: 100%;
        height: 3;
        background: #1f6feb;
        color: #ffffff;
        text-style: bold;
        border: solid #58a6ff;
    }
    #btn-use-custom:hover {
        background: #388bfd;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("enter", "select_current", "Select", priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._provider_filter = "all"
        self._search_query = ""
        self._selected_entry: dict[str, str] | None = None
        self._model_catalog: list[dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="model-dialog"):
            with Horizontal(id="model-header"):
                yield Label("✦ Model & Provider Switcher", id="model-title")
                yield Static(
                    "[dim]↑↓ Navigate · Enter Select · Esc Close[/dim]",
                    id="model-hints",
                )
            with Vertical(id="model-filter-bar"):
                yield Input(
                    placeholder="Search models (e.g. flash, gpt, deepseek, sonnet)...",
                    id="model-search-input",
                )
                with Horizontal(id="model-provider-tabs"):
                    yield Button("✦ All", id="tab-all", classes="provider-pill -active")
                    yield Button("Google", id="tab-google", classes="provider-pill")
                    yield Button("OpenAI", id="tab-openai", classes="provider-pill")
                    yield Button("Anthropic", id="tab-anthropic", classes="provider-pill")
                    yield Button("DeepSeek", id="tab-deepseek", classes="provider-pill")
                    yield Button("Groq", id="tab-groq", classes="provider-pill")
                    yield Button("Ollama", id="tab-ollama", classes="provider-pill")
                    yield Button("OpenRouter", id="tab-openrouter", classes="provider-pill")
            with Horizontal(id="model-body"):
                with Vertical(id="model-list-col"):
                    yield Label("AVAILABLE MODELS", classes="section-label")
                    yield OptionList(id="model-options")
                with Vertical(id="model-detail-col"):
                    yield Button(
                        "✓ Use Selected Model",
                        id="btn-select-model",
                        variant="primary",
                    )
                    with VerticalScroll(id="model-detail-scroll"):
                        yield Static(
                            "[dim]Select a model from the list or enter custom below...[/dim]",
                            id="model-details",
                        )
                        with Vertical(id="model-custom-section"):
                            yield Label("[bold cyan]Custom / Manual Model Entry[/bold cyan]")
                            yield Static("[dim]Type any custom model ID without overrides:[/dim]")
                            yield Input(
                                placeholder="e.g. meta-llama/Llama-3.3-70B-Instruct or qwen2.5:32b",
                                id="custom-model-input",
                            )
                            yield Select(
                                options=[
                                    ("Google (Gemini)", "google"),
                                    ("OpenAI", "openai"),
                                    ("Anthropic (Claude)", "anthropic"),
                                    ("DeepSeek", "deepseek"),
                                    ("Groq", "groq"),
                                    ("Mistral AI", "mistral"),
                                    ("Ollama (Local)", "ollama"),
                                    ("OpenRouter", "openrouter"),
                                    ("LM Studio (Local)", "lmstudio"),
                                ],
                                prompt="Select Provider for Custom Model",
                                id="custom-provider-select",
                                value="openrouter",
                            )
                            yield Button(
                                "Use Custom Model",
                                id="btn-use-custom",
                                variant="success",
                            )

    def on_mount(self) -> None:
        _apply_theme(self)
        self._build_catalog()
        self._populate_options()
        for btn in self.query(".provider-pill"):
            btn.can_focus = False
        try:
            self.query_one("#model-search-input", Input).focus()
        except Exception:
            pass

    def on_key(self, event) -> None:
        """Handle keyboard navigation keys so Up/Down arrows work from anywhere."""
        if event.key in ("down", "up", "pageup", "pagedown"):
            try:
                opts = self.query_one("#model-options", OptionList)
                if event.key == "down":
                    event.prevent_default()
                    event.stop()
                    opts.action_cursor_down()
                    opts.scroll_to_highlight()
                elif event.key == "up":
                    event.prevent_default()
                    event.stop()
                    opts.action_cursor_up()
                    opts.scroll_to_highlight()
                elif event.key == "pagedown":
                    event.prevent_default()
                    event.stop()
                    opts.action_page_down()
                elif event.key == "pageup":
                    event.prevent_default()
                    event.stop()
                    opts.action_page_up()
            except Exception:
                pass

    def _build_catalog(self) -> None:
        from sago.llm.registry import (
            get_provider_spec,
            resolve_api_key,
            split_provider_and_model,
        )
        from sago.tui.models import get_all_models, get_model_costs

        all_models = get_all_models()
        costs = get_model_costs()
        cur_model = getattr(self.app, "current_model", "")
        cur_provider = getattr(self.app, "current_provider", "")

        self._model_catalog = []
        for raw in all_models:
            explicit_prov, clean_mid = split_provider_and_model(raw)
            if explicit_prov:
                prov = explicit_prov
                mid = clean_mid if explicit_prov != "openrouter" else raw
            else:
                prov = cur_provider or "openrouter"
                mid = raw

            spec = get_provider_spec(prov)
            has_key = bool(resolve_api_key(prov, mid)) if spec and not spec.local else True
            cost_info = costs.get(raw, {})

            self._model_catalog.append(
                {
                    "raw": raw,
                    "provider": prov,
                    "model": mid,
                    "is_active": (raw == cur_model or (prov == cur_provider and mid == cur_model)),
                    "has_key": has_key,
                    "cost": cost_info,
                    "spec": spec,
                }
            )

    def _populate_options(self) -> None:
        try:
            options_widget = self.query_one("#model-options", OptionList)
            options_widget.clear_options()
        except Exception:
            return

        filtered = []
        q = self._search_query.lower().strip()
        pf = self._provider_filter

        for item in self._model_catalog:
            if pf != "all" and item["provider"] != pf:
                continue
            if q and q not in item["raw"].lower() and q not in item["provider"].lower():
                continue
            filtered.append(item)

        color_map = {
            "google": "cyan",
            "openai": "yellow",
            "anthropic": "magenta",
            "deepseek": "bright_blue",
            "groq": "bright_green",
            "mistral": "bright_cyan",
            "ollama": "green",
            "openrouter": "white",
            "lmstudio": "green",
        }

        for item in filtered:
            prov = item["provider"]
            c = color_map.get(prov, "cyan")
            active_mark = "[bold green]● [/bold green]" if item["is_active"] else "  "
            prov_tag = f"[{c}][{prov}][/{c}]"
            model_name = f"[bold white]{item['model']}[/bold white]"
            free_tag = "[green]Free[/green]" if item.get("cost", {}).get("input") == 0 else ""

            label = f"{active_mark}{prov_tag:<14} {model_name} {free_tag}".strip()
            opt_id = f"{item['provider']}::{item['model']}"
            options_widget.add_option(Option(prompt=label, id=opt_id))

        if filtered:
            first = filtered[0]
            self._selected_entry = {"provider": first["provider"], "model": first["model"]}
            self._show_details(first)
            options_widget.highlighted = 0
        else:
            self._selected_entry = None
            self.query_one("#model-details", Static).update(
                "[dim]No matching models found. Use the manual entry form below to configure any model.[/dim]"
            )

    def _show_details(self, entry: dict[str, Any]) -> None:
        prov = entry["provider"]
        model = entry["model"]
        is_active = entry["is_active"]
        has_key = entry["has_key"]
        cost = entry.get("cost", {})
        spec = entry.get("spec")

        styled = Text()
        styled.append("Selected Model: ", style="dim")
        styled.append(f"{model}\n", style="bold white")
        styled.append("Provider:       ", style="dim")
        styled.append(f"{prov.upper()}\n", style="bold cyan")

        if is_active:
            styled.append("Status:         ", style="dim")
            styled.append("● Active in current session\n", style="bold green")

        styled.append("Auth Status:    ", style="dim")
        if spec and spec.local:
            styled.append("✓ Local Engine (No API key needed)\n", style="green")
        elif has_key:
            env_var = spec.api_key_env if spec else f"{prov.upper()}_API_KEY"
            styled.append(f"✓ Configured in ${env_var}\n", style="green")
        else:
            env_var = spec.api_key_env if spec else f"{prov.upper()}_API_KEY"
            styled.append(f"⚠ Missing ${env_var}\n", style="bold yellow")
            if spec and spec.billing_url:
                styled.append(f"  Get API key: {spec.billing_url}\n", style="dim cyan")

        if cost and "input" in cost and "output" in cost:
            inp = cost["input"]
            out = cost["output"]
            styled.append("Pricing:        ", style="dim")
            if inp == 0 and out == 0:
                styled.append("100% Free / Local\n", style="bold green")
            else:
                styled.append(f"${inp:.3f}/M in, ${out:.3f}/M out\n", style="yellow")
            styled.append("Price Source:   ", style="dim")
            styled.append("Official Provider Catalog / OpenRouter API\n", style="dim cyan")

        styled.append("\nFeatures & Capabilities:\n", style="bold")
        if "reasoner" in model or "r1" in model or "o1" in model or "o3" in model:
            styled.append("  • Deep chain-of-thought step-by-step reasoning\n", style="dim")
        if "coder" in model or "sonnet" in model or "gpt-4o" in model:
            styled.append(
                "  • Specialized for complex code generation, refactoring, and multi-file AST edits\n",
                style="dim",
            )
        if "flash" in model or "mini" in model or "groq" in prov:
            styled.append(
                "  • High token throughput & near-instant response latency\n", style="dim"
            )
        styled.append("  • Full tool use and function calling enabled in SAGO\n", style="dim")

        self.query_one("#model-details", Static).update(styled)
        try:
            self.query_one("#btn-select-model", Button).label = "✓ Use Selected Model"
        except Exception:
            pass

    @on(Input.Changed, "#model-search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        self._search_query = event.value
        self._populate_options()

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid.startswith("tab-"):
            for btn in self.query(".provider-pill"):
                btn.remove_class("-active")
            event.button.add_class("-active")
            self._provider_filter = bid.replace("tab-", "")
            self._populate_options()
            try:
                self.query_one("#model-options", OptionList).focus()
            except Exception:
                pass
        elif bid == "btn-select-model":
            self.action_select_current()
        elif bid == "btn-use-custom":
            self._apply_custom_model()

    @on(OptionList.OptionHighlighted, "#model-options")
    def on_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option and event.option.id:
            prov, model = str(event.option.id).split("::", 1)
            self._selected_entry = {"provider": prov, "model": model}
            for item in self._model_catalog:
                if item["provider"] == prov and item["model"] == model:
                    self._show_details(item)
                    break

    @on(OptionList.OptionSelected, "#model-options")
    def on_option_selected(self, event: OptionList.OptionSelected) -> None:
        """When an option is clicked, highlight it and update details panel.

        The user confirms their choice by clicking '✓ Use Selected Model' or pressing Enter.
        """
        if event.option and event.option.id:
            prov, model = str(event.option.id).split("::", 1)
            self._selected_entry = {"provider": prov, "model": model}
            for item in self._model_catalog:
                if item["provider"] == prov and item["model"] == model:
                    self._show_details(item)
                    break

    def _apply_custom_model(self) -> None:
        custom_input = self.query_one("#custom-model-input", Input).value.strip()
        if not custom_input:
            return
        provider_select = self.query_one("#custom-provider-select", Select).value
        chosen_provider = str(provider_select) if provider_select else "openrouter"
        self.dismiss({"provider": chosen_provider, "model": custom_input})

    def action_select_current(self) -> None:
        if self._selected_entry:
            self.dismiss(self._selected_entry)
        else:
            self._apply_custom_model()
