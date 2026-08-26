"""Task Manager - Todo list tracking for complex tasks.

Automatically breaks down complex tasks into steps, tracks progress,
and handles user confirmations.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from sago.paths import get_sago_home
from sago.utils.errors import log_error

logger = logging.getLogger("sago.tasks")


class TaskStatus(Enum):
    """Status of a todo item."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING_INPUT = "waiting_input"
    SKIPPED = "skipped"


@dataclass
class TodoItem:
    """A single todo item in a task list."""

    id: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    result: str | None = None
    error: str | None = None
    agent: str | None = None
    tools: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    substeps: list[str] = field(default_factory=list)
    requires_confirmation: bool = False
    confirmation_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def duration(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.completed_at or time.time()
        return end - self.started_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "agent": self.agent,
            "tools": self.tools,
            "duration": self.duration(),
            "requires_confirmation": self.requires_confirmation,
        }


@dataclass
class TaskPlan:
    """A plan for executing a complex task."""

    id: str
    goal: str
    todos: list[TodoItem] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    status: str = "active"
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def progress(self) -> float:
        if not self.todos:
            return 0.0
        done = sum(1 for t in self.todos if t.status == TaskStatus.COMPLETED)
        return done / len(self.todos)

    @property
    def is_complete(self) -> bool:
        return all(t.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED) for t in self.todos)

    @property
    def current_todo(self) -> TodoItem | None:
        for t in self.todos:
            if t.status in (TaskStatus.PENDING, TaskStatus.WAITING_INPUT):
                return t
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "todos": [t.to_dict() for t in self.todos],
            "progress": f"{self.progress:.0%}",
            "status": self.status,
            "created_at": self.created_at,
        }


class TaskManager:
    """Manages todo lists for complex tasks."""

    def __init__(self) -> None:
        self.plans: dict[str, TaskPlan] = {}
        self._callbacks: list[Callable[..., None]] = []
        self._load()

    def _get_storage_path(self) -> Path:
        return get_sago_home() / "task_plans.json"

    def _load(self) -> None:
        path = self._get_storage_path()
        if path.exists():
            logger.debug("Loading task plans from %s", path)
            try:
                data = json.loads(path.read_text())
                for plan_data in data.get("plans", []):
                    plan = TaskPlan(
                        id=plan_data["id"],
                        goal=plan_data["goal"],
                        created_at=plan_data.get("created_at", time.time()),
                        status=plan_data.get("status", "active"),
                    )
                    for todo_data in plan_data.get("todos", []):
                        todo = TodoItem(
                            id=todo_data["id"],
                            description=todo_data["description"],
                            status=TaskStatus(todo_data.get("status", "pending")),
                            result=todo_data.get("result"),
                            agent=todo_data.get("agent"),
                            tools=todo_data.get("tools", []),
                            requires_confirmation=todo_data.get("requires_confirmation", False),
                            confirmation_message=todo_data.get("confirmation_message"),
                        )
                        plan.todos.append(todo)
                    self.plans[plan.id] = plan
                logger.debug("Loaded %d task plans", len(self.plans))
            except Exception as e:
                logger.error("Failed to load task plans from %s: %s", path, e)
                log_error("Failed to load persisted task plans", e)

    def _save(self) -> None:
        path = self._get_storage_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"plans": [p.to_dict() for p in self.plans.values()]}
        path.write_text(json.dumps(data, indent=2))
        logger.debug("Saved %d task plans to %s", len(self.plans), path)

    def on_update(self, callback: Callable[..., None]) -> None:
        """Register a callback for task updates."""
        self._callbacks.append(callback)

    def _notify(self, event: str, data: dict[str, Any]) -> None:
        for cb in self._callbacks:
            try:
                cb(event, data)
            except Exception as e:
                log_error("Task update callback raised", e, context={"event": event})

    def create_plan(self, goal: str, todos: list[str] | None = None) -> TaskPlan:
        """Create a new task plan."""
        plan = TaskPlan(
            id=str(uuid.uuid4())[:8],
            goal=goal,
        )
        if todos:
            for desc in todos:
                plan.todos.append(
                    TodoItem(
                        id=str(uuid.uuid4())[:8],
                        description=desc,
                    )
                )
        self.plans[plan.id] = plan
        self._save()
        logger.info(
            "Created task plan %s with %d steps for goal: %r", plan.id, len(plan.todos), goal[:80]
        )
        self._notify("plan_created", plan.to_dict())
        return plan

    def add_todo(
        self,
        plan_id: str,
        description: str,
        requires_confirmation: bool = False,
        confirmation_message: str | None = None,
    ) -> TodoItem | None:
        """Add a todo item to a plan."""
        plan = self.plans.get(plan_id)
        if not plan:
            return None
        todo = TodoItem(
            id=str(uuid.uuid4())[:8],
            description=description,
            requires_confirmation=requires_confirmation,
            confirmation_message=confirmation_message,
        )
        plan.todos.append(todo)
        self._save()
        self._notify("todo_added", {"plan_id": plan_id, "todo": todo.to_dict()})
        return todo

    def start_todo(self, plan_id: str, todo_id: str) -> bool:
        """Mark a todo as in progress."""
        plan = self.plans.get(plan_id)
        if not plan:
            return False
        for todo in plan.todos:
            if todo.id == todo_id:
                todo.status = TaskStatus.IN_PROGRESS
                todo.started_at = time.time()
                self._save()
                self._notify("todo_started", {"plan_id": plan_id, "todo": todo.to_dict()})
                return True
        return False

    def complete_todo(self, plan_id: str, todo_id: str, result: str = "") -> bool:
        """Mark a todo as completed."""
        plan = self.plans.get(plan_id)
        if not plan:
            logger.warning("complete_todo: plan %s not found", plan_id)
            return False
        for todo in plan.todos:
            if todo.id == todo_id:
                todo.status = TaskStatus.COMPLETED
                todo.result = result
                todo.completed_at = time.time()
                self._save()
                logger.debug("Todo %s completed in plan %s", todo_id, plan_id)
                self._notify("todo_completed", {"plan_id": plan_id, "todo": todo.to_dict()})
                if plan.is_complete:
                    plan.completed_at = time.time()
                    plan.status = "completed"
                    self._save()
                    logger.info("Plan %s fully completed (%d steps)", plan_id, len(plan.todos))
                    self._notify("plan_completed", plan.to_dict())
                return True
        logger.warning("complete_todo: todo %s not found in plan %s", todo_id, plan_id)
        return False

    def fail_todo(self, plan_id: str, todo_id: str, error: str) -> bool:
        """Mark a todo as failed."""
        plan = self.plans.get(plan_id)
        if not plan:
            return False
        for todo in plan.todos:
            if todo.id == todo_id:
                todo.status = TaskStatus.FAILED
                todo.error = error
                todo.completed_at = time.time()
                self._save()
                self._notify("todo_failed", {"plan_id": plan_id, "todo": todo.to_dict()})
                return True
        return False

    def skip_todo(self, plan_id: str, todo_id: str) -> bool:
        """Skip a todo item."""
        plan = self.plans.get(plan_id)
        if not plan:
            return False
        for todo in plan.todos:
            if todo.id == todo_id:
                todo.status = TaskStatus.SKIPPED
                todo.completed_at = time.time()
                self._save()
                self._notify("todo_skipped", {"plan_id": plan_id, "todo": todo.to_dict()})
                return True
        return False

    def wait_for_input(self, plan_id: str, todo_id: str, message: str) -> bool:
        """Mark a todo as waiting for user input."""
        plan = self.plans.get(plan_id)
        if not plan:
            return False
        for todo in plan.todos:
            if todo.id == todo_id:
                todo.status = TaskStatus.WAITING_INPUT
                todo.confirmation_message = message
                self._save()
                self._notify("todo_waiting", {"plan_id": plan_id, "todo": todo.to_dict()})
                return True
        return False

    def provide_input(self, plan_id: str, todo_id: str, user_input: str) -> bool:
        """Provide user input for a waiting todo."""
        plan = self.plans.get(plan_id)
        if not plan:
            return False
        for todo in plan.todos:
            if todo.id == todo_id and todo.status == TaskStatus.WAITING_INPUT:
                todo.metadata["user_input"] = user_input
                todo.status = TaskStatus.PENDING
                self._save()
                self._notify(
                    "input_received", {"plan_id": plan_id, "todo_id": todo_id, "input": user_input}
                )
                return True
        return False

    def get_active_plan(self) -> TaskPlan | None:
        """Get the most recent active plan."""
        active = [p for p in self.plans.values() if p.status == "active"]
        if active:
            return max(active, key=lambda p: p.created_at)
        return None

    def get_plan(self, plan_id: str) -> TaskPlan | None:
        return self.plans.get(plan_id)

    def list_plans(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in self.plans.values()]

    def delete_plan(self, plan_id: str) -> bool:
        if plan_id in self.plans:
            del self.plans[plan_id]
            self._save()
            return True
        return False

    def format_plan(self, plan: TaskPlan) -> str:
        """Format a plan for display — concise, no raw prompt dump."""
        # Clean goal: first line, max 80 chars, no ID noise
        clean_goal = plan.goal.split("\n")[0].strip()
        if len(clean_goal) > 80:
            clean_goal = clean_goal[:77] + "..."
        # Remove extra whitespace/typos artifacts for display
        clean_goal = " ".join(clean_goal.split())
        lines = [f"📋 Plan: {clean_goal}"]
        lines.append(
            f"   Progress: {plan.progress:.0%} | Status: {plan.status} | {len(plan.todos)} steps"
        )
        lines.append("")

        status_icons = {
            TaskStatus.PENDING: "⬜",
            TaskStatus.IN_PROGRESS: "🔄",
            TaskStatus.COMPLETED: "✅",
            TaskStatus.FAILED: "❌",
            TaskStatus.WAITING_INPUT: "⏳",
            TaskStatus.SKIPPED: "⏭️",
        }

        for idx, todo in enumerate(plan.todos, 1):
            icon = status_icons.get(todo.status, "❓")
            # Show step number + description, truncate long desc
            desc = todo.description[:90] + ("..." if len(todo.description) > 90 else "")
            line = f"   {icon} {idx}. {desc}"
            if todo.error:
                line += f" ⚠️ {todo.error[:40]}"
            lines.append(line)
        # Footer hint
        lines.append("")
        lines.append("   Tip: /plan to edit, Y to approve, N to deny, or let it auto-run")
        return "\n".join(lines)


# Global instance
_task_manager: TaskManager | None = None


def get_task_manager() -> TaskManager:
    """Get the global task manager."""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager
