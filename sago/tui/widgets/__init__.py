"""TUI widgets for Sago - Extended with parallel agent support."""

from __future__ import annotations

import threading
import time as _time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class Spinner(Static):
    """Animated spinner widget."""

    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, text: str = "Thinking", **kwargs) -> None:
        super().__init__(**kwargs)
        self.text = text
        self.frame = 0

    def render(self) -> str:
        return f"{self.FRAMES[self.frame]} {self.text}"

    def advance(self) -> None:
        self.frame = (self.frame + 1) % len(self.FRAMES)
        self.refresh()


# ============================================================================
# AGENT STATUS TRACKING
# ============================================================================


class AgentStatus(Enum):
    """Status of an agent task."""

    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentTaskInfo:
    """Information about a running agent task."""

    agent_id: str
    agent_name: str
    task: str
    status: AgentStatus = AgentStatus.IDLE
    progress: float = 0.0
    current_tool: str = ""
    start_time: float = 0.0
    elapsed: float = 0.0
    result: str = ""
    error: str = ""
    thread: threading.Thread | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    tool_calls: int = 0
    token_usage: dict[str, int] = field(default_factory=dict)


# Agent color palette for visual distinction
AGENT_COLORS = [
    "#58a6ff",  # blue
    "#3fb950",  # green
    "#d2a8ff",  # purple
    "#f0883e",  # orange
    "#f778ba",  # pink
    "#79c0ff",  # light blue
    "#56d4dd",  # cyan
    "#e3b341",  # yellow
    "#ff7b72",  # red
    "#7ee787",  # light green
    "#d2a8ff",  # light purple
    "#ffa657",  # light orange
]


def get_agent_color(agent_id: str) -> str:
    """Get a consistent color for an agent based on its ID."""
    idx = hash(agent_id) % len(AGENT_COLORS)
    return AGENT_COLORS[idx]


# ============================================================================
# AGENT SPINNER - Per-agent animated spinner with color
# ============================================================================


class AgentSpinner(Static):
    """Per-agent spinner with agent name and color."""

    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, agent_id: str, agent_name: str, task: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.task = task
        self.frame = 0
        self.color = get_agent_color(agent_id)
        self.status = AgentStatus.RUNNING
        self.current_tool = ""

    def render(self) -> str:
        icon = self.FRAMES[self.frame] if self.status == AgentStatus.RUNNING else self._status_icon()
        task_info = f" | {self.current_tool}" if self.current_tool else ""
        task_preview = f": {self.task[:40]}" if self.task else ""
        return f"[{self.color}]{icon} {self.agent_name}[/{self.color}]{task_preview}{task_info}"

    def _status_icon(self) -> str:
        icons = {
            AgentStatus.IDLE: "○",
            AgentStatus.WAITING: "◎",
            AgentStatus.COMPLETED: "●",
            AgentStatus.FAILED: "✗",
            AgentStatus.CANCELLED: "⊘",
        }
        return icons.get(self.status, "?")

    def advance(self) -> None:
        if self.status == AgentStatus.RUNNING:
            self.frame = (self.frame + 1) % len(self.FRAMES)
            self.refresh()

    def set_tool(self, tool_name: str) -> None:
        self.current_tool = tool_name
        self.refresh()

    def set_status(self, status: AgentStatus) -> None:
        self.status = status
        self.refresh()


# ============================================================================
# AGENT DASHBOARD - Sidebar showing all active agents
# ============================================================================


class AgentDashboard(Widget):
    """Dashboard sidebar showing active agents, their status, and progress."""

    CSS = """
    AgentDashboard {
        width: 35;
        height: 1fr;
        background: #161b22;
        border: solid #30363d;
        padding: 1;
        overflow-y: auto;
    }
    AgentDashboard .dashboard-title {
        color: #58a6ff;
        text-style: bold;
        padding: 0 0 1 0;
        content-align: center middle;
    }
    AgentDashboard .agent-entry {
        padding: 0 0 1 0;
        margin: 0 0 0 0;
    }
    AgentDashboard .agent-name {
        text-style: bold;
        padding: 0;
    }
    AgentDashboard .agent-status {
        color: #8b949e;
        padding: 0 0 0 1;
    }
    AgentDashboard .agent-task {
        color: #6e7681;
        text-style: italic;
        padding: 0 0 0 1;
        max-width: 32;
    }
    AgentDashboard .agent-progress {
        padding: 0 0 0 1;
    }
    AgentDashboard .agent-tools {
        color: #6e7681;
        padding: 0 0 0 1;
    }
    AgentDashboard .separator {
        color: #30363d;
        padding: 0 0 1 0;
    }
    AgentDashboard .stat-line {
        color: #8b949e;
        padding: 0 0 0 0;
    }
    AgentDashboard .active-color { color: #3fb950; }
    AgentDashboard .idle-color { color: #8b949e; }
    AgentDashboard .error-color { color: #f85149; }
    AgentDashboard .completed-color { color: #58a6ff; }
    """

    agents: reactive[list[AgentTaskInfo]] = reactive(list)
    show_details: reactive[bool] = reactive(True)

    def compose(self) -> ComposeResult:
        yield Static("Agent Dashboard", classes="dashboard-title")
        yield Vertical(id="agent-list")
        yield Static("─" * 33, classes="separator")
        yield Static("Total: 0 active", id="dashboard-stats", classes="stat-line")

    def update_agents(self, agents: list[AgentTaskInfo]) -> None:
        """Update the dashboard with current agent states."""
        self.agents = agents
        agent_list = self.query_one("#agent-list")
        agent_list.remove_children()

        active = sum(1 for a in agents if a.status == AgentStatus.RUNNING)
        completed = sum(1 for a in agents if a.status == AgentStatus.COMPLETED)
        failed = sum(1 for a in agents if a.status == AgentStatus.FAILED)

        for info in agents:
            color = get_agent_color(info.agent_id)

            entry = Vertical(classes="agent-entry")

            # Agent name with color
            status_icon = {
                AgentStatus.IDLE: "○",
                AgentStatus.RUNNING: "⟳",
                AgentStatus.WAITING: "◎",
                AgentStatus.COMPLETED: "✓",
                AgentStatus.FAILED: "✗",
                AgentStatus.CANCELLED: "⊘",
            }.get(info.status, "?")

            name_line = Static(
                f"[{color}]{status_icon} {info.agent_name}[/{color}]",
                classes="agent-name",
            )
            entry.mount(name_line)

            # Task preview
            if info.task:
                entry.mount(Static(f"  {info.task[:50]}", classes="agent-task"))

            # Current tool
            if info.current_tool and info.status == AgentStatus.RUNNING:
                entry.mount(Static(f"  → {info.current_tool}", classes="agent-tools"))

            # Progress bar
            if info.status == AgentStatus.RUNNING and info.progress > 0:
                bar_len = 20
                filled = int(bar_len * info.progress)
                bar = "█" * filled + "░" * (bar_len - filled)
                entry.mount(Static(f"  [{color}]{bar}[/{color}] {info.progress:.0%}", classes="agent-progress"))

            # Elapsed time
            if info.elapsed > 0:
                entry.mount(Static(f"  {info.elapsed:.1f}s", classes="agent-tools"))

            agent_list.mount(entry)

        # Update stats
        stats = self.query_one("#dashboard-stats")
        parts = []
        if active:
            parts.append(f"{active} active")
        if completed:
            parts.append(f"{completed} done")
        if failed:
            parts.append(f"{failed} failed")
        if not parts:
            parts.append("No agents")
        stats.update(f"Total: {', '.join(parts)}")


# ============================================================================
# HANDOFF FLOW - Visualization of agent handoff chain
# ============================================================================


class HandoffFlow(Static):
    """Shows agent handoff chain as a visual flow."""

    CSS = """
    HandoffFlow {
        background: #161b22;
        border: solid #30363d;
        padding: 1;
        margin: 0 0 1 0;
    }
    """

    def __init__(self, chain: list[dict[str, str]], **kwargs) -> None:
        """
        Args:
            chain: List of dicts with 'agent' and optionally 'status' keys.
                   Status can be: pending, running, completed, failed
        """
        super().__init__(**kwargs)
        self.chain = chain

    def render(self) -> str:
        if not self.chain:
            return "[dim]No handoff chain[/dim]"

        lines = ["[bold]Handoff Flow[/bold]"]
        for i, step in enumerate(self.chain):
            agent = step.get("agent", "?")
            status = step.get("status", "pending")
            color = get_agent_color(agent)

            status_icon = {
                "pending": "[dim]○[/dim]",
                "running": f"[{color}]⟳[/{color}]",
                "completed": "[green]✓[/green]",
                "failed": "[red]✗[/red]",
            }.get(status, "?")

            is_last = i == len(self.chain) - 1
            connector = "" if is_last else " → "

            lines.append(f"  {status_icon} [{color}]{agent}[/{color}]{connector}")

        return "\n".join(lines)

    def update_step(self, index: int, status: str) -> None:
        """Update the status of a specific step."""
        if 0 <= index < len(self.chain):
            self.chain[index]["status"] = status
            self.refresh()

    def add_step(self, agent: str, status: str = "pending") -> None:
        """Add a new step to the chain."""
        self.chain.append({"agent": agent, "status": status})
        self.refresh()


# ============================================================================
# ORCHESTRATION PLAN WIDGET - Interactive plan display
# ============================================================================


class OrchestrationPlanWidget(Widget):
    """Interactive orchestration plan with status indicators."""

    CSS = """
    OrchestrationPlanWidget {
        background: #161b22;
        border: solid #1f6feb;
        padding: 1;
        margin: 0 0 1 0;
    }
    OrchestrationPlanWidget .plan-title {
        color: #1f6feb;
        text-style: bold;
        padding: 0 0 1 0;
    }
    OrchestrationPlanWidget .plan-step {
        padding: 0 0 0 1;
    }
    OrchestrationPlanWidget .plan-step-active {
        color: #3fb950;
        text-style: bold;
    }
    OrchestrationPlanWidget .plan-step-done {
        color: #58a6ff;
    }
    OrchestrationPlanWidget .plan-step-pending {
        color: #6e7681;
    }
    """

    plan: reactive[list[dict]] = reactive(list)
    current_step: reactive[int] = reactive(-1)

    def __init__(self, plan: list[dict], **kwargs) -> None:
        super().__init__(**kwargs)
        self.plan = plan

    def compose(self) -> ComposeResult:
        yield Static(f"Orchestration Plan ({len(self.plan)} steps)", classes="plan-title")
        yield Vertical(id="plan-steps")

    def update_plan(self, plan: list[dict]) -> None:
        """Update the displayed plan."""
        self.plan = plan
        self._render_steps()

    def set_current_step(self, index: int) -> None:
        """Mark a step as currently running."""
        self.current_step = index
        self._render_steps()

    def mark_step(self, index: int, status: str) -> None:
        """Mark a step with a status (completed, failed)."""
        if 0 <= index < len(self.plan):
            self.plan[index]["status"] = status
            self._render_steps()

    def _render_steps(self) -> None:
        container = self.query_one("#plan-steps")
        container.remove_children()
        for i, step in enumerate(self.plan):
            agent = step.get("agent", "?")
            task = step.get("task", "")[:60]
            status = step.get("status", "pending")

            if i == self.current_step:
                cls = "plan-step plan-step-active"
                icon = "⟳"
            elif status == "completed":
                cls = "plan-step plan-step-done"
                icon = "✓"
            elif status == "failed":
                cls = "plan-step"
                icon = "✗"
            else:
                cls = "plan-step plan-step-pending"
                icon = "○"

            color = get_agent_color(agent)
            container.mount(
                Static(
                    f"  {icon} [{color}]{i + 1}. {agent}[/{color}] {task}",
                    classes=cls,
                )
            )


# ============================================================================
# BACKGROUND TASK MANAGER - Track and cancel background tasks
# ============================================================================


class BackgroundTaskManager:
    """Manages background tasks with cancellation support."""

    def __init__(self) -> None:
        self._tasks: dict[str, AgentTaskInfo] = {}
        self._lock = threading.Lock()
        self._counter = 0

    def create_task(self, agent_name: str, task: str) -> AgentTaskInfo:
        """Create a new background task."""
        with self._lock:
            self._counter += 1
            task_id = f"task-{self._counter}-{agent_name}"
            info = AgentTaskInfo(
                agent_id=task_id,
                agent_name=agent_name,
                task=task,
                start_time=_time.time(),
            )
            self._tasks[task_id] = info
            return info

    def get_task(self, task_id: str) -> AgentTaskInfo | None:
        """Get a task by ID."""
        with self._lock:
            return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[AgentTaskInfo]:
        """Get all tasks."""
        with self._lock:
            return list(self._tasks.values())

    def get_active_tasks(self) -> list[AgentTaskInfo]:
        """Get currently running tasks."""
        with self._lock:
            return [
                t
                for t in self._tasks.values()
                if t.status in (AgentStatus.RUNNING, AgentStatus.WAITING)
            ]

    def update_task(self, task_id: str, **kwargs: Any) -> None:
        """Update task properties."""
        with self._lock:
            if task_id in self._tasks:
                for key, value in kwargs.items():
                    setattr(self._tasks[task_id], key, value)

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task and task.status == AgentStatus.RUNNING:
                task.cancel_event.set()
                task.status = AgentStatus.CANCELLED
                return True
            return False

    def cancel_all(self) -> int:
        """Cancel all running tasks. Returns count of cancelled tasks."""
        count = 0
        with self._lock:
            for task in self._tasks.values():
                if task.status == AgentStatus.RUNNING:
                    task.cancel_event.set()
                    task.status = AgentStatus.CANCELLED
                    count += 1
        return count

    def cleanup_completed(self, max_age: float = 300.0) -> int:
        """Remove completed tasks older than max_age seconds. Returns count removed."""
        now = _time.time()
        count = 0
        with self._lock:
            to_remove = [
                tid
                for tid, task in self._tasks.items()
                if task.status
                in (AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.CANCELLED)
                and (now - task.start_time) > max_age
            ]
            for tid in to_remove:
                del self._tasks[tid]
                count += 1
        return count

    def get_summary(self) -> dict[str, int]:
        """Get summary counts by status."""
        with self._lock:
            counts: dict[str, int] = {}
            for task in self._tasks.values():
                status = task.status.value
                counts[status] = counts.get(status, 0) + 1
            return counts


# Global task manager instance
_task_manager: BackgroundTaskManager | None = None


def get_task_manager() -> BackgroundTaskManager:
    """Get the global background task manager."""
    global _task_manager
    if _task_manager is None:
        _task_manager = BackgroundTaskManager()
    return _task_manager
