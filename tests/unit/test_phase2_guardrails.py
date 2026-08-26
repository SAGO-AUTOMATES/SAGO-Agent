"""Unit tests for Phase 2: Tool Loop Guardrails and Error Classification."""

from sago.engine.tool_guardrails import ToolGuardrails
from sago.llm.error_classifier import FailReason, classify_error, get_recovery_action


class TestToolGuardrails:
    """Test tool execution circuit breakers."""

    def test_identical_failure_blocking(self):
        guard = ToolGuardrails(max_identical_failures=3)
        tool_name = "read_file"
        args = {"file_path": "nonexistent.txt"}

        assert guard.before_call(tool_name, args) is None
        guard.after_call(tool_name, args, "Error: File not found: nonexistent.txt", success=False)

        assert guard.before_call(tool_name, args) is None
        guard.after_call(tool_name, args, "Error: File not found: nonexistent.txt", success=False)

        assert guard.before_call(tool_name, args) is None
        guard.after_call(tool_name, args, "Error: File not found: nonexistent.txt", success=False)

        # 4th attempt should be blocked
        blocked = guard.before_call(tool_name, args)
        assert blocked is not None
        assert "failed 3 times" in blocked

    def test_runaway_search_cap(self):
        guard = ToolGuardrails(max_search_calls_per_turn=3)
        args = {"query": "python asyncio"}

        # 3 calls allowed
        assert guard.before_call("web_search", args) is None
        guard.after_call("web_search", args, "result 1")

        assert guard.before_call("web_search", args) is None
        guard.after_call("web_search", args, "result 2")

        assert guard.before_call("web_search", args) is None
        guard.after_call("web_search", args, "result 3")

        # 4th call should trip search cap
        blocked = guard.before_call("web_search", args)
        assert blocked is not None
        assert "Runaway search loop detected" in blocked

    def test_no_progress_loop(self):
        guard = ToolGuardrails(max_no_progress_reads=2)
        tool_name = "grep_content"
        args1 = {"query": "foo"}
        args2 = {"query": "bar"}

        guard.after_call(tool_name, args1, "line 10: foo", success=True)
        guard.after_call(tool_name, args2, "line 10: foo", success=True)
        guard.after_call(tool_name, args1, "line 10: foo", success=True)

        blocked = guard.before_call(tool_name, args1)
        assert blocked is not None
        assert "no new information" in blocked


class TestErrorClassifier:
    """Test LLM and API error classification."""

    def test_rate_limit_classification(self):
        reason = classify_error(status_code=429, message="Rate limit exceeded")
        assert reason == FailReason.RATE_LIMIT

        action = get_recovery_action(status_code=429)
        assert action.retry is True
        assert action.backoff is True

    def test_auth_classification(self):
        reason = classify_error(status_code=401, message="Invalid API key provided")
        assert reason == FailReason.AUTH

        action = get_recovery_action(status_code=401)
        assert action.retry is False
        assert action.should_rotate_credential is True

    def test_billing_classification(self):
        reason = classify_error(status_code=402, message="You exceeded your current quota")
        assert reason == FailReason.BILLING

        action = get_recovery_action(status_code=402)
        assert action.retry is False
        assert action.should_fallback_provider is True

    def test_context_overflow(self):
        reason = classify_error(message="This model's maximum context length is 8192 tokens")
        assert reason == FailReason.CONTEXT_OVERFLOW

        action = get_recovery_action(message="context_length_exceeded")
        assert action.should_compress is True
