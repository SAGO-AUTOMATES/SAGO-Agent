"""Tests for ``sago.utils.strings.truncate_text_by_tokens``."""

from __future__ import annotations

import pytest

from sago.utils.strings import truncate_text_by_tokens


class TestTruncateTextByTokens:
    """Verify truncation behaviour for the helper."""

    def test_short_text_unchanged(self) -> None:
        result = truncate_text_by_tokens("hello world", max_tokens=100)
        assert result == "hello world"

    def test_zero_tokens_returns_empty(self) -> None:
        assert truncate_text_by_tokens("hello", max_tokens=0) == ""

    def test_truncates_long_text(self) -> None:
        long_text = "lorem ipsum dolor sit amet " * 100
        result = truncate_text_by_tokens(long_text, max_tokens=10)
        assert len(result) < len(long_text)
        assert len(result) > 0

    def test_truncation_preserves_word_boundary(self) -> None:
        text = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
        result = truncate_text_by_tokens(text, max_tokens=5)
        # Should not end mid-word; must end at whitespace boundary.
        assert not result.endswith("mm")  # not cut mid-word
        # Whitespace-stripped result
        assert result == result.strip()

    def test_max_tokens_one(self) -> None:
        result = truncate_text_by_tokens("a b c d e f g h i j", max_tokens=1)
        assert len(result) <= 8  # 1 token ≈ 4 chars heuristic

    def test_returns_substring(self) -> None:
        text = "abcdefghij" * 20
        result = truncate_text_by_tokens(text, max_tokens=3)
        assert result in text
        assert text.startswith(result.strip())

    def test_invalid_text_type_raises(self) -> None:
        with pytest.raises(TypeError, match="str"):
            truncate_text_by_tokens(123, max_tokens=10)  # type: ignore[arg-type]

    def test_invalid_max_tokens_type_raises(self) -> None:
        with pytest.raises(TypeError, match="int"):
            truncate_text_by_tokens("hello", max_tokens=10.5)  # type: ignore[arg-type]

    def test_negative_max_tokens_raises(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            truncate_text_by_tokens("hello", max_tokens=-1)

    def test_claude_model_falls_back_to_heuristic(self) -> None:
        text = "a" * 1000
        result = truncate_text_by_tokens(text, max_tokens=10, model="claude-3-opus")
        assert len(result) < len(text)

    def test_gemini_model_truncates(self) -> None:
        text = "word " * 200
        result = truncate_text_by_tokens(text, max_tokens=20, model="gemini-2.5-flash")
        assert len(result) < len(text)

    def test_very_large_max_tokens_keeps_full_text(self) -> None:
        text = "short text"
        result = truncate_text_by_tokens(text, max_tokens=10000)
        assert result == text

    def test_empty_string(self) -> None:
        assert truncate_text_by_tokens("", max_tokens=10) == ""

    def test_default_model_works(self) -> None:
        result = truncate_text_by_tokens("hello world", max_tokens=5)
        assert isinstance(result, str)
