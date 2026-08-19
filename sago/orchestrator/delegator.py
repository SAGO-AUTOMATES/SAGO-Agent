"""Dynamic Task Delegation Engine

Intelligently routes tasks to the best agents based on:
- Task analysis and classification
- Agent capabilities and skills
- Effort level requirements
- Parallel vs sequential execution
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("sago.orchestrator.delegator")


class TaskType(Enum):
    """Types of tasks that can be delegated."""

    CODE_WRITE = "code_write"
    CODE_REVIEW = "code_review"
    DEBUG = "debug"
    ARCHITECTURE = "architecture"
    DEVOPS = "devops"
    SECURITY = "security"
    DATA = "data"
    DOCUMENTATION = "documentation"
    TESTING = "testing"
    DEPLOYMENT = "deployment"
    RESEARCH = "research"
    GENERAL = "general"


class TaskComplexity(Enum):
    """Task complexity levels."""

    TRIVIAL = "trivial"
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    EXPERT = "expert"


@dataclass
class TaskPlan:
    """Execution plan for a task."""

    task_type: TaskType
    complexity: TaskComplexity
    primary_agent: str
    supporting_agents: list[str] = field(default_factory=list)
    chain: list[str] = field(default_factory=list)
    parallel_groups: list[list[str]] = field(default_factory=list)
    estimated_tokens: int = 0
    effort: str = "medium"
    reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type.value,
            "complexity": self.complexity.value,
            "primary_agent": self.primary_agent,
            "supporting_agents": self.supporting_agents,
            "chain": self.chain,
            "parallel_groups": self.parallel_groups,
            "estimated_tokens": self.estimated_tokens,
            "effort": self.effort,
            "reasoning": self.reasoning,
        }


class TaskDelegator:
    """Dynamically delegates tasks to the best agents."""

    # Keywords for task classification
    TASK_KEYWORDS: dict[TaskType, list[str]] = {
        TaskType.CODE_WRITE: [
            "write",
            "create",
            "implement",
            "build",
            "develop",
            "code",
            "function",
            "class",
            "module",
            "feature",
            "api",
            "endpoint",
        ],
        TaskType.CODE_REVIEW: [
            "review",
            "check",
            "audit",
            "evaluate",
            "assess",
            "improve",
            "refactor",
            "optimize",
            "clean",
            "quality",
        ],
        TaskType.DEBUG: [
            "debug",
            "fix",
            "error",
            "bug",
            "issue",
            "problem",
            "crash",
            "exception",
            "trace",
            "stack",
            "log",
            "fail",
            "broken",
        ],
        TaskType.ARCHITECTURE: [
            "architect",
            "design",
            "plan",
            "structure",
            "scale",
            "system",
            "pattern",
            "microservice",
            "database",
            "schema",
            "migration",
        ],
        TaskType.DEVOPS: [
            "deploy",
            "docker",
            "kubernetes",
            "ci/cd",
            "pipeline",
            "terraform",
            "aws",
            "gcp",
            "azure",
            "cloud",
            "infrastructure",
            "container",
        ],
        TaskType.SECURITY: [
            "security",
            "vulnerability",
            "auth",
            "encrypt",
            "ssl",
            "tls",
            "permission",
            "access",
            "owasp",
            "pentest",
            "audit",
        ],
        TaskType.DATA: [
            "data",
            "sql",
            "query",
            "database",
            "etl",
            "pipeline",
            "analytics",
            "migration",
            "transform",
            "extract",
            "load",
        ],
        TaskType.DOCUMENTATION: [
            "document",
            "readme",
            "docs",
            "api docs",
            "comment",
            "explain",
            "tutorial",
            "guide",
            "write",
        ],
        TaskType.TESTING: [
            "test",
            "unit test",
            "integration",
            "e2e",
            "coverage",
            "mock",
            "assert",
            "pytest",
            "jest",
            "playwright",
        ],
        TaskType.DEPLOYMENT: [
            "deploy",
            "release",
            "ship",
            "production",
            "rollback",
            "monitor",
            "sre",
            "incident",
            "oncall",
        ],
        TaskType.RESEARCH: [
            "research",
            "investigate",
            "compare",
            "evaluate",
            "analyze",
            "study",
            "explore",
            "find",
            "search",
        ],
    }

    # Agent mappings by task type
    AGENT_MAP: dict[TaskType, list[str]] = {
        TaskType.CODE_WRITE: [
            "python-engineer",
            "full-stack-engineer",
            "go-engineer",
            "rust-engineer",
            "typescript-engineer",
            "java-engineer",
        ],
        TaskType.CODE_REVIEW: [
            "code-reviewer",
            "reviewer",
            "security-reviewer",
        ],
        TaskType.DEBUG: [
            "debugger",
            "security-engineer",
            "incident-response-engineer",
        ],
        TaskType.ARCHITECTURE: [
            "solutions-architect",
            "enterprise-architect",
            "domain-architect",
            "system-architect",
            "data-architect",
        ],
        TaskType.DEVOPS: [
            "devops",
            "kubernetes-engineer",
            "docker-engineer",
            "terraform-engineer",
            "aws-engineer",
            "gcp-engineer",
        ],
        TaskType.SECURITY: [
            "security-engineer",
            "appsec-engineer",
            "devsecops-engineer",
            "cloud-security-engineer",
            "k8s-security-engineer",
        ],
        TaskType.DATA: [
            "data-engineer",
            "data-architect",
            "database-administrator",
            "ml-engineer",
            "analytics-engineer",
        ],
        TaskType.DOCUMENTATION: [
            "technical-writer",
            "api-documentation-engineer",
            "documentation-updater",
        ],
        TaskType.TESTING: [
            "qa-engineer",
            "tester",
            "penetration-tester",
            "performance-engineer",
            "e2e-automation-engineer",
        ],
        TaskType.DEPLOYMENT: [
            "site-reliability-engineer",
            "release-engineer",
            "devops",
            "platform-engineer",
        ],
        TaskType.RESEARCH: [
            "researcher",
            "business-analyst",
            "data-analyst",
        ],
        TaskType.GENERAL: [
            "assistant",
            "developer",
            "engineer",
        ],
    }

    # Complexity indicators
    COMPLEXITY_INDICATORS: dict[TaskComplexity, list[str]] = {
        TaskComplexity.TRIVIAL: ["rename", "format", "lint", "fix typo"],
        TaskComplexity.SIMPLE: ["simple", "basic", "quick", "easy", "small"],
        TaskComplexity.MODERATE: ["implement", "add", "create", "modify"],
        TaskComplexity.COMPLEX: [
            "refactor",
            "optimize",
            "migrate",
            "integrate",
            "system",
            "architecture",
            "scale",
            "distributed",
        ],
        TaskComplexity.EXPERT: [
            "security",
            "performance",
            "critical",
            "production",
            "enterprise",
            "compliance",
            "audit",
            "disaster recovery",
        ],
    }

    def analyze_task(self, task: str) -> TaskPlan:
        """Analyze a task and create an execution plan."""
        logger.info("Analyzing task: %s", task[:80])
        task_lower = task.lower()

        # Classify task type
        task_type = self._classify_task_type(task_lower)
        logger.info("Classified task type: %s", task_type.value)

        # Assess complexity
        complexity = self._assess_complexity(task_lower)
        logger.info("Assessed complexity: %s", complexity.value)

        # Determine effort
        effort = self._determine_effort(complexity)

        # Select agents
        primary, supporting = self._select_agents(task_type, task_lower)
        logger.info("Selected agents: primary=%s, supporting=%s", primary, supporting)

        # Build execution chain
        chain = self._build_chain(task_type, complexity)
        logger.info("Built execution chain: %s", chain)

        # Build parallel groups
        parallel_groups = self.get_parallel_groups(chain)
        logger.debug("Parallel groups: %s", parallel_groups)

        # Estimate tokens
        estimated_tokens = self._estimate_tokens(complexity, effort)

        reasoning = self._generate_reasoning(task_type, complexity, primary)
        logger.debug("Reasoning: %s", reasoning)

        plan = TaskPlan(
            task_type=task_type,
            complexity=complexity,
            primary_agent=primary,
            supporting_agents=supporting,
            chain=chain,
            parallel_groups=parallel_groups,
            estimated_tokens=estimated_tokens,
            effort=effort,
            reasoning=reasoning,
        )
        logger.info(
            "Task plan created: type=%s complexity=%s effort=%s tokens=%d",
            task_type.value,
            complexity.value,
            effort,
            estimated_tokens,
        )
        return plan

    def _classify_task_type(self, task: str) -> TaskType:
        """Classify the task type based on keywords."""
        scores: dict[TaskType, int] = {}

        for task_type, keywords in self.TASK_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in task)
            if score > 0:
                scores[task_type] = score

        if scores:
            chosen = max(scores, key=scores.get)  # type: ignore
            logger.debug("Task type scores: %s, selected: %s", scores, chosen.value)
            return chosen
        logger.debug("No keyword matches, defaulting to GENERAL")
        return TaskType.GENERAL

    def _assess_complexity(self, task: str) -> TaskComplexity:
        """Assess task complexity."""
        scores: dict[TaskComplexity, int] = {}

        for complexity, indicators in self.COMPLEXITY_INDICATORS.items():
            score = sum(1 for ind in indicators if ind in task)
            if score > 0:
                scores[complexity] = score

        if scores:
            chosen = max(scores, key=scores.get)  # type: ignore
            logger.debug("Complexity indicator scores: %s, selected: %s", scores, chosen.value)
            return chosen

        # Default based on task length
        word_count = len(task.split())
        if word_count > 50:
            logger.debug("No indicators matched, word count %d -> COMPLEX", word_count)
            return TaskComplexity.COMPLEX
        elif word_count > 20:
            logger.debug("No indicators matched, word count %d -> MODERATE", word_count)
            return TaskComplexity.MODERATE
        logger.debug("No indicators matched, word count %d -> SIMPLE", word_count)
        return TaskComplexity.SIMPLE

    def _determine_effort(self, complexity: TaskComplexity) -> str:
        """Determine effort level based on complexity."""
        effort_map = {
            TaskComplexity.TRIVIAL: "minimal",
            TaskComplexity.SIMPLE: "low",
            TaskComplexity.MODERATE: "medium",
            TaskComplexity.COMPLEX: "high",
            TaskComplexity.EXPERT: "max",
        }
        return effort_map.get(complexity, "medium")

    def _select_agents(self, task_type: TaskType, task: str) -> tuple[str, list[str]]:
        """Select primary and supporting agents."""
        candidates = self.AGENT_MAP.get(task_type, self.AGENT_MAP[TaskType.GENERAL])
        logger.debug("Agent candidates for %s: %s", task_type.value, candidates)

        # Simple matching based on task content
        primary = candidates[0] if candidates else "developer"
        supporting = candidates[1:3] if len(candidates) > 1 else []

        logger.debug(
            "Agent selection result: primary=%s, supporting=%s",
            primary,
            supporting,
        )
        return primary, supporting

    def _build_chain(self, task_type: TaskType, complexity: TaskComplexity) -> list[str]:
        """Build execution chain based on task type and complexity."""
        chains: dict[TaskType, list[str]] = {
            TaskType.CODE_WRITE: ["developer", "code-reviewer"],
            TaskType.CODE_REVIEW: ["code-reviewer", "security-reviewer"],
            TaskType.DEBUG: ["debugger", "code-reviewer"],
            TaskType.ARCHITECTURE: ["solutions-architect", "developer"],
            TaskType.DEVOPS: ["devops", "site-reliability-engineer"],
            TaskType.SECURITY: ["security-engineer", "code-reviewer"],
            TaskType.DATA: ["data-engineer", "data-architect"],
            TaskType.DOCUMENTATION: ["technical-writer", "code-reviewer"],
            TaskType.TESTING: ["qa-engineer", "tester"],
            TaskType.DEPLOYMENT: ["devops", "site-reliability-engineer"],
            TaskType.RESEARCH: ["researcher", "analyst"],
            TaskType.GENERAL: ["developer"],
        }

        chain = chains.get(task_type, ["developer"])
        logger.debug("Base chain for %s: %s", task_type.value, chain)

        # For complex tasks, add more steps
        if complexity in (TaskComplexity.COMPLEX, TaskComplexity.EXPERT):
            if "code-reviewer" not in chain:
                chain.append("code-reviewer")
                logger.debug("Added code-reviewer to chain for %s complexity", complexity.value)

        logger.debug("Final execution chain: %s", chain)
        return chain

    def _estimate_tokens(self, complexity: TaskComplexity, effort: str) -> int:
        """Estimate token usage."""
        base_tokens = {
            TaskComplexity.TRIVIAL: 500,
            TaskComplexity.SIMPLE: 1000,
            TaskComplexity.MODERATE: 2000,
            TaskComplexity.COMPLEX: 4000,
            TaskComplexity.EXPERT: 8000,
        }

        effort_multiplier = {
            "minimal": 0.5,
            "low": 0.75,
            "medium": 1.0,
            "high": 1.5,
            "max": 2.0,
        }

        base = base_tokens.get(complexity, 2000)
        multiplier = effort_multiplier.get(effort, 1.0)

        return int(base * multiplier)

    def _generate_reasoning(
        self, task_type: TaskType, complexity: TaskComplexity, primary_agent: str
    ) -> str:
        """Generate reasoning for the delegation decision."""
        return (
            f"Task classified as {task_type.value} with {complexity.value} complexity. "
            f"Selected {primary_agent} as primary agent based on skill match. "
            f"Effort level adjusted for optimal resource usage."
        )

    def get_parallel_groups(self, chain: list[str]) -> list[list[str]]:
        """Group agents that can run in parallel."""
        # Simple grouping: agents without dependencies can run together
        independent = ["code-reviewer", "security-reviewer", "technical-writer"]

        indep_group = [a for a in chain if a in independent]
        dep_group = [a for a in chain if a not in independent]

        groups = []
        if indep_group:
            groups.append(indep_group)
        if dep_group:
            groups.append(dep_group)

        return groups
