"""Tests for upper-tier (semantic summary + deep distillation) summarization.

Covers:
- Tier promotion / deterministic summarization produces the expected structure.
- SessionCompactor.build_context_window includes distilled (upper-tier) content.

All inputs are deterministic and use no real LLM.
"""

from __future__ import annotations

from sago.memory.compaction import HierarchicalMemoryPyramid, SessionCompactor


def _sample_pyramid() -> HierarchicalMemoryPyramid:
    pyramid = HierarchicalMemoryPyramid()
    pyramid.record_turn(
        "user",
        "Goal: Build a payments service with Stripe. "
        "We need idempotency and retries for reliability.",
    )
    pyramid.record_turn(
        "assistant",
        "We decided to use idempotency keys for safety. "
        "The retry queue will use exponential backoff.",
    )
    pyramid.record_file_mod("app/payments.py")
    pyramid.record_file_mod("app/stripe_client.py")
    pyramid.record_turn("user", "milestone: checkout flow integrated with the gateway.")
    return pyramid


def test_distill_produces_upper_tiers() -> None:
    pyramid = _sample_pyramid()
    assert pyramid.architectural_goals
    assert pyramid.architectural_decisions
    assert pyramid.milestone_history

    pyramid.distill()
    # Upper-tier summarization must be populated by the deterministic fallback.
    assert pyramid.semantic_summary, "semantic summary tier should be populated"
    assert pyramid.deep_distillation, "deep distillation tier should be populated"
    # Deep distillation should weave in architectural + file + milestone context.
    assert "payments service" in pyramid.deep_distillation


def test_assemble_includes_tier_3_and_4() -> None:
    pyramid = _sample_pyramid()
    context = pyramid.assemble_compact_pyramid(max_working_turns=0)
    joined = "\n".join(block["content"] for block in context)

    assert "[ARCHITECTURAL MEMORY PYRAMID - TIER 1]" in joined
    assert "[WORKING DELTA - TIER 2]" in joined
    assert "[SEMANTIC SUMMARY - TIER 3]" in joined
    assert "[DEEP DISTILLATION - TIER 4]" in joined
    # Existing structural expectations must remain intact.
    assert "payments service" in joined


def test_distill_is_deterministic_without_llm() -> None:
    a = _sample_pyramid()
    b = _sample_pyramid()
    a.distill()
    b.distill()
    assert a.semantic_summary == b.semantic_summary
    assert a.deep_distillation == b.deep_distillation


def test_custom_summarizer_hook_is_used() -> None:
    pyramid = _sample_pyramid()

    def fake_summarizer(text: str, kind: str) -> str:
        return f"[{kind}] summarized"

    pyramid.summarizer = fake_summarizer
    pyramid.distill()
    assert pyramid.semantic_summary == "[semantic] summarized"
    assert pyramid.deep_distillation == "[deep] summarized"


def test_record_turn_invalidates_cache() -> None:
    pyramid = _sample_pyramid()
    pyramid.distill()
    prior = pyramid.semantic_summary
    pyramid.record_turn("user", "We chose PostgreSQL for the ledger store.")
    assert pyramid.semantic_summary == ""
    assert pyramid.deep_distillation == ""
    pyramid.distill()
    assert pyramid.semantic_summary != prior


def test_build_context_window_includes_distilled_content() -> None:
    compactor = SessionCompactor(max_context_tokens=10_000)
    messages = [
        {
            "role": "user",
            "content": "Goal: Build a payments service with Stripe and idempotency keys.",
        },
        {
            "role": "assistant",
            "content": "We decided to use idempotency keys for safety and a retry queue.",
        },
    ]
    # Add filler to exceed the <=10 short-circuit branch so compaction runs.
    for i in range(12):
        messages.append({"role": "user", "content": f"step {i} " + "word " * 30})

    result = compactor.build_context_window(messages, max_tokens=10_000)
    joined = "\n".join(block.get("content", "") for block in result)

    assert "[ARCHITECTURAL MEMORY PYRAMID - TIER 1]" in joined
    assert "[DEEP DISTILLATION - TIER 4]" in joined
    assert "payments service" in joined
