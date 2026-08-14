"""Sago TUI - Production Terminal Interface with parallel agent support."""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import re
import threading
import time
from typing import Any

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widgets import Button, Input, Static

from sago.tui.commands import CommandHandlers
from sago.tui.helpers import UIHelpers
from sago.tui.models import COMMANDS, EFFORT_LEVELS
from sago.tui.widgets import (
    AgentDashboard,
    AgentStatus,
    BackgroundTaskManager,
    Spinner,
    get_task_manager,
)

logger = logging.getLogger("sago.tui.app")

_time = time


class SagoApp(App, CommandHandlers, UIHelpers):
    CSS = """
    Screen { background: #0a0d12; }

    #main-layout {
        height: 1fr;
    }

    #messages-parent {
        width: 1fr;
        height: 1fr;
    }

    #agent-dashboard {
        width: 32;
        height: 1fr;
        background: #111418;
        border-left: solid #21262d;
        padding: 0 1;
        overflow-y: auto;
        scrollbar-size: 1 1;
        scrollbar-color: #30363d #111418;
    }
    #agent-dashboard.hidden { display: none; }

    .dashboard-title {
        color: #58a6ff;
        text-style: bold;
        padding: 0;
        content-align: center middle;
    }
    .agent-entry {
        background: #161b22;
        border: solid #21262d;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    .agent-name { text-style: bold; }
    .agent-status { color: #8b949e; padding: 0 0 0 1; }
    .agent-task { color: #8b949e; text-style: italic; padding: 0; max-width: 30; }
    .agent-tools { color: #58a6ff; padding: 0; }
    .agent-progress { padding: 0; color: #3fb950; }
    .dashboard-separator { color: #21262d; padding: 0; }
    .dashboard-stats { color: #8b949e; }
    .active-color { color: #3fb950; }
    .idle-color { color: #8b949e; }
    .error-color { color: #f85149; }
    .completed-color { color: #58a6ff; }

    #messages {
        height: 1fr;
        padding: 1 2;
        overflow-y: auto;
        scrollbar-size: 1 1;
        scrollbar-color: #30363d #0a0d12;
        scrollbar-color-hover: #484f58 #0a0d12;
    }

    .msg-user {
        background: #111418;
        border: solid #21262d;
        border-left: solid #388bfd;
        color: #58a6ff;
        padding: 1 2;
        margin: 1 0;
    }
    .msg-assistant {
        background: #0d1117;
        border: solid #21262d;
        color: #e6edf3;
        padding: 1 2;
        margin: 1 0;
    }
    .msg-system {
        background: #111822;
        border: solid #21262d;
        border-left: solid #d29922;
        color: #e6edf3;
        padding: 1 2;
        margin: 1 0;
    }
    .msg-meta { color: #6e7681; padding: 0; }
    .msg-parallel {
        background: #111418;
        color: #d2a8ff;
        border: solid #21262d;
        border-left: solid #d2a8ff;
        padding: 1 2;
        margin: 1 0;
    }

    .exchange-box {
        background: #0d1117;
        border: solid #21262d;
        border-left: solid #388bfd;
        padding: 0;
        margin: 1 0;
        height: auto;
    }
    .exchange-prompt-header {
        background: #0d1117;
        color: #8b949e;
        padding: 0 2;
    }
    .exchange-body {
        padding: 1 2 1 2;
        height: auto;
    }
    .exchange-user-prompt {
        color: #e6edf3;
        padding: 0 0 1 0;
    }
    .exchange-divider {
        color: #30363d;
        padding: 0;
        margin: 0;
    }
    .exchange-prompt {
        color: #58a6ff;
        text-style: bold;
        padding: 0;
        border-bottom: solid #21262d;
    }
    .exchange-assistant {
        color: #e6edf3;
        padding: 0;
    }
    .thinking-text {
        color: #8b949e;
        text-style: italic;
        padding: 1 2;
        background: #080c14;
        border: solid #21262d;
        border-left: solid #d2a8ff;
        margin: 1 0;
    }
    .plan-text {
        color: #7ee787;
        padding: 1 2;
        background: #080c14;
        border: solid #21262d;
        border-left: solid #3fb950;
        margin: 1 0;
    }

    .collapsible-card-box {
        background: #0d1117;
        border: solid #21262d;
        border-left: solid #388bfd;
        padding: 0;
        margin: 1 0;
        height: auto;
    }
    .card-header {
        background: #0d1117;
        color: #8b949e;
        padding: 0 2;
    }
    .card-body {
        padding: 1 2;
        height: auto;
    }

    /* Textual built-in Collapsible widget — uniform header treatment */
    Collapsible {
        border: solid #21262d;
        border-left: solid #388bfd;
        background: #0d1117;
        margin: 1 0;
        padding: 0;
    }
    CollapsibleTitle {
        background: #0d1117;
        color: #8b949e;
        padding: 0 2;
    }
    Collapsible > Contents {
        padding: 1 2;
        height: auto;
    }

    .code-action-bar {
        height: 1;
        margin: 1 0 0 0;
        padding: 0;
    }
    .spacer {
        width: 1fr;
    }
    .btn-copy-code {
        min-width: 14;
        height: 1;
        background: #21262d;
        color: #8b949e;
        border: solid #30363d;
        padding: 0 1;
    }
    .btn-copy-code:focus, .btn-copy-code:hover {
        background: #30363d;
        color: #58a6ff;
        border: solid #58a6ff;
    }

    /* Nord Theme */
    .theme-nord { background: #242933; }
    .theme-nord #agent-dashboard { background: #2e3440; border-left: solid #434c5e; }
    .theme-nord .exchange-box { background: #2e3440; border: solid #434c5e; border-left: solid #88c0d0; }
    .theme-nord .exchange-prompt-header { background: #3b4252; color: #88c0d0; border-bottom: solid #434c5e; }
    .theme-nord .exchange-user-prompt { color: #eceff4; }
    .theme-nord .exchange-divider { color: #434c5e; }
    .theme-nord .exchange-assistant { color: #eceff4; }
    .theme-nord .msg-system { background: #2e3440; border: solid #434c5e; border-left: solid #ebcb8b; }
    .theme-nord #input-area { background: #242933; border-top: solid #434c5e; }
    .theme-nord #msg-input { background: #2e3440; border: solid #434c5e; color: #eceff4; }
    .theme-nord #msg-input:focus { border: solid #88c0d0; }

    /* Dracula Theme */
    .theme-dracula { background: #1e1f29; }
    .theme-dracula #agent-dashboard { background: #282a36; border-left: solid #44475a; }
    .theme-dracula .exchange-box { background: #282a36; border: solid #44475a; border-left: solid #bd93f9; }
    .theme-dracula .exchange-prompt-header { background: #44475a; color: #bd93f9; border-bottom: solid #6272a4; }
    .theme-dracula .exchange-user-prompt { color: #f8f8f2; }
    .theme-dracula .exchange-divider { color: #44475a; }
    .theme-dracula .exchange-assistant { color: #f8f8f2; }
    .theme-dracula .msg-system { background: #282a36; border: solid #44475a; border-left: solid #f1fa8c; }
    .theme-dracula #input-area { background: #1e1f29; border-top: solid #44475a; }
    .theme-dracula #msg-input { background: #282a36; border: solid #44475a; color: #f8f8f2; }
    .theme-dracula #msg-input:focus { border: solid #bd93f9; }

    /* Monokai Theme */
    .theme-monokai { background: #1e1f1c; }
    .theme-monokai #agent-dashboard { background: #272822; border-left: solid #3e3d32; }
    .theme-monokai .exchange-box { background: #272822; border: solid #3e3d32; border-left: solid #a6e22e; }
    .theme-monokai .exchange-prompt-header { background: #3e3d32; color: #a6e22e; border-bottom: solid #49483e; }
    .theme-monokai .exchange-user-prompt { color: #f8f8f2; }
    .theme-monokai .exchange-divider { color: #3e3d32; }
    .theme-monokai .exchange-assistant { color: #f8f8f2; }
    .theme-monokai .msg-system { background: #272822; border: solid #3e3d32; border-left: solid #e6db74; }
    .theme-monokai #input-area { background: #1e1f1c; border-top: solid #3e3d32; }
    .theme-monokai #msg-input { background: #272822; border: solid #3e3d32; color: #f8f8f2; }
    .theme-monokai #msg-input:focus { border: solid #a6e22e; }

    /* Tokyo Night Theme */
    .theme-tokyo-night { background: #16161e; }
    .theme-tokyo-night #agent-dashboard { background: #1a1b26; border-left: solid #292e42; }
    .theme-tokyo-night .exchange-box { background: #1a1b26; border: solid #292e42; border-left: solid #7aa2f7; }
    .theme-tokyo-night .exchange-prompt-header { background: #292e42; color: #7aa2f7; border-bottom: solid #3b4261; }
    .theme-tokyo-night .exchange-user-prompt { color: #c0caf5; }
    .theme-tokyo-night .exchange-divider { color: #292e42; }
    .theme-tokyo-night .exchange-assistant { color: #c0caf5; }
    .theme-tokyo-night .msg-system { background: #1a1b26; border: solid #292e42; border-left: solid #e0af68; }
    .theme-tokyo-night #input-area { background: #16161e; border-top: solid #292e42; }
    .theme-tokyo-night #msg-input { background: #1a1b26; border: solid #292e42; color: #c0caf5; }
    .theme-tokyo-night #msg-input:focus { border: solid #7aa2f7; }

    /* Solarized Dark Theme */
    .theme-solarized-dark { background: #00212b; }
    .theme-solarized-dark #agent-dashboard { background: #002b36; border-left: solid #073642; }
    .theme-solarized-dark .exchange-box { background: #002b36; border: solid #073642; border-left: solid #268bd2; }
    .theme-solarized-dark .exchange-prompt-header { background: #073642; color: #268bd2; border-bottom: solid #586e75; }
    .theme-solarized-dark .exchange-user-prompt { color: #839496; }
    .theme-solarized-dark .exchange-divider { color: #073642; }
    .theme-solarized-dark .exchange-assistant { color: #839496; }
    .theme-solarized-dark .msg-system { background: #002b36; border: solid #073642; border-left: solid #b58900; }
    .theme-solarized-dark #input-area { background: #00212b; border-top: solid #073642; }
    .theme-solarized-dark #msg-input { background: #002b36; border: solid #073642; color: #839496; }
    .theme-solarized-dark #msg-input:focus { border: solid #268bd2; }

    /* Cyberpunk Theme */
    .theme-cyberpunk { background: #08090f; }
    .theme-cyberpunk #agent-dashboard { background: #10121d; border-left: solid #00f0ff; }
    .theme-cyberpunk .exchange-box { background: #10121d; border: solid #202637; border-left: solid #ffee00; }
    .theme-cyberpunk .exchange-prompt-header { background: #181d2e; color: #00f0ff; border-bottom: solid #00f0ff; }
    .theme-cyberpunk .exchange-user-prompt { color: #00f0ff; }
    .theme-cyberpunk .exchange-divider { color: #202637; }
    .theme-cyberpunk .exchange-assistant { color: #00f0ff; }
    .theme-cyberpunk .msg-system { background: #10121d; border: solid #202637; border-left: solid #00f0ff; }
    .theme-cyberpunk #input-area { background: #08090f; border-top: solid #202637; }
    .theme-cyberpunk #msg-input { background: #10121d; border: solid #202637; color: #00f0ff; }
    .theme-cyberpunk #msg-input:focus { border: solid #00f0ff; }

    /* Catppuccin Mocha Theme */
    .theme-catppuccin-mocha { background: #1e1e2e; }
    .theme-catppuccin-mocha #agent-dashboard { background: #181825; border-left: solid #313244; }
    .theme-catppuccin-mocha .exchange-box { background: #181825; border: solid #313244; border-left: solid #cba6f7; }
    .theme-catppuccin-mocha .exchange-prompt-header { background: #313244; color: #cba6f7; border-bottom: solid #45475a; }
    .theme-catppuccin-mocha .exchange-user-prompt { color: #cdd6f4; }
    .theme-catppuccin-mocha .exchange-divider { color: #313244; }
    .theme-catppuccin-mocha .exchange-assistant { color: #cdd6f4; }
    .theme-catppuccin-mocha .msg-system { background: #181825; border: solid #313244; border-left: solid #f9e2af; }
    .theme-catppuccin-mocha #input-area { background: #1e1e2e; border-top: solid #313244; }
    .theme-catppuccin-mocha #msg-input { background: #181825; border: solid #313244; color: #cdd6f4; }
    .theme-catppuccin-mocha #msg-input:focus { border: solid #cba6f7; }

    /* Gruvbox Dark Theme */
    .theme-gruvbox-dark { background: #1d2021; }
    .theme-gruvbox-dark #agent-dashboard { background: #282828; border-left: solid #3c3836; }
    .theme-gruvbox-dark .exchange-box { background: #282828; border: solid #3c3836; border-left: solid #fabd2f; }
    .theme-gruvbox-dark .exchange-prompt-header { background: #3c3836; color: #fabd2f; border-bottom: solid #504945; }
    .theme-gruvbox-dark .exchange-user-prompt { color: #ebdbb2; }
    .theme-gruvbox-dark .exchange-divider { color: #3c3836; }
    .theme-gruvbox-dark .exchange-assistant { color: #ebdbb2; }
    .theme-gruvbox-dark .msg-system { background: #282828; border: solid #3c3836; border-left: solid #fabd2f; }
    .theme-gruvbox-dark #input-area { background: #1d2021; border-top: solid #3c3836; }
    .theme-gruvbox-dark #msg-input { background: #282828; border: solid #3c3836; color: #ebdbb2; }
    .theme-gruvbox-dark #msg-input:focus { border: solid #fabd2f; }

    /* Rosé Pine Theme */
    .theme-rose-pine { background: #191724; }
    .theme-rose-pine #agent-dashboard { background: #1f1d2e; border-left: solid #26233a; }
    .theme-rose-pine .exchange-box { background: #1f1d2e; border: solid #26233a; border-left: solid #eb6f92; }
    .theme-rose-pine .exchange-prompt-header { background: #26233a; color: #eb6f92; border-bottom: solid #393552; }
    .theme-rose-pine .exchange-user-prompt { color: #e0def4; }
    .theme-rose-pine .exchange-divider { color: #26233a; }
    .theme-rose-pine .exchange-assistant { color: #e0def4; }
    .theme-rose-pine .msg-system { background: #1f1d2e; border: solid #26233a; border-left: solid #f6c177; }
    .theme-rose-pine #input-area { background: #191724; border-top: solid #26233a; }
    .theme-rose-pine #msg-input { background: #1f1d2e; border: solid #26233a; color: #e0def4; }
    .theme-rose-pine #msg-input:focus { border: solid #eb6f92; }

    /* Clean Light Theme */
    .theme-light { background: #f6f8fa; }
    .theme-light #agent-dashboard { background: #ffffff; border-left: solid #d0d7de; }
    .theme-light .exchange-box { background: #ffffff; border: solid #d0d7de; border-left: solid #0969da; }
    .theme-light .exchange-prompt-header { background: #f1f3f5; color: #0969da; border-bottom: solid #d0d7de; }
    .theme-light .exchange-user-prompt { color: #24292f; }
    .theme-light .exchange-divider { color: #d0d7de; }
    .theme-light .exchange-assistant { color: #24292f; }
    .theme-light .msg-system { background: #ffffff; border: solid #d0d7de; border-left: solid #9a6700; color: #24292f; }
    .theme-light #input-area { background: #f6f8fa; border-top: solid #d0d7de; }
    .theme-light #msg-input { background: #ffffff; border: solid #d0d7de; color: #24292f; }
    .theme-light #msg-input:focus { border: solid #0969da; }

    .dev-trace-text {
        color: #79c0ff;
        padding: 1 2;
        background: #06090e;
        border: solid #21262d;
        border-left: solid #f85149;
        margin: 1 0;
    }

    Collapsible {
        background: #0d1117;
        border: solid #21262d;
        margin: 1 0;
        padding: 0;
        height: auto;
    }
    Collapsible .collapsible-title {
        background: #161b22;
        color: #58a6ff;
        padding: 0 2;
        text-style: bold;
    }
    Collapsible .collapsible-body {
        background: #0d1117;
        color: #e6edf3;
        padding: 1 2;
        overflow-y: auto;
        scrollbar-size: 1 1;
        scrollbar-color: #30363d #111418;
    }

    #input-area {
        height: auto;
        padding: 0 1 1 1;
        background: #0a0d12;
        border-top: solid #21262d;
        margin: 0;
    }

    #msg-input {
        background: #0a0d12;
        border: none;
        border-top: solid #21262d;
        color: #c9d1d9;
        margin: 0;
        padding: 0 1;
    }
    #msg-input:focus {
        border: none;
        border-top: solid #388bfd;
        color: #ffffff;
        background: #0a0d12;
    }

    #suggestions {
        display: none;
        height: auto;
        max-height: 14;
        overflow-y: auto;
        background: #0a0d12;
        border: none;
        border-top: solid #21262d;
        margin: 0;
        padding: 0 1;
        scrollbar-size: 0 0;
    }
    #suggestions.visible { display: block; }

    .suggestion-item { color: #6e7681; padding: 0 1; }
    .suggestion-item.highlighted { color: #e6edf3; background: #1c2128; }

    .code-block {
        background: #161b22;
        color: #c9d1d9;
        padding: 1;
        margin: 0 0 1 0;
        border: tall #30363d;
    }

    .spinner { color: #58a6ff; text-style: italic; padding: 0 0 1 0; }

    .summary-box {
        background: #161b22;
        border: solid #1f6feb;
        color: #c9d1d9;
        padding: 1;
        margin: 0 0 1 0;
    }

    #welcome-screen {
        height: 1fr;
        align: center middle;
        content-align: center middle;
        text-align: center;
        background: #0d1117;
    }
    #welcome-screen.hidden { display: none; }

    #messages-parent.has-welcome #messages { display: none; }

    .welcome-logo {
        color: #58a6ff;
        text-style: bold;
        text-align: center;
        width: 100%;
        height: auto;
    }
    .welcome-version {
        color: #ffffff;
        text-style: bold;
        text-align: center;
        width: 100%;
        height: 1;
        margin: 1 0 0 0;
    }
    .welcome-subtitle {
        color: #8b949e;
        text-align: center;
        width: 100%;
        height: 1;
        margin: 0 0 0 0;
    }
    .welcome-hint {
        color: #484f58;
        text-align: center;
        width: 100%;
        height: 1;
        margin: 2 0 0 0;
    }
    .welcome-separator {
        color: #30363d;
        text-align: center;
        width: 100%;
        height: 1;
        margin: 1 0 0 0;
    }

    #approval-bar {
        display: none;
        height: auto;
        max-height: 4;
        background: #161b22;
        border: solid #f0883e;
        border-left: solid #f0883e;
        margin: 0 1 0 1;
        padding: 0 1;
    }
    #approval-bar.visible { display: block; }

    #approval-bar .approval-label {
        color: #f0883e;
        text-style: bold;
        padding: 0 0 0 0;
        max-width: 80;
    }

    #approval-bar .approval-buttons {
        layout: horizontal;
        height: 1;
    }

    #approval-bar Button {
        margin: 0 1 0 0;
        min-width: 10;
        max-height: 1;
    }

    .approve-btn { background: #238636; color: #ffffff; border: solid #2ea043; }
    .approve-btn:hover { background: #2ea043; }
    .approve-btn:focus { border: solid #ffffff; }

    .deny-btn { background: #da3633; color: #ffffff; border: solid #f85149; }
    .deny-btn:hover { background: #f85149; }
    .deny-btn:focus { border: solid #ffffff; }

    #parallel-bar {
        display: none;
        height: auto;
        background: #161b22;
        border: solid #d2a8ff;
        margin: 0 1 0 1;
        padding: 1;
    }
    #parallel-bar.visible { display: block; }
    #parallel-bar .parallel-title {
        color: #d2a8ff;
        text-style: bold;
        padding: 0 0 1 0;
    }
    #parallel-bar .parallel-agent {
        padding: 0 0 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+l", "clear_chat", "Clear"),
        Binding("f1", "show_shortcuts", "Help / ?"),
        Binding("escape", "dismiss_suggestions", "Dismiss"),
        Binding("y", "approve_action", "Approve", show=True, priority=True),
        Binding("n", "deny_action", "Deny", show=True, priority=True),
        Binding("ctrl+y", "approve_action", "Approve", show=False),
        Binding("ctrl+n", "deny_action", "Deny", show=False),
        Binding("ctrl+d", "toggle_dashboard", "Dashboard"),
        Binding("ctrl+t", "show_tasks", "Tasks"),
        Binding("ctrl+c", "cancel_task", "Cancel"),
        Binding("pageup", "scroll_page_up", "Scroll Up", show=False),
        Binding("pagedown", "scroll_page_down", "Scroll Down", show=False),
        Binding("ctrl+up", "scroll_line_up", "Scroll Up", show=False),
        Binding("ctrl+down", "scroll_line_down", "Scroll Down", show=False),
        Binding("shift+up", "scroll_page_up", "Scroll Up", show=False),
        Binding("shift+down", "scroll_page_down", "Scroll Down", show=False),
        Binding("ctrl+home", "scroll_home", "Top", show=False),
        Binding("ctrl+end", "scroll_end", "Bottom", show=False),
    ]

    TITLE = "Sago"

    current_agent: reactive[str] = reactive("sago-orchestrator")
    current_model: reactive[str] = reactive("openrouter/free")
    current_provider: reactive[str] = reactive("openrouter")
    current_effort: reactive[str] = reactive("medium")
    current_session_id: reactive[str] = reactive("")
    messages: reactive[list[dict]] = reactive(list)
    show_suggestions: reactive[bool] = reactive(False)
    suggestion_items: reactive[list[str]] = reactive(list)
    suggestion_values: reactive[list[str]] = reactive(list)
    suggestion_index: reactive[int] = reactive(0)
    is_thinking: reactive[bool] = reactive(False)
    pending_action: reactive[dict] = reactive(dict)
    pending_orchestration: dict | None = None
    _orchestration_lock: threading.Lock | None = None
    approval_message: reactive[str] = reactive("")
    yolo_mode: reactive[bool] = reactive(False)
    developer_mode: reactive[bool] = reactive(False)
    show_summary: reactive[bool] = reactive(False)
    # Pause/resume mechanism for todo confirmations
    _executor_pause_event: threading.Event | None = None
    _executor_thread: object = None  # running thread reference
    _tool_approved: bool = False
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_hit_tokens: int = 0
    total_cache_miss_tokens: int = 0
    # Parallel execution state
    _dashboard: AgentDashboard | None = None
    _dashboard_visible: reactive[bool] = reactive(False)
    _task_manager: BackgroundTaskManager | None = None
    _active_parallel_futures: dict[str, concurrent.futures.Future] = {}
    _parallel_lock: threading.Lock | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="main-layout"):
            with Vertical(id="messages-parent"):
                yield ScrollableContainer(id="messages")
                yield Vertical(id="welcome-screen")
                yield Vertical(id="suggestions")
                with Vertical(id="approval-bar"):
                    yield Static(
                        "Pending action",
                        id="approval-label",
                        classes="approval-label",
                        markup=False,
                    )
                    with Horizontal(id="approval-buttons"):
                        yield Button(
                            "Approve [Y]",
                            id="btn-approve",
                            variant="success",
                            classes="approve-btn",
                        )
                        yield Button("Deny [N]", id="btn-deny", variant="error", classes="deny-btn")
                with Vertical(id="parallel-bar"):
                    yield Static(
                        "Parallel Agents",
                        id="parallel-title",
                        classes="parallel-title",
                        markup=False,
                    )
                    yield Vertical(id="parallel-agents")
                with Vertical(id="input-area"):
                    yield Input(placeholder="/, @, # for autocomplete", id="msg-input")
            with Vertical(id="agent-dashboard", classes="hidden"):
                yield Static("Agent Dashboard", classes="dashboard-title", markup=True)
                yield Static("", id="agent-dashboard-content", markup=True)

    MAX_COMMAND_HISTORY = 200

    def on_mount(self) -> None:
        self._spinner = None
        self._spinner_timer = None
        self._pending_resume = getattr(self, "_pending_resume", None)
        self.command_history: list[str] = []
        self.history_index: int = -1
        self._orchestration_lock = threading.Lock()
        self._parallel_lock = threading.Lock()
        self._init_db()
        self._init_session()
        self._load_settings()
        self._task_manager = get_task_manager()
        # Populate welcome screen
        self._populate_welcome_screen()
        # Auto-resume if --resume flag was passed
        if self._pending_resume:
            self._load_session(self._pending_resume)
            self._pending_resume = None
        # Auto-refresh models if stale
        self._auto_refresh_models()
        self.query_one("#msg-input").focus()
        # Start dashboard update timer
        self._dashboard_timer = self.set_interval(1.0, self._periodic_dashboard_update)

    def _populate_welcome_screen(self) -> None:
        """Populate the welcome screen with SAGO logo and info."""
        welcome = self.query_one("#welcome-screen")
        parent = self.query_one("#messages-parent")
        parent.add_class("has-welcome")
        logo_lines = [
            "██████╗  █████╗  ██████╗  ██████╗",
            "██╔════╝ ██╔══██╗██╔════╝ ██╔═══██╗",
            "╚█████╗  ███████║██║  ███╗██║   ██║",
            " ╚═══██╗ ██╔══██║██║   ██║██║   ██║",
            "██████╔╝ ██║  ██║╚██████╔╝╚██████╔╝",
            "╚═════╝  ╚═╝  ╚═╝ ╚═════╝  ╚═════╝",
        ]
        for line in logo_lines:
            welcome.mount(Static(line, classes="welcome-logo"))
        welcome.mount(Static("─" * 40, classes="welcome-separator"))
        welcome.mount(Static("v0.1.1 — Multi-Agent Orchestration", classes="welcome-version"))
        welcome.mount(Static("AI-Powered Software Engineering Agent", classes="welcome-subtitle"))
        welcome.mount(Static("Type a message or use /help for commands", classes="welcome-hint"))

    def _hide_welcome_screen(self) -> None:
        """Hide the welcome screen and show messages."""
        try:
            welcome = self.query_one("#welcome-screen")
            welcome.add_class("hidden")
            parent = self.query_one("#messages-parent")
            parent.remove_class("has-welcome")
        except Exception as e:
            logger.debug("Could not hide welcome screen: %s", e)

    def _extract_file_context(self, message: str) -> str:
        """Extract #file references from message and return their contents as context."""
        import re
        from pathlib import Path

        # Find all #filepath references (support #file, #./file, #~/.file, etc.)
        file_refs = re.findall(r"#([^\s,#@/]+(?:/[^\s,#@/]+)*)", message)

        context_parts = []
        for ref in file_refs:
            try:
                # Expand path
                if ref.startswith("~"):
                    path = Path.home() / ref[1:]
                elif ref.startswith("./"):
                    path = Path(ref)
                else:
                    path = Path(ref)

                if path.exists() and path.is_file():
                    # Read file content (limit to 10KB per file)
                    content = path.read_text(errors="replace")[:10240]
                    context_parts.append(f"--- {path.name} ---\n{content}")
            except Exception:
                pass

        return "\n\n".join(context_parts)

    _loading_settings: bool = True

    def _load_settings(self) -> None:
        """Load persisted settings (model, provider, effort, yolo, agent)."""
        try:
            from sago.settings import load_setting

            self._loading_settings = True
            self.current_model = load_setting("model", self.current_model)
            self.current_provider = load_setting("provider", self.current_provider)
            self.current_effort = load_setting("effort", self.current_effort)
            self.current_agent = load_setting("agent", self.current_agent)
            self.yolo_mode = load_setting("yolo", self.yolo_mode)
            self.show_summary = load_setting("show_summary", self.show_summary)
        except Exception as e:
            logger.warning("Failed to load settings: %s", e)
        finally:
            self._loading_settings = False

    def _save_settings(self) -> None:
        """Persist current settings."""
        if self._loading_settings:
            return
        try:
            from sago.settings import save_setting

            save_setting("model", self.current_model)
            save_setting("provider", self.current_provider)
            save_setting("effort", self.current_effort)
            save_setting("agent", self.current_agent)
            save_setting("yolo", self.yolo_mode)
            save_setting("show_summary", self.show_summary)
        except Exception as e:
            logger.warning("Failed to save settings: %s", e)

    def _auto_refresh_models(self) -> None:
        """Refresh model list from OpenRouter if cache is stale."""
        import os

        try:
            from sago.tui.models import auto_refresh_if_stale

            # Only refresh if OpenRouter key is available
            api_key = os.environ.get("OPENROUTER_API_KEY", "")
            if not api_key:
                return
            msg = auto_refresh_if_stale(api_key)
            if msg:
                self._add_system_message(f"[auto-refresh] {msg}")
        except Exception as e:
            logger.debug("Auto-refresh models failed: %s", e)

    def _resolve_api_model(self) -> str:
        """Strip provider prefix for API calls. google/gemini-2.0-flash -> gemini-2.0-flash."""
        m = self.current_model
        p = self.current_provider
        if p == "google" and m.startswith("google/"):
            return m[len("google/") :]
        if p == "openai" and m.startswith("openai/"):
            return m[len("openai/") :]
        return m

    def _get_provider_api_key(self) -> str:
        """Get the API key for the current provider."""
        import os

        provider_key_map = {
            "google": "GEMINI_API_KEY",
            "openai": "OPENAI_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
        }
        env_var = provider_key_map.get(self.current_provider, "OPENROUTER_API_KEY")
        return os.environ.get(env_var, "")

    def _get_provider_key_name(self) -> str:
        """Get the environment variable name for the current provider's API key."""
        provider_key_map = {
            "google": "GEMINI_API_KEY",
            "openai": "OPENAI_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
        }
        return provider_key_map.get(self.current_provider, "OPENROUTER_API_KEY")

    def watch_current_model(self, value: str) -> None:
        """Auto-save model when changed."""
        self._save_settings()

    def watch_current_provider(self, value: str) -> None:
        """Auto-save provider when changed."""
        self._save_settings()

    def watch_current_effort(self, value: str) -> None:
        """Auto-save effort when changed."""
        self._save_settings()

    def watch_current_agent(self, value: str) -> None:
        """Auto-save agent when changed."""
        self._save_settings()

    def watch_yolo_mode(self, value: bool) -> None:
        """Auto-save yolo mode and sync permission manager when changed."""
        self._save_settings()
        try:
            from sago.permissions import get_permission_manager

            pm = get_permission_manager()
            pm.set_global_yolo(value)
            if hasattr(self, "current_session_id") and self.current_session_id:
                pm.set_yolo_mode(self.current_session_id, value)
        except Exception:
            pass

    def watch_show_summary(self, value: bool) -> None:
        """Auto-save summary visibility when changed."""
        self._save_settings()

    def _init_db(self) -> None:
        try:
            from sago.database import init_db

            init_db()
        except Exception as e:
            import logging

            logging.getLogger("sago.tui").debug(f"DB init failed: {e}")

    def _init_session(self) -> None:
        try:
            from sago.database import Session, init_db

            init_db()
            session = Session()
            result = session.create(title="TUI Session")
            self.current_session_id = result["id"]
            session.close()
        except Exception as e:
            import logging

            logging.getLogger("sago.tui").debug(f"Session init failed: {e}")
            self.current_session_id = "local"

    @on(Input.Changed, "#msg-input")
    def on_input_changed(self, event: Input.Changed) -> None:
        v = event.value

        # If the input starts with ?, show shortcuts quick suggestions
        if v.startswith("?"):
            self._show_shortcuts_suggestions(v)
            return

        # If the input starts with a slash command, trigger smart command autocompleter
        if v.startswith("/"):
            self._show_cmd_suggestions(v)
            return

        # Find the last space to determine current "word" for @ and # triggers
        last_space = v.rfind(" ")
        current_word = v[last_space + 1 :] if last_space >= 0 else v

        if current_word.startswith("#"):
            prefix = current_word[1:]  # remove #
            self._show_file_suggestions(prefix)
        elif current_word.startswith("@"):
            prefix = current_word[1:]  # remove @
            self._show_agent_suggestions(prefix)
        elif current_word.startswith("~"):
            prefix = current_word[1:]  # remove ~
            self._show_file_suggestions(prefix, home=True)
        else:
            self._hide_suggestions()

    @on(Button.Pressed, ".btn-copy-code")
    def on_copy_code_button(self, event: Button.Pressed) -> None:
        """Copy code snippet to system clipboard."""
        event.stop()
        from sago.tools.session.clipboard import ClipboardTool

        code = getattr(event.button, "_code_content", "")
        if code:
            ClipboardTool()._write_clipboard(code)
            event.button.label = "✓ Copied!"
            self._add_system_message("📋 Code snippet copied to clipboard.")

            def _reset() -> None:
                try:
                    event.button.label = "📋 Copy Code"
                except Exception:
                    pass

            self.set_timer(2.0, _reset)

    @on(Input.Submitted, "#msg-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        msg = event.value.strip()
        if not msg:
            return

        if self.show_suggestions and self.suggestion_values:
            val = self.suggestion_values[self.suggestion_index]
            self._hide_suggestions()

            if val.startswith("/"):
                # Complete command selected -> execute immediately
                event.input.value = ""
                self._handle_command(val)
                return
            elif val.startswith("@") or val.startswith("#") or val.startswith("~"):
                v = event.value
                last_space = v.rfind(" ")
                current_word_start = last_space + 1 if last_space >= 0 else 0
                new_val = val + " "
                event.input.value = v[:current_word_start] + new_val
                event.input.cursor_position = len(event.input.value)
                return

        event.input.value = ""
        self._hide_suggestions()
        self.history_index = -1

        if msg in ("?", "/?", "/shortcuts", "/shortcut", "/keys"):
            self._handle_shortcuts_command()
        elif (
            self._executor_pause_event is not None
            or bool(getattr(self, "approval_message", ""))
            or bool(getattr(self, "pending_action", None))
        ) and msg.lower() in (
            "y",
            "yes",
            "approve",
            "allow",
            "ok",
            "/approve",
            "/allow",
            "/y",
        ):
            self._approve_action()
        elif (
            self._executor_pause_event is not None
            or bool(getattr(self, "approval_message", ""))
            or bool(getattr(self, "pending_action", None))
        ) and msg.lower() in (
            "n",
            "no",
            "deny",
            "skip",
            "cancel",
            "block",
            "/deny",
            "/block",
            "/n",
        ):
            self._deny_action()
        elif msg.startswith("/"):
            if msg != "/history":
                self._add_to_history(msg)
            self._handle_command(msg)
        else:
            self._add_to_history(msg)
            self._add_user_message(msg)
            self._process_message(msg)

    def on_key(self, event) -> None:
        if self.show_suggestions:
            if event.key == "down":
                event.prevent_default()
                self._move_sel(1)
            elif event.key == "up":
                event.prevent_default()
                self._move_sel(-1)
            elif event.key == "tab":
                event.prevent_default()
                self._select_current()
            elif event.key == "escape":
                event.prevent_default()
                self._hide_suggestions()
        else:
            # Dedicated keyboard scrolling for messages pane
            if event.key in ("pageup", "shift+up"):
                event.prevent_default()
                try:
                    self.query_one("#messages").scroll_page_up(animate=False)
                except Exception:
                    pass
                return
            elif event.key in ("pagedown", "shift+down"):
                event.prevent_default()
                try:
                    self.query_one("#messages").scroll_page_down(animate=False)
                except Exception:
                    pass
                return

            # Command history navigation when no suggestions visible
            inp = self.query_one("#msg-input")
            if inp.cursor_position == 0 and not inp.value:
                if event.key == "up":
                    self._navigate_history("up")
                elif event.key == "down":
                    self._navigate_history("down")

    def _move_sel(self, d: int) -> None:
        n = len(self.suggestion_values)
        if n == 0:
            return
        self.suggestion_index = (self.suggestion_index + d) % n
        self._update_highlight()

    def _select_current(self) -> None:
        if self.suggestion_values:
            val = self.suggestion_values[self.suggestion_index]
            inp = self.query_one("#msg-input")
            if val.startswith("/"):
                inp.value = val + " "
                inp.cursor_position = len(inp.value)
                if (
                    val.startswith("/model ")
                    and not val.startswith("/model add")
                    and not val.startswith("/model remove")
                    and not val.startswith("/model refresh")
                ):
                    model_id = val[7:].strip()
                    provider = model_id.split("/")[0]
                    self.current_provider = provider
                    self.current_model = model_id
            else:
                v = inp.value
                last_space = v.rfind(" ")
                current_word_start = last_space + 1 if last_space >= 0 else 0
                new_val = val + " "
                inp.value = v[:current_word_start] + new_val
                inp.cursor_position = len(inp.value)
            self._hide_suggestions()

    def _update_highlight(self) -> None:
        items = self.query(".suggestion-item")
        for i, item in enumerate(items):
            is_highlighted = i == self.suggestion_index
            item.set_class(is_highlighted, "highlighted")
            # Auto-scroll highlighted item into view
            if is_highlighted:
                item.scroll_visible()

    def _add_to_history(self, cmd: str) -> None:
        if cmd and (not self.command_history or self.command_history[-1] != cmd):
            self.command_history.append(cmd)
            if len(self.command_history) > self.MAX_COMMAND_HISTORY:
                self.command_history = self.command_history[-self.MAX_COMMAND_HISTORY :]
        self.history_index = len(self.command_history)

    def _navigate_history(self, key: str) -> None:
        if not self.command_history:
            return
        if key == "up":
            self.history_index = max(0, self.history_index - 1)
        else:
            self.history_index = min(len(self.command_history) - 1, self.history_index + 1)
        if 0 <= self.history_index < len(self.command_history):
            self.query_one("#msg-input").value = self.command_history[self.history_index]

    def on_mouse_scroll_down(self, event) -> None:
        self.query_one("#messages").scroll_down()

    def on_mouse_scroll_up(self, event) -> None:
        self.query_one("#messages").scroll_up()

    def on_click(self, event) -> None:
        self.query_one("#msg-input").focus()

    def _periodic_dashboard_update(self) -> None:
        """Periodically update the dashboard with current task states."""
        if getattr(self, "_dashboard_visible", False):
            self._update_dashboard()

    def action_toggle_dashboard(self) -> None:
        """Toggle the agent dashboard sidebar."""
        self._toggle_dashboard()

    def action_show_tasks(self) -> None:
        """Show background tasks."""
        self._show_tasks()

    def action_cancel_task(self) -> None:
        """Cancel the most recent running task."""
        from sago.tui.widgets import get_task_manager

        tm = get_task_manager()
        active = tm.get_active_tasks()
        if active:
            last = active[-1]
            tm.cancel_task(last.agent_id)
            self._add_system_message(f"Cancelled: {last.agent_name} ({last.agent_id})")
        else:
            self._add_system_message("No active tasks to cancel")

    def action_show_shortcuts(self) -> None:
        """Show shortcuts reference modal."""
        self._handle_shortcuts_command()

    def _show_shortcuts_suggestions(self, query: str = "") -> None:
        """Show shortcuts and quick help suggestions."""
        items = [
            "[bold cyan]⌨️  ?[/bold cyan] [dim]Open interactive shortcuts & quick reference sheet (F1)[/dim]",
            "[bold yellow]⚡ /dev on[/bold yellow] [dim]Enable live developer telemetry & LLM traces[/dim]",
            "[bold magenta]● /theme <name>[/bold magenta] [dim]Switch between 11 terminal color themes[/dim]",
            "[bold green]● /checkpoint[/bold green] [dim]Atomic snapshot & workspace rollback[/dim]",
            "[bold blue]● /collapse all[/bold blue] [dim]Collapse/expand conversational turns[/dim]",
        ]
        values = ["?", "/dev on", "/theme obsidian", "/checkpoint list", "/collapse all"]
        self._show_suggestions(items, values)

    def _show_cmd_suggestions(self, prefix: str) -> None:
        raw = prefix.strip()

        # 1. /model suggestions
        if raw.startswith("/model"):
            query = raw[6:].strip()
            self._show_model_suggestions(query)
            return

        # 2. /theme or /themes suggestions
        if raw.startswith("/theme") or raw.startswith("/themes"):
            query = raw.split(None, 1)[1].strip() if " " in raw else ""
            from sago.tui.models import THEMES

            matches = [k for k in THEMES if query.lower() in k.lower()] or list(THEMES.keys())
            items = [f"[bold cyan]● {k:<16}[/bold cyan] [dim]{THEMES[k]}[/dim]" for k in matches]
            values = [f"/theme {k}" for k in matches]
            self._show_suggestions(items, values)
            return

        # 3. /developer or /dev suggestions
        if raw.startswith("/dev") or raw.startswith("/developer"):
            query = raw.split(None, 1)[1].strip() if " " in raw else ""
            dev_opts = {
                "on": "Enable full execution tracing & telemetry",
                "off": "Disable developer mode",
                "toggle": "Toggle developer mode",
                "logs": "View live telemetry log buffer",
                "traces": "View microsecond function latency traces",
                "export": "Export traces to JSON/Markdown (/dev export [file])",
                "clear": "Clear trace buffer",
            }
            matches = [k for k in dev_opts if query.lower() in k.lower()] or list(dev_opts.keys())
            items = [
                f"[bold yellow]⚡ {k:<10}[/bold yellow] [dim]{dev_opts[k]}[/dim]" for k in matches
            ]
            values = [f"/dev {k}" for k in matches]
            self._show_suggestions(items, values)
            return

        # 4. /effort suggestions
        if raw.startswith("/effort"):
            query = raw[7:].strip()
            efforts = {
                "low": "Fast responses, minimal reasoning tokens",
                "medium": "Balanced reasoning and speed (default)",
                "high": "Deep reasoning and extensive analysis",
                "max": "Maximum compute, exhaustive exploration",
            }
            matches = [k for k in efforts if query.lower() in k.lower()] or list(efforts.keys())
            items = [f"[bold green]● {k:<8}[/bold green] [dim]{efforts[k]}[/dim]" for k in matches]
            values = [f"/effort {k}" for k in matches]
            self._show_suggestions(items, values)
            return

        # 5. /agent suggestions
        if raw.startswith("/agent "):
            query = raw[7:].strip()
            try:
                from sago.agents.registry import list_agents

                agents = list_agents()
                matches = [a for a in agents if query.lower() in a["name"].lower()]
                items = [
                    f"[bold magenta]@{a['name']}[/bold magenta] [dim]{a.get('description', '')[:40]}[/dim]"
                    for a in matches[:25]
                ]
                values = [f"/agent {a['name']}" for a in matches[:25]]
                self._show_suggestions(items, values)
                return
            except Exception:
                pass

        # 6. /checkpoint suggestions
        if raw.startswith("/checkpoint"):
            query = raw.split(None, 1)[1].strip() if " " in raw else ""
            opts = {
                "create": "Create a new atomic point-in-time snapshot",
                "list": "List available workspace checkpoints",
                "restore": "Restore workspace to a checkpoint (/checkpoint restore <id>)",
            }
            matches = [k for k in opts if query.lower() in k.lower()] or list(opts.keys())
            items = [f"[bold blue]● {k:<10}[/bold blue] [dim]{opts[k]}[/dim]" for k in matches]
            values = [f"/checkpoint {k}" for k in matches]
            self._show_suggestions(items, values)
            return

        # 7. General command prefix matching
        matches = [cmd for cmd in COMMANDS if cmd.startswith(raw.lower())]
        if not matches:
            matches = [cmd for cmd in COMMANDS if raw.lower().lstrip("/") in cmd]
        values = matches
        items = [f"[bold cyan]{cmd:<14}[/bold cyan] [dim]{COMMANDS[cmd]}[/dim]" for cmd in matches]
        self._show_suggestions(items, values)

    def _show_model_suggestions(self, query: str, provider_filter: str = "") -> None:
        from sago.tui.models import BUILTIN_MODELS, get_all_models

        models = get_all_models()
        query = query.strip().lower()
        if "/" in query:
            parts = query.split("/", 1)
            provider_filter = parts[0]
            query = parts[1]

        if provider_filter:
            models = [m for m in models if m.lower().startswith(provider_filter.lower())]

        if query:
            models = [m for m in models if query in m.lower()]

        if not models:
            models = [m for m in BUILTIN_MODELS if query in m.lower()]

        items = [f"[bold cyan]● {m}[/bold cyan]" for m in models[:30]]
        values = [f"/model {m}" for m in models[:30]]
        self._show_suggestions(items, values)

    def _show_agent_suggestions(self, prefix: str) -> None:
        try:
            from sago.agents.registry import list_agents

            agents = list_agents()
            if "," in prefix:
                already_selected = [a.strip() for a in prefix.split(",")]
                current_typing = already_selected[-1]
                prefix_before = ",".join(already_selected[:-1]) + ","
                matches = [
                    a["name"]
                    for a in agents
                    if a["name"].startswith(current_typing) and a["name"] not in already_selected
                ]
                items = [f"@{name}" for name in matches]
                values = [f"@{prefix_before}{name}" for name in matches]
            else:
                matches = [a["name"] for a in agents if a["name"].startswith(prefix)]
                items = [f"@{name}" for name in matches]
                values = [f"@{name}" for name in matches]
            self._show_suggestions(items, values)
        except Exception:
            pass

    def _show_file_suggestions(self, prefix: str, home: bool = False) -> None:
        import os
        from pathlib import Path

        if home:
            base_path = Path.home()
            search_prefix = prefix
        elif "/" in prefix:
            last_slash = prefix.rfind("/")
            dir_part = prefix[:last_slash]
            search_prefix = prefix[last_slash + 1 :]
            base_path = Path.cwd() / dir_part if not os.path.isabs(dir_part) else Path(dir_part)
        else:
            base_path = Path.cwd()
            search_prefix = prefix

        if not base_path.exists() or not base_path.is_dir():
            self._hide_suggestions()
            return

        items = []
        values = []
        try:
            entries = sorted(base_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            self._hide_suggestions()
            return

        for f in entries:
            if not f.name.lower().startswith(search_prefix.lower()):
                continue
            if f.name.startswith(".") and not search_prefix.startswith("."):
                continue  # Skip hidden files unless explicitly searching
            name = f.name + "/" if f.is_dir() else f.name
            items.append(name)
            if home:
                values.append(f"~{f.name}")
            else:
                values.append(f"#{f.name}")
        self._show_suggestions(items, values)

    def _show_suggestions(self, items: list[str], values: list[str]) -> None:
        if not items:
            self._hide_suggestions()
            return
        self.suggestion_items = items
        self.suggestion_values = values
        self.suggestion_index = 0
        self.show_suggestions = True
        container = self.query_one("#suggestions")
        container.remove_children()
        for item in items:
            container.mount(Static(item, classes="suggestion-item", markup=True))
        container.add_class("visible")
        self._update_highlight()

    def _hide_suggestions(self) -> None:
        self.show_suggestions = False
        self.suggestion_items = []
        self.suggestion_values = []
        self.query_one("#suggestions").remove_class("visible")

    def action_dismiss_suggestions(self) -> None:
        """Dismiss suggestions and approval bar."""
        self._hide_suggestions()
        if self.approval_message:
            self._hide_approval_bar()

    def action_approve_action(self) -> None:
        """Handle Y key or Approve action."""
        self._approve_action()

    def action_deny_action(self) -> None:
        """Handle N key or Deny action."""
        self._deny_action()

    @on(Button.Pressed, "#btn-approve")
    def on_approve_pressed(self, event: Button.Pressed) -> None:
        """Handle Approve button click."""
        self._approve_action()

    @on(Button.Pressed, "#btn-deny")
    def on_deny_pressed(self, event: Button.Pressed) -> None:
        """Handle Deny button click."""
        self._deny_action()

    def _show_approval_bar(self, message: str) -> None:
        """Show the approval bar with a message."""
        self.approval_message = message
        label = self.query_one("#approval-label", Static)
        label.update(f"  {message}")
        self.query_one("#approval-bar").add_class("visible")

    def _hide_approval_bar(self) -> None:
        """Hide the approval bar."""
        self.approval_message = ""
        self.query_one("#approval-bar").remove_class("visible")

    def _show_spinner(self, text: str = "Thinking") -> None:
        self._hide_spinner()
        s = Spinner(text, classes="spinner")
        target_card = getattr(self, "_active_exchange_card", None)
        if target_card is not None and hasattr(target_card, "mount_child"):
            target_card.mount_child(s)
        elif target_card is not None:
            target_card.mount(s)
        else:
            self.query_one("#messages").mount(s)
        self.query_one("#messages").scroll_end()
        self._spinner = s
        self._spinner_timer = self.set_interval(0.08, self._advance_spinner)

    def _advance_spinner(self) -> None:
        if self._spinner:
            self._spinner.advance()

    def _update_spinner(self, text: str) -> None:
        if self._spinner:
            self._spinner.text = text
            self._spinner.refresh()

    def _hide_spinner(self) -> None:
        if self._spinner_timer:
            self._spinner_timer.stop()
            self._spinner_timer = None
        if self._spinner:
            try:
                self._spinner.remove()
            except Exception as e:
                logger.debug("Could not remove spinner: %s", e)
            self._spinner = None

    def _handle_command(self, command: str) -> None:
        self._hide_welcome_screen()
        parts = command.strip().split(None, 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        handlers = {
            "/help": lambda: self._show_help(),
            "/?": lambda: self._handle_shortcuts_command(args),
            "/shortcuts": lambda: self._handle_shortcuts_command(args),
            "/shortcut": lambda: self._handle_shortcuts_command(args),
            "/keys": lambda: self._handle_shortcuts_command(args),
            "/agents": lambda: self._show_agents(args),
            "/agent": lambda: self._set_agent(args),
            "/delegate": lambda: self._delegate_task(args),
            "/chain": lambda: self._chain_agents(args),
            "/orchestrate": lambda: self._orchestrate_task(args),
            "/clear": lambda: self.action_clear_chat(),
            "/status": lambda: self._show_status(),
            "/export": lambda: self._export_session(args),
            "/sessions": lambda: self._show_sessions(),
            "/session": lambda: self._switch_session(args),
            "/history": lambda: self._show_history(),
            "/model": lambda: self._change_model(args),
            "/provider": lambda: self._change_provider(args),
            "/effort": lambda: self._set_effort(args),
            "/cost": lambda: self._show_cost(),
            "/compact": lambda: self._compact(),
            "/retry": lambda: self._retry_last(),
            "/reset": lambda: self._reset(),
            "/save": lambda: self._save_session(args),
            "/load": lambda: self._load_session(args),
            "/git": lambda: self._git_status(),
            "/diff": lambda: self._git_diff(args),
            "/commit": lambda: self._git_commit(args),
            "/approve": lambda: self._approve_action(),
            "/deny": lambda: self._deny_action(),
            "/version": lambda: self._show_version(),
            "/yolo": lambda: self._toggle_yolo(),
            "/permissions": lambda: self._show_permissions(args),
            "/allow": lambda: self._allow_tool(args),
            "/block": lambda: self._block_tool(args),
            "/todo": lambda: self._show_todo(args),
            "/todos": lambda: self._show_all_todos(),
            "/done": lambda: self._mark_todo_done(args),
            "/ask": lambda: self._ask_user(args),
            "/plan": lambda: self._show_plan(args),
            "/undo": lambda: self._undo_change(),
            "/changes": lambda: self._show_changes(),
            "/exit": lambda: self._exit_session(),
            "/resume": lambda: self._list_sessions(),
            "/parallel": lambda: self._run_parallel(args),
            "/dashboard": lambda: self._toggle_dashboard(),
            "/tasks": lambda: self._show_tasks(),
            "/cancel": lambda: self._cancel_task(args),
            "/handoff": lambda: self._show_handoff(),
            "/agents-color": lambda: self._list_agents_color(),
            "/summary": lambda: self._toggle_summary(),
            "/map": lambda: self._show_repo_map(args),
            "/verify": lambda: self._run_verify(),
            "/skills": lambda: self._show_skills(args),
            "/plugins": lambda: self._show_plugins(),
            "/theme": lambda: self._set_theme(args),
            "/themes": lambda: self._set_theme(args),
            "/collapse": lambda: self._collapse_chats(args),
            "/developer": lambda: self._handle_developer_command(args),
            "/dev": lambda: self._handle_developer_command(args),
            "/checkpoint": lambda: self._handle_checkpoint_command(args),
            "/project_graph": lambda: self._show_project_graph(args),
            "/graph": lambda: self._show_project_graph(args),
            "/search": lambda: self._handle_search_command(args),
            "/semantic": lambda: self._handle_search_command(args),
            "/detach": lambda: self._detach_session(),
            "/copy": lambda: self._handle_copy_command(args),
            "/clip": lambda: self._handle_copy_command(args),
        }

        if cmd in handlers:
            handlers[cmd]()
        else:
            self._add_system_message(f"Unknown: {cmd}\nType /help for commands")

    def action_quit(self) -> None:
        """Save session and exit."""
        self._exit_session()

    def action_clear_chat(self) -> None:
        self.query_one("#messages").remove_children()
        self.messages.clear()
        self._add_system_message("Cleared.")

    def action_scroll_page_up(self) -> None:
        """Scroll message viewport page up."""
        try:
            self.query_one("#messages").scroll_page_up(animate=True)
        except Exception:
            pass

    def action_scroll_page_down(self) -> None:
        """Scroll message viewport page down."""
        try:
            self.query_one("#messages").scroll_page_down(animate=True)
        except Exception:
            pass

    def action_scroll_line_up(self) -> None:
        """Scroll message viewport line up."""
        try:
            self.query_one("#messages").scroll_up(animate=False)
        except Exception:
            pass

    def action_scroll_line_down(self) -> None:
        """Scroll message viewport line down."""
        try:
            self.query_one("#messages").scroll_down(animate=False)
        except Exception:
            pass

    def action_scroll_home(self) -> None:
        """Scroll message viewport to top."""
        try:
            self.query_one("#messages").scroll_home(animate=True)
        except Exception:
            pass

    def action_scroll_end(self) -> None:
        """Scroll message viewport to bottom."""
        try:
            self.query_one("#messages").scroll_end(animate=True)
        except Exception:
            pass

    def _process_delegation(self, agent_name: str, task: str) -> None:
        self.is_thinking = True
        t = threading.Thread(
            target=self._process_delegation_thread, args=(agent_name, task), daemon=True
        )
        t.start()

    def _process_delegation_thread(self, agent_name: str, task: str) -> None:
        tm = self._task_manager or get_task_manager()
        info = tm.create_task(agent_name, task)
        info.status = AgentStatus.RUNNING
        self.call_from_thread(self._update_dashboard)
        self.call_from_thread(self._show_spinner, f"Delegating to {agent_name}...")
        try:
            api_key = self._get_provider_api_key()
            if not api_key:
                self.call_from_thread(self._hide_spinner)
                self.call_from_thread(
                    self._add_system_message,
                    f"No API key. Set {self._get_provider_key_name()} environment variable.",
                )
                return

            from sago.tools.file.spawn_agent import SpawnAgentTool

            tool = SpawnAgentTool()
            result = tool.run(task=task, agent_name=agent_name)

            info.status = AgentStatus.COMPLETED
            info.result = result
            info.elapsed = _time.time() - info.start_time
            self.call_from_thread(self._update_dashboard)
            self.call_from_thread(self._hide_spinner)
            if "could not be spawned" in result or "Error:" in result:
                self.call_from_thread(
                    self._add_system_message,
                    f"{result}\n\nTry running the task directly.",
                )
            else:
                self.call_from_thread(self._add_assistant_message, result, agent_name=agent_name)
        except Exception as e:
            info.status = AgentStatus.FAILED
            info.error = str(e)
            self.call_from_thread(self._update_dashboard)
            self.call_from_thread(self._hide_spinner)
            self.call_from_thread(self._add_system_message, f"Delegation error: {e}")
        finally:
            self.is_thinking = False

    def _process_chain(self, agents: list[str], task: str) -> None:
        self.is_thinking = True
        t = threading.Thread(target=self._process_chain_thread, args=(agents, task), daemon=True)
        t.start()

    def _process_chain_thread(self, agents: list[str], task: str) -> None:
        tm = self._task_manager or get_task_manager()
        self.call_from_thread(self._show_spinner, f"Chain: {' → '.join(agents)}")
        try:
            api_key = self._get_provider_api_key()
            if not api_key:
                self.call_from_thread(self._hide_spinner)
                self.call_from_thread(
                    self._add_system_message,
                    f"No API key. Set {self._get_provider_key_name()} environment variable.",
                )
                return

            from sago.tools.file.spawn_agent import SpawnAgentTool

            tool = SpawnAgentTool()
            current_input = task
            for i, agent in enumerate(agents):
                info = tm.create_task(agent, f"Chain step {i + 1}: {task[:50]}")
                info.status = AgentStatus.RUNNING
                self.call_from_thread(self._update_dashboard)
                self.call_from_thread(self._update_spinner, f"Step {i + 1}/{len(agents)}: {agent}")
                result = tool.run(task=current_input, agent_name=agent)
                info.status = AgentStatus.COMPLETED
                info.result = result
                info.elapsed = _time.time() - info.start_time
                self.call_from_thread(self._update_dashboard)
                current_input = f"Previous agent ({agent}) said:\n\n{result}\n\nNow continue."
            self.call_from_thread(self._hide_spinner)
            self.call_from_thread(self._add_assistant_message, current_input, agent_name=agents[-1])
        except Exception as e:
            self.call_from_thread(self._hide_spinner)
            self.call_from_thread(self._add_system_message, f"Chain error: {e}")
        finally:
            self.is_thinking = False

    def _process_orchestration(self, task: str) -> None:
        self.is_thinking = True
        t = threading.Thread(target=self._process_orchestration_thread, args=(task,), daemon=True)
        t.start()

    def _process_orchestration_thread(self, task: str) -> None:
        self.call_from_thread(self._show_spinner, "Analyzing task for delegation...")
        try:
            api_key = self._get_provider_api_key()
            if not api_key:
                self.call_from_thread(self._hide_spinner)
                self.call_from_thread(
                    self._add_system_message,
                    f"No API key. Set {self._get_provider_key_name()} environment variable.",
                )
                return

            from openai import OpenAI

            from sago.agents.registry import list_agents

            client = OpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                timeout=30.0,
            )
            agents = list_agents()
            agent_list_str = "\n".join(
                [
                    f"- {a['name']}: {a.get('role', '')} | Skills: {', '.join(a.get('skills', [])[:3])}"
                    for a in agents[:50]
                ]
            )

            try:
                response = client.chat.completions.create(
                    model=self.current_model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a task orchestrator. Analyze the task and break it into steps.\n"
                                "For each step, specify which agent should handle it.\n"
                                'Reply with a JSON list of steps: [{"agent": "agent-name", "task": "what to do"}]\n\n'
                                f"Available agents:\n{agent_list_str}"
                            ),
                        },
                        {"role": "user", "content": task},
                    ],
                    max_tokens=1024,
                )
            except Exception as api_err:
                self.call_from_thread(self._hide_spinner)
                self.call_from_thread(
                    self._add_system_message,
                    f"Failed to create plan: {api_err}",
                )
                return

            plan_text = response.choices[0].message.content or "[]"
            try:
                json_match = re.search(r"\[.*\]", plan_text, re.DOTALL)
                if json_match:
                    plan = json.loads(json_match.group())
                else:
                    plan = [{"agent": "python-engineer", "task": task}]
            except json.JSONDecodeError:
                plan = [{"agent": "python-engineer", "task": task}]

            # Show plan and ask for confirmation
            plan_lines = []
            for i, step in enumerate(plan):
                agent = step.get("agent", "python-engineer")
                step_task = step.get("task", "")[:80]
                plan_lines.append(f"  {i + 1}. {agent}: {step_task}")
            plan_summary = f"Orchestration plan ({len(plan)} steps):\n" + "\n".join(plan_lines)
            self.call_from_thread(self._hide_spinner)
            self.call_from_thread(self._add_system_message, plan_summary)

            # Show approval bar with buttons
            approval_msg = f"Execute {len(plan)} steps?  Press [Y] Approve or [N] Deny"
            self.call_from_thread(self._show_approval_bar, approval_msg)

            # Store plan for /approve command
            self.pending_orchestration = {"task": task, "plan": plan}

        except Exception as e:
            self.call_from_thread(self._hide_spinner)
            self.call_from_thread(self._add_system_message, f"Orchestration error: {e}")
        finally:
            self.is_thinking = False

    def _execute_orchestration_plan(self, plan: list[dict]) -> None:
        """Execute an approved orchestration plan — dispatches to background thread."""
        self.is_thinking = True
        self._show_spinner(f"Executing {len(plan)} steps...")
        t = threading.Thread(
            target=self._execute_orchestration_plan_thread, args=(plan,), daemon=True
        )
        t.start()

    def _execute_orchestration_plan_thread(self, plan: list[dict]) -> None:
        """Runs in a background thread — all call_from_thread calls are safe here."""
        try:
            from sago.tools.file.spawn_agent import SpawnAgentTool

            tool = SpawnAgentTool()
            results = []
            for i, step in enumerate(plan):
                agent = step.get("agent", "python-engineer")
                step_task = step.get("task", "")
                self.call_from_thread(self._update_spinner, f"Step {i + 1}/{len(plan)}: {agent}")
                result = tool.run(task=step_task, agent_name=agent)
                results.append(f"**{agent}**: {result[:500]}")

            self.call_from_thread(self._hide_spinner)
            final = f"Orchestration complete ({len(plan)} steps):\n\n" + "\n\n".join(results)
            self.call_from_thread(self._add_assistant_message, final)
        except Exception as e:
            self.call_from_thread(self._hide_spinner)
            self.call_from_thread(self._add_system_message, f"Execution error: {e}")
        finally:
            self.is_thinking = False

    def _process_parallel(self, agents: list[str], task: str) -> None:
        """Run multiple agents in parallel on the same task."""
        self.is_thinking = True
        t = threading.Thread(target=self._process_parallel_thread, args=(agents, task), daemon=True)
        t.start()

    def _process_parallel_thread(self, agents: list[str], task: str) -> None:
        """Runs in a background thread."""
        tm = self._task_manager or get_task_manager()

        # Create task entries for each agent
        task_infos = []
        for agent_name in agents:
            info = tm.create_task(agent_name, task)
            info.status = AgentStatus.RUNNING
            task_infos.append(info)

        # Show parallel bar
        self.call_from_thread(self._show_parallel_bar, agents)

        # Update dashboard
        self.call_from_thread(self._update_dashboard)

        try:
            from sago.tools.file.spawn_agent import SpawnAgentTool

            tool = SpawnAgentTool()
            results: list[dict[str, Any]] = []

            def execute_agent(agent_name: str, subtask: str, info: Any) -> dict[str, Any]:
                """Execute a single agent, respecting cancellation."""
                start = _time.time()
                try:
                    # Check cancellation before starting
                    if info.cancel_event.is_set():
                        info.status = AgentStatus.CANCELLED
                        return {
                            "agent": agent_name,
                            "result": "Cancelled",
                            "elapsed": 0,
                            "success": False,
                        }

                    result = tool.run(task=subtask, agent_name=agent_name)
                    elapsed = _time.time() - start
                    info.elapsed = elapsed
                    info.status = AgentStatus.COMPLETED
                    info.result = result
                    self.call_from_thread(self._update_dashboard)
                    return {
                        "agent": agent_name,
                        "result": result,
                        "elapsed": elapsed,
                        "success": True,
                    }
                except Exception as e:
                    elapsed = _time.time() - start
                    info.elapsed = elapsed
                    info.status = AgentStatus.FAILED
                    info.error = str(e)
                    self.call_from_thread(self._update_dashboard)
                    return {
                        "agent": agent_name,
                        "result": f"Error: {e}",
                        "elapsed": elapsed,
                        "success": False,
                    }

            # Execute all agents in parallel using ThreadPoolExecutor
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(agents)) as executor:
                futures = {}
                for info in task_infos:
                    future = executor.submit(execute_agent, info.agent_name, task, info)
                    futures[future] = info
                    if self._parallel_lock:
                        with self._parallel_lock:
                            self._active_parallel_futures[info.agent_id] = future

                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    results.append(result)

            # Show results
            self.call_from_thread(self._hide_parallel_bar)
            self.call_from_thread(self._hide_spinner)

            # Sort results by agent name for consistent display
            results.sort(key=lambda r: r["agent"])

            for r in results:
                self.call_from_thread(
                    self._add_parallel_result,
                    r["agent"],
                    r["result"],
                    r["elapsed"],
                    r["success"],
                )

            # Summary
            ok = sum(1 for r in results if r["success"])
            fail = len(results) - ok
            total_time = sum(r["elapsed"] for r in results)
            max_time = max(r["elapsed"] for r in results) if results else 0
            self.call_from_thread(
                self._add_system_message,
                f"Parallel complete: {ok} ok, {fail} failed | "
                f"Total wall time: {max_time:.1f}s | Combined: {total_time:.1f}s",
            )

        except Exception as e:
            self.call_from_thread(self._hide_parallel_bar)
            self.call_from_thread(self._hide_spinner)
            self.call_from_thread(self._add_system_message, f"Parallel error: {e}")
        finally:
            self.is_thinking = False
            if self._parallel_lock:
                with self._parallel_lock:
                    self._active_parallel_futures.clear()
            self.call_from_thread(self._update_dashboard)

    def _show_parallel_bar(self, agents: list[str]) -> None:
        """Show the parallel agent status bar."""
        container = self.query_one("#parallel-agents")
        container.remove_children()
        for agent_name in agents:
            container.mount(
                Static(
                    f"{agent_name} Waiting...",
                    classes="parallel-agent",
                    markup=False,
                )
            )
        self.query_one("#parallel-bar").add_class("visible")

    def _hide_parallel_bar(self) -> None:
        """Hide the parallel agent status bar."""
        self.query_one("#parallel-bar").remove_class("visible")

    def _process_message(self, message: str) -> None:
        """Entry point — runs on main thread, dispatches work to a background thread."""
        self.is_thinking = True
        self._show_spinner()
        t = threading.Thread(target=self._process_message_thread, args=(message,), daemon=True)
        t.start()

    def _process_message_thread(self, message: str) -> None:
        """Runs in a background thread — all call_from_thread calls are safe here."""
        try:
            effort = EFFORT_LEVELS.get(self.current_effort, EFFORT_LEVELS["medium"])

            def on_tool(name, args):
                args_str = ", ".join(f"{k}={str(v)[:30]}" for k, v in list(args.items())[:3])
                self.call_from_thread(self._update_spinner, f"Running: {name}({args_str})")

            def on_tool_result(name, args, result, success):
                self.call_from_thread(self._add_tool_call, name, args, result, success)

            def on_thinking(text):
                self.call_from_thread(self._update_spinner, text)

            # Try streaming first
            try:
                import sago.engine.simple_executor as _se
                from sago.llm.tui_providers import get_tui_client

                _se._discover_tools()  # Ensure tools are loaded
                from sago.engine.simple_executor import (
                    PROMPTS,
                    _build_openai_tools,
                    _detect_project_context,
                    _detect_task_type,
                    _discover_tools,
                    _generate_plan_with_llm,
                    _get_context,
                    _is_complex_task,
                    _load_agent_profile,
                )

                tools = _discover_tools()

                # Get provider client (handles google, openai, openrouter, etc.)
                try:
                    client, api_model = get_tui_client(self.current_provider, self.current_model)
                    use_native_gemini = self.current_provider == "google"
                    gemini_client = client if use_native_gemini else None
                except ValueError as e:
                    self.call_from_thread(self._hide_spinner)
                    self.call_from_thread(self._add_system_message, str(e))
                    return

                start_time = _time.time()

                from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer

                get_dev_tracer().record(
                    event_type=TraceEventType.FUNCTION_CALL,
                    source="sago.tui.app",
                    action=f"process_message({self.current_agent})",
                    data={
                        "task": message[:120],
                        "model": self.current_model,
                        "provider": self.current_provider,
                    },
                )

                # Detect project context
                project_context = _detect_project_context()
                project_ctx = _get_context()

                if project_context["languages"]:
                    project_ctx += (
                        f"\nDetected languages: {', '.join(project_context['languages'])}"
                    )
                if project_context["frameworks"]:
                    project_ctx += (
                        f"\nDetected frameworks: {', '.join(project_context['frameworks'])}"
                    )

                # Extract file references from message and add as context
                file_context = self._extract_file_context(message)
                if file_context:
                    project_ctx += f"\n\nReferenced files:\n{file_context}"

                # Load learning suggestions
                learning_suggestion = None
                try:
                    from sago.learning import get_learning_store

                    ls = get_learning_store()
                    learning_suggestion = ls.suggest_approach("general", list(tools.keys()))
                except Exception as e:
                    logger.debug("Learning suggestion failed: %s", e)

                # Load profile and build prompt
                profile = _load_agent_profile(self.current_agent.replace("-", " ").title())
                task_type = _detect_task_type(message)
                template = PROMPTS.get(task_type, PROMPTS["create"])
                system_prompt = template.format(
                    agent_role=self.current_agent.replace("-", " ").title(),
                    project_ctx=project_ctx,
                )

                if profile and profile.get("system_prompt"):
                    system_prompt = profile["system_prompt"]

                # Inject learning suggestion
                if learning_suggestion:
                    system_prompt += (
                        f"\n\n=== PAST SUCCESSFUL APPROACH ===\n"
                        f"Based on past similar tasks, this approach worked:\n"
                        f"{learning_suggestion}\n"
                        f"Consider using a similar approach, but adapt to the current context."
                    )

                # Inject project instructions
                try:
                    from sago.memory.project_instructions import (
                        get_project_instructions,
                    )

                    pi = get_project_instructions()
                    instructions_prompt = pi.get_for_prompt()
                    if instructions_prompt:
                        system_prompt += instructions_prompt
                except Exception as e:
                    logger.debug("Project instructions failed: %s", e)

                # TODO system
                task_plan = None
                current_todo_index = 0
                todo_tool_counts: dict[str, int] = {}

                if _is_complex_task(message):
                    try:
                        from sago.tasks import TaskStatus, get_task_manager

                        tm = get_task_manager()
                        steps = _generate_plan_with_llm(message, client, self.current_model, "")
                        task_plan = tm.create_plan(goal=message, todos=steps)
                        confirm_keywords = [
                            "confirm",
                            "approve",
                            "review",
                            "check",
                            "verify",
                            "validate",
                        ]
                        for todo in task_plan.todos:
                            if any(kw in todo.description.lower() for kw in confirm_keywords):
                                todo.requires_confirmation = True
                        self.call_from_thread(
                            self._add_plan_card,
                            tm.format_plan(task_plan),
                            len(task_plan.todos),
                        )
                        if task_plan.todos:
                            tm.start_todo(task_plan.id, task_plan.todos[0].id)
                            self.call_from_thread(
                                self._update_spinner,
                                f"Step 1/{len(task_plan.todos)}: {task_plan.todos[0].description[:50]}",
                            )
                    except Exception as e:
                        logger.debug("Task plan creation failed: %s", e)
                        task_plan = None

                # Assemble multi-turn conversational history from prior messages
                history: list[dict[str, Any]] = []
                for m in self.messages[:-1]:
                    r = m.get("role")
                    c = m.get("content")
                    if r in ("user", "assistant") and c:
                        # Clean out reasoning tags from context history
                        cleaned_c = re.sub(
                            r"<(?:thinking|thought)>.*?</(?:thinking|thought)>",
                            "",
                            c,
                            flags=re.DOTALL,
                        ).strip()
                        if cleaned_c:
                            history.append({"role": r, "content": cleaned_c})

                # Retain up to last 16 turns to maintain complete conversational memory
                if len(history) > 16:
                    history = history[-16:]

                messages = (
                    [{"role": "system", "content": system_prompt}]
                    + history
                    + [{"role": "user", "content": message}]
                )

                # Build OpenAI function calling tool definitions
                openai_tools = _build_openai_tools(tools)

                tool_history = []
                files_created = []
                total_tokens_in = 0
                total_tokens_out = 0
                cumulative_tokens = 0
                content = ""
                tool_call_counts: dict[str, int] = {}
                failed_calls: set[str] = set()
                executed_calls: set[str] = set()
                MAX_CUMULATIVE_TOKENS = 40000  # hard cap per message

                # Initialize DB stores for this session
                _tool_usage_store = None
                _token_tracker = None
                if self.current_session_id and self.current_session_id != "local":
                    try:
                        from sago.database import ToolUsageStore, init_db

                        init_db()
                        _tool_usage_store = ToolUsageStore(self.current_session_id)
                    except Exception as e:
                        logger.debug("ToolUsageStore init failed: %s", e)
                try:
                    from sago.tracking.token_tracker import get_token_tracker

                    _token_tracker = get_token_tracker()
                except Exception as e:
                    logger.debug("Token tracker init failed: %s", e)

                for iteration in range(effort["max_iterations"]):
                    # Hard token cap — stop if budget exceeded
                    if cumulative_tokens >= MAX_CUMULATIVE_TOKENS:
                        self.call_from_thread(
                            self._add_system_message,
                            f"[STOP] Token budget exhausted ({cumulative_tokens:,} tokens used). Finishing up.",
                        )
                        break

                    # Update spinner
                    todo_info = ""
                    if task_plan and current_todo_index < len(task_plan.todos):
                        todo = task_plan.todos[current_todo_index]
                        todo_info = f" | Step {current_todo_index + 1}/{len(task_plan.todos)}: {todo.description[:40]}"
                    self.call_from_thread(
                        self._update_spinner,
                        f"Step {iteration + 1}/{effort['max_iterations']}{todo_info}...",
                    )

                    # Call LLM — native Gemini or OpenAI-compatible with function calling
                    native_tool_calls: list[dict] = []

                    if use_native_gemini:
                        # Convert messages to Google format with tools
                        sys_msg = ""
                        contents = []
                        for msg in messages:
                            if msg["role"] == "system":
                                sys_msg = msg["content"]
                            elif msg["role"] in ("user", "assistant"):
                                contents.append(msg["content"])
                        if not contents:
                            contents = ["Hello"]
                        from google.genai import types as google_types

                        # Convert tools to Google format
                        google_tools = []
                        for tool in openai_tools:
                            func = tool["function"]
                            params = func.get("parameters", {})
                            properties = {
                                k: google_types.Schema(
                                    type=google_types.Type.STRING,
                                    description=v.get("description", ""),
                                )
                                for k, v in params.get("properties", {}).items()
                            }
                            google_tools.append(
                                google_types.FunctionDeclaration(
                                    name=func["name"],
                                    description=func.get("description", ""),
                                    parameters=google_types.Schema(
                                        type=google_types.Type.OBJECT,
                                        properties=properties,
                                        required=params.get("required", []),
                                    ),
                                )
                            )

                        google_config = google_types.GenerateContentConfig(
                            system_instruction=sys_msg or None,
                            max_output_tokens=effort["max_tokens"],
                            temperature=0.3,
                        )
                        if google_tools:
                            google_config.tools = [
                                google_types.Tool(function_declarations=google_tools)
                            ]

                        response = gemini_client.models.generate_content(
                            model=api_model,
                            contents=contents,
                            config=google_config,
                        )
                        content = response.text or ""
                        # Extract tool calls from Gemini response
                        if response.candidates and response.candidates[0].content:
                            for part in response.candidates[0].content.parts or []:
                                if part.function_call:
                                    native_tool_calls.append(
                                        {
                                            "id": f"gemini_{len(native_tool_calls)}",
                                            "name": part.function_call.name,
                                            "args": dict(part.function_call.args)
                                            if part.function_call.args
                                            else {},
                                        }
                                    )
                    else:
                        # OpenAI-compatible with native function calling (streaming)
                        api_kwargs = {
                            "model": api_model,
                            "messages": messages,
                            "max_tokens": effort["max_tokens"],
                            "temperature": 0.3,
                            "stream": True,
                            "stream_options": {"include_usage": True},
                        }
                        if openai_tools:
                            api_kwargs["tools"] = openai_tools
                            api_kwargs["tool_choice"] = "auto"

                        stream = client.chat.completions.create(**api_kwargs)

                        content = ""
                        tool_call_deltas: dict[int, dict] = {}

                        for chunk in stream:
                            if hasattr(chunk, "usage") and chunk.usage:
                                total_tokens_in = chunk.usage.prompt_tokens or 0
                                total_tokens_out = chunk.usage.completion_tokens or 0
                                cumulative_tokens += total_tokens_out
                            if not chunk.choices:
                                continue
                            delta = chunk.choices[0].delta
                            if delta.content:
                                content += delta.content
                            # Accumulate streaming tool calls
                            if delta.tool_calls:
                                for tc_delta in delta.tool_calls:
                                    idx = tc_delta.index
                                    if idx not in tool_call_deltas:
                                        tool_call_deltas[idx] = {
                                            "id": "",
                                            "name": "",
                                            "arguments": "",
                                        }
                                    if tc_delta.id:
                                        tool_call_deltas[idx]["id"] = tc_delta.id
                                    if tc_delta.function:
                                        if tc_delta.function.name:
                                            tool_call_deltas[idx]["name"] = tc_delta.function.name
                                        if tc_delta.function.arguments:
                                            tool_call_deltas[idx]["arguments"] += (
                                                tc_delta.function.arguments
                                            )

                        # Convert accumulated deltas to tool calls
                        for idx in sorted(tool_call_deltas.keys()):
                            tc = tool_call_deltas[idx]
                            try:
                                parsed_args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                            except json.JSONDecodeError:
                                parsed_args = {}
                            native_tool_calls.append(
                                {
                                    "id": tc["id"],
                                    "name": tc["name"],
                                    "args": parsed_args,
                                }
                            )

                        from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer

                        get_dev_tracer().record(
                            event_type=TraceEventType.LLM_PAYLOAD,
                            source=f"tui.llm.{self.current_provider}",
                            action=f"chat.completions.create({api_model})",
                            data={
                                "model": api_model,
                                "provider": self.current_provider,
                                "messages_count": len(messages),
                                "tokens_in": total_tokens_in,
                                "tokens_out": total_tokens_out,
                                "tool_calls_generated": len(native_tool_calls),
                            },
                        )

                    # Handle empty content with no tool calls
                    if not content and not native_tool_calls:
                        if iteration < effort["max_iterations"] - 1:
                            messages.append(
                                {
                                    "role": "user",
                                    "content": "You returned an empty response. Please use the available tools to complete the task.",
                                }
                            )
                            continue
                        else:
                            content = "I wasn't able to generate a response. Please try again."

                    # Build assistant message
                    assistant_msg: dict = {"role": "assistant", "content": content or None}
                    if native_tool_calls:
                        assistant_msg["tool_calls"] = [
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": json.dumps(tc["args"])
                                    if isinstance(tc["args"], dict)
                                    else tc["args"],
                                },
                            }
                            for tc in native_tool_calls
                        ]
                    messages.append(assistant_msg)

                    # If no tool calls, check for fabrication or finish
                    if not native_tool_calls:
                        fabrication_phrases = [
                            "the file contains",
                            "the contents are",
                            "i read the file",
                            "the file has",
                            "i can see that",
                            "looking at the file",
                            "the code shows",
                            "i opened the file",
                            "the file shows",
                            "successfully created",
                            "i saved the file",
                            "the file was created",
                            "i have created",
                            "i've created",
                            "done! the file",
                        ]
                        content_lower = content.lower() if content else ""
                        is_fabrication = not tool_history and any(
                            phrase in content_lower for phrase in fabrication_phrases
                        )

                        if is_fabrication and iteration < effort["max_iterations"] - 1:
                            messages.append(
                                {
                                    "role": "user",
                                    "content": (
                                        "STOP. You are fabricating results without calling tools. "
                                        "You MUST use a tool to interact with the system. Do it NOW."
                                    ),
                                }
                            )
                            continue

                        # Handle todo completion
                        if task_plan and current_todo_index < len(task_plan.todos):
                            from sago.tasks import TaskStatus, get_task_manager

                            tm = get_task_manager()
                            todo = task_plan.todos[current_todo_index]
                            if todo.status == TaskStatus.IN_PROGRESS:
                                tm.complete_todo(
                                    task_plan.id, todo.id, result=content[:200] if content else ""
                                )
                                self.call_from_thread(
                                    self._add_system_message,
                                    f"Step {current_todo_index + 1} completed: {todo.description[:60]}",
                                )
                                current_todo_index += 1
                                if current_todo_index < len(task_plan.todos):
                                    next_todo = task_plan.todos[current_todo_index]
                                    tm.start_todo(task_plan.id, next_todo.id)
                                    messages.append(
                                        {
                                            "role": "user",
                                            "content": f"Moving to next step: {next_todo.description}\nExecute this step now.",
                                        }
                                    )
                                    continue
                        break

                    # ---- Execute native tool calls ----
                    tools_used_in_iteration = []

                    for tc in native_tool_calls:
                        tc_id = tc["id"]
                        name = tc["name"]
                        args = tc["args"] if isinstance(tc["args"], dict) else {}

                        if name not in tools:
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc_id,
                                    "content": f"Unknown tool: {name}",
                                }
                            )
                            continue

                        # Loop protection — skip duplicate successful calls
                        call_key = f"{name}:{json.dumps(args, sort_keys=True)}"
                        if call_key in executed_calls:
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc_id,
                                    "content": f"[SKIP] Already executed: {name} with identical args. Do not repeat the same call.",
                                }
                            )
                            continue
                        if call_key in failed_calls:
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc_id,
                                    "content": f"[SKIP] Already failed: {name} with same args. Try a different approach.",
                                }
                            )
                            continue

                        # Per-tool call limit (max 3 per tool name)
                        tool_call_counts[name] = tool_call_counts.get(name, 0) + 1
                        if tool_call_counts[name] > 3:
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc_id,
                                    "content": f"[SKIP] Tool '{name}' has been called {tool_call_counts[name] - 1} times already. Stop calling it and provide a final answer.",
                                }
                            )
                            continue

                        # Check permissions
                        from sago.permissions import RiskLevel, get_permission_manager

                        pm = get_permission_manager()
                        risk = pm.get_risk_level(name)

                        if self.yolo_mode:
                            allowed = True
                            reason = "YOLO mode"
                        else:
                            allowed, reason = pm.check_permission(
                                name, args, self.current_session_id
                            )

                        if not allowed:
                            if risk in (
                                RiskLevel.MEDIUM,
                                RiskLevel.HIGH,
                                RiskLevel.CRITICAL,
                            ):
                                self._tool_approved = False
                                self.call_from_thread(
                                    self._show_approval_bar,
                                    f"Allow {name}? (risk: {risk.value}) -- Press [Y] or [N]",
                                )
                                self.call_from_thread(
                                    self._add_system_message,
                                    f"⚡ Tool '[bold yellow]{name}[/bold yellow]' ({risk.value} risk) requires approval.\nPress [bold green][Y] Approve[/bold green] / [bold red][N] Deny[/bold red] or type 'y' / 'n'.",
                                )
                                pause_event = threading.Event()
                                self._executor_pause_event = pause_event
                                self._pending_tool_approval = {"name": name, "args": args}
                                pause_event.wait(timeout=300)
                                self._executor_pause_event = None
                                self._pending_tool_approval = None
                                if not self._tool_approved:
                                    messages.append(
                                        {
                                            "role": "tool",
                                            "tool_call_id": tc_id,
                                            "content": f"Permission denied: {name} requires approval",
                                        }
                                    )
                                    continue
                                # Remember session approval
                                pm.approve_tool(name, self.current_session_id)
                                self._tool_approved = False
                            else:
                                messages.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": tc_id,
                                        "content": f"Permission denied: {reason}",
                                    }
                                )
                                continue

                        on_tool(name, args)
                        t_tool_start = time.perf_counter()
                        try:
                            tool_cls = tools.get(name)
                            if tool_cls is None:
                                result_str = f"Error: Tool '{name}' not found."
                                is_error = True
                            else:
                                clean_args = dict(args)
                                if "file_path" not in clean_args and "path" in clean_args:
                                    clean_args["file_path"] = clean_args["path"]
                                if "file_path" not in clean_args and "filename" in clean_args:
                                    clean_args["file_path"] = clean_args["filename"]
                                if "command" not in clean_args and "cmd" in clean_args:
                                    clean_args["command"] = clean_args["cmd"]
                                if (
                                    "pattern" not in clean_args
                                    and "query" in clean_args
                                    and name in ("grep_content", "grep_search")
                                ):
                                    clean_args["pattern"] = clean_args["query"]

                                tool_instance = tool_cls()
                                result = tool_instance.run(**clean_args)
                                result_str = str(result)
                                is_error = (
                                    result_str.lower().startswith("error")
                                    or "traceback" in result_str.lower()
                                )
                        except Exception as tool_exc:
                            result_str = f"Error executing tool '{name}': {tool_exc}"
                            is_error = True

                        tool_dur_ms = (time.perf_counter() - t_tool_start) * 1000.0

                        is_error = (
                            result_str.lower().startswith("error")
                            or "traceback" in result_str.lower()
                        )
                        if is_error:
                            failed_calls.add(call_key)
                        else:
                            executed_calls.add(call_key)

                        from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer

                        get_dev_tracer().record(
                            event_type=TraceEventType.TOOL_DISPATCH,
                            source="tui.tool_dispatcher",
                            action=f"run({name})",
                            data={
                                "tool_name": name,
                                "arguments": args,
                                "result_preview": result_str[:250],
                                "risk_level": risk.value if "risk" in locals() else "SAFE",
                            },
                            status="FAILED" if is_error else "OK",
                            duration_ms=tool_dur_ms,
                        )

                        if name in ("write_file", "edit_file", "file_operations") and not is_error:
                            fp = (
                                args.get("file_path", "")
                                or args.get("target_file", "")
                                or args.get("path", "")
                            )
                            if fp and fp not in files_created:
                                files_created.append(fp)
                            try:
                                from sago.engine.verifier import get_continuous_verifier

                                get_continuous_verifier().enqueue_files([fp] if fp else [])
                            except Exception:
                                pass

                        if name == "write_file" and not is_error:
                            # Nudge LLM to stop after successful file write
                            if iteration < effort["max_iterations"] - 1:
                                messages.append(
                                    {
                                        "role": "user",
                                        "content": (
                                            "[SYSTEM] File operation succeeded. "
                                            "Do NOT call any more tools. Provide your final answer now."
                                        ),
                                    }
                                )

                        if name == "edit_file" and not is_error:
                            # Nudge LLM to stop after successful edit
                            if iteration < effort["max_iterations"] - 1:
                                messages.append(
                                    {
                                        "role": "user",
                                        "content": (
                                            "[SYSTEM] Edit succeeded. "
                                            "Do NOT call any more tools. Provide your final answer now."
                                        ),
                                    }
                                )

                        tool_history.append(
                            {
                                "tool": name,
                                "args": args,
                                "result": result_str[:2000],
                                "success": not is_error,
                            }
                        )
                        tools_used_in_iteration.append(name)
                        on_tool_result(name, args, result_str, not is_error)

                        # Log tool usage to DB
                        if _tool_usage_store:
                            try:
                                _tool_usage_store.log(
                                    tool_name=name,
                                    arguments=args,
                                    result=result_str[:1000],
                                    success=not is_error,
                                )
                            except Exception:
                                pass

                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "content": result_str[:500]
                                if len(result_str) > 500
                                else result_str,
                            }
                        )

                    # TODO progress
                    if task_plan:
                        try:
                            from sago.tasks import TaskStatus, get_task_manager

                            tm = get_task_manager()
                            if current_todo_index < len(task_plan.todos):
                                todo = task_plan.todos[current_todo_index]
                                if todo.id not in todo_tool_counts:
                                    todo_tool_counts[todo.id] = 0
                                todo_tool_counts[todo.id] += len(tools_used_in_iteration)

                                if (
                                    todo.requires_confirmation
                                    and todo.status == TaskStatus.IN_PROGRESS
                                ):
                                    self.call_from_thread(
                                        self._show_approval_bar,
                                        f"Confirm: {todo.confirmation_message or todo.description}",
                                    )
                                    pause_event = threading.Event()
                                    self._executor_pause_event = pause_event
                                    pause_event.wait(timeout=300)
                                    self._executor_pause_event = None

                                successful_tools = [
                                    t["tool"]
                                    for t in tool_history
                                    if t.get("success") and t["tool"] in tools_used_in_iteration
                                ]
                                tools_for_todo = todo_tool_counts.get(todo.id, 0)
                                if (tools_for_todo >= 5 and len(successful_tools) >= 3) or (
                                    tools_for_todo >= 4 and len(tools_used_in_iteration) >= 1
                                ):
                                    tm.complete_todo(
                                        task_plan.id,
                                        todo.id,
                                        result=f"Completed: {', '.join(successful_tools[:3])}",
                                    )
                                    self.call_from_thread(
                                        self._add_system_message,
                                        f"Step {current_todo_index + 1} completed: {todo.description[:60]}",
                                    )
                                    current_todo_index += 1
                                    if current_todo_index < len(task_plan.todos):
                                        next_todo = task_plan.todos[current_todo_index]
                                        tm.start_todo(task_plan.id, next_todo.id)
                                        messages.append(
                                            {
                                                "role": "user",
                                                "content": f"[PROGRESS] Step completed. Next step: {next_todo.description}\nExecute this step now.",
                                            }
                                        )
                                    else:
                                        messages.append(
                                            {
                                                "role": "user",
                                                "content": "[PROGRESS] All steps completed. Provide final summary.",
                                            }
                                        )
                        except Exception as e:
                            logger.debug("TODO progress update failed: %s", e)

                    continue  # Loop back for next LLM call with tool results as role:tool messages

                # Post-execution: test → fix → retry
                if files_created:
                    self.call_from_thread(self._update_spinner, "Running tests...")
                    from sago.engine.simple_executor import (
                        _auto_install_deps,
                        _run_tests_if_exist,
                    )

                    _auto_install_deps(files_created)
                    test_fix_attempts = 0
                    max_test_fix_attempts = 3

                    while test_fix_attempts < max_test_fix_attempts:
                        test_result = _run_tests_if_exist(files_created, tools)
                        if test_result is None:
                            break

                        test_passed, test_output = test_result
                        if test_passed:
                            self.call_from_thread(self._add_system_message, "✅ All tests passed!")
                            break

                        test_fix_attempts += 1
                        if test_fix_attempts >= max_test_fix_attempts:
                            self.call_from_thread(
                                self._add_system_message,
                                f"❌ Tests still failing after {max_test_fix_attempts} attempts",
                            )
                            break

                        self.call_from_thread(
                            self._update_spinner,
                            f"Tests failed (attempt {test_fix_attempts}/{max_test_fix_attempts}), fixing...",
                        )

                        try:
                            fix_msgs = messages + [
                                {
                                    "role": "user",
                                    "content": (
                                        f"The tests are failing. Fix them.\n\n"
                                        f"Test output:\n{test_output[:3000]}\n\n"
                                        f"Files: {', '.join(files_created)}\n"
                                        f"Fix the issues. Use edit_file or write_file."
                                    ),
                                },
                            ]
                            fix_api_kwargs = {
                                "model": api_model,
                                "messages": fix_msgs,
                                "max_tokens": effort["max_tokens"],
                                "temperature": 0.3,
                                "stream": True,
                                "stream_options": {"include_usage": True},
                            }
                            if openai_tools:
                                fix_api_kwargs["tools"] = openai_tools
                                fix_api_kwargs["tool_choice"] = "auto"

                            fix_stream = client.chat.completions.create(**fix_api_kwargs)
                            fix_content = ""
                            fix_tc_deltas: dict[int, dict] = {}
                            for chunk in fix_stream:
                                if not chunk.choices:
                                    continue
                                delta = chunk.choices[0].delta
                                if delta.content:
                                    fix_content += delta.content
                                if delta.tool_calls:
                                    for tc_delta in delta.tool_calls:
                                        idx = tc_delta.index
                                        if idx not in fix_tc_deltas:
                                            fix_tc_deltas[idx] = {
                                                "id": "",
                                                "name": "",
                                                "arguments": "",
                                            }
                                        if tc_delta.id:
                                            fix_tc_deltas[idx]["id"] = tc_delta.id
                                        if tc_delta.function:
                                            if tc_delta.function.name:
                                                fix_tc_deltas[idx]["name"] = tc_delta.function.name
                                            if tc_delta.function.arguments:
                                                fix_tc_deltas[idx]["arguments"] += (
                                                    tc_delta.function.arguments
                                                )

                            # Process accumulated fix tool calls
                            if fix_tc_deltas:
                                fix_tcs = [fix_tc_deltas[k] for k in sorted(fix_tc_deltas.keys())]
                                messages.append(
                                    {
                                        "role": "assistant",
                                        "content": fix_content or None,
                                        "tool_calls": [
                                            {
                                                "id": tc["id"],
                                                "type": "function",
                                                "function": {
                                                    "name": tc["name"],
                                                    "arguments": tc["arguments"],
                                                },
                                            }
                                            for tc in fix_tcs
                                        ],
                                    }
                                )
                                for tc in fix_tcs:
                                    try:
                                        fix_args = (
                                            json.loads(tc["arguments"]) if tc["arguments"] else {}
                                        )
                                    except json.JSONDecodeError:
                                        fix_args = {}
                                    fix_name = tc["name"]
                                    if fix_name in tools:
                                        tool_instance = tools[fix_name]()
                                        result = tool_instance.run(**fix_args)
                                        result_str = str(result)
                                        is_error = result_str.lower().startswith("error")
                                        tool_history.append(
                                            {
                                                "tool": fix_name,
                                                "args": fix_args,
                                                "result": result_str[:2000],
                                                "success": not is_error,
                                            }
                                        )
                                        if fix_name == "write_file" and not is_error:
                                            fp = fix_args.get("file_path", "")
                                            if fp and fp not in files_created:
                                                files_created.append(fp)
                                        messages.append(
                                            {
                                                "role": "tool",
                                                "tool_call_id": tc["id"],
                                                "content": result_str,
                                            }
                                        )
                            elif fix_content:
                                messages.append({"role": "assistant", "content": fix_content})
                        except Exception as e:
                            logger.debug("Test-fix loop failed: %s", e)
                            break

                # Final todo cleanup
                if task_plan:
                    try:
                        from sago.tasks import TaskStatus, get_task_manager

                        tm = get_task_manager()
                        for idx in range(current_todo_index, len(task_plan.todos)):
                            todo = task_plan.todos[idx]
                            if todo.status in (
                                TaskStatus.PENDING,
                                TaskStatus.IN_PROGRESS,
                            ):
                                tm.complete_todo(
                                    task_plan.id,
                                    todo.id,
                                    result="Task completed",
                                )
                        self.call_from_thread(self._add_system_message, tm.format_plan(task_plan))
                    except Exception as e:
                        logger.debug("Final todo cleanup failed: %s", e)

                elapsed = _time.time() - start_time
                self.call_from_thread(self._hide_spinner)

                # Record token usage to tracker
                if _token_tracker and (total_tokens_in > 0 or total_tokens_out > 0):
                    try:
                        _token_tracker.record(
                            provider=self.current_provider,
                            model=self.current_model,
                            input_tokens=total_tokens_in,
                            output_tokens=total_tokens_out,
                            latency_ms=elapsed * 1000,
                            metadata={"session_id": self.current_session_id},
                        )
                        _token_tracker.save()
                    except Exception as e:
                        logger.debug("Token tracker save failed: %s", e)

                # Flush tool usage store
                if _tool_usage_store:
                    try:
                        _tool_usage_store.flush()
                    except Exception as e:
                        logger.debug("Tool usage store flush failed: %s", e)

                # Show summary
                self.call_from_thread(
                    self._add_summary,
                    tool_history,
                    content,
                    elapsed,
                    {
                        "input": total_tokens_in,
                        "output": total_tokens_out,
                        "cumulative": cumulative_tokens,
                    },
                )

                # Show change summary
                if files_created:
                    try:
                        from sago.memory.change_tracker import get_change_tracker

                        tracker = get_change_tracker()
                        change_summary = tracker.get_diff_summary()
                        if change_summary and "No changes" not in change_summary:
                            self.call_from_thread(
                                self._add_system_message,
                                f"📝 {change_summary}",
                            )
                    except Exception as e:
                        logger.debug("Change tracker failed: %s", e)

                # Record learning
                try:
                    from sago.learning import get_learning_store

                    ls = get_learning_store()
                    successful_tools = [t["tool"] for t in tool_history if t.get("success")]
                    if successful_tools:
                        ls.record_success(
                            task_type,
                            successful_tools,
                            f"Used {', '.join(set(successful_tools[:5]))}",
                        )
                    for tool_record in tool_history:
                        ls.record_tool_effectiveness(
                            tool_record["tool"], tool_record.get("success", False)
                        )
                except Exception as e:
                    logger.debug("Learning record failed: %s", e)

                # Show response — if tools were executed, show results not raw JSON
                if tool_history:
                    # Tools were executed — show a summary of what happened
                    last_results = []
                    for t in tool_history[-3:]:
                        status = "✓" if t.get("success") else "✗"
                        last_results.append(f"{status} {t['tool']}: {t.get('result', '')[:200]}")
                    summary = "\n".join(last_results)
                    if content and content.strip() and not content.strip().startswith("{"):
                        # LLM also produced text output (not just tool calls)
                        self.call_from_thread(self._add_assistant_message, content)
                    else:
                        self.call_from_thread(self._add_assistant_message, summary)
                elif content and content.strip():
                    self.call_from_thread(self._add_assistant_message, content)
                elif tool_history:
                    tools_done = [t["tool"] for t in tool_history]
                    self.call_from_thread(
                        self._add_assistant_message,
                        f"Completed using: {', '.join(tools_done)}",
                    )
                else:
                    self.call_from_thread(
                        self._add_assistant_message,
                        "I wasn't able to process your request. Please try rephrasing.",
                    )

            except ImportError:
                # Fallback to non-streaming
                from sago.engine.simple_executor import execute_agent_task

                def on_todo_created(plan):
                    self.call_from_thread(
                        self._add_system_message,
                        f"📋 Created plan with {len(plan.todos)} steps:",
                    )
                    from sago.tasks import get_task_manager

                    tm = get_task_manager()
                    self.call_from_thread(self._add_system_message, tm.format_plan(plan))

                def on_todo_update(plan, todo_index, status):
                    if todo_index < len(plan.todos):
                        todo = plan.todos[todo_index]
                        if status == "started":
                            self.call_from_thread(
                                self._update_spinner,
                                f"Step {todo_index + 1}/{len(plan.todos)}: {todo.description[:50]}",
                            )
                        elif status == "completed":
                            self.call_from_thread(
                                self._add_system_message,
                                f"✅ Step {todo_index + 1} completed: {todo.description[:60]}",
                            )

                # Get API key for the current provider
                provider_key = os.environ.get(
                    {"google": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY"}.get(
                        self.current_provider, "OPENROUTER_API_KEY"
                    ),
                    "",
                )
                provider_base_url = {
                    "google": None,
                    "openai": "https://api.openai.com/v1",
                    "openrouter": "https://openrouter.ai/api/v1",
                }.get(self.current_provider, "https://openrouter.ai/api/v1")

                result = execute_agent_task(
                    task=message,
                    agent_role=self.current_agent.replace("-", " ").title(),
                    api_key=provider_key,
                    model=self.current_model,
                    base_url=provider_base_url,
                    max_tokens=effort["max_tokens"],
                    max_iterations=effort["max_iterations"],
                    on_tool_call=on_tool,
                    on_tool_result=on_tool_result,
                    on_thinking=on_thinking,
                    on_todo_created=on_todo_created,
                    on_todo_update=on_todo_update,
                )

                if result.get("task_plan"):
                    from sago.tasks import get_task_manager

                    tm = get_task_manager()
                    plan = tm.get_active_plan()
                    if plan:
                        self.call_from_thread(self._add_system_message, tm.format_plan(plan))

                self.call_from_thread(self._hide_spinner)

                output = result.get("output", "")
                tool_calls = result.get("tool_calls", [])
                if output and output.strip():
                    self.call_from_thread(self._add_assistant_message, output)
                elif tool_calls:
                    tools_done = [t.get("tool", "unknown") for t in tool_calls]
                    self.call_from_thread(
                        self._add_assistant_message,
                        f"Completed using: {', '.join(tools_done)}",
                    )
                else:
                    self.call_from_thread(
                        self._add_assistant_message,
                        "I wasn't able to process your request. Please try rephrasing.",
                    )

        except Exception as e:
            self.call_from_thread(self._hide_spinner)
            error_msg = str(e)
            if "429" in error_msg or "rate" in error_msg.lower():
                provider_urls = {
                    "google": "https://console.cloud.google.com/billing",
                    "openai": "https://platform.openai.com/settings/organization/billing",
                    "openrouter": "https://openrouter.ai/settings/credits",
                }
                url = provider_urls.get(self.current_provider, "your provider's dashboard")
                error_msg = f"Rate limited. Wait or check credits at {url}"
            elif "401" in error_msg or "auth" in error_msg.lower():
                error_msg = f"Authentication failed. Check your {self.current_provider} API key."
            elif "404" in error_msg:
                error_msg = f"Model '{self.current_model}' not found. Try a different model."
            self.call_from_thread(self._add_system_message, f"Error: {error_msg}")
        finally:
            self.is_thinking = False


def main():
    SagoApp().run()
