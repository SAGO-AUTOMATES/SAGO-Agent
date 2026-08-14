"""Unit tests for workflow engine: state transitions, error recovery, builder."""

import time

import pytest

from sago.workflow.engine import (
    StepStatus,
    Workflow,
    WorkflowBuilder,
    WorkflowEngine,
    WorkflowState,
    WorkflowStatus,
    WorkflowStep,
)


@pytest.fixture
def engine():
    return WorkflowEngine()


@pytest.fixture
def engine_with_persist(tmp_path):
    return WorkflowEngine(persist_dir=tmp_path)


# ── WorkflowState ────────────────────────────────────────────────────────


class TestWorkflowState:
    def test_set_and_get(self):
        state = WorkflowState()
        state.set("key", "value")
        assert state.get("key") == "value"

    def test_get_default(self):
        state = WorkflowState()
        assert state.get("missing", "default") == "default"

    def test_set_records_history(self):
        state = WorkflowState()
        state.set("x", 42)
        assert len(state.history) == 1
        assert state.history[0]["action"] == "set"

    def test_update_context(self):
        state = WorkflowState()
        state.update_context({"a": 1, "b": 2})
        assert state.context["a"] == 1
        assert len(state.history) == 1
        assert state.history[0]["action"] == "context_update"


# ── Workflow ─────────────────────────────────────────────────────────────


class TestWorkflow:
    def test_active_steps(self):
        wf = Workflow(id="w1", name="W", description="")
        wf.steps.append(WorkflowStep(id="s1", name="S1", type="agent_call", status=StepStatus.RUNNING))
        wf.steps.append(WorkflowStep(id="s2", name="S2", type="agent_call", status=StepStatus.PENDING))
        assert len(wf.active_steps()) == 1

    def test_completed_steps(self):
        wf = Workflow(id="w1", name="W", description="")
        wf.steps.append(WorkflowStep(id="s1", name="S1", type="agent_call", status=StepStatus.COMPLETED))
        assert len(wf.completed_steps()) == 1

    def test_failed_steps(self):
        wf = Workflow(id="w1", name="W", description="")
        wf.steps.append(WorkflowStep(id="s1", name="S1", type="agent_call", status=StepStatus.FAILED))
        assert len(wf.failed_steps()) == 1

    def test_next_steps_deps_met(self):
        wf = Workflow(id="w1", name="W", description="")
        s1 = WorkflowStep(id="s1", name="S1", type="agent_call", status=StepStatus.COMPLETED)
        s2 = WorkflowStep(id="s2", name="S2", type="agent_call", status=StepStatus.PENDING, depends_on=["s1"])
        wf.steps.extend([s1, s2])
        ready = wf.next_steps()
        assert len(ready) == 1
        assert ready[0].id == "s2"

    def test_next_steps_deps_not_met(self):
        wf = Workflow(id="w1", name="W", description="")
        s1 = WorkflowStep(id="s1", name="S1", type="agent_call", status=StepStatus.PENDING)
        s2 = WorkflowStep(id="s2", name="S2", type="agent_call", status=StepStatus.PENDING, depends_on=["s1"])
        wf.steps.extend([s1, s2])
        ready = wf.next_steps()
        assert len(ready) == 1
        assert ready[0].id == "s1"

    def test_to_dict(self):
        wf = Workflow(id="w1", name="Test", description="A test")
        wf.steps.append(WorkflowStep(id="s1", name="S1", type="agent_call"))
        d = wf.to_dict()
        assert d["id"] == "w1"
        assert d["status"] == "draft"
        assert len(d["steps"]) == 1


# ── WorkflowStep ─────────────────────────────────────────────────────────


class TestWorkflowStep:
    def test_duration_not_started(self):
        step = WorkflowStep(id="s1", name="S", type="agent_call")
        assert step.duration() == 0.0

    def test_duration_with_start(self):
        step = WorkflowStep(id="s1", name="S", type="agent_call")
        step.started_at = time.time() - 10
        step.completed_at = time.time()
        assert step.duration() >= 9.0

    def test_to_dict(self):
        step = WorkflowStep(id="s1", name="S1", type="agent_call", config={"k": "v"})
        d = step.to_dict()
        assert d["id"] == "s1"
        assert d["status"] == "pending"


# ── WorkflowEngine CRUD ──────────────────────────────────────────────────


class TestWorkflowEngineCRUD:
    def test_create_workflow(self, engine):
        wf = engine.create_workflow(name="Test", description="desc")
        assert wf.name == "Test"
        assert wf.status == WorkflowStatus.DRAFT

    def test_add_step(self, engine):
        wf = engine.create_workflow(name="T", description="")
        step = engine.add_step(wf.id, name="S1", step_type="agent_call", config={"task": "do"})
        assert step is not None
        assert len(wf.steps) == 1

    def test_add_step_nonexistent_workflow(self, engine):
        result = engine.add_step("no-such", name="S", step_type="agent_call")
        assert result is None

    def test_get_workflow(self, engine):
        wf = engine.create_workflow(name="T", description="")
        assert engine.get_workflow(wf.id) is wf

    def test_get_workflow_nonexistent(self, engine):
        assert engine.get_workflow("no") is None

    def test_list_workflows(self, engine):
        engine.create_workflow(name="A", description="")
        engine.create_workflow(name="B", description="")
        assert len(engine.list_workflows()) == 2


# ── Cancel / Pause / Resume ─────────────────────────────────────────────


class TestWorkflowTransitions:
    def test_cancel_workflow(self, engine):
        wf = engine.create_workflow(name="T", description="")
        assert engine.cancel_workflow(wf.id) is True
        assert wf.status == WorkflowStatus.CANCELLED

    def test_cancel_nonexistent(self, engine):
        assert engine.cancel_workflow("no") is False

    def test_pause_workflow(self, engine):
        wf = engine.create_workflow(name="T", description="")
        wf.status = WorkflowStatus.RUNNING
        assert engine.pause_workflow(wf.id) is True
        assert wf.status == WorkflowStatus.PAUSED

    def test_pause_non_running(self, engine):
        wf = engine.create_workflow(name="T", description="")
        assert engine.pause_workflow(wf.id) is False

    def test_resume_workflow(self, engine):
        wf = engine.create_workflow(name="T", description="")
        wf.status = WorkflowStatus.PAUSED
        wf.steps.append(WorkflowStep(id="s1", name="S", type="agent_call", status=StepStatus.WAITING))
        assert engine.resume_workflow(wf.id) is True
        assert wf.status == WorkflowStatus.RUNNING
        assert wf.steps[0].status == StepStatus.PENDING

    def test_resume_non_paused(self, engine):
        wf = engine.create_workflow(name="T", description="")
        assert engine.resume_workflow(wf.id) is False


# ── Execute / Error Recovery ─────────────────────────────────────────────


class TestWorkflowExecution:
    def test_execute_with_custom_executor(self, engine):
        engine.register_executor("mock", lambda ctx, cfg: {"result": "ok", "success": True})
        wf = engine.create_workflow(name="T", description="")
        engine.add_step(wf.id, name="S1", step_type="mock", config={})
        result = engine.execute_workflow(wf.id)
        assert result["steps"][0]["status"] == "completed"

    def test_execute_no_executor_fails_step(self, engine):
        wf = engine.create_workflow(name="T", description="")
        engine.add_step(wf.id, name="S1", step_type="unknown_type", config={})
        result = engine.execute_workflow(wf.id)
        assert result["steps"][0]["status"] == "failed"
        assert "No executor" in result["steps"][0]["error"]

    def test_execute_nonexistent_workflow(self, engine):
        result = engine.execute_workflow("no")
        assert "error" in result

    def test_execute_step_retry_on_failure(self, engine):
        call_count = 0

        def flaky_executor(ctx, cfg):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("transient error")
            return {"result": "recovered", "success": True}

        engine.register_executor("flaky", flaky_executor)
        wf = engine.create_workflow(name="T", description="")
        engine.add_step(wf.id, name="S1", step_type="flaky", config={}, max_retries=3)
        result = engine.execute_workflow(wf.id)
        assert result["steps"][0]["status"] == "completed"
        assert call_count == 3

    def test_execute_step_permanent_failure(self, engine):
        def always_fail(ctx, cfg):
            raise RuntimeError("permanent error")

        engine.register_executor("fail", always_fail)
        wf = engine.create_workflow(name="T", description="")
        engine.add_step(wf.id, name="S1", step_type="fail", config={}, max_retries=0)
        result = engine.execute_workflow(wf.id)
        assert result["steps"][0]["status"] == "failed"
        assert "permanent error" in result["steps"][0]["error"]

    def test_parallel_steps(self, engine):
        def slow_ok(ctx, cfg):
            return {"result": "done", "success": True}

        engine.register_executor("slow", slow_ok)
        wf = engine.create_workflow(name="T", description="")
        engine.add_step(wf.id, name="P1", step_type="slow", config={})
        engine.add_step(wf.id, name="P2", step_type="slow", config={})
        result = engine.execute_workflow(wf.id)
        statuses = [s["status"] for s in result["steps"]]
        assert all(s == "completed" for s in statuses)


# ── Persistence ──────────────────────────────────────────────────────────


class TestWorkflowPersistence:
    def test_save_and_load(self, engine_with_persist):
        wf = engine_with_persist.create_workflow(name="Persistent", description="")
        engine_with_persist.add_step(wf.id, name="S1", step_type="agent_call")
        wf_id = wf.id
        # Create new engine loading from disk
        engine2 = WorkflowEngine(persist_dir=engine_with_persist.persist_dir)
        loaded = engine2.get_workflow(wf_id)
        assert loaded is not None
        assert loaded.name == "Persistent"
        assert len(loaded.steps) == 1


# ── Callbacks ────────────────────────────────────────────────────────────


class TestWorkflowCallbacks:
    def test_notify_callback(self, engine):
        events = []
        engine.add_callback(lambda ev, data: events.append(ev))
        wf = engine.create_workflow(name="T", description="")
        engine.cancel_workflow(wf.id)
        assert "workflow_created" in events
        assert "workflow_cancelled" in events

    def test_callback_exception_swallowed(self, engine):
        def bad_callback(ev, data):
            raise RuntimeError("boom")

        engine.add_callback(bad_callback)
        # Should not raise
        engine.create_workflow(name="T", description="")


# ── WorkflowBuilder ──────────────────────────────────────────────────────


class TestWorkflowBuilder:
    def test_builder_chain(self, engine):
        builder = WorkflowBuilder(engine)
        wf = builder.create(name="Built", description="").step(name="S1", step_type="agent_call").step(name="S2", step_type="agent_call").build()
        assert wf is not None
        assert wf.name == "Built"
        assert len(wf.steps) == 2
        assert wf.steps[1].depends_on == [wf.steps[0].id]

    def test_builder_no_workflow_raises(self):
        builder = WorkflowBuilder(WorkflowEngine())
        with pytest.raises(ValueError):
            builder.step(name="S", step_type="agent_call")

    def test_builder_parallel(self, engine):
        builder = WorkflowBuilder(engine)
        wf = (
            builder.create(name="Parallel", description="")
            .step(name="Pre", step_type="agent_call")
            .parallel(
                [
                    {"name": "A", "type": "agent_call"},
                    {"name": "B", "type": "agent_call"},
                ]
            )
            .build()
        )
        assert len(wf.steps) == 3
