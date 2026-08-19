"""Learning System - Remembers what worked/failed across sessions.

Stores patterns, successful approaches, and failure reasons
to help the agent grow smarter over time.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

from sago.paths import get_sago_home
from sago.utils.errors import log_error

logger = logging.getLogger("sago.learning")


class LearningStore:
    """Persistent store for learning from past sessions."""

    def __init__(self) -> None:
        self._path = get_sago_home() / "learning.json"
        self._lock = threading.Lock()
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if self._path.exists():
            try:
                logger.debug("Loading learning store from %s", self._path)
                return json.loads(self._path.read_text())
            except Exception as e:
                log_error("Failed to load learning store", e)
                logger.error("Failed to load learning store: %s", e)
        else:
            logger.debug("No existing learning store, using defaults")
        return {
            "successful_patterns": {},
            "failed_patterns": {},
            "tool_effectiveness": {},
            "language_patterns": {},
            "error_fixes": {},
        }

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._data, indent=2, default=str))
            logger.debug("Saved learning store to %s", self._path)
        except Exception as e:
            log_error("Failed to save learning store", e)
            logger.error("Failed to save learning store: %s", e)

    def record_success(self, task_type: str, tools_used: list[str], approach: str) -> None:
        """Record a successful approach for a task type."""
        with self._lock:
            logger.info("Recording success: task_type=%s, tools=%s", task_type, tools_used)
            if task_type not in self._data["successful_patterns"]:
                self._data["successful_patterns"][task_type] = []
            self._data["successful_patterns"][task_type].append(
                {
                    "tools": tools_used,
                    "approach": approach,
                    "timestamp": time.time(),
                }
            )
            # Keep only last 10 successes per type
            self._data["successful_patterns"][task_type] = self._data["successful_patterns"][
                task_type
            ][-10:]
            self._save()

    def record_failure(self, task_type: str, error: str, context: str = "") -> None:
        """Record a failure to learn from."""
        with self._lock:
            logger.info("Recording failure: task_type=%s, error=%s", task_type, error[:100])
            if task_type not in self._data["failed_patterns"]:
                self._data["failed_patterns"][task_type] = []
            self._data["failed_patterns"][task_type].append(
                {
                    "error": error[:500],
                    "context": context[:500],
                    "timestamp": time.time(),
                }
            )
            self._data["failed_patterns"][task_type] = self._data["failed_patterns"][task_type][
                -10:
            ]
            self._save()

    def record_error_fix(self, error_pattern: str, fix_approach: str) -> None:
        """Record how an error was fixed."""
        with self._lock:
            key = error_pattern[:100]
            logger.info("Recording error fix: pattern=%s", key)
            self._data["error_fixes"][key] = {
                "fix": fix_approach[:500],
                "timestamp": time.time(),
            }
            # Keep only last 50 error fixes
            if len(self._data["error_fixes"]) > 50:
                oldest = sorted(
                    self._data["error_fixes"].items(), key=lambda x: x[1].get("timestamp", 0)
                )[:10]
                for k, _ in oldest:
                    del self._data["error_fixes"][k]
            self._save()

    def record_tool_effectiveness(self, tool_name: str, success: bool) -> None:
        """Track tool effectiveness."""
        with self._lock:
            if tool_name not in self._data["tool_effectiveness"]:
                self._data["tool_effectiveness"][tool_name] = {"success": 0, "total": 0}
            self._data["tool_effectiveness"][tool_name]["total"] += 1
            if success:
                self._data["tool_effectiveness"][tool_name]["success"] += 1
            self._save()

    def record_language_pattern(self, language: str, pattern: str, details: str) -> None:
        """Record discovered language/project patterns."""
        with self._lock:
            if language not in self._data["language_patterns"]:
                self._data["language_patterns"][language] = []
            self._data["language_patterns"][language].append(
                {
                    "pattern": pattern,
                    "details": details[:500],
                    "timestamp": time.time(),
                }
            )
            self._data["language_patterns"][language] = self._data["language_patterns"][language][
                -5:
            ]
            self._save()

    def get_successful_approaches(self, task_type: str) -> list[dict]:
        """Get past successful approaches for a task type."""
        with self._lock:
            return list(self._data["successful_patterns"].get(task_type, []))

    def get_known_fixes(self, error: str) -> str | None:
        """Check if we've seen this error before and know how to fix it."""
        with self._lock:
            for key, fix_data in self._data["error_fixes"].items():
                if key.lower() in error.lower():
                    logger.info("Known fix found for error pattern: %s", key)
                    return fix_data["fix"]
            logger.debug("No known fix for error: %s", error[:100])
            return None

    def get_tool_stats(self) -> dict[str, dict]:
        """Get tool effectiveness stats."""
        with self._lock:
            stats = {}
            for tool, data in self._data["tool_effectiveness"].items():
                total = data["total"]
                success = data["success"]
                stats[tool] = {
                    "success_rate": success / total if total > 0 else 0,
                    "total_uses": total,
                }
            return stats

    def get_language_patterns(self, language: str) -> list[dict]:
        """Get discovered patterns for a language."""
        with self._lock:
            return list(self._data["language_patterns"].get(language, []))

    def suggest_approach(self, task_type: str, available_tools: list[str]) -> str | None:
        """Suggest an approach based on past successes."""
        successes = self.get_successful_approaches(task_type)
        if not successes:
            logger.debug("No past successes for task_type=%s", task_type)
            return None
        for success in reversed(successes):
            if any(t in available_tools for t in success["tools"]):
                logger.info(
                    "Suggested approach for task_type=%s: %s", task_type, success["approach"][:100]
                )
                return success["approach"]
        return None


# Global instance
_learning_store: LearningStore | None = None


def get_learning_store() -> LearningStore:
    """Get the global learning store."""
    global _learning_store
    if _learning_store is None:
        _learning_store = LearningStore()
    return _learning_store
