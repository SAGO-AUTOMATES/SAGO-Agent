"""Tests for the shared hallucination verifier module."""

from __future__ import annotations


class TestResponseVerifier:
    """Test the ResponseVerifier class."""

    def test_clean_response_no_issues(self) -> None:
        """Clean response should have no issues."""
        from sago.engine.hallucination_verifier import ResponseVerifier

        verifier = ResponseVerifier(enable_external_checks=False)
        result = verifier.verify(
            "I'll read the file first.",
            tool_history=[{"tool": "read_file", "args": {"file_path": "test.py"}, "result": "content"}],
        )
        assert not result.has_hallucinations
        assert result.confidence >= 80

    def test_fabrication_detection(self) -> None:
        """Detect fabrication phrases without tool evidence."""
        from sago.engine.hallucination_verifier import ResponseVerifier

        verifier = ResponseVerifier(enable_external_checks=False)
        result = verifier.verify(
            "I've verified the fix works. All tests pass now.",
            tool_history=[],
        )
        assert result.has_hallucinations
        assert len(result.issues) > 0
        assert result.confidence < 80

    def test_user_mention_fabrication(self) -> None:
        """Detect agent fabricating what the user said."""
        from sago.engine.hallucination_verifier import ResponseVerifier

        verifier = ResponseVerifier(enable_external_checks=False)
        result = verifier.verify(
            "I cannot analyze the files you mentioned (`fake_file.py`).",
            tool_history=[],
        )
        assert result.has_hallucinations
        assert any("user mentioned" in issue.lower() for issue in result.claim_issues)

    def test_file_listing_without_tools(self) -> None:
        """Detect listing files without search tools."""
        from sago.engine.hallucination_verifier import ResponseVerifier

        verifier = ResponseVerifier(enable_external_checks=False)
        result = verifier.verify(
            "The available files are:\n1. `foo.py`\n2. `bar.py`\n3. `baz.py`",
            tool_history=[],
        )
        assert result.has_hallucinations
        assert any("lists specific files" in issue.lower() for issue in result.claim_issues)

    def test_external_python_syntax_check(self) -> None:
        """Detect Python syntax errors via py_compile."""
        from sago.engine.hallucination_verifier import ResponseVerifier

        verifier = ResponseVerifier(enable_external_checks=True)
        result = verifier.verify(
            "Here's the code:\n```python\ndef foo(\n    return 1\n```",
            tool_history=[],
        )
        # Should detect syntax error (either from AST or py_compile)
        assert result.has_hallucinations

    def test_sanitize_content(self) -> None:
        """Sanitize content by removing hallucinated sentences."""
        from sago.engine.hallucination_verifier import ResponseVerifier

        verifier = ResponseVerifier(enable_external_checks=False, auto_sanitize=True, confidence_threshold=100)
        result = verifier.verify(
            "The file `fake.py` exists. But this sentence is fine.",
            tool_history=[],
        )
        assert result.sanitized
        assert "fake.py" not in result.cleaned_content
        assert "fine" in result.cleaned_content

    def test_verify_and_warn(self) -> None:
        """Verify and return warning message."""
        from sago.engine.hallucination_verifier import ResponseVerifier

        verifier = ResponseVerifier(enable_external_checks=False)
        content, warning = verifier.verify_and_warn(
            "I've verified all tests pass.",
            tool_history=[],
        )
        assert "WARNING" in warning
        assert len(warning) > 50

    def test_chat_task_skip_verification(self) -> None:
        """Chat tasks without tools should skip detailed verification."""
        from sago.engine.hallucination_verifier import ResponseVerifier

        verifier = ResponseVerifier(enable_external_checks=False)
        result = verifier.verify(
            "Hello! How can I help you?",
            tool_history=[],
            task_type="chat",
        )
        assert result.confidence >= 85  # Should not be heavily penalized

    def test_confidence_bounds(self) -> None:
        """Confidence should be bounded 0-100."""
        from sago.engine.hallucination_verifier import ResponseVerifier

        verifier = ResponseVerifier(enable_external_checks=False)
        # Worst case
        result = verifier.verify("", tool_history=[])
        assert 0 <= result.confidence <= 100
        # Best case
        result = verifier.verify(
            "Done.",
            tool_history=[
                {"tool": "read_file", "args": {}, "result": "ok", "success": True},
                {"tool": "edit_file", "args": {}, "result": "ok", "success": True},
            ],
        )
        assert 0 <= result.confidence <= 100

    def test_all_issues_combined(self) -> None:
        """all_issues should combine all issue types."""
        from sago.engine.hallucination_verifier import ResponseVerifier

        verifier = ResponseVerifier(enable_external_checks=False)
        result = verifier.verify(
            "I've verified the code works. The file `missing.py` exists.",
            tool_history=[],
        )
        assert len(result.all_issues) > 0
        assert result.all_issues == result.issues + result.code_issues + result.claim_issues + result.external_issues


class TestFabricationPhraseDetection:
    """Test fabrication phrase detection."""

    def test_detect_verified_phrase(self) -> None:
        from sago.engine.hallucination_verifier import _detect_fabrication_phrases
        issues = _detect_fabrication_phrases("I've verified the fix works.", [])
        assert len(issues) > 0

    def test_detect_tests_pass_phrase(self) -> None:
        from sago.engine.hallucination_verifier import _detect_fabrication_phrases
        issues = _detect_fabrication_phrases("All tests pass after the fix.", [])
        assert len(issues) > 0

    def test_no_flag_with_tool_evidence(self) -> None:
        from sago.engine.hallucination_verifier import _detect_fabrication_phrases
        issues = _detect_fabrication_phrases(
            "All tests pass.",
            [{"tool": "execute_shell", "args": {}, "result": "passed"}],
        )
        test_issues = [i for i in issues if "tests pass" in i.lower()]
        assert len(test_issues) == 0

    def test_structural_claims_detected(self) -> None:
        from sago.engine.hallucination_verifier import _detect_fabrication_phrases
        issues = _detect_fabrication_phrases("The codebase has 42 files.", [])
        assert len(issues) > 0


class TestClaimVerification:
    """Test claim vs tool-history verification."""

    def test_read_claim_without_tool(self) -> None:
        from sago.engine.hallucination_verifier import _verify_claims
        issues = _verify_claims("I read main.py and it has a bug.", [])
        assert any("read" in issue.lower() for issue in issues)

    def test_write_claim_without_tool(self) -> None:
        from sago.engine.hallucination_verifier import _verify_claims
        issues = _verify_claims("I created output.py with the fix.", [])
        assert any("created" in issue.lower() for issue in issues)

    def test_search_claim_without_tool(self) -> None:
        from sago.engine.hallucination_verifier import _verify_claims
        issues = _verify_claims("I searched for the function and found it.", [])
        assert any("search" in issue.lower() for issue in issues)

    def test_honest_response_no_issues(self) -> None:
        from sago.engine.hallucination_verifier import _verify_claims
        issues = _verify_claims(
            "I've updated the file.",
            [{"tool": "edit_file", "args": {"file_path": "code.py"}, "result": "ok"}],
        )
        assert not any("claims to have" in issue.lower() for issue in issues)


class TestCodeBlockValidation:
    """Test code block syntax validation."""

    def test_invalid_python_syntax(self) -> None:
        from sago.engine.hallucination_verifier import _validate_code_blocks
        issues = _validate_code_blocks("```python\ndef foo(\n    return 1\n```")
        assert any("syntax error" in issue.lower() for issue in issues)

    def test_valid_python_no_issues(self) -> None:
        from sago.engine.hallucination_verifier import _validate_code_blocks
        issues = _validate_code_blocks("```python\ndef foo():\n    return 1\n```")
        syntax_issues = [i for i in issues if "syntax error" in i.lower()]
        assert len(syntax_issues) == 0

    def test_unbalanced_js_braces(self) -> None:
        from sago.engine.hallucination_verifier import _validate_code_blocks
        issues = _validate_code_blocks("```javascript\nfunction foo() { return 1; \n```")
        assert any("unclosed brace" in issue.lower() for issue in issues)


class TestHedgingDetection:
    """Test hedging/subtle claim detection."""

    def test_should_work_without_running(self) -> None:
        """'This should work' without execute_shell should be flagged."""
        from sago.engine.hallucination_verifier import _detect_hedging_phrases
        issues = _detect_hedging_phrases("This should work now.", [])
        assert len(issues) > 0
        assert any("should work" in i for i in issues)

    def test_should_work_with_tool_not_flagged(self) -> None:
        """'This should work' with execute_shell should not be flagged."""
        from sago.engine.hallucination_verifier import _detect_hedging_phrases
        issues = _detect_hedging_phrases(
            "This should work now.",
            [{"tool": "execute_shell", "args": {}, "result": "ok"}],
        )
        assert len(issues) == 0

    def test_trust_me_flagged(self) -> None:
        """'Trust me' should always be flagged."""
        from sago.engine.hallucination_verifier import _detect_hedging_phrases
        issues = _detect_hedging_phrases("Trust me, this is correct.", [])
        assert len(issues) > 0
        assert any("trust me" in i.lower() for i in issues)

    def test_no_breaking_changes_without_testing(self) -> None:
        """'No breaking changes' without test tools should be flagged."""
        from sago.engine.hallucination_verifier import _detect_hedging_phrases
        issues = _detect_hedging_phrases("There are no breaking changes.", [])
        assert len(issues) > 0
        assert any("breaking" in i for i in issues)

    def test_no_breaking_changes_with_testing(self) -> None:
        """'No breaking changes' with test tools should not be flagged."""
        from sago.engine.hallucination_verifier import _detect_hedging_phrases
        issues = _detect_hedging_phrases(
            "There are no breaking changes.",
            [{"tool": "execute_shell", "args": {}, "result": "all tests pass"}],
        )
        assert len(issues) == 0

    def test_verified_without_read_tool(self) -> None:
        """'I verified' without read tools should be flagged."""
        from sago.engine.hallucination_verifier import _detect_hedging_phrases
        issues = _detect_hedging_phrases("I verified the fix.", [])
        assert len(issues) > 0
        assert any("verified" in i for i in issues)

    def test_verified_with_read_tool(self) -> None:
        """'I verified' with read_file should not be flagged."""
        from sago.engine.hallucination_verifier import _detect_hedging_phrases
        issues = _detect_hedging_phrases(
            "I verified the fix.",
            [{"tool": "read_file", "args": {}, "result": "content"}],
        )
        assert len(issues) == 0


class TestToolResultIntegrity:
    """Test tool result integrity checking."""

    def test_no_modification_no_issues(self) -> None:
        """Unmodified result should have no issues."""
        from sago.engine.hallucination_verifier import ToolResultIntegrity
        ti = ToolResultIntegrity()
        ti.record_original("read_file", {"file_path": "test.py"}, "file content")
        issues = ti.check_after_plugin("read_file", {"file_path": "test.py"}, "file content")
        assert len(issues) == 0

    def test_modification_detected(self) -> None:
        """Modified result should be detected."""
        from sago.engine.hallucination_verifier import ToolResultIntegrity
        ti = ToolResultIntegrity()
        ti.record_original("read_file", {"file_path": "test.py"}, "original content")
        issues = ti.check_after_plugin("read_file", {"file_path": "test.py"}, "modified content")
        assert len(issues) > 0
        assert any("modified by plugin" in i for i in issues)

    def test_different_tool_not_affected(self) -> None:
        """Different tool with same args should not be affected."""
        from sago.engine.hallucination_verifier import ToolResultIntegrity
        ti = ToolResultIntegrity()
        ti.record_original("read_file", {"file_path": "test.py"}, "content")
        issues = ti.check_after_plugin("grep_content", {"file_path": "test.py"}, "different")
        assert len(issues) == 0


class TestExtendedLanguageBraceMatching:
    """Test brace matching for extended languages."""

    def test_java_unclosed_brace(self) -> None:
        from sago.engine.hallucination_verifier import _validate_code_blocks
        issues = _validate_code_blocks("```java\nclass Foo { void bar() { return; \n```")
        assert any("unclosed brace" in issue.lower() for issue in issues)

    def test_kotlin_unclosed_brace(self) -> None:
        from sago.engine.hallucination_verifier import _validate_code_blocks
        issues = _validate_code_blocks("```kotlin\nfun main() { println(\"hi\") \n```")
        assert any("unclosed brace" in issue.lower() for issue in issues)

    def test_swift_unclosed_brace(self) -> None:
        from sago.engine.hallucination_verifier import _validate_code_blocks
        issues = _validate_code_blocks("```swift\nfunc foo() { return 1 \n```")
        assert any("unclosed brace" in issue.lower() for issue in issues)

    def test_ruby_valid_no_issues(self) -> None:
        from sago.engine.hallucination_verifier import _validate_code_blocks
        issues = _validate_code_blocks("```ruby\ndef foo\n  puts 'hi'\nend\n```")
        assert not any("brace" in issue.lower() for issue in issues)

    def test_go_balanced_braces(self) -> None:
        from sago.engine.hallucination_verifier import _validate_code_blocks
        issues = _validate_code_blocks("```go\nfunc Foo() { return 1 }\n```")
        assert not any("unclosed brace" in issue.lower() for issue in issues)
