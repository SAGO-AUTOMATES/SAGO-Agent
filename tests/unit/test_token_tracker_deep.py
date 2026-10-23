"""Comprehensive tests for sago.tracking.token_tracker."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from sago.tracking.token_tracker import (
    COST_TABLE,
    TokenTracker,
    TokenUsage,
    TokenWaste,
    UsageSummary,
    get_token_tracker,
)


class TestTokenUsage:
    def test_total_tokens(self) -> None:
        u = TokenUsage(provider="openai", model="gpt-4o", input_tokens=100, output_tokens=50)
        assert u.total_tokens == 150

    def test_to_dict(self) -> None:
        u = TokenUsage(
            provider="gemini",
            model="gemini-2.5-flash",
            input_tokens=200,
            output_tokens=80,
            cached=True,
            latency_ms=230.5,
            cost_usd=0.002,
            metadata={"session_id": "s1"},
        )
        d = u.to_dict()
        assert d["provider"] == "gemini"
        assert d["total_tokens"] == 280
        assert d["cached"] is True
        assert d["latency_ms"] == 230.5
        assert d["metadata"]["session_id"] == "s1"

    def test_defaults(self) -> None:
        u = TokenUsage(provider="claude", model="claude-3-haiku", input_tokens=10, output_tokens=20)
        assert u.cached is False
        assert u.latency_ms == 0.0
        assert u.cost_usd == 0.0
        assert u.metadata == {}


class TestUsageSummary:
    def test_total_tokens(self) -> None:
        s = UsageSummary(total_input_tokens=300, total_output_tokens=150)
        assert s.total_tokens == 450

    def test_cache_hit_rate_zero_total(self) -> None:
        s = UsageSummary()
        assert s.cache_hit_rate == 0.0

    def test_cache_hit_rate_nonzero(self) -> None:
        s = UsageSummary(cache_hits=3, cache_misses=1)
        assert s.cache_hit_rate == 75.0

    def test_to_dict(self) -> None:
        s = UsageSummary(
            total_requests=5, total_input_tokens=1000, total_output_tokens=500, total_cost_usd=0.01
        )
        d = s.to_dict()
        assert d["total_requests"] == 5
        assert d["total_tokens"] == 1500
        assert d["total_cost_usd"] == pytest.approx(0.01, rel=1e-5)


class TestTokenWaste:
    def test_to_dict(self) -> None:
        w = TokenWaste(
            reason="tool_error", tokens_wasted=150, tool_name="read_file", details="file not found"
        )
        d = w.to_dict()
        assert d["reason"] == "tool_error"
        assert d["tokens_wasted"] == 150
        assert d["tool_name"] == "read_file"
        assert d["details"] == "file not found"


class TestCostTable:
    def test_providers_present(self) -> None:
        for provider in ("gemini", "openai", "claude", "deepseek", "openrouter", "ollama"):
            assert provider in COST_TABLE

    def test_model_cost_structure(self) -> None:
        gemini_costs = COST_TABLE["gemini"]["gemini-2.5-flash"]
        assert len(gemini_costs) == 2
        assert all(isinstance(c, float) for c in gemini_costs)


class TestTokenTracker:
    def test_record_usage(self) -> None:
        tracker = TokenTracker()
        usage = tracker.record("openai", "gpt-4o", 1000, 500, latency_ms=250.0)
        assert isinstance(usage, TokenUsage)
        assert usage.input_tokens == 1000
        assert usage.output_tokens == 500
        assert usage.cost_usd > 0
        assert len(tracker._usages) == 1

    def test_record_with_metadata(self) -> None:
        tracker = TokenTracker()
        tracker.record(
            "gemini", "gemini-2.5-flash", 100, 50, cached=True, metadata={"session_id": "sess1"}
        )
        assert tracker._usages[0].cached is True
        assert tracker._usages[0].metadata["session_id"] == "sess1"

    def test_record_trims_at_10000(self) -> None:
        tracker = TokenTracker()
        # Add 10001 records
        for _ in range(10001):
            tracker.record("openai", "gpt-4o-mini", 10, 10)
        assert len(tracker._usages) == 10000

    def test_record_updates_daily_usage(self) -> None:
        tracker = TokenTracker()
        tracker.record("claude", "claude-3-haiku", 50, 25)
        day = time.strftime("%Y-%m-%d")
        assert tracker._daily_usage[day]["requests"] == 1
        assert tracker._daily_usage[day]["tokens"] == 75

    def test_record_waste(self) -> None:
        tracker = TokenTracker()
        waste = tracker.record_waste("empty_args", 200, "execute_shell", details="no command")
        assert isinstance(waste, TokenWaste)
        assert waste.reason == "empty_args"
        assert len(tracker._waste_log) == 1

    def test_record_waste_trims_at_5000(self) -> None:
        tracker = TokenTracker()
        for _ in range(5001):
            tracker.record_waste("tool_error", 10, "some_tool")
        assert len(tracker._waste_log) == 5000

    def test_get_waste_summary_empty(self) -> None:
        tracker = TokenTracker()
        s = tracker.get_waste_summary()
        assert s["total_wasted"] == 0
        assert s["count"] == 0

    def test_get_waste_summary_populated(self) -> None:
        tracker = TokenTracker()
        tracker.record_waste("tool_error", 100, "read_file")
        tracker.record_waste("tool_error", 50, "write_file")
        tracker.record_waste("empty_args", 30, "read_file")
        s = tracker.get_waste_summary()
        assert s["total_wasted"] == 180
        assert s["by_reason"]["tool_error"] == 150
        assert s["by_tool"]["read_file"] == 130

    def test_check_rate_limit_unknown_provider(self) -> None:
        tracker = TokenTracker()
        allowed, wait = tracker.check_rate_limit("unknown_llm")
        assert allowed is True
        assert wait == 0.0

    def test_check_rate_limit_within_limit(self) -> None:
        tracker = TokenTracker()
        allowed, wait = tracker.check_rate_limit("gemini")
        assert allowed is True
        assert wait == 0.0

    def test_check_rate_limit_exhausted(self) -> None:
        tracker = TokenTracker()
        # Saturate the gemini limit (60 requests per minute)
        now = time.time()
        tracker._rate_limits["gemini"] = [now] * 60
        allowed, wait = tracker.check_rate_limit("gemini")
        assert allowed is False
        assert wait >= 0

    def test_get_summary_empty(self) -> None:
        tracker = TokenTracker()
        summary = tracker.get_summary()
        assert summary.total_requests == 0
        assert summary.total_tokens == 0

    def test_get_summary_populated(self) -> None:
        tracker = TokenTracker()
        tracker.record("openai", "gpt-4o", 1000, 500)
        tracker.record("openai", "gpt-4o", 500, 200)
        tracker.record("gemini", "gemini-2.5-flash", 300, 100, cached=True)
        summary = tracker.get_summary()
        assert summary.total_requests == 3
        assert summary.total_input_tokens == 1800
        assert summary.total_output_tokens == 800
        assert summary.cache_hits == 1
        assert summary.cache_misses == 2
        assert "openai" in summary.by_provider
        assert "gemini" in summary.by_provider
        assert "openai/gpt-4o" in summary.by_model

    def test_get_summary_time_filter(self) -> None:
        tracker = TokenTracker()
        # Add old record (25 hours ago)
        old = TokenUsage(
            provider="openai",
            model="gpt-4o",
            input_tokens=999,
            output_tokens=1,
            timestamp=time.time() - 90000,
        )
        tracker._usages.append(old)
        # Add fresh record
        tracker.record("gemini", "gemini-2.5-flash", 100, 50)
        summary = tracker.get_summary(time_range="1h")
        assert summary.total_requests == 1  # Only the fresh one

    def test_get_daily_usage(self) -> None:
        tracker = TokenTracker()
        tracker.record("openai", "gpt-4o", 100, 50)
        daily = tracker.get_daily_usage()
        assert isinstance(daily, dict)
        assert len(daily) == 1

    def test_get_recent(self) -> None:
        tracker = TokenTracker()
        for i in range(15):
            tracker.record("openai", "gpt-4o", 10 * i, 5 * i)
        recent = tracker.get_recent(5)
        assert len(recent) == 5

    def test_get_for_session(self) -> None:
        tracker = TokenTracker()
        tracker.record("openai", "gpt-4o", 100, 50, metadata={"session_id": "sess_A"})
        tracker.record("openai", "gpt-4o", 200, 100, metadata={"session_id": "sess_B"})
        tracker.record("openai", "gpt-4o", 50, 25, metadata={"session_id": "sess_A"})
        results = tracker.get_for_session("sess_A")
        assert len(results) == 2

    def test_save_and_load(self, tmp_path: Path) -> None:
        persist_file = tmp_path / "token_usage.json"
        tracker = TokenTracker(persist_path=persist_file)
        tracker.record("gemini", "gemini-2.5-flash", 500, 250)
        tracker.record("claude", "claude-3-haiku", 100, 50)
        tracker.save()
        assert persist_file.exists()

        # Load into fresh tracker
        tracker2 = TokenTracker(persist_path=persist_file)
        assert len(tracker2._usages) == 2
        assert tracker2._usages[0].provider == "gemini"

    def test_save_no_persist_path(self) -> None:
        tracker = TokenTracker(persist_path=None)
        tracker.record("openai", "gpt-4o", 10, 5)
        # Should not raise
        tracker.save()

    def test_calculate_cost_known_model(self) -> None:
        tracker = TokenTracker()
        cost = tracker._calculate_cost("openai", "gpt-4o", 1000, 1000)
        # 1000/1000 * 0.0025 + 1000/1000 * 0.01 = 0.0125
        assert cost == pytest.approx(0.0125, rel=1e-5)

    def test_calculate_cost_unknown_model_uses_default(self) -> None:
        tracker = TokenTracker()
        cost = tracker._calculate_cost("openai", "some-unknown-model", 1000, 0)
        assert cost > 0

    def test_singleton_accessor(self) -> None:
        t1 = get_token_tracker(persist=False)
        t2 = get_token_tracker(persist=False)
        assert t1 is t2
