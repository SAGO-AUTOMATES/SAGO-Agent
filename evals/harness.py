"""Evaluation harness for hallucination, tool-use, and code-intel benchmarks (additive)."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger("sago.evals.harness")


def load_benchmark_cases(cases_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Load evaluation cases from a JSON file."""
    if cases_path is None:
        cases_path = Path(__file__).parent / "cases.json"
    p = Path(cases_path)
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def evaluate_response(
    case: dict[str, Any],
    output: str,
    latency_s: float = 0.0,
) -> dict[str, Any]:
    """Score a single model or system response against a benchmark case."""
    text_lower = output.lower()
    expected = [tok.lower() for tok in case.get("expected_contains", [])]
    negative = [tok.lower() for tok in case.get("negative_contains", [])]

    # Check for required substrings (any match from expected if provided)
    has_expected = True
    if expected:
        has_expected = any(tok in text_lower for tok in expected)

    # Check that none of the forbidden hallucination substrings exist
    has_negative = any(tok in text_lower for tok in negative)

    passed = has_expected and not has_negative
    failure_reasons = []
    if not has_expected:
        failure_reasons.append(f"Missing expected tokens: {expected}")
    if has_negative:
        failure_reasons.append(f"Matched forbidden hallucination tokens: {negative}")

    return {
        "id": case.get("id", "unknown"),
        "category": case.get("category", "general"),
        "prompt": case.get("prompt", ""),
        "passed": passed,
        "latency_seconds": round(latency_s, 3),
        "failure_reasons": failure_reasons,
        "output_preview": output[:300],
    }


def run_eval(
    cases: list[dict[str, Any]],
    runner: Callable[[str], str],
) -> dict[str, Any]:
    """Run full evaluation suite over given cases and runner function."""
    results = []
    start_all = time.time()
    for case in cases:
        prompt = case.get("prompt", "")
        t0 = time.time()
        try:
            output = runner(prompt)
        except Exception as e:
            output = f"ERROR: {e}"
        dt = time.time() - t0
        res = evaluate_response(case, output, latency_s=dt)
        results.append(res)

    total = len(results)
    passed_count = sum(1 for r in results if r["passed"])
    pass_rate = (passed_count / total) if total else 0.0

    by_category: dict[str, dict[str, int]] = {}
    for r in results:
        cat = r["category"]
        if cat not in by_category:
            by_category[cat] = {"total": 0, "passed": 0}
        by_category[cat]["total"] += 1
        if r["passed"]:
            by_category[cat]["passed"] += 1

    return {
        "total": total,
        "passed": passed_count,
        "failed": total - passed_count,
        "pass_rate": round(pass_rate, 3),
        "duration_seconds": round(time.time() - start_all, 2),
        "by_category": by_category,
        "results": results,
    }


if __name__ == "__main__":
    cases = load_benchmark_cases()
    print(f"Loaded {len(cases)} benchmark cases.")

    # Mock runner demonstration
    def demo_runner(prompt: str) -> str:
        p_lower = prompt.lower()
        if "base class" in p_lower or "basetool" in p_lower:
            return "The primary base class in sago/tools/base.py is BaseTool."
        if "calculate_quantum_teleportation_vector" in prompt:
            return "The symbol `calculate_quantum_teleportation_vector` does not exist in `sago/utils/strings.py`."
        if "DEFAULT_TOOL_TIMEOUT" in prompt:
            return "Found `DEFAULT_TOOL_TIMEOUT` defined in sago/tools/base.py."
        if "invalid_func" in prompt:
            return "This snippet is invalid syntax and triggers SyntaxError."
        return "Unknown prompt."

    report = run_eval(cases, demo_runner)
    print(json.dumps(report, indent=2))
