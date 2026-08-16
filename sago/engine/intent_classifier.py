"""Intent Classification Engine - Multi-Tiered Semantic Intent Detection with Fast-Path Caching.

Uses a high-speed micro-LLM intent classifier with in-memory LRU caching and resilient
heuristic fallback to accurately distinguish casual chat/jokes from code creation,
bug fixing, testing, and analysis.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from dataclasses import asdict, dataclass
from typing import Any

from sago.config.loader import get_config
from sago.llm.factory import create_provider

logger = logging.getLogger("sago.engine.intent_classifier")


@dataclass
class IntentClassification:
    """Classified user intent with metadata and routing hints."""

    task_type: str  # "chat", "fix", "create", "analyze", "test", "devops"
    needs_tools: bool
    confidence: float
    suggested_agent: str
    rationale: str = ""
    source: str = "llm"  # "cache", "llm", "heuristic"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IntentClassifier:
    """Multi-tiered intent classifier with micro-LLM and LRU cache."""

    VALID_TYPES = {"chat", "fix", "create", "analyze", "test", "devops"}

    def __init__(self, cache_size: int = 1024) -> None:
        self.cache_size = cache_size
        self._cache: dict[str, IntentClassification] = {}
        self._lock = threading.Lock()

    def _get_cache_key(self, prompt: str) -> str:
        norm = " ".join(prompt.lower().strip().split())
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]

    def classify(
        self,
        prompt: str,
        use_llm: bool = True,
        timeout: float = 1.2,
    ) -> IntentClassification:
        """Classify user intent using Cache -> Micro-LLM -> Heuristic."""
        if not prompt or not prompt.strip():
            return IntentClassification(
                task_type="chat",
                needs_tools=False,
                confidence=1.0,
                suggested_agent="general-assistant",
                rationale="Empty prompt",
                source="heuristic",
            )

        clean_prompt = prompt.strip()
        key = self._get_cache_key(clean_prompt)

        # 1. Tier 1: Check In-Memory Cache
        with self._lock:
            if key in self._cache:
                cached = self._cache[key]
                return IntentClassification(
                    task_type=cached.task_type,
                    needs_tools=cached.needs_tools,
                    confidence=cached.confidence,
                    suggested_agent=cached.suggested_agent,
                    rationale=cached.rationale,
                    source="cache",
                )

        # 2. Tier 2: Micro-LLM Intent Classification
        if use_llm:
            try:
                classification = self._call_micro_llm(clean_prompt, timeout=timeout)
                if classification:
                    with self._lock:
                        if len(self._cache) >= self.cache_size:
                            # Evict oldest item
                            self._cache.pop(next(iter(self._cache)))
                        self._cache[key] = classification
                    return classification
            except Exception as e:
                logger.debug("Micro-LLM intent classification skipped: %s", e)

        # 3. Tier 3: Resilient Heuristic Fallback
        fallback = self._classify_heuristic(clean_prompt)
        with self._lock:
            if len(self._cache) < self.cache_size:
                self._cache[key] = fallback
        return fallback

    def _call_micro_llm(self, prompt: str, timeout: float = 1.2) -> IntentClassification | None:
        """Call micro-LLM with single-line JSON constraint for sub-second intent classification."""
        try:
            cfg = get_config()
            llm_cfg = getattr(cfg, "llm", None)
            api_key = getattr(llm_cfg, "api_key", None) if llm_cfg else None

            # Skip remote network call if no real API key is configured
            if not api_key:
                return None

            provider_name = getattr(llm_cfg, "provider", "openrouter") or "openrouter"
            model = getattr(llm_cfg, "model", "openrouter/free") or "openrouter/free"

            provider = create_provider(
                provider_name,
                {
                    "api_key": api_key,
                    "model": model,
                    "max_tokens": 40,
                    "temperature": 0.0,
                },
            )

            system_prompt = (
                "You are an ultra-fast strict intent classifier for an engineering AI assistant. "
                "Classify the user's prompt into ONE category:\n"
                "- chat: Casual conversation, jokes, tell more jokes/pun/riddles, greetings, questions about you, non-code banter (needs_tools: false)\n"
                "- fix: Debugging, fixing bugs, resolving errors/exceptions, repairing broken code (needs_tools: true)\n"
                "- create: Writing new code, implementing new features, creating files, scaffolding (needs_tools: true)\n"
                "- analyze: Explaining code, reviewing files, searching codebase, understanding concepts (needs_tools: true)\n"
                "- test: Writing or running unit/integration tests, test suites, coverage (needs_tools: true)\n"
                "- devops: Docker, Kubernetes, CI/CD, deployment, bash/powershell scripts (needs_tools: true)\n\n"
                'Respond with ONLY a single raw JSON line: {"type": "<category>", "needs_tools": <bool>, "suggested_agent": "<agent_name>", "confidence": <float>}'
            )

            raw_text = provider.generate(prompt[:400], system_prompt=system_prompt)
            raw_text = str(raw_text).strip()
            # Extract JSON object
            m = re.search(r"\{.*\}", raw_text)
            if m:
                data = json.loads(m.group(0))
                ttype = str(data.get("type", "")).lower().strip()
                if ttype in self.VALID_TYPES:
                    return IntentClassification(
                        task_type=ttype,
                        needs_tools=bool(data.get("needs_tools", ttype != "chat")),
                        confidence=float(data.get("confidence", 0.95)),
                        suggested_agent=str(data.get("suggested_agent", "python-engineer")),
                        rationale="Classified via micro-LLM",
                        source="llm",
                    )
        except Exception as e:
            logger.debug("Micro-LLM call failed: %s", e)
        return None

    def _classify_heuristic(self, task: str) -> IntentClassification:
        """Enhanced regex and keyword boundary intent classification."""
        task_lower = task.lower().strip()

        chat_words = (
            "joke",
            "jokes",
            "funny",
            "pun",
            "puns",
            "riddle",
            "story",
            "poem",
            "hello",
            "hi",
            "hoi",
            "hey",
            "sup",
            "yo",
            "howdy",
            "greetings",
            "good morning",
            "good afternoon",
            "good evening",
            "thanks",
            "thank you",
            "who are you",
            "how are you",
            "what's up",
            "whats up",
            "weather",
            "forecast",
            "temperature",
            "today",
            "tell me a joke",
            "more joke",
            "laugh",
            "fact",
            "facts",
            "quote",
            "news",
        )

        code_intent_words = (
            "file",
            "files",
            "code",
            "repo",
            "repository",
            "function",
            "functions",
            "class",
            "classes",
            "test",
            "tests",
            "pytest",
            "build",
            "script",
            "scripts",
            "directory",
            "folder",
            "git",
            "import",
            "database",
            "sql",
            "endpoint",
            "api",
            "json",
            "yaml",
            "config",
            "variable",
            "compile",
            "refactor",
            "debug",
            "traceback",
            "npm",
            "pip",
            "cargo",
            "fix",
            "bug",
            "error",
            "exception",
            "issue",
            "patch",
            "broken",
            "crash",
            "leak",
            "create",
            "implement",
            "scaffold",
            "optimize",
            "lint",
            "typecheck",
            "deploy",
            "docker",
            "k8s",
            "kubernetes",
            "commit",
            "pr",
            "pull request",
            "branch",
            "benchmark",
            "profile",
            "session",
            "sessions",
            "manager",
            "service",
            "handler",
            "controller",
            "auth",
            "authentication",
            "router",
            "route",
            "model",
            "models",
            "schema",
            "schemas",
            "agent",
            "agents",
            "tool",
            "tools",
            "middleware",
            "state",
            "cache",
            "query",
            "module",
            "modules",
            "package",
            "packages",
            "component",
            "components",
            "ui",
            "tui",
            "cli",
            "client",
            "server",
            "worker",
            "thread",
            "process",
            "pipeline",
        )

        has_file_pattern = bool(
            re.search(
                r"\b[\w\-\./]+\.(?:py|js|ts|tsx|jsx|rs|go|c|cpp|h|java|kt|rb|php|html|css|json|yaml|yml|toml|sql|sh|md)\b",
                task_lower,
            )
        )

        chat_patterns = (
            r"\b(hello|hellos|helloo|hi|hii|hiii|hoi|heyy|heyyy|hey|heya|sup|yo|yoo|howdy|greetings|good\s+(?:morning|afternoon|evening|day)|thanks|thank\s+you|who\s+are\s+you|how\s+are\s+you|what\'?s\s+up|weather|forecast|temperature|joke|jokes|pun|riddle|story|poem)\b",
            r"(?:what|wehta|wat|wht)\s+(?:can|do)\s+(?:you|yiu|u)\s+(?:do|help|perform|show|tell)",
            r"\b(what\s+are\s+your\s+(?:capabilities|skills|tools|features|agents)|who\s+are\s+you|what\s+is\s+sago|help\s+me\s+understand\s+what\s+you\s+can\s+do|what\s+can\s+i\s+ask\s+you|what\s+can\s+you\s+do)\b",
        )

        # Detect conversational requests (weather, greetings, capabilities, jokes, general knowledge)
        has_chat = (
            any(re.search(p, task_lower) for p in chat_patterns)
            or any(re.search(r"\b" + re.escape(w) + r"\b", task_lower) for w in chat_words)
            or bool(re.search(r"^\d+(?:-\d+)?\s+more", task_lower))
        )

        has_code = has_file_pattern or any(
            re.search(r"\b" + re.escape(w) + r"\b", task_lower) for w in code_intent_words
        )

        # Fast-path for conversational greetings & capability questions without explicit coding commands
        if (
            has_chat
            and not has_file_pattern
            and not re.search(
                r"\b(pytest|docker|git\s+commit|git\s+push|refactor\s+code)\b", task_lower
            )
        ):
            return IntentClassification(
                task_type="chat",
                needs_tools=False,
                confidence=0.95,
                suggested_agent="general-assistant",
                rationale="Conversational greeting, pleasantries, or capability inquiry",
                source="heuristic",
            )

        from sago.agents.registry import resolve_specialist_agent

        resolved_agent = resolve_specialist_agent(task=task_lower)

        # 1. Testing & Quality Assurance (e.g. "why is pytest failing", "run unit tests")
        test_patterns = (
            r"\b(test|tests|pytest|unittest|integration\s+test|unit\s+test|coverage|e2e|mock|assert|assertions)\b",
            r"\b(why\s+is\s+(?:test|pytest|suite)\s+failing)\b",
        )
        if any(re.search(p, task_lower) for p in test_patterns):
            return IntentClassification(
                task_type="test",
                needs_tools=True,
                confidence=0.90,
                suggested_agent="qa-engineer",
                rationale="Testing suite execution and validation",
                source="heuristic",
            )

        # 2. Bug fixing & failure troubleshooting (e.g. "why is this not working", "it crashes", "why does this fail")
        troubleshoot_patterns = (
            r"\b(fix|debug|bug|bugs|error|errors|broken|issue|issues|resolve|patch|failing|failed|crash|crashes|crashing)\b",
            r"\b(why\s+(?:is\s+this\s+not\s+working|is\s+it\s+not\s+working|does\s+this\s+fail|does\s+it\s+fail|am\s+i\s+getting|is\s+it\s+broken))\b",
            r"\b(not\s+working|not\s+starting|won\'?t\s+start|infinite\s+loop|hanging|deadlock|segfault|traceback|exception)\b",
        )
        if any(re.search(p, task_lower) for p in troubleshoot_patterns):
            return IntentClassification(
                task_type="fix",
                needs_tools=True,
                confidence=0.92,
                suggested_agent="debugger"
                if resolved_agent in ("general-assistant", "python-engineer")
                else resolved_agent,
                rationale="Troubleshooting and error diagnosis",
                source="heuristic",
            )

        # 3. DevOps, Deployment, Docker & Environment Setup (e.g. "how do I run this", "deploy to docker")
        devops_patterns = (
            r"\b(docker|k8s|kubernetes|dockerfile|docker-compose|compose|deploy|deployment|ci/cd|pipeline|github\s+actions)\b",
            r"\b(how\s+(?:do\s+i\s+run\s+this|to\s+run\s+this|to\s+start|do\s+i\s+start|to\s+install|to\s+setup|to\s+deploy))\b",
            r"\b(provision|terraform|ansible|helm|ingress|nginx|env\s+vars|environment\s+setup)\b",
        )
        if any(re.search(p, task_lower) for p in devops_patterns):
            devops_target = (
                resolved_agent
                if resolved_agent
                in (
                    "azure-engineer",
                    "aws-engineer",
                    "gcp-engineer",
                    "docker-engineer",
                    "kubernetes-engineer",
                    "terraform-engineer",
                )
                else "devops-engineer"
            )
            return IntentClassification(
                task_type="devops",
                needs_tools=True,
                confidence=0.90,
                suggested_agent=devops_target,
                rationale="Infrastructure and deployment operations",
                source="heuristic",
            )

        # 4. Codebase Exploration, Architecture & Code Review (e.g. "projects", "what projects are in here", "how does X work", "compare files")
        analyze_patterns = (
            r"\b(projects?|project\s+structure|codebase|architecture|topology|overview|modules?|layout)\b",
            r"\b(what\s+(?:projects|files|modules|components|apis)\s+(?:are\s+in\s+here|exist|are\s+available))\b",
            r"\b(how\s+does\s+(?:[\w\-\s]+?)\s+work|where\s+is\s+(?:[\w\-\s]+?)\s+(?:defined|implemented|configured|used))\b",
            r"\b(explain|analyze|analysis|inspect|review|audit|trace|find\s+where|understand|search\s+for|compare|diff|difference)\b",
        )
        if any(re.search(p, task_lower) for p in analyze_patterns):
            return IntentClassification(
                task_type="analyze",
                needs_tools=True,
                confidence=0.88,
                suggested_agent="code-reviewer",
                rationale="Code review, exploration, and architecture analysis",
                source="heuristic",
            )

        # 5. Performance Optimization & Profiling (e.g. "this feels slow", "make it faster", "memory leak")
        optimize_patterns = (
            r"\b(optimize|optimization|performance|perf|slow|speed\s+up|make\s+it\s+faster|latency|throughput|bottleneck|profiling|profile)\b",
            r"\b(memory\s+leak|leak|high\s+cpu|memory\s+usage|cache|caching|reduce\s+allocations)\b",
        )
        if any(re.search(p, task_lower) for p in optimize_patterns):
            return IntentClassification(
                task_type="create",
                needs_tools=True,
                confidence=0.88,
                suggested_agent=resolved_agent,
                rationale="Performance profiling and optimization",
                source="heuristic",
            )

        # 6. Refactoring & Code Cleanup (e.g. "clean this up", "make this cleaner")
        refactor_patterns = (
            r"\b(clean\s+(?:this\s+up|up|the\s+code)|make\s+this\s+cleaner|tidy\s+up|refactor|restructure|reorganize|simplify|modularize|modernize|upgrade)\b",
        )
        if any(re.search(p, task_lower) for p in refactor_patterns):
            return IntentClassification(
                task_type="create",
                needs_tools=True,
                confidence=0.88,
                suggested_agent=resolved_agent,
                rationale="Code refactoring and modernization",
                source="heuristic",
            )

        # 7. General non-code questions & casual chat (only if no action patterns matched)
        is_general_qa = not has_code and bool(
            re.search(
                r"^(what|who|when|where|why|how|is|are|was|were|can you tell|tell me)\b",
                task_lower,
            )
        )

        if (has_chat or is_general_qa) and not has_code:
            return IntentClassification(
                task_type="chat",
                needs_tools=False,
                confidence=0.95,
                suggested_agent="general-assistant",
                rationale="Conversational / general QA intent",
                source="heuristic",
            )

        # Default fallback: feature creation & code implementation with resolved specialist
        return IntentClassification(
            task_type="create",
            needs_tools=True,
            confidence=0.80,
            suggested_agent=resolved_agent,
            rationale="Feature creation and code implementation",
            source="heuristic",
        )


_global_intent_classifier: IntentClassifier | None = None


def get_intent_classifier() -> IntentClassifier:
    """Singleton getter for the intent classifier."""
    global _global_intent_classifier
    if _global_intent_classifier is None:
        _global_intent_classifier = IntentClassifier()
    return _global_intent_classifier


def detect_task_type(task: str, use_llm: bool = True) -> str:
    """Convenience functional helper for task type detection."""
    return get_intent_classifier().classify(task, use_llm=use_llm).task_type
