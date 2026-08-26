"""Sago TUI - Production Terminal Interface with parallel agent support."""

from __future__ import annotations

import collections
import concurrent.futures
import logging
import os
import re
import threading
import time
from typing import Any

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import (  # noqa: F401
    Horizontal,
    ScrollableContainer,
    Vertical,
    VerticalScroll,
)
from textual.reactive import reactive
from textual.widgets import Button, Input, Static

from sago.logging_config import setup_logging
from sago.tui.commands import CommandHandlers
from sago.tui.helpers import UIHelpers
from sago.tui.models import COMMANDS
from sago.tui.orchestrator import AgentOrchestrationMixin
from sago.tui.processor import MessageProcessorMixin
from sago.tui.styles import TUI_CSS

# ── Global markup hardening ──
# Any unescaped dynamic content (git diff, tool output, LLM text) that
# hits Static(markup=True) will otherwise raise MarkupError lazily during
# get_content_height and kill the TUI. Patch Content.from_markup + visualize
# to never crash — falls back to escaped plaintext.
try:
    from rich.errors import MarkupError as _RichMarkupError  # type: ignore[import-not-found]
    from textual.content import Content as _Content  # type: ignore[import-not-found]

    _orig_from_markup = _Content.from_markup

    def _safe_from_markup(cls, markup, *a, **kw):  # type: ignore[no-untyped-def]
        try:
            return _orig_from_markup(markup, *a, **kw)
        except Exception as e:
            if "MarkupError" in type(e).__name__ or isinstance(e, _RichMarkupError):
                from rich.markup import escape as _esc2

                try:
                    return _orig_from_markup(_esc2(str(markup)), *a, **kw)
                except Exception:
                    from textual.content import Content as _C2

                    return _C2(str(markup))
            raise

    _Content.from_markup = classmethod(_safe_from_markup)  # type: ignore[assignment]
    # Also harden visualize() which calls from_markup internally
    import textual.visual as _vis_mod  # type: ignore[import-not-found]

    _orig_vis = _vis_mod.visualize

    def _safe_visualize(obj, content, markup=True, **kw):  # type: ignore[no-untyped-def]
        try:
            return _orig_vis(obj, content, markup=markup, **kw)
        except Exception as e:
            if "MarkupError" in type(e).__name__ or "MissingStyle" in type(e).__name__:
                from rich.markup import escape as _esc3

                try:
                    return _orig_vis(obj, _esc3(str(content)), markup=True, **kw)
                except Exception:
                    return _orig_vis(obj, str(content), markup=False, **kw)
            raise

    _vis_mod.visualize = _safe_visualize  # type: ignore[assignment]
except Exception:
    pass

from sago.tui.widgets import (
    AgentDashboard,
    BackgroundTaskManager,
    Spinner,
    get_task_manager,
)
from sago.utils.safe import log_exception

logger = logging.getLogger("sago.tui.app")

_time = time


class SagoApp(App, CommandHandlers, UIHelpers, AgentOrchestrationMixin, MessageProcessorMixin):
    CSS = TUI_CSS

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+l", "clear_chat", "Clear"),
        Binding("f1", "show_shortcuts", "Help / ?"),
        Binding("f2", "open_trace_viewer", "Traces"),
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
        Binding("end", "scroll_end", "Bottom", show=False),
    ]

    TITLE = "Sago"

    current_agent: reactive[str] = reactive("sago-orchestrator")
    current_model: reactive[str] = reactive("openrouter/free")
    current_provider: reactive[str] = reactive("openrouter")
    current_effort: reactive[str] = reactive("high")  # default high — always some thinking
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
    developer_mode: reactive[bool] = reactive(
        True
    )  # TODO: flip to false at 1.0 — default ON until beta
    show_summary: reactive[bool] = reactive(False)
    show_action_bar: reactive[bool] = reactive(True)
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
    _spinner: Spinner | None = None
    _spinner_timer: Any | None = None  # textual Timer
    # Message queue for concurrent input while thinking — reasoning:
    # TUI previously spawned a new thread per Enter with no guard, so two
    # messages interleaved tool calls and raced _active_exchange_card /
    # _active_cancel_event. Serializing via a FIFO queue keeps one active
    # ExchangeTurnCard at a time and preserves UX (user can keep typing).
    _pending_message_queue: collections.deque[str] | None = None
    _queue_lock: threading.Lock | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="main-layout"):
            with Vertical(id="messages-parent"):
                yield ScrollableContainer(id="messages")
                yield Static(
                    "↧ New messages (press End)", id="new-messages-badge", classes="hidden"
                )
                yield Vertical(id="welcome-screen")
                yield Vertical(id="suggestions")
                with Vertical(id="approval-bar"):
                    yield Static(
                        "Pending action",
                        id="approval-label",
                        classes="approval-label",
                        markup=True,
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
                    yield Input(
                        placeholder="/, @, # for autocomplete (or type a message)", id="msg-input"
                    )
                    with Horizontal(id="input-action-bar"):
                        yield Button(
                            "⌨  Help [F1]", id="btn-input-help", classes="btn-input-action"
                        )
                        yield Button(
                            "⚡ Dev Traces [F2]",
                            id="btn-input-traces",
                            classes="btn-input-action btn-action-traces dev-only-btn",
                        )
                        yield Button("🧹 Clear", id="btn-input-clear", classes="btn-input-action")
                        yield Button(
                            "⛔ Cancel",
                            id="btn-input-cancel",
                            classes="btn-input-action btn-action-cancel",
                        )
                        yield Button(
                            "🚪 Exit",
                            id="btn-input-exit",
                            classes="btn-input-action btn-action-exit",
                        )
            with Vertical(id="agent-dashboard", classes="hidden"):
                yield Static("Agent Dashboard", classes="dashboard-title", markup=True)
                yield Static("", id="agent-dashboard-content", markup=True)

    MAX_COMMAND_HISTORY = 200
    TUI_MAX_RENDERED_CARDS = 60  # beyond this, collapse oldest to avoid lag

    def on_mount(self) -> None:
        setup_logging()
        self._spinner = None
        self._spinner_timer = None
        self._suggestion_debounce_timer: Any | None = None
        self._pending_resume = getattr(self, "_pending_resume", None)
        self.command_history: list[str] = []
        self.history_index: int = -1
        self.session_tool_calls: list[dict[str, Any]] = []
        self._orchestration_lock = threading.Lock()
        self._parallel_lock = threading.Lock()
        self._queue_lock = threading.Lock()
        self._pending_message_queue = collections.deque()
        self._loading_session = False
        self._active_exchange_card = None
        self._current_thinking_buffer: list[dict[str, Any]] = []
        self._message_store = None
        self.current_session_title = "TUI Session"
        self._init_db()
        self._init_session()
        self._load_settings()
        self._task_manager = get_task_manager()
        # Initialize dev mode class if active
        if getattr(self, "developer_mode", False):
            self.add_class("dev-mode-enabled")
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

    def watch_developer_mode(self, value: bool) -> None:
        """Dynamically add or remove .dev-mode-enabled class when developer mode changes."""
        if value:
            self.add_class("dev-mode-enabled")
        else:
            self.remove_class("dev-mode-enabled")
        self._save_settings()

    def watch_show_action_bar(self, value: bool) -> None:
        """Dynamically add or remove .hide-action-bar class when action bar toggle changes."""
        if not value:
            self.add_class("hide-action-bar")
        else:
            self.remove_class("hide-action-bar")
        self._save_settings()

    def is_scrolled_to_bottom(self, threshold: int = 100) -> bool:
        """Check if #messages is within threshold px of bottom via VerticalScroll scroll_y + virtual_size + size.height."""
        try:
            container = self.query_one("#messages")
            scroll_y = getattr(container, "scroll_y", 0)
            virtual_size = getattr(container, "virtual_size", None)
            size = getattr(container, "size", None)
            if virtual_size is None or size is None:
                return True
            v_h = virtual_size.height if hasattr(virtual_size, "height") else 0
            s_h = size.height if hasattr(size, "height") else 0
            if v_h == 0 or s_h == 0:
                return True
            return (v_h - s_h - scroll_y) <= threshold
        except Exception:
            return True

    def _show_new_messages_badge(self) -> None:
        try:
            badge = self.query_one("#new-messages-badge", Static)
            badge.remove_class("hidden")
            badge.add_class("visible")
        except Exception:
            pass

    def _hide_new_messages_badge(self) -> None:
        try:
            badge = self.query_one("#new-messages-badge", Static)
            badge.add_class("hidden")
            badge.remove_class("visible")
        except Exception:
            pass

    def _smart_scroll_end(self, animate: bool = False) -> None:
        """Only auto-scroll if already at bottom; otherwise show badge."""
        try:
            if self.is_scrolled_to_bottom():
                self.query_one("#messages").scroll_end(animate=animate)
                self._hide_new_messages_badge()
            else:
                self._show_new_messages_badge()
        except Exception as e:
            log_exception(e, "smart scroll failed")
            try:
                self.query_one("#messages").scroll_end(animate=animate)
            except Exception:
                pass

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
        from sago import __version__

        welcome.mount(
            Static(f"v{__version__} — Multi-Agent Orchestration", classes="welcome-version")
        )
        if getattr(self, "developer_mode", False):
            welcome.mount(
                Static(
                    "[bold #3fb950]● Dev Mode ON[/bold #3fb950]  [dim]─ F2 Dev Traces Active[/dim]",
                    classes="welcome-dev-badge",
                    markup=True,
                )
            )
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
        from pathlib import Path

        # Find all #filepath references (support #file, #./file, #~/.file, #dir/file.py)
        file_refs = re.findall(r"#([^\s,#@]+)", message)

        context_parts = []
        seen_paths = set()

        for ref in file_refs:
            try:
                # Expand path
                if ref.startswith("~"):
                    path = Path.home() / ref[1:]
                elif ref.startswith("./"):
                    path = Path(ref)
                else:
                    path = Path(ref)

                if not (path.exists() and path.is_file()):
                    # Fallback: search workspace recursively for matching relative path or basename
                    for p in Path.cwd().rglob(path.name):
                        if p.is_file() and not any(
                            part.startswith(".")
                            or part in ("node_modules", "venv", "__pycache__", "dist", "build")
                            for part in p.parts
                        ):
                            path = p
                            break

                if path.exists() and path.is_file():
                    resolved_str = str(path.resolve())
                    if resolved_str in seen_paths:
                        continue
                    seen_paths.add(resolved_str)

                    # Read file content (limit to 12KB per file)
                    rel_label = (
                        str(path.relative_to(Path.cwd()))
                        if path.is_relative_to(Path.cwd())
                        else str(path)
                    )
                    content = path.read_text(errors="replace")[:12288]
                    context_parts.append(
                        f"--- File: {rel_label} ---\n```{path.suffix.lstrip('.')}\n{content}\n```"
                    )
            except Exception as e:
                log_exception(e, f"Failed to read file reference #{ref}")

        return "\n\n".join(context_parts)

    def print_exit_summary(self) -> None:
        """Print clean session highlights summary banner to stdout after TUI terminal buffer is restored."""
        messages = list(getattr(self, "messages", []))
        user_queries = sum(1 for m in messages if m.get("role") == "user")
        if user_queries == 0:
            return

        sid = getattr(self, "current_session_id", "default")[:8]
        full_sid = getattr(self, "current_session_id", "default")
        total_messages = len(messages)

        # Tool calls stats
        tool_calls = getattr(self, "session_tool_calls", [])
        total_tools = len(tool_calls)
        tool_counts: dict[str, int] = {}
        for tc in tool_calls:
            t_name = tc.get("tool", "tool")
            tool_counts[t_name] = tool_counts.get(t_name, 0) + 1

        if not tool_counts:
            try:
                from sago.tracking.dev_tracer import TraceEventType, get_dev_tracer

                events = get_dev_tracer().get_recent_traces()
                for e in events:
                    if e.event_type == TraceEventType.TOOL_DISPATCH:
                        t_name = e.data.get("tool_name", e.action)
                        tool_counts[t_name] = tool_counts.get(t_name, 0) + 1
                total_tools = sum(tool_counts.values())
            except Exception as e:
                log_exception(e, "Failed to load dev tracer traces for exit summary")

        # Token stats
        t_in = getattr(self, "total_input_tokens", 0)
        t_out = getattr(self, "total_output_tokens", 0)
        total_tokens = t_in + t_out

        # Engaged agents
        agents = sorted({m.get("agent_name") for m in messages if m.get("agent_name")})
        agents_str = (
            ", ".join(f"@{a}" for a in agents)
            if agents
            else f"@{getattr(self, 'current_agent', 'sago')}"
        )

        # Tool breakdown
        if tool_counts:
            sorted_tools = sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)[:4]
            tools_breakdown = ", ".join(f"{t} ({cnt})" for t, cnt in sorted_tools)
            if len(tool_counts) > 4:
                tools_breakdown += f", +{len(tool_counts) - 4} more"
        else:
            tools_breakdown = "0 calls"

        dev_artifacts_info = []
        if getattr(self, "developer_mode", False):
            import os
            from pathlib import Path

            data_dir = Path.cwd() / ".sago" / "data" / full_sid
            if data_dir.exists():
                dev_artifacts_info.append("📁 DEV MODE ARTIFACTS SAVED:")
                for fname in ("chat_export.md", "trace.md", "trace.json"):
                    fpath = data_dir / fname
                    if fpath.exists():
                        rel = os.path.relpath(fpath, Path.cwd())
                        dev_artifacts_info.append(f"   ↳ {rel}")

        from sago.engine.prompt_enhancer import generate_session_title

        title = getattr(self, "current_session_title", "")
        if not title or title in ("TUI Session", "Interactive Session"):
            title = generate_session_title(messages)

        import sys

        print("\n" + "━" * 60, file=sys.stderr)
        print(f"📊 SAGO SESSION SUMMARY ({sid})", file=sys.stderr)
        print("━" * 60, file=sys.stderr)
        print(f"• Title          : {title}", file=sys.stderr)
        print(
            f"• Total Queries  : {user_queries} user turns ({total_messages} messages)",
            file=sys.stderr,
        )
        print(f"• Specialist(s)  : {agents_str}", file=sys.stderr)
        print(f"• Tool Calls     : {total_tools} total [{tools_breakdown}]", file=sys.stderr)
        print(
            f"• Token Usage    : {total_tokens:,} tokens ({t_in:,} in, {t_out:,} out)",
            file=sys.stderr,
        )
        print(f"• Resume Command : sago tui --resume {sid}  (or /load {sid})", file=sys.stderr)

        if dev_artifacts_info:
            print("━" * 60, file=sys.stderr)
            print("\n".join(dev_artifacts_info), file=sys.stderr)

        print("━" * 60 + "\n", file=sys.stderr)

    _loading_settings: bool = True

    def _load_settings(self) -> None:
        """Load persisted settings (model, provider, effort, yolo, agent, dev_mode)."""
        try:
            from sago.config.loader import is_dev_mode_enabled
            from sago.settings import load_setting
            from sago.tracking.dev_tracer import get_dev_tracer

            self._loading_settings = True
            self.current_model = load_setting("model", self.current_model)
            self.current_provider = load_setting("provider", self.current_provider)
            self.current_effort = load_setting("effort", self.current_effort)
            self.current_agent = load_setting("agent", self.current_agent)
            self.yolo_mode = load_setting("yolo", self.yolo_mode)
            self.show_summary = load_setting("show_summary", self.show_summary)
            self.show_action_bar = load_setting("show_action_bar", self.show_action_bar)
            if not self.show_action_bar:
                self.add_class("hide-action-bar")

            # Load dev_mode from ~/.sago config or settings
            # v0.1.14: default ON until 1.0 — need to respect explicit False in settings.json
            # but also allow env var SAGO_DEV_MODE to override persisted False (test expects env true → enabled)
            dev_config = is_dev_mode_enabled()
            _env_explicit = (os.environ.get("SAGO_DEV_MODE") is not None) or (
                os.environ.get("DEV_MODE") is not None
            )
            try:
                from sago.settings import load_settings

                _all = load_settings()
                if _env_explicit:
                    # Env var explicitly set — honor dev_config (env) even if persisted False
                    self.developer_mode = bool(dev_config)
                elif "dev_mode" in _all:
                    self.developer_mode = bool(_all["dev_mode"])
                else:
                    self.developer_mode = bool(dev_config)
            except Exception:
                persisted_dev = load_setting("dev_mode", dev_config)
                if _env_explicit:
                    self.developer_mode = bool(dev_config)
                elif persisted_dev is False:
                    self.developer_mode = False
                else:
                    self.developer_mode = bool(persisted_dev or dev_config)
            if self.developer_mode:
                get_dev_tracer().set_enabled(True)
                self.add_class("dev-mode-enabled")
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
            save_setting("show_action_bar", self.show_action_bar)
            save_setting("dev_mode", self.developer_mode)
        except Exception as e:
            logger.warning("Failed to save settings: %s", e)

    def _auto_refresh_models(self) -> None:
        """Refresh model list from OpenRouter if cache is stale."""

        try:
            from sago.tui.models import auto_refresh_if_stale

            # Only refresh if OpenRouter key is available
            api_key = os.environ.get("OPENROUTER_API_KEY", "")
            if not api_key:
                return
            msg = auto_refresh_if_stale(api_key)
            if msg:
                self._add_system_message(f"\\[auto-refresh\\] {msg}")
        except Exception as e:
            logger.debug("Auto-refresh models failed: %s", e)

    def _resolve_api_model(self) -> str:
        """Strip provider prefix for API calls. google/gemini-2.0-flash -> gemini-2.0-flash."""
        from sago.llm.registry import strip_model_prefix

        return strip_model_prefix(self.current_provider, self.current_model)

    def _get_provider_api_key(self) -> str:
        """Get the API key for the current provider."""
        from sago.llm.registry import get_provider_spec, normalize_provider

        spec = get_provider_spec(normalize_provider(self.current_provider))
        env_var = spec.api_key_env if spec and spec.api_key_env else "OPENROUTER_API_KEY"
        return os.environ.get(env_var, "")

    def _get_provider_key_name(self) -> str:
        """Get the environment variable name for the current provider's API key."""
        from sago.llm.registry import get_provider_spec, normalize_provider

        spec = get_provider_spec(normalize_provider(self.current_provider))
        return spec.api_key_env if spec and spec.api_key_env else "OPENROUTER_API_KEY"

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
        except Exception as e:
            log_exception(e, "Failed to sync yolo mode to permission manager")

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
            # Skip creating a new session if we're about to resume an existing one
            if self._pending_resume:
                return
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
        # Debounce: typing lag when chat is large is due to ranking 300+ agents
        # + workspace file scan on every keystroke. Delay 120ms and cancel prior.
        v = event.value
        try:
            if self._suggestion_debounce_timer:
                self._suggestion_debounce_timer.stop()
        except Exception:
            pass

        def _do_suggestions() -> None:
            vv = v  # capture
            if vv.startswith("?"):
                self._show_shortcuts_suggestions(vv)
                return
            if vv.startswith("/"):
                self._show_cmd_suggestions(vv)
                return
            if vv.startswith("@delegate") or vv.startswith("@chain") or vv.startswith("@agent"):
                self._show_cmd_suggestions(vv)
                return
            last_space = vv.rfind(" ")
            current_word = vv[last_space + 1 :] if last_space >= 0 else vv
            if current_word.startswith("#"):
                prefix = current_word[1:]
                self._show_file_suggestions(prefix)
            elif current_word.startswith("@"):
                prefix = current_word[1:]
                self._show_agent_suggestions(prefix)
            elif current_word.startswith("~"):
                prefix = current_word[1:]
                self._show_file_suggestions(prefix, home=True)
            else:
                self._hide_suggestions()

        # 120ms debounce keeps typing responsive even with 80+ cards rendered
        try:
            self._suggestion_debounce_timer = self.set_timer(0.12, _do_suggestions)
        except Exception:
            _do_suggestions()

    def _maybe_compact_tui_messages(self) -> None:
        """Collapse oldest cards when chat grows large to keep UI responsive."""
        try:
            container = self.query_one("#messages")
            children = list(container.children)
            if len(children) <= self.TUI_MAX_RENDERED_CARDS:
                return
            # Keep last N, remove oldest, replace with placeholder
            to_remove = len(children) - self.TUI_MAX_RENDERED_CARDS
            # Remove oldest ExchangeTurnCards first, keep system notices
            removed = 0
            for child in children:
                if removed >= to_remove:
                    break
                # Never remove the last few or welcome screen
                if child.has_class("exchange-box"):
                    child.remove()
                    removed += 1
            if removed:
                # Insert placeholder at top if not already present
                has_placeholder = any(
                    c.has_class("tui-compact-placeholder") for c in container.children
                )
                if not has_placeholder:
                    from textual.widgets import Static

                    container.mount(
                        Static(
                            f"[dim]… {removed} older messages collapsed for performance — /clear to reset or scroll up to keep more[/dim]",
                            classes="tui-compact-placeholder msg-system",
                            markup=True,
                        ),
                        before=container.children[0] if container.children else None,
                    )
                if self.is_scrolled_to_bottom():
                    container.scroll_end(animate=False)
                    self._hide_new_messages_badge()
                else:
                    self._show_new_messages_badge()
        except Exception as e:
            logger.debug("TUI compaction failed: %s", e)

    @on(Button.Pressed, ".btn-copy-code")
    def on_copy_code_button(self, event: Button.Pressed) -> None:
        """Copy code snippet to system clipboard. TUI captures mouse, so Shift+drag also works natively."""
        event.stop()
        from sago.tools.session.clipboard import ClipboardTool

        code = getattr(event.button, "_code_content", "")
        if code:
            result = ClipboardTool()._write_clipboard(code)
            is_error = result.startswith("Error")
            if is_error:
                event.button.label = "✗ Copy failed"
                self._add_system_message(
                    f"📋 {result} — tip: hold Shift while selecting text to copy natively"
                )
            else:
                event.button.label = "✓ Copied!"
                self._add_system_message(
                    f"📋 {result} — tip: Shift+drag selects text natively in terminal"
                )

            def _reset() -> None:
                try:
                    event.button.label = "📋 Copy Code"
                except Exception as e:
                    log_exception(e, "Failed to reset copy button label")

            self.set_timer(2.0, _reset)

    @on(Input.Submitted, "#msg-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        msg = event.value.strip()
        if not msg:
            return

        if self.show_suggestions and self.suggestion_values:
            val = self.suggestion_values[self.suggestion_index]
            self._hide_suggestions()

            # Commands that still require additional arguments from the user
            # (e.g. bare /delegate without an agent or /chain without task or /plan)
            requires_more_args = (
                val.startswith("/delegate")
                or val.startswith("@delegate")
                or val.startswith("/chain")
                or val.startswith("@chain")
                or (val.startswith("/agent") and len(val.split()) == 1)
                or (val.startswith("@agent") and len(val.split()) == 1)
                or val in ("/plan", "/plan <task>")
            )

            # If user explicitly selected a complete suggestion like "/dev on", "/model openrouter/free", "/effort max", "/theme nord", execute right away!
            if not requires_more_args and val.startswith("/"):
                event.input.value = ""
                self._handle_command(val)
                return
            elif requires_more_args:
                event.input.value = val + " "
                event.input.cursor_position = len(event.input.value)
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

        # ── Queue reasoning: if a long task is running, don't interleave —
        # serialize via FIFO so tool calls / cards don't race. User can keep
        # typing; queued items run in order after current finishes.
        # Control messages (y/n/cancel/help) bypass the queue so user can
        # still approve/deny/cancel the active task.
        if self.is_thinking and not self._is_control_message(msg):
            try:
                q = getattr(self, "_pending_message_queue", None)
                lock = getattr(self, "_queue_lock", None)
                if q is not None and lock is not None:
                    with lock:
                        q.append(msg)  # type: ignore[union-attr]
                        q_len = len(q)
                    self._add_system_message(
                        f"⏳ Queued ({q_len}): {msg[:60]} — will run after current task. Press Ctrl+C to cancel current task."
                    )
                    # Update input placeholder to show queue depth
                    try:
                        inp = self.query_one("#msg-input", Input)  # type: ignore[attr-defined]
                        inp.placeholder = f"Queued {q_len} — type to add more (Enter to queue)"
                    except Exception:
                        pass
                    return
            except Exception as e:
                log_exception(e, "Failed to queue message")

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
        elif msg.startswith("!") and len(msg) > 1:
            self._execute_shell_escape(msg[1:].strip())
        elif msg.startswith("/"):
            if msg != "/history":
                self._add_to_history(msg)
            self._handle_command(msg)
        else:
            self._add_to_history(msg)
            self._add_user_message(msg)
            self._process_message(msg)

    def _execute_shell_escape(self, cmd: str) -> None:
        """Execute !<cmd> shell escape and mount standard Collapsible output like other commands."""
        self._hide_welcome_screen()
        self._add_to_history(f"!{cmd}")
        container = self.query_one("#messages")

        def _worker() -> None:
            t0 = time.time()
            try:
                import subprocess

                res = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                out = (res.stdout or "") + ("\n" + res.stderr if res.stderr else "")
                dur = time.time() - t0
                status_tag = (
                    f"[green]✓ exit 0[/green] [dim]({dur:.2f}s)[/dim]"
                    if res.returncode == 0
                    else f"[red]✗ exit {res.returncode}[/red] [dim]({dur:.2f}s)[/dim]"
                )
                content = out.strip() if out.strip() else "[dim](no output)[/dim]"
            except Exception as e:
                dur = time.time() - t0
                status_tag = f"[red]✗ error[/red] [dim]({dur:.2f}s)[/dim]"
                content = f"[red]Error executing command:[/red] {e}"

            def _mount() -> None:
                from textual.widgets import Collapsible, Static

                container.mount(
                    Collapsible(
                        Static(content),
                        title=f"$ {cmd}  {status_tag}",
                        collapsed=False,
                    )
                )
                if self.is_scrolled_to_bottom():
                    container.scroll_end(animate=False)
                    self._hide_new_messages_badge()
                else:
                    self._show_new_messages_badge()

            self.call_from_thread(_mount)

        threading.Thread(target=_worker, daemon=True).start()

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
                except Exception as e:
                    log_exception(e, "Failed to scroll page up via keyboard")
                return
            elif event.key in ("pagedown", "shift+down"):
                event.prevent_default()
                try:
                    self.query_one("#messages").scroll_page_down(animate=False)
                    if self.is_scrolled_to_bottom():
                        self._hide_new_messages_badge()
                except Exception as e:
                    log_exception(e, "Failed to scroll page down via keyboard")
                return
            elif event.key in ("end", "ctrl+end"):
                event.prevent_default()
                try:
                    self.query_one("#messages").scroll_end(animate=False)
                    self._hide_new_messages_badge()
                except Exception as e:
                    log_exception(e, "Failed to scroll to end via keyboard")
                return

            # Command history navigation when no suggestions visible
            inp = self.query_one("#msg-input", Input)  # type: ignore[attr-defined]
            if inp.cursor_position == 0 and not inp.value:  # type: ignore[attr-defined]
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
            inp = self.query_one("#msg-input", Input)  # type: ignore[attr-defined]
            if val.startswith("/"):
                inp.value = val + " "  # type: ignore[attr-defined]
                inp.cursor_position = len(inp.value)  # type: ignore[attr-defined]
                if (
                    val.startswith("/model ")
                    and not val.startswith("/model add")
                    and not val.startswith("/model remove")
                    and not val.startswith("/model refresh")
                ):
                    from sago.llm.registry import infer_provider_for_model

                    model_id = val[7:].strip()
                    inferred = infer_provider_for_model(model_id)
                    if inferred:
                        self.current_provider = inferred
                    self.current_model = model_id
            else:
                v = inp.value  # type: ignore[attr-defined]
                last_space = v.rfind(" ")
                current_word_start = last_space + 1 if last_space >= 0 else 0
                new_val = val + " "
                inp.value = v[:current_word_start] + new_val  # type: ignore[attr-defined]
                inp.cursor_position = len(inp.value)  # type: ignore[attr-defined]
            self._hide_suggestions()

    def _update_highlight(self) -> None:
        items = list(self.query(".suggestion-item"))
        for i, item in enumerate(items):
            is_highlighted = i == self.suggestion_index
            item.set_class(is_highlighted, "highlighted")
            # Auto-scroll highlighted item into view
            if is_highlighted:
                try:
                    item.scroll_visible(animate=False)
                except Exception as e:
                    log_exception(e, "Failed to scroll suggestion item into view")

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
            self.query_one("#msg-input", Input).value = self.command_history[self.history_index]  # type: ignore[attr-defined]

    # ── Message queue: serialize concurrent input while thinking ──
    def _is_control_message(self, msg: str) -> bool:
        """Control messages (y/n, cancel, help) must bypass the queue and run immediately."""
        m = msg.strip().lower()
        if m in (
            "y",
            "yes",
            "n",
            "no",
            "approve",
            "deny",
            "cancel",
            "help",
            "clear",
            "status",
            "exit",
            "quit",
        ):
            return True
        if m.startswith(
            (
                "/cancel",
                "/help",
                "/clear",
                "/status",
                "/exit",
                "/quit",
                "/tasks",
                "/y",
                "/n",
                "/approve",
                "/deny",
            )
        ):
            return True
        if m in ("/help", "/?", "/shortcuts"):
            return True
        return False

    def _try_process_queue(self) -> None:
        """If not thinking and queue has items, dispatch next. Called via watch_is_thinking and explicit call."""
        try:
            q = getattr(self, "_pending_message_queue", None)
            lock = getattr(self, "_queue_lock", None)
            if q is None or lock is None:
                return
            with lock:
                if not q or self.is_thinking:
                    # Reset placeholder when queue empty and idle
                    if not q and not self.is_thinking:
                        try:
                            inp = self.query_one("#msg-input", Input)  # type: ignore[attr-defined]
                            inp.placeholder = "/, @, # for autocomplete (or type a message)"
                        except Exception:
                            pass
                    return
                next_msg = q.popleft()
                remaining = len(q)
            # Update placeholder to reflect queue depth
            try:
                inp = self.query_one("#msg-input", Input)  # type: ignore[attr-defined]
                if remaining:
                    inp.placeholder = f"Queued {remaining} — will run after current task"
                else:
                    inp.placeholder = "/, @, # for autocomplete (or type a message)"
            except Exception:
                pass
            # Dispatch outside lock
            self._add_system_message(
                f"▶️ Processing queued ({remaining} remaining): {next_msg[:70]}"
            )
            if next_msg.startswith("/") or next_msg.startswith("!"):
                self._handle_command(next_msg)
            elif next_msg.startswith("@") or next_msg.startswith("#"):
                # Treat mentions as normal messages but preserve raw
                self._add_user_message(next_msg)
                self._process_message(next_msg)
            else:
                self._add_user_message(next_msg)
                self._process_message(next_msg)
        except Exception as e:
            log_exception(e, "Failed to process queued message")

    def watch_is_thinking(self, value: bool) -> None:
        """Reactive watcher — when thinking finishes, drain the queue."""
        if not value:
            # Defer to next tick so UI updates settle
            try:
                self.call_after_refresh(self._try_process_queue)  # type: ignore[attr-defined]
            except Exception:
                self._try_process_queue()

    def on_mouse_scroll_down(self, event) -> None:
        self.query_one("#messages").scroll_down()
        try:
            if self.is_scrolled_to_bottom():
                self._hide_new_messages_badge()
        except Exception:
            pass

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
        """Cancel current running LLM iteration or background task (Ctrl+C)."""
        cancelled_anything = False

        # 1. Cancel active conversational message thread if running
        if getattr(self, "is_thinking", False) or getattr(self, "_active_cancel_event", None):
            cancel_ev = getattr(self, "_active_cancel_event", None)
            if cancel_ev:
                cancel_ev.set()
            pause_ev = getattr(self, "_executor_pause_event", None)
            if pause_ev:
                pause_ev.set()
            self.is_thinking = False
            self._hide_spinner()
            self._add_system_message(
                "⛔ [bold red]Execution interrupted and cancelled by user (Ctrl+C).[/bold red]"
            )
            cancelled_anything = True

        # 2. Cancel background task from TaskManager if any
        from sago.tui.widgets import get_task_manager

        tm = get_task_manager()
        active = tm.get_active_tasks()
        if active:
            last = active[-1]
            tm.cancel_task(last.agent_id)
            self._add_system_message(
                f"Cancelled background task: {last.agent_name} ({last.agent_id})"
            )
            cancelled_anything = True

        if not cancelled_anything:
            self._add_system_message("No active tasks or generation to cancel")
        else:
            # If we cancelled the active task, proactively drain queue so next
            # queued message doesn't wait for the watch_is_thinking debounce.
            try:
                self.call_after_refresh(self._try_process_queue)  # type: ignore[attr-defined]
            except Exception:
                self._try_process_queue()

    def action_show_shortcuts(self) -> None:
        """Show shortcuts reference modal."""
        self._handle_shortcuts_command()

    def action_open_trace_viewer(self) -> None:
        """Open the deep trace viewer popup."""
        from sago.tracking.dev_tracer import get_dev_tracer

        tracer = get_dev_tracer()
        events = tracer.get_recent_traces(limit=500)
        if not events:
            self._add_system_message(
                "⚡ No traces yet. Enable with `/dev on`, then run some tasks."
            )
            return
        try:
            from sago.tui.trace_viewer import TraceViewerScreen

            self.push_screen(TraceViewerScreen(events))
        except Exception as e:
            self._add_system_message(f"⚡ Trace viewer error: {e}")

    @on(Button.Pressed, "#btn-top-traces")
    @on(Button.Pressed, "#btn-input-traces")
    def on_traces_button_clicked(self) -> None:
        """Open trace viewer from top bar or input action bar button."""
        self.action_open_trace_viewer()

    @on(Button.Pressed, ".btn-view-trace")
    def on_view_trace_button(self, event: Button.Pressed) -> None:
        """Handle per-turn 'View Trace ⚡' button clicks."""
        btn = event.button
        trace_events = getattr(btn, "_trace_events", None)
        trace_label = getattr(btn, "_trace_label", "")
        if not trace_events:
            from sago.tracking.dev_tracer import get_dev_tracer

            trace_events = get_dev_tracer().get_recent_traces(limit=500)
        if not trace_events:
            self._add_system_message("⚡ No traces captured yet.")
            return
        try:
            from sago.tui.trace_viewer import TraceViewerScreen

            self.push_screen(TraceViewerScreen(trace_events, turn_label=trace_label))
        except Exception as e:
            self._add_system_message(f"⚡ Trace viewer error: {e}")

    @on(Button.Pressed, "#btn-top-dashboard")
    @on(Button.Pressed, "#btn-input-dashboard")
    def on_dashboard_button_clicked(self) -> None:
        """Toggle agent dashboard from top bar or input action bar button."""
        self.action_toggle_dashboard()

    @on(Button.Pressed, "#btn-top-help")
    @on(Button.Pressed, "#btn-input-help")
    def on_help_button_clicked(self) -> None:
        """Show shortcuts help from top bar or input action bar button."""
        self.action_show_shortcuts()

    @on(Button.Pressed, "#btn-input-clear")
    def on_clear_button_clicked(self) -> None:
        """Clear message log from input action bar button."""
        self.action_clear_chat()

    @on(Button.Pressed, "#btn-input-cancel")
    def on_cancel_button_clicked(self) -> None:
        """Cancel current execution from input action bar button."""
        self.action_cancel_task()

    @on(Button.Pressed, "#btn-input-exit")
    def on_exit_button_clicked(self) -> None:
        """Exit the application."""
        self.action_quit()

    def _show_shortcuts_suggestions(self, query: str = "") -> None:
        """Show shortcuts and quick help suggestions with clean monospace alignment."""
        shortcuts_list = [
            ("?", "Open interactive shortcuts & quick reference modal (F1)"),
            ("Ctrl+D", "Toggle agent & metrics dashboard sidebar"),
            ("Ctrl+T", "Toggle background tasks panel"),
            ("Ctrl+C", "Cancel active agent task or thinking stream"),
            ("@<agent>", "Mention & route task to specialist agent (@python-engineer)"),
            ("#<file>", "Smart workspace file path autocomplete"),
            ("/help", "View complete command reference"),
        ]
        items = [
            f"[bold cyan]{key:<12}[/bold cyan] [dim]{desc}[/dim]"
            for key, desc in shortcuts_list
            if not query or query.lower() in key.lower() or query.lower() in desc.lower()
        ]
        values = ["?", "/dashboard", "/tasks", "/cancel", "@", "#", "/help"]
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

        # 5. /delegate or @delegate suggestions
        if raw.startswith("/delegate") or raw.startswith("@delegate"):
            query = raw.split(None, 1)[1].strip() if " " in raw else ""
            prefix_cmd = "/delegate" if raw.startswith("/") else "@delegate"
            try:
                from sago.agents.registry import list_agents

                agents = list_agents()
                matches = self._rank_agent_matches(agents, query)
                items = [  # type: ignore[index]
                    f"[bold magenta]⚡ @{a['name']}[/bold magenta] [dim]{a.get('description', '')[:45]}[/dim]"  # type: ignore[attr-defined]
                    for a in matches[:35]
                ]
                values = [f"{prefix_cmd} {a['name']}" for a in matches[:35]]  # type: ignore[index]
                self._show_suggestions(items, values)
                return
            except Exception as e:
                log_exception(e, "Failed to load agent list for /delegate suggestions")

        # 6. /chain or @chain suggestions
        if raw.startswith("/chain") or raw.startswith("@chain"):
            query = raw.split(None, 1)[1].strip() if " " in raw else ""
            prefix_cmd = "/chain" if raw.startswith("/") else "@chain"
            try:
                from sago.agents.registry import list_agents

                agents = list_agents()
                if "," in query:
                    parts = [p.strip() for p in query.split(",")]
                    current_typing = parts[-1].lower()
                    prefix_before = ",".join(parts[:-1]) + ","
                    matches = self._rank_agent_matches(
                        [a for a in agents if a["name"] not in parts],
                        current_typing,  # type: ignore[index]
                    )
                    items = [  # type: ignore[index]
                        f"[bold magenta]🔗 {prefix_before}{a['name']}[/bold magenta] [dim]{a.get('description', '')[:40]}[/dim]"  # type: ignore[attr-defined]
                        for a in matches[:30]
                    ]
                    values = [f"{prefix_cmd} {prefix_before}{a['name']}" for a in matches[:30]]  # type: ignore[index]
                else:
                    matches = self._rank_agent_matches(agents, query)
                    items = [  # type: ignore[index]
                        f"[bold magenta]🔗 @{a['name']}[/bold magenta] [dim]{a.get('description', '')[:45]}[/dim]"  # type: ignore[attr-defined]
                        for a in matches[:35]
                    ]
                    values = [f"{prefix_cmd} {a['name']}" for a in matches[:35]]  # type: ignore[index]
                self._show_suggestions(items, values)
                return
            except Exception as e:
                log_exception(e, "Failed to load agent list for /chain suggestions")

        # 7. /agent or @agent suggestions
        if raw.startswith("/agent") or raw.startswith("@agent"):
            query = raw.split(None, 1)[1].strip() if " " in raw else ""
            prefix_cmd = "/agent" if raw.startswith("/") else "@agent"
            try:
                from sago.agents.registry import list_agents

                agents = list_agents()
                matches = self._rank_agent_matches(agents, query)
                items = [  # type: ignore[index]
                    f"[bold magenta]@{a['name']}[/bold magenta] [dim]{a.get('description', '')[:45]}[/dim]"  # type: ignore[attr-defined]
                    for a in matches[:35]
                ]
                values = [f"{prefix_cmd} {a['name']}" for a in matches[:35]]  # type: ignore[index]
                self._show_suggestions(items, values)
                return
            except Exception as e:
                log_exception(e, "Failed to load agent list for /agent suggestions")

        # Dynamic subcommand completions (/git, /pr, /session, /checkpoint)
        from sago.tui.smart_suggest import fuzzy_score, get_subcommand_completions

        sub_res = get_subcommand_completions(raw)
        if sub_res is not None:
            items, values = sub_res
            self._show_suggestions(items, values)
            return

        # 9. General command fuzzy matching
        scored_cmds = []
        for cmd in COMMANDS:
            s = fuzzy_score(raw, cmd)
            if s > 0:
                scored_cmds.append((s, cmd))

        scored_cmds.sort(key=lambda x: x[0], reverse=True)
        matches = [cmd for _, cmd in scored_cmds]
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
            from sago.tui.smart_suggest import fuzzy_score

            models = [m for m in models if fuzzy_score(query, m) > 0]
            models.sort(key=lambda m: fuzzy_score(query, m), reverse=True)

        if not models:
            models = [m for m in BUILTIN_MODELS if query in m.lower()]

        items = [f"[bold cyan]● {m}[/bold cyan]" for m in models[:30]]
        values = [f"/model {m}" for m in models[:30]]
        self._show_suggestions(items, values)

    def _rank_agent_matches(self, agents: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
        """Rank agent matches so exact/fuzzy/prefix matches and core specialists appear first."""
        from sago.tui.smart_suggest import rank_agents_fuzzy

        return rank_agents_fuzzy(agents, query)  # type: ignore[return-value]

    def _show_agent_suggestions(self, prefix: str) -> None:
        try:
            from sago.agents.registry import list_agents

            agents = list_agents()
            prefix_clean = prefix.strip()
            if "," in prefix_clean:
                already_selected = [a.strip() for a in prefix_clean.split(",")]
                current_typing = already_selected[-1].lower()
                prefix_before = ",".join(already_selected[:-1]) + ","
                matches = self._rank_agent_matches(
                    [a for a in agents if a["name"] not in already_selected],
                    current_typing,
                )
                items = [
                    f"[bold magenta]@{prefix_before}{a['name']}[/bold magenta] [dim]{a.get('description', '')[:45]}[/dim]"
                    for a in matches[:35]
                ]
                values = [f"@{prefix_before}{a['name']}" for a in matches[:35]]
            else:
                matches = self._rank_agent_matches(agents, prefix_clean)
                items = [
                    f"[bold magenta]@{a['name']}[/bold magenta] [dim]{a.get('description', '')[:45]}[/dim]"
                    for a in matches[:35]
                ]
                values = [f"@{a['name']}" for a in matches[:35]]
            self._show_suggestions(items, values)
        except Exception as e:
            log_exception(e, "Failed to load agent list for @agent suggestions")

    def _show_file_suggestions(self, prefix: str, home: bool = False) -> None:
        from sago.tui.smart_suggest import rank_files_smart

        items, values = rank_files_smart(prefix, home=home)
        if items:
            self._show_suggestions(items, values)
        else:
            self._hide_suggestions()

    def _show_suggestions(self, items: list[str], values: list[str]) -> None:
        if not items:
            self._hide_suggestions()
            return
        # Support full scrollable suggestion list without artificial 8-item pagination trap
        items = items[:100]
        values = values[:100]
        self.suggestion_items = items
        self.suggestion_values = values
        self.suggestion_index = 0
        self.show_suggestions = True
        try:
            container = self.query_one("#suggestions")
        except Exception:
            return
        try:
            container.remove_children()
        except Exception:
            pass
        for item in items:
            # Items are intentional markup like "[bold cyan]/pr[/bold cyan] [dim]..." for
            # command help — don't pre-escape or markup breaks (shows literal tags).
            # Try markup=True first; file paths with stray "[" will fallback to plaintext.
            try:
                container.mount(Static(str(item), classes="suggestion-item", markup=True))
            except Exception:
                try:
                    from rich.markup import escape as _esc_s

                    container.mount(
                        Static(_esc_s(str(item)), classes="suggestion-item", markup=False)
                    )
                except Exception:
                    pass
        try:
            container.add_class("visible")
        except Exception:
            pass
        try:
            self._update_highlight()
        except Exception:
            pass

    def _hide_suggestions(self) -> None:
        self.show_suggestions = False
        self.suggestion_items = []
        self.suggestion_values = []
        try:
            self.query_one("#suggestions").remove_class("visible")
        except Exception:
            pass

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
        self._smart_scroll_end(animate=False)
        self._spinner = s
        self._spinner_timer = self.set_interval(0.2, self._advance_spinner)

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
            "/plan": lambda: self._plan_or_show(args),
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
            "/continue": lambda: self._continue_last(),
            "/reset": lambda: self._reset(),
            "/save": lambda: self._save_session(args),
            "/load": lambda: self._load_session(args),
            "/git": lambda: self._handle_git_command(args),
            "/diff": lambda: self._git_diff(args),
            "/commit": lambda: self._git_commit(args),
            "/approve": lambda: self._approve_action(),
            "/deny": lambda: self._deny_action(),
            "/version": lambda: self._show_version(),
            "/yolo": lambda: self._toggle_yolo(),
            "/perms": lambda: self._handle_perms_command(args),
            "/permissions": lambda: self._handle_perms_command(args),
            "/allow": lambda: self._allow_tool(args),
            "/block": lambda: self._block_tool(args),
            "/todo": lambda: self._handle_todo_command(args),
            "/todos": lambda: self._show_all_todos(),
            "/done": lambda: self._mark_todo_done(args),
            "/ask": lambda: self._ask_user(args),
            "/undo": lambda: self._undo_change(),
            "/changes": lambda: self._show_changes(),
            "/exit": lambda: self._exit_session(),
            "/resume": lambda: self._list_sessions(),
            "/parallel": lambda: self._run_parallel(args),
            "/dashboard": lambda: self._toggle_dashboard(),
            "/tasks": lambda: self._handle_tasks_command(args),
            "/cancel": lambda: self._cancel_task(args),
            "/handoff": lambda: self._show_handoff(),
            "/agents-color": lambda: self._list_agents_color(),
            "/summary": lambda: self._toggle_summary(),
            "/map": lambda: self._show_repo_map(args),
            "/verify": lambda: self._run_verify(),
            "/tools": lambda: self._show_tools(args),
            "/tool": lambda: self._show_tools(args),
            "/skills": lambda: self._show_skills(args),
            "/skill": lambda: self._show_skills(args),
            "/plugins": lambda: self._show_plugins(),
            "/plugin": lambda: self._show_plugins(),
            "/mcp": lambda: self._handle_mcp_command(args),
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
            "/clean": lambda: self._handle_clean_command(args),
            "/gc": lambda: self._handle_clean_command(args),
            "/copy": lambda: self._handle_copy_command(args),
            "/clip": lambda: self._handle_copy_command(args),
            "/buttons": lambda: self._handle_buttons_command(args),
            "/bar": lambda: self._handle_buttons_command(args),
            "/show": lambda: self._handle_buttons_command("show " + args),
            "/hide": lambda: self._handle_buttons_command("hide " + args),
            "/pr": lambda: self._handle_pr_command(args),
        }

        if cmd in handlers:
            handlers[cmd]()
        else:
            self._add_system_message(f"Unknown: {cmd}\nType /help for commands")

    def action_quit(self) -> None:  # type: ignore[override]
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
        except Exception as e:
            log_exception(e, "Failed to scroll page up")

    def action_scroll_page_down(self) -> None:
        """Scroll message viewport page down."""
        try:
            self.query_one("#messages").scroll_page_down(animate=True)
            if self.is_scrolled_to_bottom():
                self._hide_new_messages_badge()
        except Exception as e:
            log_exception(e, "Failed to scroll page down")

    def action_scroll_line_up(self) -> None:
        """Scroll message viewport line up."""
        try:
            self.query_one("#messages").scroll_up(animate=False)
        except Exception as e:
            log_exception(e, "Failed to scroll line up")

    def action_scroll_line_down(self) -> None:
        """Scroll message viewport line down."""
        try:
            self.query_one("#messages").scroll_down(animate=False)
            if self.is_scrolled_to_bottom():
                self._hide_new_messages_badge()
        except Exception as e:
            log_exception(e, "Failed to scroll line down")

    def action_scroll_home(self) -> None:
        """Scroll message viewport to top."""
        try:
            self.query_one("#messages").scroll_home(animate=True)
        except Exception as e:
            log_exception(e, "Failed to scroll to home")

    def action_scroll_end(self) -> None:
        """Scroll message viewport to bottom and hide badge (End key)."""
        try:
            self.query_one("#messages").scroll_end(animate=True)
            self._hide_new_messages_badge()
        except Exception as e:
            log_exception(e, "Failed to scroll to end")

    def on_exception(self, error: Exception) -> None:  # type: ignore[override]
        """Global TUI exception handler — never crash or hang on MarkupError etc."""
        try:
            from rich.errors import MarkupError, MissingStyle, StyleSyntaxError

            is_markup = isinstance(error, (MarkupError, MissingStyle, StyleSyntaxError))
        except Exception:
            is_markup = any(
                x in type(error).__name__ for x in ("MarkupError", "MissingStyle", "StyleSyntax")
            )
        logger.error("TUI unhandled exception (%s): %s", type(error).__name__, error, exc_info=True)
        try:
            from rich.markup import escape

            msg = escape(str(error)[:500])
            if is_markup:
                msg = f"Handled MarkupError (no crash): {msg} — content was auto-escaped"
            # Avoid recursion if _add_system_message itself fails
            try:
                self._add_system_message(f"⚠️ Handled error: {msg}")
            except Exception:
                self.query_one("#messages").mount(
                    __import__("textual.widgets").widgets.Static(
                        f"Handled error: {msg}", markup=False
                    )
                )
        except Exception as e2:
            logger.debug("Failed to show handled error: %s", e2)
        # Do not re-raise — keep TUI alive

    def handle_exception(self, error: Exception) -> bool:
        """Textual 8+ hook — return True to suppress crash."""
        self.on_exception(error)
        return True


def main():
    SagoApp().run()
