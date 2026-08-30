"""Tests for sago.engine.simple_executor pure functions."""

from __future__ import annotations

from sago.engine.simple_executor import (
    _compute_confidence_score,
    _detect_code_hallucinations,
    _detect_overthinking_loop,
    _is_complex_task,
    _is_simple_analyze,
    _strip_hallucinated_sentences,
    _verify_claims_against_history,
)


class TestIsComplexTask:
    def test_simple_greeting(self):
        assert _is_complex_task("hello") is False

    def test_joke_request(self):
        assert _is_complex_task("tell me a joke") is False

    def test_refactor_task(self):
        assert _is_complex_task("refactor the auth module") is True

    def test_build_project(self):
        assert _is_complex_task("build a new project from scratch") is True

    def test_long_task(self):
        task = " ".join(["step"] * 35)
        assert _is_complex_task(task) is True

    def test_simple_fix(self):
        assert _is_complex_task("fix the typo in main.py") is False

    def test_migration(self):
        assert _is_complex_task("migrate database schema") is True

    def test_test_and_fix(self):
        assert _is_complex_task("test the code and fix any issues") is True

    def test_create(self):
        assert _is_complex_task("create a REST API with authentication") is False

    def test_implement(self):
        assert _is_complex_task("implement feature X") is True

    def test_optimize(self):
        assert _is_complex_task("optimize the database queries for performance") is False

    def test_analyze(self):
        assert _is_complex_task("analyze the codebase") is False


class TestDetectCodeHallucinations:
    def test_empty_content(self):
        assert _detect_code_hallucinations("", []) == []

    def test_valid_python_no_issues(self):
        content = "```python\nprint('hello')\n```"
        issues = _detect_code_hallucinations(content, [])
        assert issues == []

    def test_fabrication_no_tools(self):
        content = "I've verified the code works correctly."
        issues = _detect_code_hallucinations(content, [])
        assert any("Fabrication" in i for i in issues)

    def test_overconfidence_without_tools(self):
        content = "It definitely works perfectly."
        issues = _detect_code_hallucinations(content, [])
        assert any("Overconfidence" in i for i in issues)

    def test_non_code_content_no_issues(self):
        content = "This is just plain text about the project."
        issues = _detect_code_hallucinations(content, [])
        assert issues == []


class TestVerifyClaimsAgainstHistory:
    def test_empty_content(self):
        assert _verify_claims_against_history("", []) == []

    def test_no_claims_no_history(self):
        assert _verify_claims_against_history("Hello world", []) == []

    def test_read_claim_no_tool(self):
        content = "I read the file main.py and found the bug."
        issues = _verify_claims_against_history(content, [])
        assert any("read" in i.lower() for i in issues)

    def test_test_pass_claim_no_shell(self):
        content = "All tests pass successfully."
        issues = _verify_claims_against_history(content, [])
        assert any("execute_shell" in i for i in issues)

    def test_fix_claim_no_write(self):
        content = "I fixed the bug in the code."
        issues = _verify_claims_against_history(content, [])
        assert any("edit_file" in i or "write_file" in i for i in issues)

    def test_read_claim_with_matching_tool(self):
        content = "I read the file main.py."
        tool_history = [{"tool": "read_file", "args": {"file_path": "main.py"}, "result": "ok"}]
        issues = _verify_claims_against_history(content, tool_history)
        assert not any("main.py" in i and "read" in i.lower() for i in issues)

    def test_search_claim_no_tool(self):
        content = "I searched for the function and found it."
        issues = _verify_claims_against_history(content, [])
        assert any("search" in i.lower() for i in issues)

    def test_analyze_claim_no_read(self):
        content = "After analyzing the code, I found issues."
        issues = _verify_claims_against_history(content, [])
        assert any("analyze" in i.lower() for i in issues)


class TestStripHallucinatedSentences:
    def test_empty_content(self):
        assert _strip_hallucinated_sentences("", []) == ""

    def test_no_issues(self):
        assert _strip_hallucinated_sentences("Hello world.", []) == "Hello world."

    def test_removes_sentence_with_hallucinated_file(self):
        content = "The main.py file is great. But utils.py needs work."
        issues = ["Referenced file 'main.py' not found"]
        result = _strip_hallucinated_sentences(content, issues)
        assert "main.py" not in result
        assert "utils.py" in result

    def test_removes_fabrication_pattern(self):
        content = "Based on my analysis, the code is good. I agree."
        issues = ["Fabrication: 'based on my analysis'"]
        result = _strip_hallucinated_sentences(content, issues)
        assert "Based on my analysis" not in result


class TestComputeConfidenceScore:
    def test_perfect_score(self):
        score = _compute_confidence_score(
            "A detailed response with sufficient length " * 5,
            [{"tool": "read_file", "success": True}],
            ["file.py"],
            [], [], [],
        )
        assert 80 <= score <= 100

    def test_no_tools_penalty(self):
        score = _compute_confidence_score("Short.", [], [], [], [], [])
        assert score < 70

    def test_many_fabrication_issues(self):
        score = _compute_confidence_score(
            "A reasonably long response " * 10,
            [],
            [],
            ["Fabrication: a", "Fabrication: b", "Fabrication: c", "Fabrication: d"],
            [], [],
        )
        assert score < 50

    def test_score_clamped_to_100(self):
        score = _compute_confidence_score(
            "A detailed response " * 20,
            [{"success": True}] * 5,
            ["f1.py", "f2.py", "f3.py", "f4.py"],
            [], [], [],
        )
        assert score <= 100

    def test_score_clamped_to_zero(self):
        score = _compute_confidence_score(
            "",
            [],
            [],
            ["Fabrication: a"] * 10,
            ["code issue"] * 10,
            ["claim issue"] * 10,
        )
        assert score >= 0


class TestDetectOverthinkingLoop:
    def test_no_loop_short_history(self):
        result = _detect_overthinking_loop(
            [{"tool": "read_file", "args": {"file_path": "a.py"}}],
            [{"role": "assistant", "content": "hi"}],
            1,
        )
        assert result is None

    def test_same_tool_three_times(self):
        history = [
            {"tool": "read_file", "args": {"file_path": "a.py"}},
            {"tool": "read_file", "args": {"file_path": "a.py"}},
            {"tool": "read_file", "args": {"file_path": "a.py"}},
        ]
        result = _detect_overthinking_loop(history, [], 3)
        assert result is not None

    def test_different_tools_no_loop(self):
        history = [
            {"tool": "read_file", "args": {"file_path": "a.py"}},
            {"tool": "grep_content", "args": {"pattern": "foo"}},
            {"tool": "execute_shell", "args": {"command": "ls"}},
        ]
        result = _detect_overthinking_loop(history, [], 3)
        assert result is None

    def test_high_iteration_no_success(self):
        history = [{"tool": "execute_shell", "args": {}, "success": False}] * 5
        messages = [{"role": "assistant", "content": "x"}] * 7
        result = _detect_overthinking_loop(history, messages, 6)
        assert result is not None

    def test_near_identical_content(self):
        messages = [
            {"role": "assistant", "content": "I need to fix the bug."},
            {"role": "assistant", "content": "I need to fix the bug."},
            {"role": "assistant", "content": "I need to fix the bug."},
            {"role": "assistant", "content": "I need to fix the bug."},
        ]
        result = _detect_overthinking_loop([], messages, 4)
        assert result is not None


class TestIsSimpleAnalyze:
    def test_analyze_with_few_files(self):
        assert _is_simple_analyze("analyze", 3) is True

    def test_analyze_with_many_files(self):
        assert _is_simple_analyze("analyze", 10) is False

    def test_non_analyze_task(self):
        assert _is_simple_analyze("create", 3) is False

    def test_unknown_file_count(self):
        assert _is_simple_analyze("analyze", None) is False

    def test_analyze_exactly_5_files(self):
        assert _is_simple_analyze("analyze", 5) is True

    def test_analyze_6_files(self):
        assert _is_simple_analyze("analyze", 6) is False
