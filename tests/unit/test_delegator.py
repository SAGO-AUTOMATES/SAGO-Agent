"""Unit tests for task delegator: classification, routing, complexity."""

import pytest

from sago.orchestrator.delegator import (
    TaskComplexity,
    TaskDelegator,
    TaskPlan,
    TaskType,
)


@pytest.fixture
def delegator():
    return TaskDelegator()


# ── TaskType Classification ──────────────────────────────────────────────


class TestTaskClassification:
    def test_code_write(self, delegator):
        result = delegator.analyze_task("Create a REST API endpoint")
        assert result.task_type == TaskType.CODE_WRITE

    def test_code_review(self, delegator):
        result = delegator.analyze_task("Review the code quality and refactor")
        assert result.task_type == TaskType.CODE_REVIEW

    def test_debug(self, delegator):
        result = delegator.analyze_task("Fix the bug causing crash in main.py")
        assert result.task_type == TaskType.DEBUG

    def test_architecture(self, delegator):
        result = delegator.analyze_task("Design a scalable system architecture")
        assert result.task_type == TaskType.ARCHITECTURE

    def test_devops(self, delegator):
        result = delegator.analyze_task("Deploy to Kubernetes cluster")
        assert result.task_type == TaskType.DEVOPS

    def test_security(self, delegator):
        result = delegator.analyze_task("Perform a pentest and encrypt all sensitive data")
        assert result.task_type == TaskType.SECURITY

    def test_data(self, delegator):
        result = delegator.analyze_task("Write SQL query for analytics")
        assert result.task_type == TaskType.DATA

    def test_documentation(self, delegator):
        result = delegator.analyze_task("Write documentation and API docs")
        assert result.task_type == TaskType.DOCUMENTATION

    def test_testing(self, delegator):
        result = delegator.analyze_task("Write unit tests with pytest")
        assert result.task_type == TaskType.TESTING

    def test_deployment(self, delegator):
        result = delegator.analyze_task("Release to production and monitor")
        assert result.task_type == TaskType.DEPLOYMENT

    def test_research(self, delegator):
        result = delegator.analyze_task("Research and compare frameworks")
        assert result.task_type == TaskType.RESEARCH

    def test_general_fallback(self, delegator):
        result = delegator.analyze_task("do something random")
        assert result.task_type == TaskType.GENERAL


# ── Complexity Assessment ────────────────────────────────────────────────


class TestComplexityAssessment:
    def test_trivial(self, delegator):
        result = delegator.analyze_task("rename the function")
        assert result.complexity in (TaskComplexity.TRIVIAL, TaskComplexity.SIMPLE)

    def test_simple(self, delegator):
        result = delegator.analyze_task("quick basic fix")
        assert result.complexity == TaskComplexity.SIMPLE

    def test_expert(self, delegator):
        result = delegator.analyze_task("security audit for production compliance")
        assert result.complexity == TaskComplexity.EXPERT

    def test_long_task_complex(self, delegator):
        words = " ".join(["word"] * 60)
        result = delegator.analyze_task(words)
        assert result.complexity == TaskComplexity.COMPLEX

    def test_moderate_task(self, delegator):
        words = " ".join(["word"] * 25)
        result = delegator.analyze_task(words)
        assert result.complexity == TaskComplexity.MODERATE


# ── Effort Determination ─────────────────────────────────────────────────


class TestEffortDetermination:
    def test_trivial_minimal(self, delegator):
        result = delegator.analyze_task("rename a variable")
        if result.complexity == TaskComplexity.TRIVIAL:
            assert result.effort == "minimal"

    def test_expert_max(self, delegator):
        result = delegator.analyze_task("security audit for production compliance")
        assert result.effort == "max"

    def test_effort_all_levels(self):
        d = TaskDelegator()
        for complexity, expected in [
            (TaskComplexity.TRIVIAL, "minimal"),
            (TaskComplexity.SIMPLE, "low"),
            (TaskComplexity.MODERATE, "medium"),
            (TaskComplexity.COMPLEX, "high"),
            (TaskComplexity.EXPERT, "max"),
        ]:
            assert d._determine_effort(complexity) == expected


# ── Agent Selection ──────────────────────────────────────────────────────


class TestAgentSelection:
    def test_select_agents_returns_tuple(self, delegator):
        primary, supporting = delegator._select_agents(TaskType.CODE_WRITE, "write code")
        assert isinstance(primary, str)
        assert isinstance(supporting, list)

    def test_general_agents_for_unknown(self, delegator):
        primary, supporting = delegator._select_agents(TaskType.GENERAL, "do stuff")
        assert primary in delegator.AGENT_MAP[TaskType.GENERAL]

    def test_code_write_agents(self, delegator):
        primary, supporting = delegator._select_agents(TaskType.CODE_WRITE, "build feature")
        assert primary in delegator.AGENT_MAP[TaskType.CODE_WRITE]


# ── Chain Building ───────────────────────────────────────────────────────


class TestChainBuilding:
    def test_chain_returns_list(self, delegator):
        chain = delegator._build_chain(TaskType.CODE_WRITE, TaskComplexity.SIMPLE)
        assert isinstance(chain, list)
        assert len(chain) >= 1

    def test_complex_adds_reviewer(self, delegator):
        chain = delegator._build_chain(TaskType.CODE_WRITE, TaskComplexity.COMPLEX)
        assert "code-reviewer" in chain

    def test_expert_adds_reviewer(self, delegator):
        chain = delegator._build_chain(TaskType.CODE_WRITE, TaskComplexity.EXPERT)
        assert "code-reviewer" in chain

    def test_all_task_types_have_chains(self, delegator):
        for tt in TaskType:
            chain = delegator._build_chain(tt, TaskComplexity.SIMPLE)
            assert len(chain) >= 1


# ── Token Estimation ─────────────────────────────────────────────────────


class TestTokenEstimation:
    def test_base_tokens(self, delegator):
        tokens = delegator._estimate_tokens(TaskComplexity.SIMPLE, "low")
        assert tokens > 0

    def test_expert_more_than_trivial(self, delegator):
        trivial = delegator._estimate_tokens(TaskComplexity.TRIVIAL, "minimal")
        expert = delegator._estimate_tokens(TaskComplexity.EXPERT, "max")
        assert expert > trivial

    def test_effort_multiplier(self, delegator):
        minimal = delegator._estimate_tokens(TaskComplexity.SIMPLE, "minimal")
        max_effort = delegator._estimate_tokens(TaskComplexity.SIMPLE, "max")
        assert max_effort > minimal


# ── Reasoning Generation ────────────────────────────────────────────────


class TestReasoning:
    def test_generate_reasoning(self, delegator):
        reasoning = delegator._generate_reasoning(
            TaskType.CODE_WRITE, TaskComplexity.MODERATE, "python-engineer"
        )
        assert "code_write" in reasoning
        assert "moderate" in reasoning
        assert "python-engineer" in reasoning


# ── Parallel Groups ──────────────────────────────────────────────────────


class TestParallelGroups:
    def test_parallel_groups(self, delegator):
        chain = ["developer", "code-reviewer", "security-reviewer"]
        groups = delegator.get_parallel_groups(chain)
        assert len(groups) == 2  # independent + dependent

    def test_all_independent(self, delegator):
        chain = ["code-reviewer", "security-reviewer"]
        groups = delegator.get_parallel_groups(chain)
        assert len(groups) >= 1


# ── TaskPlan ─────────────────────────────────────────────────────────────


class TestTaskPlan:
    def test_to_dict(self):
        plan = TaskPlan(
            task_type=TaskType.CODE_WRITE,
            complexity=TaskComplexity.MODERATE,
            primary_agent="dev",
            reasoning="test reasoning",
        )
        d = plan.to_dict()
        assert d["task_type"] == "code_write"
        assert d["complexity"] == "moderate"
        assert d["primary_agent"] == "dev"
        assert "supporting_agents" in d
        assert "chain" in d


# ── Full Analyze ─────────────────────────────────────────────────────────


class TestFullAnalyze:
    def test_analyze_returns_plan(self, delegator):
        plan = delegator.analyze_task("Create a Python REST API with tests and deploy it")
        assert isinstance(plan, TaskPlan)
        assert plan.primary_agent
        assert len(plan.chain) > 0
        assert plan.estimated_tokens > 0
        assert plan.effort in ("minimal", "low", "medium", "high", "max")
