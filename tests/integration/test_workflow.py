"""Integration tests for workflow engine."""

import pytest

from sago.workflow.engine import Workflow, WorkflowEngine, WorkflowStep, StepStatus, WorkflowStatus


@pytest.fixture
def engine():
    """Create a workflow engine."""
    return WorkflowEngine()


@pytest.fixture
def sample_workflow():
    """Create a sample workflow."""
    return Workflow(
        id="test-workflow",
        name="Test Workflow",
        description="A test workflow",
        steps=[
            WorkflowStep(id="step1", name="Step 1", type="agent_call", config={"task": "Task 1"}),
            WorkflowStep(id="step2", name="Step 2", type="agent_call", config={"task": "Task 2"}, depends_on=["step1"]),
            WorkflowStep(id="step3", name="Step 3", type="agent_call", config={"task": "Task 3"}, depends_on=["step1"]),
        ],
    )


class TestWorkflow:
    def test_workflow_creation(self, sample_workflow):
        assert sample_workflow.id == "test-workflow"
        assert sample_workflow.name == "Test Workflow"
        assert len(sample_workflow.steps) == 3

    def test_step_dependencies(self, sample_workflow):
        step2 = sample_workflow.steps[1]
        assert "step1" in step2.depends_on

    def test_step_status(self, sample_workflow):
        step = sample_workflow.steps[0]
        assert step.status == StepStatus.PENDING

    def test_workflow_status(self, sample_workflow):
        assert sample_workflow.status == WorkflowStatus.DRAFT


class TestWorkflowEngine:
    def test_engine_creation(self, engine):
        assert engine is not None

    def test_engine_create_workflow(self, engine):
        wf = engine.create_workflow(
            name="Test",
            description="A test workflow",
        )
        assert wf is not None
        assert wf.name == "Test"

    def test_engine_add_step(self, engine):
        wf = engine.create_workflow(
            name="Test",
            description="A test workflow",
        )
        step = engine.add_step(
            workflow_id=wf.id,
            name="Step 1",
            step_type="agent_call",
            config={"task": "Task 1"},
        )
        assert step is not None
        assert len(wf.steps) == 1

    def test_engine_get_workflow(self, engine):
        wf = engine.create_workflow(
            name="Test",
            description="A test workflow",
        )
        retrieved = engine.get_workflow(wf.id)
        assert retrieved is not None
        assert retrieved.name == "Test"

    def test_engine_list_workflows(self, engine):
        engine.create_workflow(name="W1", description="Workflow 1")
        engine.create_workflow(name="W2", description="Workflow 2")
        workflows = engine.list_workflows()
        assert len(workflows) >= 2

    def test_engine_cancel_workflow(self, engine):
        wf = engine.create_workflow(
            name="Test",
            description="A test workflow",
        )
        result = engine.cancel_workflow(wf.id)
        assert result is True
        assert wf.status == WorkflowStatus.CANCELLED


class TestWorkflowStep:
    def test_step_creation(self):
        step = WorkflowStep(id="s1", name="Step 1", type="agent_call", config={"task": "Do something"})
        assert step.id == "s1"
        assert step.status == StepStatus.PENDING

    def test_step_with_dependencies(self):
        step = WorkflowStep(id="s2", name="Step 2", type="agent_call", config={"task": "Do more"}, depends_on=["s1"])
        assert "s1" in step.depends_on

    def test_step_duration(self):
        step = WorkflowStep(id="s1", name="Step 1", type="agent_call", config={})
        assert step.duration() == 0.0
