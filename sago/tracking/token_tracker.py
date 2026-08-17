"""Token Usage Tracker

Tracks token usage across all LLM providers with cost estimation,
rate limiting, and usage analytics.
"""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sago.utils.errors import log_error


@dataclass
class TokenUsage:
    """Token usage for a single request."""

    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    timestamp: float = field(default_factory=time.time)
    cached: bool = False
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "timestamp": self.timestamp,
            "cached": self.cached,
            "latency_ms": self.latency_ms,
            "cost_usd": self.cost_usd,
            "metadata": self.metadata,
        }


@dataclass
class UsageSummary:
    """Aggregated usage summary."""

    total_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    by_provider: dict[str, dict[str, Any]] = field(default_factory=dict)
    by_model: dict[str, dict[str, Any]] = field(default_factory=dict)
    cache_hits: int = 0
    cache_misses: int = 0
    avg_latency_ms: float = 0.0
    waste_summary: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        return (self.cache_hits / total * 100) if total > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "total_tokens": self.total_tokens,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate_percent": round(self.cache_hit_rate, 2),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "by_provider": self.by_provider,
            "by_model": self.by_model,
            "waste_summary": self.waste_summary,
        }


@dataclass
class TokenWaste:
    """A single token waste event."""

    reason: str  # "empty_args", "tool_error", "circular_call", "rejected", "quality_fail"
    tokens_wasted: int
    tool_name: str
    timestamp: float = field(default_factory=time.time)
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "tokens_wasted": self.tokens_wasted,
            "tool_name": self.tool_name,
            "timestamp": self.timestamp,
            "details": self.details,
        }


# Cost per 1K tokens (input/output) by provider/model
COST_TABLE: dict[str, dict[str, tuple[float, float]]] = {
    "gemini": {
        "gemini-2.0-flash": (0.000075, 0.0003),
        "gemini-2.0-flash-001": (0.000075, 0.0003),
        "gemini-2.5-flash": (0.00015, 0.0006),
        "gemini-2.5-pro": (0.00125, 0.005),
        "gemini-1.5-pro": (0.00125, 0.005),
        "gemini-1.5-flash": (0.000075, 0.0003),
    },
    "openai": {
        "gpt-4o": (0.0025, 0.01),
        "gpt-4o-mini": (0.00015, 0.0006),
        "gpt-4-turbo": (0.01, 0.03),
        "gpt-3.5-turbo": (0.0005, 0.0015),
        "o1": (0.015, 0.06),
        "o1-mini": (0.003, 0.012),
        "o3": (0.01, 0.04),
        "o3-mini": (0.0011, 0.0044),
    },
    "claude": {
        "claude-sonnet-4-20250514": (0.003, 0.015),
        "claude-3-5-sonnet-20241022": (0.003, 0.015),
        "claude-3-5-sonnet": (0.003, 0.015),
        "claude-3-5-haiku-20241022": (0.0008, 0.004),
        "claude-3-haiku": (0.00025, 0.00125),
        "claude-3-opus": (0.015, 0.075),
        "claude-3-sonnet": (0.003, 0.015),
    },
    "deepseek": {
        "deepseek-chat": (0.00014, 0.00028),
        "deepseek-reasoner": (0.00055, 0.00219),
    },
    "openrouter": {
        "default": (0.001, 0.003),
    },
    "ollama": {
        "default": (0.0, 0.0),
    },
}


class TokenTracker:
    """Tracks token usage across all providers."""

    def __init__(self, persist_path: Path | None = None) -> None:
        self.persist_path = persist_path
        self._usages: list[TokenUsage] = []
        self._waste_log: list[TokenWaste] = []
        self._daily_usage: dict[str, dict[str, float]] = defaultdict(
            lambda: {"requests": 0, "tokens": 0, "cost": 0.0}
        )

        # Rate limiting
        self._rate_limits: dict[str, list[float]] = defaultdict(list)
        self._limits: dict[str, tuple[int, float]] = {
            "gemini": (60, 60.0),  # 60 requests per minute
            "openai": (60, 60.0),
            "claude": (60, 60.0),
            "openrouter": (200, 60.0),
        }

        # Load persisted data
        if persist_path and persist_path.exists():
            self._load()

    def record(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached: bool = False,
        latency_ms: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> TokenUsage:
        """Record token usage."""
        # Calculate cost
        cost = self._calculate_cost(provider, model, input_tokens, output_tokens)

        usage = TokenUsage(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached=cached,
            latency_ms=latency_ms,
            cost_usd=cost,
            metadata=metadata or {},
        )

        self._usages.append(usage)
        if len(self._usages) > 10000:
            self._usages = self._usages[-10000:]

        # Update daily stats
        day = time.strftime("%Y-%m-%d")
        self._daily_usage[day]["requests"] += 1
        self._daily_usage[day]["tokens"] += usage.total_tokens
        self._daily_usage[day]["cost"] += cost

        return usage

    def record_waste(
        self,
        reason: str,
        tokens: int,
        tool: str,
        details: str = "",
    ) -> TokenWaste:
        """Record a token waste event (failed tool call, rejected args, etc.)."""
        waste = TokenWaste(
            reason=reason,
            tokens_wasted=tokens,
            tool_name=tool,
            details=details,
        )
        self._waste_log.append(waste)
        if len(self._waste_log) > 5000:
            self._waste_log = self._waste_log[-5000:]
        return waste

    def get_waste_summary(self) -> dict[str, Any]:
        """Get summary of token waste across all reasons."""
        if not self._waste_log:
            return {"total_wasted": 0, "by_reason": {}, "by_tool": {}, "count": 0}
        by_reason: dict[str, int] = defaultdict(int)
        by_tool: dict[str, int] = defaultdict(int)
        for w in self._waste_log:
            by_reason[w.reason] += w.tokens_wasted
            by_tool[w.tool_name] += w.tokens_wasted
        return {
            "total_wasted": sum(w.tokens_wasted for w in self._waste_log),
            "count": len(self._waste_log),
            "by_reason": dict(by_reason),
            "by_tool": dict(by_tool),
        }

    def check_rate_limit(self, provider: str) -> tuple[bool, float]:
        """Check if rate limit allows another request.

        Returns:
            Tuple of (allowed, wait_seconds)
        """
        if provider not in self._limits:
            return True, 0.0

        limit, window = self._limits[provider]
        now = time.time()

        # Clean old entries
        self._rate_limits[provider] = [t for t in self._rate_limits[provider] if now - t < window]

        if len(self._rate_limits[provider]) >= limit:
            oldest = self._rate_limits[provider][0]
            wait = window - (now - oldest)
            return False, max(0, wait)

        self._rate_limits[provider].append(now)
        return True, 0.0

    def get_summary(
        self,
        time_range: str | None = None,
    ) -> UsageSummary:
        """Get usage summary."""
        usages = self._usages

        if time_range:
            usages = self._filter_by_time(usages, time_range)

        summary = UsageSummary()

        # Waste summary (always include, even if no LLM usages)
        summary.waste_summary = self.get_waste_summary()

        if not usages:
            return summary

        summary = UsageSummary()
        summary.total_requests = len(usages)
        summary.total_input_tokens = sum(u.input_tokens for u in usages)
        summary.total_output_tokens = sum(u.output_tokens for u in usages)
        summary.total_cost_usd = sum(u.cost_usd for u in usages)
        summary.cache_hits = sum(1 for u in usages if u.cached)
        summary.cache_misses = sum(1 for u in usages if not u.cached)

        latencies = [u.latency_ms for u in usages if u.latency_ms > 0]
        summary.avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0.0

        # By provider
        for usage in usages:
            if usage.provider not in summary.by_provider:
                summary.by_provider[usage.provider] = {
                    "requests": 0,
                    "tokens": 0,
                    "cost": 0.0,
                }
            p = summary.by_provider[usage.provider]
            p["requests"] += 1
            p["tokens"] += usage.total_tokens
            p["cost"] += usage.cost_usd

        # By model
        for usage in usages:
            key = f"{usage.provider}/{usage.model}"
            if key not in summary.by_model:
                summary.by_model[key] = {
                    "requests": 0,
                    "tokens": 0,
                    "cost": 0.0,
                }
            m = summary.by_model[key]
            m["requests"] += 1
            m["tokens"] += usage.total_tokens
            m["cost"] += usage.cost_usd

        # Waste summary
        summary.waste_summary = self.get_waste_summary()

        return summary

    def get_daily_usage(self) -> dict[str, dict[str, Any]]:
        """Get daily usage breakdown."""
        return dict(self._daily_usage)

    def get_recent(self, count: int = 10) -> list[dict[str, Any]]:
        """Get recent token usages."""
        return [u.to_dict() for u in self._usages[-count:]]

    def get_for_session(self, session_id: str) -> list[dict[str, Any]]:
        """Get token usages for a specific session (filtered by metadata)."""
        return [u.to_dict() for u in self._usages if u.metadata.get("session_id") == session_id]

    def _calculate_cost(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Calculate cost in USD."""
        provider_costs = COST_TABLE.get(provider, {})
        costs = provider_costs.get(model, provider_costs.get("default", (0.001, 0.003)))

        input_cost = (input_tokens / 1000) * costs[0]
        output_cost = (output_tokens / 1000) * costs[1]

        return input_cost + output_cost

    def _filter_by_time(
        self,
        usages: list[TokenUsage],
        time_range: str,
    ) -> list[TokenUsage]:
        """Filter usages by time range."""
        now = time.time()

        range_seconds: dict[str, float] = {
            "1h": 3600,
            "24h": 86400,
            "7d": 604800,
            "30d": 2592000,
        }

        seconds = range_seconds.get(time_range, 86400)
        cutoff = now - seconds

        return [u for u in usages if u.timestamp >= cutoff]

    def _load(self) -> None:
        """Load usage data from disk."""
        try:
            if self.persist_path and self.persist_path.exists():
                data = json.loads(self.persist_path.read_text())
                import dataclasses

                field_names = {f.name for f in dataclasses.fields(TokenUsage)}
                for usage_data in data.get("usages", []):
                    filtered = {k: v for k, v in usage_data.items() if k in field_names}
                    usage = TokenUsage(**filtered)
                    self._usages.append(usage)
                self._daily_usage = defaultdict(
                    lambda: {"requests": 0, "tokens": 0, "cost": 0.0},
                    data.get("daily", {}),
                )
        except Exception as e:
            log_error("Failed to load token usage data", e)

    def save(self) -> None:
        """Persist usage data to disk."""
        if not self.persist_path:
            return

        # Keep only last 10000 entries
        if len(self._usages) > 10000:
            self._usages = self._usages[-10000:]

        data = {
            "usages": [u.to_dict() for u in self._usages],
            "daily": dict(self._daily_usage),
        }

        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        self.persist_path.write_text(json.dumps(data, default=str))


# Global tracker instance
_global_tracker: TokenTracker | None = None
_tracker_lock = threading.Lock()


def get_token_tracker(persist: bool = True) -> TokenTracker:
    """Get or create the global token tracker."""
    global _global_tracker
    if _global_tracker is None:
        with _tracker_lock:
            if _global_tracker is None:
                from sago.paths import get_sago_home

                persist_path = get_sago_home() / "token_usage.json" if persist else None
                _global_tracker = TokenTracker(persist_path=persist_path)
    return _global_tracker
