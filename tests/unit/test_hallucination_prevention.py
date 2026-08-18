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
