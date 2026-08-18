"""Tests for hallucination prevention enhancements."""

from __future__ import annotations


class TestFabricationPhraseDetection:
    """Test expanded fabrication phrase detection."""

    def test_expanded_phrases_include_conversational(self) -> None:
        """Verify conversational fabrication phrases are included."""
        from sago.engine.simple_executor import PROMPTS

        # The prompts should contain anti-hallucination directives
        for prompt_key in ("create", "fix", "analyze", "test"):
            assert prompt_key in PROMPTS
            prompt = PROMPTS[prompt_key]
            assert "NEVER" in prompt
            assert "tool" in prompt.lower()

    def test_chat_prompt_has_hallucination_guard(self) -> None:
        """Verify chat prompt has hallucination prevention."""
        from sago.engine.simple_executor import PROMPTS

        chat_prompt = PROMPTS["chat"]
        assert "hallucinate" in chat_prompt.lower() or "NEVER" in chat_prompt

    def test_create_prompt_requires_tools(self) -> None:
        """Verify create prompt mandates tool usage."""
        from sago.engine.simple_executor import PROMPTS

        create_prompt = PROMPTS["create"]
        assert "read_file" in create_prompt
        assert "write_file" in create_prompt
        assert "execute_shell" in create_prompt

    def test_fix_prompt_requires_verification(self) -> None:
        """Verify fix prompt requires actual verification."""
        from sago.engine.simple_executor import PROMPTS

        fix_prompt = PROMPTS["fix"]
        assert "tests pass" in fix_prompt.lower() or "run" in fix_prompt.lower()
        assert "read_file" in fix_prompt

    def test_analyze_prompt_requires_file_reading(self) -> None:
        """Verify analyze prompt requires actual file reading."""
        from sago.engine.simple_executor import PROMPTS

        analyze_prompt = PROMPTS["analyze"]
        assert "read_file" in analyze_prompt
        assert "NEVER" in analyze_prompt

    def test_prompts_have_complexity_calibration(self) -> None:
        """All prompts should have complexity calibration to prevent overthinking."""
        from sago.engine.simple_executor import PROMPTS

        for key in ("chat", "create", "fix", "analyze", "test"):
            assert "COMPLEXITY CALIBRATION" in PROMPTS[key], (
                f"Prompt '{key}' missing complexity calibration"
            )

    def test_prompts_discourage_overclaiming(self) -> None:
        """Prompts should discourage overclaiming without tool evidence."""
        from sago.engine.simple_executor import PROMPTS

        for key in ("create", "fix", "analyze", "test"):
            assert "production-ready" in PROMPTS[key].lower() or "NEVER claim" in PROMPTS[key]


class TestCodeHallucinationDetection:
    """Test code-level hallucination detection."""

    def test_detect_invalid_python_syntax(self) -> None:
        """Detect hallucinated Python code with syntax errors."""
        from sago.engine.simple_executor import _detect_code_hallucinations

        content = "Here's the fix:\n```python\ndef foo(\n    return 1\n```"
        issues = _detect_code_hallucinations(content, [])
        assert any("syntax error" in issue.lower() for issue in issues)

    def test_valid_python_code_no_issues(self) -> None:
        """Valid Python code should not trigger issues."""
        from sago.engine.simple_executor import _detect_code_hallucinations

        content = "Here's the fix:\n```python\ndef foo():\n    return 1\n```"
        issues = _detect_code_hallucinations(content, [])
        syntax_issues = [i for i in issues if "syntax error" in i.lower()]
        assert len(syntax_issues) == 0

    def test_hallucinated_file_path_detection(self) -> None:
        """Detect references to non-existent files."""
        from sago.engine.simple_executor import _detect_code_hallucinations

        content = 'I read the file `nonexistent_fake_file_xyz.py` and it contains code.'
        issues = _detect_code_hallucinations(content, [])
        # Should flag the non-existent file
        assert any("nonexistent" in issue.lower() or "may not exist" in issue.lower() for issue in issues)

    def test_empty_content_no_issues(self) -> None:
        """Empty content should produce no issues."""
        from sago.engine.simple_executor import _detect_code_hallucinations

        issues = _detect_code_hallucinations("", [])
        assert issues == []

    def test_no_code_blocks_no_issues(self) -> None:
        """Content without code blocks should not trigger syntax checks."""
        from sago.engine.simple_executor import _detect_code_hallucinations

        content = "This is a simple text response without any code."
        issues = _detect_code_hallucinations(content, [])
        assert issues == []

    def test_detect_fabrication_phrases(self) -> None:
        """Detect common LLM fabrication phrases without tool evidence."""
        from sago.engine.simple_executor import _detect_code_hallucinations

        content = "I've verified the fix works. The tests pass now. Everything is working correctly."
        # No tools called — should flag fabrication
        issues = _detect_code_hallucinations(content, [])
        assert any("fabrication" in issue.lower() for issue in issues)

    def test_fabrication_with_tools_not_flagged(self) -> None:
        """Fabrication phrases backed by actual tool calls should not be flagged."""
        from sago.engine.simple_executor import _detect_code_hallucinations

        content = "I've verified the fix works. The tests pass now."
        tool_history = [
            {"tool": "execute_shell", "args": {}, "result": "all tests passed", "success": True},
        ]
        issues = _detect_code_hallucinations(content, tool_history)
        # Should not flag test claims since execute_shell was called
        test_fabrications = [i for i in issues if "tests pass" in i.lower() and "fabrication" in i.lower()]
        assert len(test_fabrications) == 0

    def test_detect_js_code_block_syntax(self) -> None:
        """Detect unbalanced braces in JavaScript code blocks."""
        from sago.engine.simple_executor import _detect_code_hallucinations

        content = "Here's the JS fix:\n```javascript\nfunction foo() { return 1; \n```"
        issues = _detect_code_hallucinations(content, [])
        assert any("unclosed brace" in issue.lower() for issue in issues)

    def test_detect_go_code_block_syntax(self) -> None:
        """Detect unbalanced braces in Go code blocks."""
        from sago.engine.simple_executor import _detect_code_hallucinations

        content = "Here's the Go fix:\n```go\nfunc Foo() { return 1 \n```"
        issues = _detect_code_hallucinations(content, [])
        assert any("unclosed brace" in issue.lower() or "unbalanced" in issue.lower() for issue in issues)

    def test_detect_overconfidence_without_tools(self) -> None:
        """Detect overconfident claims without any tool usage."""
        from sago.engine.simple_executor import _detect_code_hallucinations

        content = "This definitely works perfectly and is guaranteed to handle all cases."
        issues = _detect_code_hallucinations(content, [])
        assert any("overconfidence" in issue.lower() for issue in issues)

    def test_hallucinated_import_detection(self) -> None:
        """Detect imports of non-standard modules."""
        from sago.engine.simple_executor import _detect_code_hallucinations

        content = "```python\nimport fake_nonexistent_module_xyz\nprint('hello')\n```"
        issues = _detect_code_hallucinations(content, [])
        assert any("hallucinated import" in issue.lower() for issue in issues)

    def test_known_import_not_flagged(self) -> None:
        """Standard library imports should not be flagged."""
        from sago.engine.simple_executor import _detect_code_hallucinations

        content = "```python\nimport os\nimport json\nprint('hello')\n```"
        issues = _detect_code_hallucinations(content, [])
        import_issues = [i for i in issues if "hallucinated import" in i.lower()]
        assert len(import_issues) == 0


class TestClaimVerification:
    """Test cross-reference checking of claims vs tool history."""

    def test_read_claim_without_tool(self) -> None:
        """Detect claims to read files without using read_file tool."""
        from sago.engine.simple_executor import _verify_claims_against_history

        content = "I read the file main.py and it has a bug."
        tool_history = [{"tool": "write_file", "args": {"file_path": "test.py"}, "result": "ok"}]
        issues = _verify_claims_against_history(content, tool_history)
        assert any("read" in issue.lower() for issue in issues)

    def test_write_claim_without_tool(self) -> None:
        """Detect claims to write files without using write_file tool."""
        from sago.engine.simple_executor import _verify_claims_against_history

        content = "I created the file output.py with the fix."
        tool_history = [{"tool": "read_file", "args": {"file_path": "input.py"}, "result": "content"}]
        issues = _verify_claims_against_history(content, tool_history)
        assert any("created" in issue.lower() or "write" in issue.lower() for issue in issues)

    def test_test_claim_without_shell(self) -> None:
        """Detect claims about tests without running execute_shell."""
        from sago.engine.simple_executor import _verify_claims_against_history

        content = "All tests pass now after the fix."
        tool_history = [{"tool": "edit_file", "args": {"file_path": "test.py"}, "result": "ok"}]
        issues = _verify_claims_against_history(content, tool_history)
        assert any("test" in issue.lower() for issue in issues)

    def test_fix_claim_without_edit(self) -> None:
        """Detect claims to fix without using edit_file/write_file."""
        from sago.engine.simple_executor import _verify_claims_against_history

        content = "I fixed the bug in the function."
        tool_history = [{"tool": "read_file", "args": {"file_path": "code.py"}, "result": "content"}]
        issues = _verify_claims_against_history(content, tool_history)
        assert any("fix" in issue.lower() for issue in issues)

    def test_honest_response_no_issues(self) -> None:
        """Honest response with matching tool calls should have no issues."""
        from sago.engine.simple_executor import _verify_claims_against_history

        content = "I've updated the file with the fix."
        tool_history = [{"tool": "edit_file", "args": {"file_path": "code.py"}, "result": "ok"}]
        issues = _verify_claims_against_history(content, tool_history)
        # Should not flag since edit_file was actually called
        assert not any("claims to have" in issue.lower() for issue in issues)

    def test_empty_history_no_issues(self) -> None:
        """Empty tool history should not cause issues for simple text."""
        from sago.engine.simple_executor import _verify_claims_against_history

        content = "Here's a simple explanation of how Python works."
        issues = _verify_claims_against_history(content, [])
        assert issues == []

    def test_analyze_claim_without_read(self) -> None:
        """Detect claims to analyze without read tools."""
        from sago.engine.simple_executor import _verify_claims_against_history

        content = "After analyzing the code, I found the issue in main.py."
        tool_history = [{"tool": "execute_shell", "args": {}, "result": "ok"}]
        issues = _verify_claims_against_history(content, tool_history)
        # Should detect that analyze claims need read/search tools
        assert len(issues) > 0

    def test_search_claim_without_search_tool(self) -> None:
        """Detect claims to search without search tools."""
        from sago.engine.simple_executor import _verify_claims_against_history

        content = "I searched for the function and found it in utils.py."
        tool_history = [{"tool": "write_file", "args": {}, "result": "ok"}]
        issues = _verify_claims_against_history(content, tool_history)
        assert any("search" in issue.lower() for issue in issues)


class TestConfidenceScoring:
    """Test response confidence scoring."""

    def test_perfect_response_high_confidence(self) -> None:
        """Response with proper tool usage should have high confidence."""
        from sago.engine.simple_executor import _compute_confidence_score

        content = "I've read the file and applied the fix."
        tool_history = [
            {"tool": "read_file", "args": {}, "result": "file content", "success": True},
            {"tool": "edit_file", "args": {}, "result": "edited", "success": True},
        ]
        files_created = ["code.py"]
        confidence = _compute_confidence_score(
            content, tool_history, files_created, [], [], []
        )
        assert confidence >= 80

    def test_fabrication_lowers_confidence(self) -> None:
        """Fabrication issues should lower confidence."""
        from sago.engine.simple_executor import _compute_confidence_score

        content = "I've fixed everything."
        tool_history = []
        confidence = _compute_confidence_score(
            content, tool_history, [],
            fabrication_issues=["fabrication detected"],
            code_issues=[],
            claim_issues=[],
        )
        assert confidence < 70

    def test_code_issues_lower_confidence(self) -> None:
        """Code issues should lower confidence."""
        from sago.engine.simple_executor import _compute_confidence_score

        content = "Here's the code:\n```python\ndef foo(\n```"
        tool_history = [{"tool": "write_file", "args": {}, "result": "ok", "success": True}]
        confidence = _compute_confidence_score(
            content, tool_history, [],
            fabrication_issues=[],
            code_issues=["syntax error in code block"],
            claim_issues=[],
        )
        assert confidence < 90

    def test_no_tools_reduces_confidence(self) -> None:
        """No tool usage should reduce confidence."""
        from sago.engine.simple_executor import _compute_confidence_score

        content = "Here's a response without any tool usage."
        tool_history = []
        confidence = _compute_confidence_score(content, tool_history, [], [], [], [])
        assert confidence < 80

    def test_confidence_bounds(self) -> None:
        """Confidence should be bounded between 0 and 100."""
        from sago.engine.simple_executor import _compute_confidence_score

        # Worst case
        confidence = _compute_confidence_score(
            "", [],
            fabrication_issues=["f1", "f2", "f3", "f4", "f5"],
            code_issues=["c1", "c2", "c3", "c4", "c5"],
            claim_issues=["cl1", "cl2", "cl3", "cl4", "cl5"],
            files_created=[],
        )
        assert 0 <= confidence <= 100

        # Best case
        confidence = _compute_confidence_score(
            "A good response with details.",
            [{"tool": "read_file", "success": True}, {"tool": "edit_file", "success": True}],
            ["file.py"],
            [], [], [],
        )
        assert 0 <= confidence <= 100

    def test_tool_diversity_bonus(self) -> None:
        """Using multiple different tools should boost confidence."""
        from sago.engine.simple_executor import _compute_confidence_score

        content = "I read the file, searched for patterns, and applied the fix."
        tool_history = [
            {"tool": "read_file", "args": {}, "result": "content", "success": True},
            {"tool": "grep_content", "args": {}, "result": "found", "success": True},
            {"tool": "edit_file", "args": {}, "result": "edited", "success": True},
        ]
        confidence_diverse = _compute_confidence_score(
            content, tool_history, [], [], [], []
        )
        # Single tool usage
        tool_history_single = [
            {"tool": "read_file", "args": {}, "result": "content", "success": True},
            {"tool": "read_file", "args": {}, "result": "content2", "success": True},
            {"tool": "read_file", "args": {}, "result": "content3", "success": True},
        ]
        confidence_single = _compute_confidence_score(
            content, tool_history_single, [], [], [], []
        )
        assert confidence_diverse >= confidence_single

    def test_excessive_fabrication_heavy_penalty(self) -> None:
        """Multiple fabrication signals should incur heavy penalty."""
        from sago.engine.simple_executor import _compute_confidence_score

        content = "Long response without tools"
        fabrication_issues = [
            "Fabrication: 'tests pass' — no execute_shell",
            "Fabrication: 'I verified' — no read tool",
            "Fabrication: 'fixed the issue' — no edit tool",
        ]
        confidence = _compute_confidence_score(
            content, [], [], fabrication_issues, [], []
        )
        assert confidence < 50


class TestPromptEnhancements:
    """Test prompt enhancements for anti-hallucination."""

    def test_all_prompts_have_thinking_step(self) -> None:
        """All prompts should include a thinking/verification step."""
        from sago.engine.simple_executor import PROMPTS

        for key, prompt in PROMPTS.items():
            assert "THINKING STEP" in prompt or "verify" in prompt.lower(), (
                f"Prompt '{key}' missing verification step"
            )

    def test_create_prompt_has_quality_standards(self) -> None:
        """Create prompt should have quality standards."""
        from sago.engine.simple_executor import PROMPTS

        create_prompt = PROMPTS["create"]
        assert "QUALITY STANDARDS" in create_prompt
        assert "production-ready" in create_prompt.lower() or "error handling" in create_prompt.lower()

    def test_fix_prompt_has_minimal_change(self) -> None:
        """Fix prompt should emphasize minimal changes."""
        from sago.engine.simple_executor import PROMPTS

        fix_prompt = PROMPTS["fix"]
        assert "minimal" in fix_prompt.lower() or "precise" in fix_prompt.lower()

    def test_analyze_prompt_has_specificity(self) -> None:
        """Analyze prompt should require specific findings."""
        from sago.engine.simple_executor import PROMPTS

        analyze_prompt = PROMPTS["analyze"]
        assert "file paths" in analyze_prompt.lower() or "line numbers" in analyze_prompt.lower()


class TestFabricationPhrasePatterns:
    """Test the fabrication phrase regex patterns."""

    def test_fabrication_phrases_defined(self) -> None:
        """Verify fabrication phrases are defined."""
        from sago.engine.simple_executor import _FABRICATION_PHRASES
        assert len(_FABRICATION_PHRASES) > 10

    def test_detect_i_verified_phrase(self) -> None:
        """Detect 'I've verified' fabrication phrase."""
        import re
        from sago.engine.simple_executor import _FABRICATION_PHRASES

        text = "I've verified that the code works correctly."
        for pattern in _FABRICATION_PHRASES:
            if re.search(pattern, text, re.IGNORECASE):
                return  # Found it
        assert False, "Should have detected 'I've verified' fabrication phrase"

    def test_detect_tests_pass_phrase(self) -> None:
        """Detect 'tests pass' fabrication phrase."""
        import re
        from sago.engine.simple_executor import _FABRICATION_PHRASES

        text = "All tests pass after the fix."
        for pattern in _FABRICATION_PHRASES:
            if re.search(pattern, text, re.IGNORECASE):
                return  # Found it
        assert False, "Should have detected 'tests pass' fabrication phrase"
