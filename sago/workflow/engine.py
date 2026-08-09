"""Temporal Workflow Engine

Stateful workflow execution with:
- Step-by-step state tracking
- Pause/resume capability
- Error recovery and retry
- Conditional branching
- Parallel execution
- Custom triggers and schedules
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class StepStatus(Enum):
    """Status of a workflow step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING = "waiting"
    CANCELLED = "cancelled"


class WorkflowStatus(Enum):
    """Status of a workflow."""

    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TriggerType(Enum):
    """Types of workflow triggers."""

    MANUAL = "manual"
    SCHEDULE = "schedule"
    EVENT = "event"
    WEBHOOK = "webhook"
    TICKET = "ticket"


@dataclass
class WorkflowStep:
    """A single step in a workflow."""

    id: str
    name: str
    type: str  # agent_call, tool_call, condition, parallel, wait
    config: dict[str, Any] = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: str | None = None
    started_at: float | None = None
    completed_at: float | None = None
    retry_count: int = 0
    max_retries: int = 3
    timeout: float = 300.0
    depends_on: list[str] = field(default_factory=list)

    def duration(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.completed_at or time.time()
        return end - self.started_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "status": self.status.value,
            "result": str(self.result)[:500] if self.result else None,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration": self.duration(),
            "retry_count": self.retry_count,
        }


@dataclass
class WorkflowState:
    """State of a workflow execution."""

    variables: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)

    def set(self, key: str, value: Any) -> None:
        self.variables[key] = value
        self.history.append({
            "action": "set",
            "key": key,
            "value": str(value)[:200],
            "timestamp": time.time(),
        })

    def get(self, key: str, default: Any = None) -> Any:
        return self.variables.get(key, default)

    def update_context(self, data: dict[str, Any]) -> None:
        self.context.update(data)
        self.history.append({
            "action": "context_update",
            "keys": list(data.keys()),
            "timestamp": time.time(),
        })


@dataclass
class Workflow:
    """A complete workflow definition."""

    id: str
    name: str
    description: str
    steps: list[WorkflowStep] = field(default_factory=list)
    status: WorkflowStatus = WorkflowStatus.DRAFT
    trigger: TriggerType = TriggerType.MANUAL
    trigger_config: dict[str, Any] = field(default_factory=dict)
    state: WorkflowState = field(default_factory=WorkflowState)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def active_steps(self) -> list[WorkflowStep]:
        return [s for s in self.steps if s.status == StepStatus.RUNNING]

    def completed_steps(self) -> list[WorkflowStep]:
        return [s for s in self.steps if s.status == StepStatus.COMPLETED]

    def failed_steps(self) -> list[WorkflowStep]:
        return [s for s in self.steps if s.status == StepStatus.FAILED]

    def next_steps(self) -> list[WorkflowStep]:
        """Get steps ready to execute (pending with deps met)."""
        completed_ids = {s.id for s in self.completed_steps()}
        return [
            s for s in self.steps
            if s.status == StepStatus.PENDING
            and all(dep in completed_ids for dep in s.depends_on)
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "trigger": self.trigger.value,
            "steps": [s.to_dict() for s in self.steps],
            "state": {
                "variables": self.state.variables,
                "context_keys": list(self.state.context.keys()),
            },
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "progress": f"{len(self.completed_steps())}/{len(self.steps)}",
        }


class WorkflowEngine:
    """Engine for executing stateful workflows."""

    def __init__(self, persist_dir: Path | None = None) -> None:
        self.persist_dir = persist_dir
        self.workflows: dict[str, Workflow] = {}
        self._executors: dict[str, Callable[..., Any]] = {}
        self._callbacks: list[Callable[..., None]] = []

        # Register default executors
        self._register_default_executors()

        if persist_dir:
            persist_dir.mkdir(parents=True, exist_ok=True)
            self._load_all()

    def _register_default_executors(self) -> None:
        """Register default executors for common step types."""
        import os

        def _agent_call_executor(context: dict, config: dict) -> dict[str, Any]:
            """Execute an agent call step."""
            task = config.get("task", "")
            agent = config.get("agent", "sago-orchestrator")
            api_key = os.environ.get("OPENROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", ""))

            if not api_key:
                return {"error": "No API key", "success": False}

            from sago.engine.simple_executor import execute_agent_task
            result = execute_agent_task(
                task=task,
                agent_role=agent.replace("-", " ").title(),
                api_key=api_key,
                model="openrouter/free",
                max_tokens=4096,
                max_iterations=5,
            )
            return result

        def _tool_call_executor(context: dict, config: dict) -> dict[str, Any]:
            """Execute a tool call step."""
            import importlib
            from sago.tools.base import BaseTool

            tool_name = config.get("tool", "")
            tool_args = config.get("args", {})

            # Discover tool
            tools_dir = Path(__file__).parent.parent / "tools"
            for py_file in tools_dir.rglob("*.py"):
                if py_file.name.startswith("_") or py_file.name == "base.py":
                    continue
                parts = py_file.relative_to(tools_dir).with_suffix("").as_posix().split("/")
                module_name = ".".join(["sago", "tools"] + parts)
                try:
                    mod = importlib.import_module(module_name)
                    for attr_name in dir(mod):
                        obj = getattr(mod, attr_name)
                        if isinstance(obj, type) and hasattr(obj, "name") and obj.name == tool_name:
                            if issubclass(obj, BaseTool):
                                tool_instance = obj()
                                result = tool_instance.run(**tool_args)
                                return {"result": str(result), "success": True}
                except Exception:
                    continue

            return {"error": f"Tool not found: {tool_name}", "success": False}

        self._executors["agent_call"] = _agent_call_executor
        self._executors["tool_call"] = _tool_call_executor

    def register_executor(
        self,
        step_type: str,
        executor: Callable[..., Any],
    ) -> None:
        """Register an executor for a step type."""
        self._executors[step_type] = executor

    def add_callback(self, callback: Callable[..., None]) -> None:
        """Add a callback for workflow events."""
        self._callbacks.append(callback)

    def create_workflow(
        self,
        name: str,
        description: str = "",
        trigger: TriggerType = TriggerType.MANUAL,
        trigger_config: dict[str, Any] | None = None,
    ) -> Workflow:
        """Create a new workflow."""
        workflow = Workflow(
            id=str(uuid.uuid4()),
            name=name,
            description=description,
            trigger=trigger,
            trigger_config=trigger_config or {},
        )
        self.workflows[workflow.id] = workflow
        self._save(workflow)
        self._notify("workflow_created", {"workflow_id": workflow.id})
        return workflow

    def add_step(
        self,
        workflow_id: str,
        name: str,
        step_type: str,
        config: dict[str, Any] | None = None,
        depends_on: list[str] | None = None,
        timeout: float = 300.0,
        max_retries: int = 3,
    ) -> WorkflowStep | None:
        """Add a step to a workflow."""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return None

        step = WorkflowStep(
            id=str(uuid.uuid4()),
            name=name,
            type=step_type,
            config=config or {},
            depends_on=depends_on or [],
            timeout=timeout,
            max_retries=max_retries,
        )
        workflow.steps.append(step)
        workflow.updated_at = time.time()
        self._save(workflow)
        return step

    def execute_workflow(
        self,
        workflow_id: str,
        initial_vars: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a workflow from start to finish."""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return {"error": "Workflow not found"}

        # Set initial variables
        if initial_vars:
            for key, value in initial_vars.items():
                workflow.state.set(key, value)

        workflow.status = WorkflowStatus.RUNNING
        workflow.started_at = time.time()
        self._notify("workflow_started", {"workflow_id": workflow_id})

        try:
            while True:
                next_steps = workflow.next_steps()
                if not next_steps:
                    break

                for step in next_steps:
                    self._execute_step(workflow, step)

                # Check if workflow is complete
                if all(
                    s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)
                    for s in workflow.steps
                ):
                    workflow.status = WorkflowStatus.COMPLETED
                    break

                # Check for failures
                if any(s.status == StepStatus.FAILED for s in workflow.steps):
                    workflow.status = WorkflowStatus.FAILED
                    break

            workflow.completed_at = time.time()
            workflow.updated_at = time.time()
            self._save(workflow)
            self._notify("workflow_completed", {"workflow_id": workflow_id})

            return workflow.to_dict()

        except Exception as e:
            workflow.status = WorkflowStatus.FAILED
            workflow.completed_at = time.time()
            self._save(workflow)
            return {"error": str(e), "workflow": workflow.to_dict()}

    def pause_workflow(self, workflow_id: str) -> bool:
        """Pause a running workflow."""
        workflow = self.workflows.get(workflow_id)
        if not workflow or workflow.status != WorkflowStatus.RUNNING:
            return False

        workflow.status = WorkflowStatus.PAUSED
        for step in workflow.steps:
            if step.status == StepStatus.RUNNING:
                step.status = StepStatus.WAITING
        self._save(workflow)
        self._notify("workflow_paused", {"workflow_id": workflow_id})
        return True

    def resume_workflow(self, workflow_id: str) -> bool:
        """Resume a paused workflow."""
        workflow = self.workflows.get(workflow_id)
        if not workflow or workflow.status != WorkflowStatus.PAUSED:
            return False

        workflow.status = WorkflowStatus.RUNNING
        for step in workflow.steps:
            if step.status == StepStatus.WAITING:
                step.status = StepStatus.PENDING
        self._save(workflow)
        self._notify("workflow_resumed", {"workflow_id": workflow_id})
        return True

    def cancel_workflow(self, workflow_id: str) -> bool:
        """Cancel a workflow."""
        workflow = self.workflows.get(workflow_id)
        if not workflow:
            return False

        workflow.status = WorkflowStatus.CANCELLED
        for step in workflow.steps:
            if step.status in (StepStatus.PENDING, StepStatus.RUNNING, StepStatus.WAITING):
                step.status = StepStatus.CANCELLED
        self._save(workflow)
        self._notify("workflow_cancelled", {"workflow_id": workflow_id})
        return True

    def get_workflow(self, workflow_id: str) -> Workflow | None:
        return self.workflows.get(workflow_id)

    def list_workflows(self) -> list[dict[str, Any]]:
        return [w.to_dict() for w in self.workflows.values()]

    def _execute_step(self, workflow: Workflow, step: WorkflowStep) -> None:
        """Execute a single workflow step."""
        step.status = StepStatus.RUNNING
        step.started_at = time.time()
        self._notify("step_started", {
            "workflow_id": workflow.id,
            "step_id": step.id,
            "step_name": step.name,
        })

        executor = self._executors.get(step.type)
        if not executor:
            step.error = f"No executor for step type: {step.type}"
            step.status = StepStatus.FAILED
            step.completed_at = time.time()
            return

        try:
            # Build step context
            context = {
                "workflow_id": workflow.id,
                "step_id": step.id,
                "state": workflow.state.variables,
                "config": step.config,
            }

            result = executor(context, step.config)
            step.result = result
            step.status = StepStatus.COMPLETED

            # Update state with result
            if isinstance(result, dict):
                workflow.state.update_context(result)

        except Exception as e:
            if step.retry_count < step.max_retries:
                step.retry_count += 1
                step.status = StepStatus.PENDING
                step.error = f"Retry {step.retry_count}/{step.max_retries}: {e}"
            else:
                step.error = str(e)
                step.status = StepStatus.FAILED

        finally:
            step.completed_at = time.time()
            workflow.updated_at = time.time()
            self._save(workflow)

    def _save(self, workflow: Workflow) -> None:
        """Persist workflow to disk."""
        if not self.persist_dir:
            return

        path = self.persist_dir / f"{workflow.id}.json"
        path.write_text(json.dumps(workflow.to_dict(), default=str))

    def _load_all(self) -> None:
        """Load all workflows from disk."""
        if not self.persist_dir:
            return

        for path in self.persist_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                workflow = Workflow(
                    id=data["id"],
                    name=data["name"],
                    description=data.get("description", ""),
                    status=WorkflowStatus(data.get("status", "draft")),
                )
                # Restore steps
                for step_data in data.get("steps", []):
                    step = WorkflowStep(
                        id=step_data["id"],
                        name=step_data["name"],
                        type=step_data["type"],
                        config=step_data.get("config", {}),
                        status=StepStatus(step_data.get("status", "pending")),
                    )
                    workflow.steps.append(step)
                # Restore state
                state_data = data.get("state", {})
                workflow.state.variables = state_data.get("variables", {})
                workflow.state.context = state_data.get("context", {})
                self.workflows[workflow.id] = workflow
            except Exception:
                pass

    def _notify(self, event: str, data: dict[str, Any]) -> None:
        """Notify callbacks of workflow events."""
        for callback in self._callbacks:
            try:
                callback(event, data)
            except Exception:
                pass


class WorkflowBuilder:
    """Fluent builder for creating workflows."""

    def __init__(self, engine: WorkflowEngine) -> None:
        self.engine = engine
        self._workflow: Workflow | None = None
        self._last_step_id: str | None = None

    def create(
        self,
        name: str,
        description: str = "",
        trigger: TriggerType = TriggerType.MANUAL,
    ) -> WorkflowBuilder:
        """Create a new workflow."""
        self._workflow = self.engine.create_workflow(
            name, description, trigger
        )
        return self

    def step(
        self,
        name: str,
        step_type: str,
        config: dict[str, Any] | None = None,
        timeout: float = 300.0,
    ) -> WorkflowBuilder:
        """Add a step to the workflow."""
        if not self._workflow:
            raise ValueError("No workflow created")

        depends_on = [self._last_step_id] if self._last_step_id else []

        step = self.engine.add_step(
            self._workflow.id,
            name,
            step_type,
            config,
            depends_on=depends_on,
            timeout=timeout,
        )

        if step:
            self._last_step_id = step.id

        return self

    def parallel(
        self,
        steps: list[dict[str, Any]],
    ) -> WorkflowBuilder:
        """Add parallel steps."""
        if not self._workflow:
            raise ValueError("No workflow created")

        step_ids = []
        for step_def in steps:
            step = self.engine.add_step(
                self._workflow.id,
                step_def["name"],
                step_def["type"],
                step_def.get("config"),
                depends_on=[self._last_step_id] if self._last_step_id else [],
            )
            if step:
                step_ids.append(step.id)

        # All parallel steps depend on the last sequential step
        if step_ids:
            self._last_step_id = step_ids[-1]

        return self

    def build(self) -> Workflow | None:
        """Get the built workflow."""
        return self._workflow
