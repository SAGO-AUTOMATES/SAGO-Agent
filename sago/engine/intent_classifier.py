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
            "hey",
            "thanks",
            "thank you",
            "who are you",
            "how are you",
            "tell me a joke",
            "more joke",
            "laugh",
        )

        code_intent_words = (
            "file",
            "files",
            "code",
            "repo",
            "function",
            "class",
            "test",
            "tests",
            "build",
            "script",
            "directory",
            "folder",
            "git",
            "import",
            "database",
            "sql",
        )

        # Detect conversational requests (jokes, banter, greetings)
        has_chat = any(
            re.search(r"\b" + re.escape(w) + r"\b", task_lower) for w in chat_words
        ) or bool(re.search(r"^\d+(?:-\d+)?\s+more", task_lower))
        has_code = any(
            re.search(r"\b" + re.escape(w) + r"\b", task_lower) for w in code_intent_words
        )

        if has_chat and not has_code:
            return IntentClassification(
                task_type="chat",
                needs_tools=False,
                confidence=0.92,
                suggested_agent="general-assistant",
                rationale="Conversational banter / joke intent",
                source="heuristic",
            )

        if any(
            re.search(r"\b" + re.escape(w) + r"\b", task_lower)
            for w in ("fix", "debug", "bug", "error", "broken", "issue", "resolve")
        ):
            return IntentClassification(
                task_type="fix",
                needs_tools=True,
                confidence=0.90,
                suggested_agent="debugger",
                rationale="Bug fixing and error diagnosis",
                source="heuristic",
            )

        if any(
            re.search(r"\b" + re.escape(w) + r"\b", task_lower)
            for w in ("test", "pytest", "unit test", "integration test", "coverage")
        ):
            return IntentClassification(
                task_type="test",
                needs_tools=True,
                confidence=0.90,
                suggested_agent="qa-engineer",
                rationale="Testing suite execution and validation",
                source="heuristic",
            )

        if any(
            re.search(r"\b" + re.escape(w) + r"\b", task_lower)
            for w in ("docker", "k8s", "kubernetes", "deploy", "ci/cd", "pipeline")
        ):
            return IntentClassification(
                task_type="devops",
                needs_tools=True,
                confidence=0.90,
                suggested_agent="devops-engineer",
                rationale="Infrastructure and container operations",
                source="heuristic",
            )

        if any(
            re.search(r"\b" + re.escape(w) + r"\b", task_lower)
            for w in ("explain", "analyze", "describe", "review", "search", "what is", "how does")
        ):
            return IntentClassification(
                task_type="analyze",
                needs_tools=True,
                confidence=0.85,
                suggested_agent="code-reviewer",
                rationale="Code review and architecture analysis",
                source="heuristic",
            )

        return IntentClassification(
            task_type="create",
            needs_tools=True,
            confidence=0.80,
            suggested_agent="python-engineer",
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
