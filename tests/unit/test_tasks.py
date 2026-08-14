"""Unit tests for task manager."""

import pytest

import sago.tasks as tasks_module
from sago.tasks import TaskManager, TaskStatus


@pytest.fixture(autouse=True)
def clean_tasks():
    """Reset global task manager before each test."""
    tasks_module._task_manager = None
    yield
    tasks_module._task_manager = None


@pytest.fixture
def tm(tmp_path):
    """Create a fresh task manager with isolated storage."""
    manager = TaskManager()
    # Override storage path BEFORE clearing loaded data
    manager._get_storage_path = lambda: tmp_path / "task_plans.json"
    manager.plans.clear()
    return manager


class TestTaskManager:
    def test_create_plan(self, tm):
        plan = tm.create_plan(goal="Test goal", todos=["Step 1", "Step 2"])
        assert plan is not None
        assert plan.goal == "Test goal"
        assert len(plan.todos) == 2

    def test_add_todo(self, tm):
        plan = tm.create_plan(goal="Test")
        todo = tm.add_todo(plan.id, "New step")
        assert todo is not None
        assert todo.description == "New step"
        assert len(plan.todos) == 1

    def test_start_todo(self, tm):
        plan = tm.create_plan(goal="Test", todos=["Step 1"])
        todo = plan.todos[0]
        result = tm.start_todo(plan.id, todo.id)
        assert result is True
        assert todo.status == TaskStatus.IN_PROGRESS

    def test_complete_todo(self, tm):
        plan = tm.create_plan(goal="Test", todos=["Step 1"])
        todo = plan.todos[0]
        tm.start_todo(plan.id, todo.id)
        result = tm.complete_todo(plan.id, todo.id, result="Done")
        assert result is True
        assert todo.status == TaskStatus.COMPLETED
        assert todo.result == "Done"

    def test_fail_todo(self, tm):
        plan = tm.create_plan(goal="Test", todos=["Step 1"])
        todo = plan.todos[0]
        result = tm.fail_todo(plan.id, todo.id, error="Failed")
        assert result is True
        assert todo.status == TaskStatus.FAILED
        assert todo.error == "Failed"

    def test_skip_todo(self, tm):
        plan = tm.create_plan(goal="Test", todos=["Step 1"])
        todo = plan.todos[0]
        result = tm.skip_todo(plan.id, todo.id)
        assert result is True
        assert todo.status == TaskStatus.SKIPPED

    def test_wait_for_input(self, tm):
        plan = tm.create_plan(goal="Test", todos=["Step 1"])
        todo = plan.todos[0]
        result = tm.wait_for_input(plan.id, todo.id, "What do you want?")
        assert result is True
        assert todo.status == TaskStatus.WAITING_INPUT
        assert todo.confirmation_message == "What do you want?"

    def test_provide_input(self, tm):
        plan = tm.create_plan(goal="Test", todos=["Step 1"])
        todo = plan.todos[0]
        tm.wait_for_input(plan.id, todo.id, "Question?")
        result = tm.provide_input(plan.id, todo.id, "Answer")
        assert result is True
        assert todo.metadata["user_input"] == "Answer"
        assert todo.status == TaskStatus.PENDING

    def test_get_active_plan(self, tm):
        assert tm.get_active_plan() is None
        plan = tm.create_plan(goal="Test")
        active = tm.get_active_plan()
        assert active is not None
        assert active.id == plan.id

    def test_list_plans(self, tm):
        tm.create_plan(goal="Plan 1")
        tm.create_plan(goal="Plan 2")
        plans = tm.list_plans()
        assert len(plans) == 2

    def test_delete_plan(self, tm):
        plan = tm.create_plan(goal="Test")
        result = tm.delete_plan(plan.id)
        assert result is True
        assert tm.get_plan(plan.id) is None


class TestTaskPlan:
    def test_progress(self, tm):
        plan = tm.create_plan(goal="Test", todos=["S1", "S2", "S3"])
        assert plan.progress == 0.0
        tm.complete_todo(plan.id, plan.todos[0].id)
        assert plan.progress == pytest.approx(0.33, rel=0.1)

    def test_is_complete(self, tm):
        plan = tm.create_plan(goal="Test", todos=["S1", "S2"])
        assert plan.is_complete is False
        tm.complete_todo(plan.id, plan.todos[0].id)
        assert plan.is_complete is False
        tm.complete_todo(plan.id, plan.todos[1].id)
        assert plan.is_complete is True

    def test_current_todo(self, tm):
        plan = tm.create_plan(goal="Test", todos=["S1", "S2", "S3"])
        assert plan.current_todo == plan.todos[0]
        tm.complete_todo(plan.id, plan.todos[0].id)
        assert plan.current_todo == plan.todos[1]

    def test_format_plan(self, tm):
        plan = tm.create_plan(goal="Test", todos=["Step 1", "Step 2"])
        formatted = tm.format_plan(plan)
        assert "Test" in formatted
        assert "Step 1" in formatted
        assert "Step 2" in formatted


class TestComplexTaskDetection:
    def test_simple_task(self):
        from sago.engine.simple_executor import _is_complex_task

        assert _is_complex_task("Fix the bug") is False

    def test_complex_task(self):
        from sago.engine.simple_executor import _is_complex_task

        assert _is_complex_task("Create a REST API and then deploy it") is True

    def test_long_task(self):
        from sago.engine.simple_executor import _is_complex_task

        task = " ".join(["word"] * 35)
        assert _is_complex_task(task) is True
