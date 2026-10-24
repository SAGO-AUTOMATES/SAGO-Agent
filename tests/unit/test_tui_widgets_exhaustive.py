"""Exhaustive tests for sago/tui/widgets/__init__.py."""

from __future__ import annotations

import time

import pytest
from textual.app import App, ComposeResult

from sago.tui.widgets import (
    AgentDashboard,
    AgentSpinner,
    AgentStatus,
    AgentTaskInfo,
    BackgroundTaskManager,
    HandoffFlow,
    OrchestrationPlanWidget,
    Spinner,
    get_agent_color,
    get_task_manager,
)


def test_spinner_widget() -> None:
    s_short = Spinner(text="Thinking")
    rendered_short = s_short.render()
    assert "Thinking" in rendered_short

    s_long = Spinner(text="Thinking about " + "x" * 100)
    rendered_long = s_long.render()
    assert len(s_long.text) > 80
    assert "Thinking" in rendered_long

    # Advance
    initial_frame = s_short.frame
    s_short.advance()
    assert s_short.frame == (initial_frame + 1) % len(Spinner.FRAMES)


def test_agent_color() -> None:
    c1 = get_agent_color("coder")
    c2 = get_agent_color("coder")
    assert c1 == c2
    assert c1.startswith("#")


def test_agent_spinner_lifecycle() -> None:
    asp = AgentSpinner("agent-123", "CoderAgent", task="Refactor database schema")
    # Initial running state
    r1 = asp.render()
    assert "CoderAgent" in r1
    assert "Refactor" in r1

    asp.set_tool("run_test")
    r2 = asp.render()
    assert "run_test" in r2

    asp.advance()

    # Test all statuses
    for st in [
        AgentStatus.IDLE,
        AgentStatus.WAITING,
        AgentStatus.COMPLETED,
        AgentStatus.FAILED,
        AgentStatus.CANCELLED,
    ]:
        asp.set_status(st)
        r = asp.render()
        assert asp._status_icon() in r


def test_handoff_flow_widget() -> None:
    hf_empty = HandoffFlow(chain=[])
    assert "No handoff chain" in hf_empty.render()

    chain = [
        {"agent": "architect", "status": "completed"},
        {"agent": "coder", "status": "running"},
        {"agent": "tester", "status": "pending"},
        {"agent": "deployer", "status": "failed"},
    ]
    hf = HandoffFlow(chain=chain)
    rendered = hf.render()
    assert "architect" in rendered
    assert "coder" in rendered
    assert "tester" in rendered
    assert "deployer" in rendered

    hf.update_step(1, "completed")
    assert hf.chain[1]["status"] == "completed"

    hf.add_step("security-auditor", "running")
    assert len(hf.chain) == 5


class WidgetHarnessApp(App):
    """Test harness for Dashboard and Plan widgets."""

    def __init__(self, dashboard: AgentDashboard, plan: OrchestrationPlanWidget) -> None:
        super().__init__()
        self.dashboard = dashboard
        self.plan_widget = plan

    def compose(self) -> ComposeResult:
        yield self.dashboard
        yield self.plan_widget


@pytest.mark.asyncio
async def test_dashboard_and_plan_widgets() -> None:
    dash = AgentDashboard()
    plan = OrchestrationPlanWidget(
        plan=[
            {"agent": "architect", "task": "Design system", "status": "pending"},
            {"agent": "coder", "task": "Write implementation", "status": "pending"},
        ]
    )
    app = WidgetHarnessApp(dash, plan)

    async with app.run_test() as pilot:
        await pilot.pause()

        # Update dashboard agents
        agents = [
            AgentTaskInfo(
                agent_id="a1",
                agent_name="Architect",
                task="Analyze requirements",
                status=AgentStatus.RUNNING,
                progress=0.45,
                current_tool="ast_grep",
                elapsed=5.2,
            ),
            AgentTaskInfo(
                agent_id="a2",
                agent_name="Coder",
                task="Generate code",
                status=AgentStatus.COMPLETED,
            ),
            AgentTaskInfo(
                agent_id="a3",
                agent_name="Tester",
                task="Run tests",
                status=AgentStatus.FAILED,
            ),
        ]
        dash.update_agents(agents)
        await pilot.pause()

        stats = dash.query_one("#dashboard-stats")
        rendered_stats = str(stats.render())
        assert "1 active" in rendered_stats
        assert "1 done" in rendered_stats
        assert "1 failed" in rendered_stats

        # Update plan widget
        plan.set_current_step(0)
        await pilot.pause()
        plan.mark_step(0, "completed")
        plan.mark_step(1, "failed")
        await pilot.pause()

        plan.update_plan(
            [{"agent": "deployer", "task": "Release container", "status": "completed"}]
        )
        await pilot.pause()


def test_background_task_manager() -> None:
    mgr = BackgroundTaskManager()

    # Create tasks
    t1 = mgr.create_task("coder", "refactor")
    t2 = mgr.create_task("tester", "run test")

    assert mgr.get_task(t1.agent_id) is t1
    assert len(mgr.get_all_tasks()) == 2

    # Active tasks
    t1.status = AgentStatus.RUNNING
    t2.status = AgentStatus.WAITING
    assert len(mgr.get_active_tasks()) == 2

    # Update task
    mgr.update_task(t1.agent_id, progress=0.75, current_tool="edit_file")
    assert t1.progress == 0.75
    assert t1.current_tool == "edit_file"

    # Cancel task
    assert mgr.cancel_task(t1.agent_id) is True
    assert t1.status == AgentStatus.CANCELLED
    assert t1.cancel_event.is_set()

    # Cancel all
    t2.status = AgentStatus.RUNNING
    cancelled_count = mgr.cancel_all()
    assert cancelled_count == 1
    assert t2.status == AgentStatus.CANCELLED

    # Summary
    summary = mgr.get_summary()
    assert summary["cancelled"] == 2

    # Cleanup completed
    t1.start_time = time.time() - 400
    cleaned = mgr.cleanup_completed(max_age=300)
    assert cleaned >= 1

    # Singleton
    mgr_global = get_task_manager()
    assert isinstance(mgr_global, BackgroundTaskManager)
