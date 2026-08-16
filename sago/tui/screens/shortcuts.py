"""Interactive Shortcuts & Quick Reference Modal for SAGO TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ShortcutsScreen(ModalScreen[None]):
    """Modal screen displaying keyboard shortcuts, commands, and mention triggers."""

    DEFAULT_CSS = """
    ShortcutsScreen {
        align: center middle;
        background: rgba(10, 13, 18, 0.85);
    }

    #shortcuts-dialog {
        width: 80;
        max-width: 95%;
        height: auto;
        max-height: 85%;
        background: #111418;
        border: solid #30363d;
        border-top: solid #58a6ff;
        padding: 1 2;
    }

    .shortcuts-header {
        color: #58a6ff;
        text-style: bold;
        padding: 0 0 1 0;
        border-bottom: solid #21262d;
        content-align: center middle;
    }

    .shortcuts-content {
        height: auto;
        max-height: 24;
        overflow-y: auto;
        scrollbar-size: 1 1;
        scrollbar-color: #30363d #111418;
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
        height: 3;
        margin-top: 1;
        border-top: solid #21262d;
        content-align: right middle;
        layout: horizontal;
    }

    .shortcuts-hint {
        color: #8b949e;
        width: 1fr;
        content-align: left middle;
    }

    #close-btn {
        min-width: 12;
        background: #21262d;
        color: #8b949e;
        border: solid #30363d;
    }
    #close-btn:focus, #close-btn:hover {
        background: #30363d;
        color: #c9d1d9;
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
                    "[dim]Press ESC or Enter to close[/dim]",
                    classes="shortcuts-hint",
                    markup=True,
                )
                yield Button("Close (Esc)", id="close-btn", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-btn":
            self.dismiss()
