"""Smart Agent Router - Intelligent agent selection from 300+ profiles.

Provides a unified routing API that all entry points (spawn_agent, TUI, orchestrator)
can use to select the best agent(s) for a task.

Uses multi-signal scoring:
- Skill tag matching (token overlap + synonym expansion)
- Category relevance
- Project context (languages/frameworks from config)
- Task type classification
- Agent popularity/success history (future)
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("sago.router")

# ============================================================================
# SYNONYM MAP for better skill matching
# ============================================================================

SYNONYM_MAP: dict[str, list[str]] = {
    "python": ["python", "py", "fastapi", "django", "flask", "pydantic", "pip", "poetry", "pytest"],
    "javascript": ["javascript", "js", "typescript", "ts", "node", "nodejs", "npm", "deno", "bun"],
    "react": ["react", "reactjs", "jsx", "tsx", "nextjs", "next.js", "remix"],
    "vue": ["vue", "vuejs", "vue.js", "nuxt", "nuxtjs"],
    "angular": ["angular", "angularjs", "ng"],
    "java": ["java", "spring", "springboot", "maven", "gradle", "jvm"],
    "go": ["go", "golang", "gin", "echo", "fiber"],
    "rust": ["rust", "cargo", "rustc", "tokio", "actix"],
    "csharp": ["c#", "csharp", "dotnet", ".net", "blazor", "xamarin"],
    "cpp": ["c++", "cpp", "cmake", "clang", "gcc"],
    "php": ["php", "laravel", "symfony", "composer"],
    "ruby": ["ruby", "rails", "rubyonrails", "sinatra", "bundler"],
    "swift": ["swift", "swiftui", "uikit", "cocoapods", "spm"],
    "kotlin": ["kotlin", "kotlinjvm", "ktor", "android"],
    "dart": ["dart", "flutter", "dartlang"],
    "sql": [
        "sql",
        "mysql",
        "postgres",
        "postgresql",
        "sqlite",
        "mssql",
        "oracle",
        "database",
        "db",
    ],
    "nosql": ["nosql", "mongodb", "redis", "cassandra", "dynamodb", "couchdb", "elasticsearch"],
    "docker": ["docker", "container", "containerization", "dockerfile", "compose"],
    "kubernetes": ["kubernetes", "k8s", "helm", "istio", "operators"],
    "aws": ["aws", "amazon", "lambda", "s3", "ec2", "ecs", "fargate", "cloudformation", "sam"],
    "azure": ["azure", "microsoft", "aks", "functions", "devops"],
    "gcp": ["gcp", "google cloud", "cloud run", "cloud functions", "bigquery", "firestore"],
    "terraform": ["terraform", "infrastructure as code", "iac", "hcl", "pulumi"],
    "cicd": ["ci/cd", "cicd", "pipeline", "jenkins", "github actions", "gitlab ci", "circleci"],
    "security": [
        "security",
        "vulnerability",
        "pentest",
        "owasp",
        "auth",
        "authentication",
        "authorization",
        "encryption",
        "oauth",
        "jwt",
        "saml",
    ],
    "testing": [
        "test",
        "testing",
        "pytest",
        "jest",
        "mocha",
        "cypress",
        "playwright",
        "selenium",
        "tdd",
        "bdd",
        "unit test",
        "integration test",
    ],
    "frontend": [
        "frontend",
        "front-end",
        "ui",
        "ux",
        "css",
        "scss",
        "tailwind",
        "bootstrap",
        "material",
        "responsive",
    ],
    "backend": ["backend", "back-end", "api", "rest", "graphql", "grpc", "websocket", "server"],
    "mobile": ["mobile", "android", "ios", "react native", "flutter", "xamarin"],
    "data": [
        "data",
        "etl",
        "pipeline",
        "warehouse",
        "analytics",
        "big data",
        "spark",
        "kafka",
        "airflow",
    ],
    "ml": [
        "ml",
        "machine learning",
        "ai",
        "artificial intelligence",
        "deep learning",
        "neural",
        "tensorflow",
        "pytorch",
        "sklearn",
    ],
    "devops": ["devops", "sre", "reliability", "monitoring", "logging", "alerting", "incident"],
    "cloud": ["cloud", "saas", "paas", "iaas", "serverless", "lambda", "functions"],
    "database": [
        "database",
        "db",
        "schema",
        "migration",
        "index",
        "query",
        "optimization",
        "normalization",
    ],
    "api": ["api", "rest", "graphql", "grpc", "openapi", "swagger", "endpoint"],
    "web": ["web", "website", "web app", "webapp", "http", "html", "css", "browser"],
    "blockchain": ["blockchain", "web3", "smart contract", "solidity", "ethereum", "defi", "nft"],
    "game": ["game", "gaming", "unity", "unreal", "godot", "2d", "3d", "graphics"],
    "iot": ["iot", "embedded", "raspberry pi", "arduino", "mqtt", "sensors"],
    "cli": ["cli", "command line", "terminal", "shell", "bash", "command-line"],
    "documentation": ["documentation", "docs", "readme", "technical writing", "api docs"],
    "performance": ["performance", "optimization", "profiling", "benchmark", "caching", "cdn"],
    "architecture": [
        "architecture",
        "design pattern",
        "microservices",
        "monolith",
        "distributed",
        "system design",
    ],
}

# ============================================================================
# TASK TYPE KEYWORDS
# ============================================================================

TASK_TYPE_KEYWORDS: dict[str, list[str]] = {
    "create": [
        "create",
        "build",
        "write",
        "implement",
        "develop",
        "generate",
        "make",
        "scaffold",
        "setup",
        "initialize",
    ],
    "fix": [
        "fix",
        "bug",
        "error",
        "broken",
        "issue",
        "problem",
        "debug",
        "crash",
        "exception",
        "fail",
    ],
    "refactor": [
        "refactor",
        "restructure",
        "reorganize",
        "clean",
        "improve",
        "optimize",
        "simplify",
        "extract",
    ],
    "review": ["review", "audit", "check", "analyze", "inspect", "evaluate", "assess", "critique"],
    "test": ["test", "testing", "spec", "assert", "mock", "stub", "coverage", "qa", "quality"],
    "deploy": [
        "deploy",
        "deployment",
        "release",
        "publish",
        "ship",
        "ci/cd",
        "pipeline",
        "containerize",
    ],
    "document": ["document", "documentation", "readme", "docs", "comment", "annotate", "explain"],
    "design": ["design", "architecture", "structure", "layout", "wireframe", "mockup", "prototype"],
    "debug": ["debug", "trace", "log", "investigate", "diagnose", "profile", "traceback"],
    "secure": ["security", "vulnerability", "audit", "hardening", "encrypt", "auth", "permission"],
    "optimize": [
        "optimize",
        "performance",
        "speed",
        "fast",
        "efficient",
        "cache",
        "lazy",
        "parallel",
    ],
    "integrate": ["integrate", "integration", "connect", "api", "webhook", "sync", "bridge"],
}


@dataclass
class AgentScore:
    """Score for a candidate agent."""

    agent_name: str
    skill_score: float = 0.0
    category_score: float = 0.0
    task_type_score: float = 0.0
    project_score: float = 0.0
    total_score: float = 0.0
    reasons: list[str] = field(default_factory=list)


class SmartRouter:
    """Intelligent agent router that selects the best agent(s) for a task."""

    def __init__(self) -> None:
        self._agents: dict[str, Any] = {}
        self._skill_index: dict[str, set[str]] = defaultdict(set)  # skill -> agent names
        self._category_index: dict[str, set[str]] = defaultdict(set)  # category -> agent names
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Lazy-load agent registry."""
        if self._loaded:
            return
        try:
            from sago.agents.registry import AGENTS

            self._agents = AGENTS
            for name, agent in AGENTS.items():
                for skill in agent.skills:
                    self._skill_index[skill.lower()].add(name)
                self._category_index[agent.category.lower()].add(name)
            self._loaded = True
        except Exception as e:
            logger.warning(f"Failed to load agent registry: {e}")

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into lowercase words, filtering short tokens."""
        return [w for w in re.split(r"[\s\-_/,;.()]+", text.lower()) if len(w) > 2]

    def _expand_synonyms(self, tokens: list[str]) -> list[str]:
        """Expand tokens using synonym map."""
        expanded = list(tokens)
        for token in tokens:
            for key, synonyms in SYNONYM_MAP.items():
                if token in synonyms and key not in expanded:
                    expanded.append(key)
        return expanded

    def _score_skills(self, task_tokens: list[str], agent_name: str) -> tuple[float, list[str]]:
        """Score agent based on skill tag matching."""
        agent = self._agents.get(agent_name)
        if not agent:
            return 0.0, []

        score = 0.0
        reasons = []
        agent_skills_lower = [s.lower() for s in agent.skills]
        expanded_tokens = self._expand_synonyms(task_tokens)

        for token in expanded_tokens:
            for skill in agent_skills_lower:
                if token == skill:
                    score += 2.0
                    reasons.append(f"exact skill match: {skill}")
                elif token in skill or skill in token:
                    score += 1.0
                    reasons.append(f"partial skill match: {token}~{skill}")

        # Bonus for matching multiple skills
        matched_skills = sum(
            1 for t in expanded_tokens if any(t in s or s in t for s in agent_skills_lower)
        )
        if matched_skills >= 3:
            score *= 1.5
            reasons.append(f"multi-skill bonus ({matched_skills} skills)")

        return min(score, 10.0), reasons[:3]

    def _score_category(self, task_tokens: list[str], agent_name: str) -> tuple[float, list[str]]:
        """Score agent based on category relevance."""
        agent = self._agents.get(agent_name)
        if not agent:
            return 0.0, []

        score = 0.0
        reasons = []
        category = agent.category.lower()

        # Direct category keyword matches
        category_keywords = {
            "language-specific": [
                "python",
                "java",
                "go",
                "rust",
                "c++",
                "ruby",
                "php",
                "swift",
                "kotlin",
                "dart",
            ],
            "frontend-frameworks": ["react", "vue", "angular", "css", "ui", "frontend"],
            "data-intelligence": ["data", "ml", "ai", "analytics", "etl", "pipeline"],
            "infrastructure-ops": ["devops", "docker", "kubernetes", "ci/cd", "deploy"],
            "database-specialists": ["database", "sql", "schema", "migration", "query"],
            "testing-quality": ["test", "qa", "quality", "coverage", "automation"],
            "cloud-infra-architecture": ["aws", "azure", "gcp", "cloud", "terraform"],
            "specialized-engineering": ["security", "performance", "blockchain", "iot", "mobile"],
        }

        for cat, keywords in category_keywords.items():
            if cat in category:
                for kw in keywords:
                    if kw in task_tokens:
                        score += 1.5
                        reasons.append(f"category match: {cat} + {kw}")

        return min(score, 5.0), reasons[:2]

    def _score_task_type(self, task_tokens: list[str], agent_name: str) -> tuple[float, list[str]]:
        """Score agent based on task type alignment."""
        score = 0.0
        reasons = []

        # Detect task type
        task_type = "create"  # default
        best_type_score = 0
        for ttype, keywords in TASK_TYPE_KEYWORDS.items():
            type_score = sum(1 for kw in keywords if kw in task_tokens)
            if type_score > best_type_score:
                best_type_score = type_score
                task_type = ttype

        # Map task types to agent preferences
        type_agent_map = {
            "create": ["engineer", "developer", "builder"],
            "fix": ["debugger", "engineer", "fixer"],
            "review": ["reviewer", "auditor", "critic"],
            "test": ["qa", "tester", "automation"],
            "deploy": ["devops", "sre", "cloud"],
            "design": ["architect", "designer", "planner"],
            "document": ["writer", "documenter", "technical-writer"],
            "secure": ["security", "appsec", "pentester"],
            "optimize": ["performance", "engineer", "optimizer"],
        }

        preferred_roles = type_agent_map.get(task_type, [])
        agent = self._agents.get(agent_name)
        if agent:
            agent_role_lower = agent.role.lower()
            agent_name_lower = agent.name.lower()
            for pref in preferred_roles:
                if pref in agent_role_lower or pref in agent_name_lower:
                    score += 2.0
                    reasons.append(f"task type match: {task_type} -> {pref}")
                    break

        return min(score, 5.0), reasons[:2]

    def _score_project_context(
        self, task_tokens: list[str], agent_name: str
    ) -> tuple[float, list[str]]:
        """Score agent based on project context from config."""
        score = 0.0
        reasons = []

        try:
            from sago.config.loader import get_config

            config = get_config()
            project = getattr(config, "project", None)
            if project:
                languages = getattr(project, "languages", []) or []
                frameworks = getattr(project, "frameworks", []) or []
                for lang in languages:
                    if lang.lower() in task_tokens:
                        agent = self._agents.get(agent_name)
                        if agent:
                            agent_text = (
                                f"{agent.name} {agent.role} {' '.join(agent.skills)}".lower()
                            )
                            if lang.lower() in agent_text:
                                score += 1.0
                                reasons.append(f"project lang: {lang}")
                for fw in frameworks:
                    if fw.lower() in task_tokens:
                        agent = self._agents.get(agent_name)
                        if agent:
                            agent_text = (
                                f"{agent.name} {agent.role} {' '.join(agent.skills)}".lower()
                            )
                            if fw.lower() in agent_text:
                                score += 0.5
                                reasons.append(f"project fw: {fw}")
        except Exception:
            pass

        return min(score, 3.0), reasons[:2]

    def score_agent(self, task: str, agent_name: str) -> AgentScore:
        """Score a single agent against a task."""
        self._ensure_loaded()
        task_tokens = self._tokenize(task)

        skill_score, skill_reasons = self._score_skills(task_tokens, agent_name)
        cat_score, cat_reasons = self._score_category(task_tokens, agent_name)
        type_score, type_reasons = self._score_task_type(task_tokens, agent_name)
        proj_score, proj_reasons = self._score_project_context(task_tokens, agent_name)

        total = skill_score + cat_score + type_score + proj_score
        all_reasons = skill_reasons + cat_reasons + type_reasons + proj_reasons

        return AgentScore(
            agent_name=agent_name,
            skill_score=skill_score,
            category_score=cat_score,
            task_type_score=type_score,
            project_score=proj_score,
            total_score=total,
            reasons=all_reasons,
        )

    def route(self, task: str, top_n: int = 3, min_score: float = 1.0) -> list[AgentScore]:
        """Route a task to the best agent(s).

        Args:
            task: The task description.
            top_n: Number of top agents to return.
            min_score: Minimum score threshold.

        Returns:
            List of AgentScore objects, sorted by total_score descending.
        """
        self._ensure_loaded()

        if not self._agents:
            logger.warning("No agents loaded, cannot route")
            return []

        # Score all agents
        scores = []
        for agent_name in self._agents:
            score = self.score_agent(task, agent_name)
            if score.total_score >= min_score:
                scores.append(score)

        # Sort by total score descending
        scores.sort(key=lambda s: s.total_score, reverse=True)

        return scores[:top_n]

    def route_single(self, task: str) -> str:
        """Route a task to the single best agent name.

        Returns agent name string, or 'software-engineer' as fallback.
        """
        scores = self.route(task, top_n=1, min_score=0.5)
        if scores:
            return scores[0].agent_name
        return "software-engineer"

    def route_for_chain(self, task: str, max_agents: int = 4) -> list[str]:
        """Route a task to a chain of agents that should collaborate.

        Returns list of agent names in execution order.
        """
        self._ensure_loaded()
        task_tokens = self._tokenize(task)
        task_lower = task.lower()

        # Detect if task explicitly mentions multiple languages/domains
        detected_domains = []
        domain_patterns = {
            "python": ["python", ".py"],
            "java": ["java", ".java"],
            "go": ["golang", "go ", ".go"],
            "rust": ["rust", ".rs"],
            "frontend": ["frontend", "ui", "react", "vue", "css"],
            "backend": ["backend", "api", "server", "rest"],
            "database": ["database", "sql", "schema", "migration"],
            "devops": ["devops", "docker", "kubernetes", "ci/cd", "deploy"],
            "security": ["security", "auth", "vulnerability"],
            "test": ["test", "testing", "qa"],
            "mobile": ["mobile", "android", "ios", "flutter"],
        }

        for domain, patterns in domain_patterns.items():
            if any(p in task_lower for p in patterns):
                detected_domains.append(domain)

        # If multiple domains detected, create a chain
        if len(detected_domains) > 1:
            chain = []
            for domain in detected_domains[:max_agents]:
                scores = self.route(f"{task} {domain}", top_n=1, min_score=0.5)
                if scores and scores[0].agent_name not in chain:
                    chain.append(scores[0].agent_name)
            return chain

        # Single domain — route to best agent + optional reviewer
        scores = self.route(task, top_n=2, min_score=1.0)
        chain = [s.agent_name for s in scores]

        # Add reviewer if task is complex (many words, multiple verbs)
        word_count = len(task_tokens)
        verb_count = sum(
            1 for t in task_tokens if t in ["create", "build", "fix", "refactor", "test", "deploy"]
        )
        if word_count > 15 and verb_count > 1 and "reviewer" not in chain:
            chain.append("code-reviewer")

        return chain[:max_agents]


# Global router instance
_router: SmartRouter | None = None


def get_router() -> SmartRouter:
    """Get or create the global smart router."""
    global _router
    if _router is None:
        _router = SmartRouter()
    return _router


def route_task(task: str, top_n: int = 3) -> list[AgentScore]:
    """Convenience function to route a task."""
    return get_router().route(task, top_n=top_n)


def route_single(task: str) -> str:
    """Convenience function to get the best single agent."""
    return get_router().route_single(task)


def route_for_chain(task: str, max_agents: int = 4) -> list[str]:
    """Convenience function to get a chain of agents."""
    return get_router().route_for_chain(task, max_agents=max_agents)
