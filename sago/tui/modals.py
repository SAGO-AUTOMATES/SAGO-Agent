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
from textual.widgets import DirectoryTree, Label, OptionList, Static
from textual.widgets.option_list import Option

logger = logging.getLogger("sago.tui.modals")


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
        scrollbar-size: 1 1;
        scrollbar-color: #388bfd #161b22;
    }
    #diff-content-scroll {
        width: 68%;
        height: 100%;
        padding: 0 0 0 1;
        scrollbar-size: 1 1;
        scrollbar-color: #388bfd #161b22;
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
                yield Label("Workspace Diff", id="diff-title")
                yield Static("[dim]R Refresh · Esc Close[/dim]", id="diff-hints")
            with Horizontal(id="diff-body"):
                with Vertical(id="diff-file-list"):
                    yield Label("CHANGED FILES", id="diff-file-label")
                    yield OptionList(id="diff-options")
                with VerticalScroll(id="diff-content-scroll"):
                    yield Static("[dim]Select a file to view its diff...[/dim]", id="diff-content")

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
                    "[bold green]Clean Working Tree[/bold green]\n\n"
                    "No unstaged or staged changes detected."
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
                    raw_diff = f"[Untracked: {fpath}]"
                self._diff_map[fpath] = raw_diff
                tag_col = "green" if status == "A" else ("yellow" if status == "M" else "red")
                option_list.add_option(
                    Option(f"[{tag_col}]{status:<2}[/{tag_col}] {escape(fpath)}", id=fpath)
                )

            initial_file = self.target_file if self.target_file in self._diff_map else files[0][1]
            self._display_file_diff(initial_file)

        except Exception as e:
            self.query_one("#diff-content", Static).update(f"[red]Error fetching diff: {e}[/red]")

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
        scrollbar-size: 1 1;
        scrollbar-color: #388bfd #161b22;
    }
    #preview-container {
        width: 68%;
        height: 100%;
        padding-left: 1;
        scrollbar-size: 1 1;
        scrollbar-color: #388bfd #161b22;
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
                yield Label(f"Workspace Explorer — {cwd.name}", id="file-title")
                yield Static("[dim]Esc Close[/dim]", id="file-hints")
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
                theme="monokai",
                line_numbers=True,
                word_wrap=True,
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
        scrollbar-size: 1 1;
        scrollbar-color: #388bfd #161b22;
    }
    #session-detail-col {
        width: 60%;
        height: 100%;
        padding: 1 0 0 1;
        scrollbar-size: 1 1;
        scrollbar-color: #388bfd #161b22;
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
                yield Label("Session History & Switcher", id="session-title")
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
