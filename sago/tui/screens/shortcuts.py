"""Interactive Shortcuts & Quick Reference Modal for SAGO TUI."""

from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

logger = logging.getLogger("sago.tui.screens.shortcuts")


class ShortcutsScreen(ModalScreen[None]):
    """Modal screen displaying keyboard shortcuts, commands, and mention triggers."""

    DEFAULT_CSS = """
    ShortcutsScreen {
        align: center middle;
        background: rgba(1, 4, 9, 0.88);
    }

    #shortcuts-dialog {
        width: 80;
        max-width: 95%;
        height: auto;
        max-height: 85%;
        background: #0d1117;
        border: solid #1c2128;
        border-top: solid #58a6ff;
        padding: 0 1 1 1;
    }

    .shortcuts-header {
        color: #58a6ff;
        text-style: bold;
        padding: 0 0 1 0;
        border-bottom: solid #1c2128;
        content-align: center middle;
    }

    .shortcuts-content {
        height: auto;
        max-height: 24;
        overflow-y: auto;
        scrollbar-size: 1 1;
        scrollbar-color: #388bfd #161b22;
        padding: 1 0;
    }

    .section-title {
        color: #f0883e;
        text-style: bold;
        padding: 1 0 0 0;
    }

    .shortcut-row {
        color: #c9d1d9;
        padding: 0 0 0 1;
    }

    .shortcuts-footer {
        height: 1;
        margin-top: 1;
        border-top: solid #1c2128;
        content-align: right middle;
        layout: horizontal;
    }

    .shortcuts-hint {
        color: #484f58;
        width: 1fr;
        content-align: left middle;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close", show=True),
        Binding("q", "dismiss", "Close", show=False),
        Binding("f1", "dismiss", "Close", show=False),
        Binding("enter", "dismiss", "Close", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="shortcuts-dialog"):
            yield Static("⌨️  SAGO SHORTCUTS & QUICK REFERENCE", classes="shortcuts-header")
            with ScrollableContainer(classes="shortcuts-content"):
                yield Static(
                    "[bold yellow]─── KEYBOARD SHORTCUTS ───[/bold yellow]",
                    classes="section-title",
                    markup=True,
                )
                yield Static(
                    "  [bold cyan]F1[/bold cyan] or [bold cyan]?[/bold cyan]         : Show this Shortcuts Reference Modal",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold cyan]F2[/bold cyan]              : Open Deep Trace & Dev Telemetry Viewer",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold cyan]F3[/bold cyan]              : Open Workspace Diff & Git Inspector",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold cyan]F4[/bold cyan]              : Open Workspace File Tree Explorer",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold cyan]F5[/bold cyan]              : Open Session Switcher & History Manager",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold cyan]Ctrl + R[/bold cyan]       : Hot-reload configuration and execution mode",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold cyan]Ctrl + D[/bold cyan]       : Toggle Live Agent Dashboard sidebar",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold cyan]Ctrl + T[/bold cyan]       : View active background tasks",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold cyan]Ctrl + C[/bold cyan]       : Cancel running task or agent execution",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold cyan]Ctrl + L[/bold cyan]       : Clear conversation buffer",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold cyan]Ctrl + Q[/bold cyan]       : Quit Sago TUI",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold cyan]Tab[/bold cyan] / [bold cyan]Enter[/bold cyan]    : Accept highlighted autocomplete suggestion",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold cyan]Up[/bold cyan] / [bold cyan]Down[/bold cyan]      : Navigate suggestions or command history",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold cyan]PageUp / PageDown[/bold cyan] : Fast page viewport scroll",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold cyan]Shift+Up / Down[/bold cyan]   : Line-by-line smooth viewport scroll",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold cyan]Ctrl+Home / End[/bold cyan]   : Jump to top / bottom of chat messages",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold cyan]Escape[/bold cyan]            : Dismiss suggestions / Close modals",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold cyan]y[/bold cyan] / [bold cyan]n[/bold cyan]             : Quick Approve / Deny tool permission prompt",
                    classes="shortcut-row",
                    markup=True,
                )

                yield Static(
                    "\n[bold magenta]─── POWER COMMANDS ───[/bold magenta]",
                    classes="section-title",
                    markup=True,
                )
                yield Static(
                    "  [bold magenta]/graph [view][/bold magenta]     : Architecture & data graph (arch, process, models, flow)",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold magenta]/map [query][/bold magenta]      : AST symbol map & outline for current workspace",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold magenta]/session [action][/bold magenta] : Manage sessions (list, switch, save, load, reset)",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold magenta]/checkpoint[/bold magenta]       : Save, restore, or prune workspace snapshot rollback",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold magenta]/perms [action][/bold magenta]   : Tool permissions manager (list, allow, block)",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold magenta]/todo [action][/bold magenta]    : Task checklist tracker (list, done <id>)",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold magenta]/dev on|off[/bold magenta]       : Real-time function tracing & deep LLM telemetry",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold magenta]/theme <name>[/bold magenta]     : Switch color theme (11 built-in themes)",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold magenta]/model <id>[/bold magenta]      : Switch active model (GPT-4o, Claude 3.7, Gemini 2.5)",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold magenta]/effort <level>[/bold magenta]  : Set reasoning effort (low, med, high, max)",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold magenta]/cost[/bold magenta]            : Token usage analytics & spend breakdown",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold magenta]/help[/bold magenta]            : Comprehensive interactive command manual",
                    classes="shortcut-row",
                    markup=True,
                )

                yield Static(
                    "\n[bold green]─── SPECIAL MENTIONS & TRIGGERS ───[/bold green]",
                    classes="section-title",
                    markup=True,
                )
                yield Static(
                    "  [bold green]@<agent>[/bold green]         : Route task to specialist agent profile (@coder, @architect)",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold green]#<file>[/bold green]          : Smart workspace file path autocompletion & context",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold green]~<file>[/bold green]          : Home directory file path lookup",
                    classes="shortcut-row",
                    markup=True,
                )
                yield Static(
                    "  [bold green]?[/bold green]               : Quick shortcut lookup",
                    classes="shortcut-row",
                    markup=True,
                )

            with Horizontal(classes="shortcuts-footer"):
                yield Static(
                    "[dim]Press Esc or Enter to close[/dim]",
                    classes="shortcuts-hint",
                    markup=True,
                )

    def on_mount(self) -> None:
        try:
            theme = getattr(self.app, "sago_theme", "obsidian")
            for t in [
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
            ]:
                self.remove_class(f"theme-{t}")
            if theme and theme != "obsidian":
                self.add_class(f"theme-{theme}")
        except Exception:
            pass
