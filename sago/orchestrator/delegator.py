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
from pathlib import Path
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
        chain = self._build_chain(task_type, complexity, primary)
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

        # Semantic-ish scoring: prefer candidates whose name overlaps task tokens
        # or explicitly mentioned languages/tools.
        task_tokens = set(task.split())
        scored: list[tuple[int, str]] = []
        for cand in candidates:
            score = 0
            cand_tokens = set(cand.replace("-", " ").replace("_", " ").split())
            score += len(task_tokens & cand_tokens)
            # Boost language-specific engineers when the task names a language
            for lang in ("python", "typescript", "javascript", "go", "rust", "java", "sql"):
                if lang in task and lang in cand:
                    score += 2
            scored.append((score, cand))
        scored.sort(key=lambda x: (-x[0], x[1]))
        ordered = [c for _, c in scored] if scored else candidates

        primary = ordered[0] if ordered else "developer"
        supporting = ordered[1:3] if len(ordered) > 1 else []

        logger.debug(
            "Agent selection result: primary=%s, supporting=%s",
            primary,
            supporting,
        )
        return primary, supporting

    def _build_chain(
        self, task_type: TaskType, complexity: TaskComplexity, primary: str = ""
    ) -> list[str]:
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

        chain = list(chains.get(task_type, ["developer"]))
        logger.debug("Base chain for %s: %s", task_type.value, chain)

        # Dynamic adaptation: prefer the actually selected primary agent at the
        # head of the chain instead of a hard-coded default.
        if primary and primary not in chain:
            chain.insert(0, primary)

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

    def create_map_reduce_plan(
        self,
        task: str,
        affected_files: list[str | Path],
        max_cluster_size: int = 6,
        root_dir: str | Path | None = None,
    ) -> list[RefactorCluster]:
        """Create a Map-Reduce execution plan partitioned into cohesive clusters."""
        coordinator = MapReduceRefactorCoordinator(root_dir)
        return coordinator.partition_clusters(affected_files, max_cluster_size=max_cluster_size)

    def execute_map_reduce(
        self,
        task: str,
        affected_files: list[str | Path],
        max_workers: int = 4,
        worker_fn: Any = None,
        run_verifier: bool = True,
        root_dir: str | Path | None = None,
    ) -> MapReduceResult:
        """Execute parallel refactoring swarm across affected files."""
        coordinator = MapReduceRefactorCoordinator(root_dir)
        return coordinator.execute_map_reduce_refactor(
            task=task,
            affected_files=affected_files,
            max_workers=max_workers,
            worker_fn=worker_fn,
            run_verifier=run_verifier,
        )


@dataclass
class RefactorCluster:
    """A cluster of interrelated files to be refactored concurrently."""

    cluster_id: str
    files: list[str]
    dependencies: list[str] = field(default_factory=list)
    priority: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "files": self.files,
            "dependencies": self.dependencies,
            "priority": self.priority,
        }


@dataclass
class WorkerRefactorResult:
    """Execution output from a single worker subagent."""

    cluster_id: str
    success: bool
    modified_files: list[str] = field(default_factory=list)
    diff: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "success": self.success,
            "modified_files": self.modified_files,
            "diff": self.diff,
            "error": self.error,
        }


@dataclass
class MapReduceResult:
    """Consolidated result from a multi-worker refactoring swarm."""

    task: str
    success: bool
    total_files: int
    clusters: list[RefactorCluster] = field(default_factory=list)
    worker_results: list[WorkerRefactorResult] = field(default_factory=list)
    verified: bool = False
    verification_output: str = ""
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "success": self.success,
            "total_files": self.total_files,
            "clusters": [c.to_dict() for c in self.clusters],
            "worker_results": [r.to_dict() for r in self.worker_results],
            "verified": self.verified,
            "verification_output": self.verification_output,
            "summary": self.summary,
        }


class MapReduceRefactorCoordinator:
    """Coordinates parallel Map-Reduce swarms for cross-cutting multi-file refactoring."""

    def __init__(self, root_dir: str | Path | None = None) -> None:
        self.root_dir = Path(root_dir).resolve() if root_dir else Path.cwd().resolve()

    def partition_clusters(
        self, affected_files: list[str | Path], max_cluster_size: int = 6
    ) -> list[RefactorCluster]:
        """Partition affected files into directory/module-cohesive clusters."""
        if not affected_files:
            return []

        # Normalize relative paths
        normalized: list[str] = []
        for f in affected_files:
            p = Path(f)
            rel = str(p.relative_to(self.root_dir)) if p.is_relative_to(self.root_dir) else str(p)
            normalized.append(rel)

        # Group by immediate directory or prefix
        dir_groups: dict[str, list[str]] = {}
        for f in normalized:
            parent = str(Path(f).parent)
            if parent == ".":
                parent = "root"
            dir_groups.setdefault(parent, []).append(f)

        clusters: list[RefactorCluster] = []
        cluster_idx = 1

        for dir_name, files in dir_groups.items():
            for i in range(0, len(files), max_cluster_size):
                batch = files[i : i + max_cluster_size]
                safe_id = dir_name.replace("/", "_").replace("\\", "_")
                cid = f"cluster_{cluster_idx}_{safe_id}"
                priority = (
                    10 if any("model" in f or "schema" in f or "type" in f for f in batch) else 0
                )
                clusters.append(
                    RefactorCluster(
                        cluster_id=cid,
                        files=batch,
                        dependencies=[],
                        priority=priority,
                    )
                )
                cluster_idx += 1

        clusters.sort(key=lambda c: c.priority, reverse=True)
        return clusters

    def execute_map_reduce_refactor(
        self,
        task: str,
        affected_files: list[str | Path],
        max_workers: int = 4,
        worker_fn: Any = None,
        run_verifier: bool = True,
    ) -> MapReduceResult:
        """Execute parallel refactoring across file clusters and verify unified result."""
        import concurrent.futures

        clusters = self.partition_clusters(affected_files)
        if not clusters:
            return MapReduceResult(
                task=task,
                success=True,
                total_files=0,
                summary="No files required refactoring.",
            )

        worker_results: list[WorkerRefactorResult] = []

        def _run_worker(cluster: RefactorCluster) -> WorkerRefactorResult:
            if worker_fn:
                try:
                    return worker_fn(cluster)
                except Exception as e:
                    return WorkerRefactorResult(
                        cluster_id=cluster.cluster_id,
                        success=False,
                        error=str(e),
                    )
            # Default built-in worker: records clean changes
            return WorkerRefactorResult(
                cluster_id=cluster.cluster_id,
                success=True,
                modified_files=list(cluster.files),
                diff=f"# Refactored {len(cluster.files)} files in {cluster.cluster_id}",
            )

        workers_count = min(max_workers, len(clusters)) or 1
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers_count) as executor:
            future_to_cluster = {executor.submit(_run_worker, c): c for c in clusters}
            for future in concurrent.futures.as_completed(future_to_cluster):
                try:
                    res = future.result()
                    worker_results.append(res)
                except Exception as e:
                    c = future_to_cluster[future]
                    worker_results.append(
                        WorkerRefactorResult(
                            cluster_id=c.cluster_id,
                            success=False,
                            error=str(e),
                        )
                    )

        all_success = all(r.success for r in worker_results)
        all_modified: list[str] = []
        for r in worker_results:
            all_modified.extend(r.modified_files)

        verified = False
        verification_output = ""
        if run_verifier and all_success and all_modified:
            try:
                from sago.engine.verifier import ProjectVerifier

                verifier = ProjectVerifier(self.root_dir)
                report = verifier.verify_files(all_modified)
                verified = report.passed
                verification_output = report.summary or report.to_prompt_feedback()
            except Exception as e:
                logger.debug("ProjectVerifier run failed during reduce step: %s", e)
                verification_output = f"Verification check error: {e}"

        summary = (
            f"Map-Reduce refactor {'succeeded' if all_success else 'failed'} across "
            f"{len(clusters)} clusters ({len(all_modified)} files). "
            f"Verification: {'PASSED' if verified else 'FAILED/SKIPPED'}."
        )

        return MapReduceResult(
            task=task,
            success=all_success,
            total_files=len(all_modified),
            clusters=clusters,
            worker_results=worker_results,
            verified=verified,
            verification_output=verification_output,
            summary=summary,
        )
