"""Unit tests for Phase 4: Subagent Isolation and Iteration Budgets."""

from sago.agents.iteration_budget import IterationBudget
from sago.agents.subagent_isolation import (
    filter_tools_for_subagent,
    is_tool_allowed_for_subagent,
)


class TestIterationBudget:
    """Test token and iteration budget counting."""

    def test_budget_consumption(self):
        budget = IterationBudget(max_iterations=3, name="subagent-test")
        assert budget.remaining == 3
        assert budget.is_exhausted is False

        assert budget.consume() is True
        assert budget.consume() is True
        assert budget.consume() is True
        assert budget.is_exhausted is True

        # 4th consume fails
        assert budget.consume() is False

    def test_budget_refund(self):
        budget = IterationBudget(max_iterations=2)
        budget.consume(2)
        assert budget.is_exhausted is True

        budget.refund(1)
        assert budget.remaining == 1
        assert budget.is_exhausted is False


class TestSubagentIsolation:
    """Test tool filtering for subagents."""

    def test_blocked_tools(self):
        assert is_tool_allowed_for_subagent("read_file") is True
        assert is_tool_allowed_for_subagent("write_file") is True
        assert is_tool_allowed_for_subagent("delegate_to_agent") is False
        assert is_tool_allowed_for_subagent("ask_question") is False
        assert is_tool_allowed_for_subagent("spawn_agent") is False

    def test_filter_tools_list(self):
        tools = ["read_file", "write_file", "delegate_to_agent", "ask_question"]
        allowed = filter_tools_for_subagent(tools)
        assert allowed == ["read_file", "write_file"]
