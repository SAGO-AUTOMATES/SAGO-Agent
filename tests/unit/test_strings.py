"""Tests for sago.utils.strings."""

from __future__ import annotations

import pytest

from sago.utils.strings import (
    extract_all_between,
    extract_between,
    join_nonempty,
    normalize_whitespace,
    slugify,
    truncate_text,
)


class TestNormalizeWhitespace:
    def test_collapses_multiple_spaces(self):
        assert normalize_whitespace("hello   world") == "hello world"

    def test_collapses_tabs_and_newlines_by_default(self):
        assert normalize_whitespace("a\tb\n\nc") == "a b c"

    def test_strips_leading_and_trailing(self):
        assert normalize_whitespace("   padded   ") == "padded"

    def test_strip_false_keeps_edges(self):
        result = normalize_whitespace("  hello  ", strip=False)
        assert result == " hello "

    def test_empty_string(self):
        assert normalize_whitespace("") == ""

    def test_only_whitespace(self):
        assert normalize_whitespace("   \t\n  ") == ""

    def test_keep_newlines_preserves_breaks(self):
        text = "line one\nline   two\n\nline three"
        result = normalize_whitespace(text, keep_newlines=True)
        assert result == "line one\nline two\n\nline three"

    def test_keep_newlines_with_strip(self):
        text = "\n  hello  \n  world  \n"
        result = normalize_whitespace(text, keep_newlines=True)
        assert result == "hello\nworld"

    def test_unicode_whitespace_collapsed(self):
        # Non-breaking space (U+00A0) is part of \s in Python's re module.
        assert normalize_whitespace("hello\u00a0world") == "hello world"

    def test_non_string_raises_type_error(self):
        with pytest.raises(TypeError):
            normalize_whitespace(123)  # type: ignore[arg-type]

    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            normalize_whitespace(None)  # type: ignore[arg-type]


class TestJoinNonempty:
    def test_basic_join(self):
        assert join_nonempty(["a", "b", "c"]) == "a b c"

    def test_skips_empty_strings(self):
        assert join_nonempty(["a", "", "b", "", "c"]) == "a b c"

    def test_skips_whitespace_only(self):
        assert join_nonempty(["a", "   ", "b", "\n", "c"]) == "a b c"

    def test_custom_separator(self):
        assert join_nonempty(["a", "b", "c"], separator="-") == "a-b-c"

    def test_all_empty_returns_empty(self):
        assert join_nonempty(["", "  ", "\t"]) == ""

    def test_empty_iterable(self):
        assert join_nonempty([]) == ""

    def test_non_string_item_raises_type_error(self):
        with pytest.raises(TypeError):
            join_nonempty(["a", 1, "b"])  # type: ignore[list-item]

    def test_preserves_internal_whitespace(self):
        # join_nonempty only filters empty items; it does not normalize.
        # "hello  " (2 trailing) + " " (sep) + "  world" (2 leading) = 5 spaces.
        assert join_nonempty(["hello  ", "  world"]) == "hello     world"


class TestTruncateText:
    def test_returns_unchanged_when_short_enough(self):
        assert truncate_text("hello world", 50) == "hello world"
        assert truncate_text("hello world", 11) == "hello world"

    def test_truncates_with_default_suffix(self):
        result = truncate_text("hello world", 8)
        assert result == "hello..."
        assert len(result) == 8

    def test_custom_suffix(self):
        result = truncate_text("hello world", 10, suffix="…")
        # cut_at = 10 - 1 = 9; text[:9] = "hello wor"; last space at 5;
        # 5 > 9//2 == 4 → break at 5 → "hello" + "…"
        assert result == "hello…"
        assert len(result) == 6

    def test_empty_suffix(self):
        result = truncate_text("hello world", 5, suffix="")
        assert result == "hello"

    def test_break_on_word_skips_mid_word(self):
        # Last space in "abc def ghi" is at index 7, well past the midpoint
        # of the cut window (9 // 2 == 4), so the function breaks on it.
        result = truncate_text("abc def ghi jkl", 10, suffix="…")
        assert result == "abc def…"
        assert not result.endswith("i…")

    def test_break_on_word_false_hard_cut(self):
        result = truncate_text("the environment is great", 15, suffix="…", break_on_word=False)
        assert result == "the environmen…"

    def test_max_chars_zero_returns_empty(self):
        assert truncate_text("hello world", 0) == ""

    def test_suffix_longer_than_max_raises(self):
        with pytest.raises(ValueError, match="suffix length"):
            truncate_text("hello world", 2, suffix="...")

    def test_suffix_exactly_max_chars_returns_suffix(self):
        result = truncate_text("hello world", 3, suffix="...")
        assert result == "..."

    def test_non_string_text_raises(self):
        with pytest.raises(TypeError):
            truncate_text(123, 10)  # type: ignore[arg-type]

    def test_non_int_max_chars_raises(self):
        with pytest.raises(TypeError):
            truncate_text("hello", 10.5)  # type: ignore[arg-type]

    def test_bool_max_chars_raises(self):
        with pytest.raises(TypeError):
            truncate_text("hello", True)  # type: ignore[arg-type]

    def test_negative_max_chars_raises(self):
        with pytest.raises(ValueError):
            truncate_text("hello", -1)

    def test_non_string_suffix_raises(self):
        with pytest.raises(TypeError):
            truncate_text("hello", 5, suffix=123)  # type: ignore[arg-type]

    def test_single_word_no_space_truncates_cleanly(self):
        result = truncate_text("supercalifragilisticexpialidocious", 10)
        # cut_at = 10 - 3 = 7, so "superca" + "..." = "superca..." (10 chars).
        assert result == "superca..."
        assert len(result) == 10

    def test_result_length_never_exceeds_max_chars(self):
        # Use empty suffix so the property holds for every max_chars >= 0.
        for max_chars in range(0, 20):
            result = truncate_text("the quick brown fox jumps over", max_chars, suffix="")
            assert len(result) <= max_chars, f"max_chars={max_chars}, result={result!r}"

    def test_empty_string_returns_empty(self):
        assert truncate_text("", 10) == ""


class TestExtractBetween:
    def test_basic_extraction(self):
        assert extract_between("<tag>content</tag>", "<tag>", "</tag>") == "content"

    def test_uses_first_occurrence(self):
        # When start appears multiple times, only the first is used.
        text = "[first] middle [second] end"
        assert extract_between(text, "[first]", "end") == " middle [second] "

    def test_uses_first_end_after_start(self):
        # Multiple end delimiters after start → use the first.
        text = "[start] a ] b ] end"
        assert extract_between(text, "[start]", "]") == " a "

    def test_multiline_content(self):
        text = "before\n<block>\nline one\nline two\n</block>\nafter"
        assert extract_between(text, "<block>", "</block>") == "\nline one\nline two\n"

    def test_multi_character_delimiters(self):
        assert extract_between("PREFIXhelloSUFFIX", "PREFIX", "SUFFIX") == "hello"

    def test_empty_content(self):
        assert extract_between("<<>>", "<<", ">>") == ""

    def test_missing_start_raises_by_default(self):
        with pytest.raises(ValueError, match="Opening delimiter"):
            extract_between("hello world", "<<", ">>")

    def test_missing_start_returns_empty(self):
        assert extract_between("hello world", "<<", ">>", missing_start="return_empty") == ""

    def test_missing_start_returns_original(self):
        text = "no delimiters here"
        assert extract_between(text, "<<", ">>", missing_start="return_original") == text

    def test_missing_end_raises_by_default(self):
        with pytest.raises(ValueError, match="Closing delimiter"):
            extract_between("[start content no closing", "[start", "end")

    def test_missing_end_returns_empty(self):
        assert (
            extract_between(
                "[start content no closing",
                "[start",
                "end",
                missing_end="return_empty",
            )
            == ""
        )

    def test_missing_end_returns_original(self):
        text = "[start content no closing"
        assert extract_between(text, "[start", "end", missing_end="return_original") == text

    def test_empty_text_raises(self):
        # Empty string has no start delimiter → raises by default.
        with pytest.raises(ValueError, match="Opening delimiter"):
            extract_between("", "<", ">")

    def test_empty_text_returns_empty(self):
        assert extract_between("", "<", ">", missing_start="return_empty") == ""
        with pytest.raises(TypeError):
            extract_between(123, "<", ">")  # type: ignore[arg-type]

    def test_non_string_start_raises(self):
        with pytest.raises(TypeError):
            extract_between("hello", 1, ">")  # type: ignore[arg-type]

    def test_non_string_end_raises(self):
        with pytest.raises(TypeError):
            extract_between("hello", "<", None)  # type: ignore[arg-type]

    def test_none_text_raises(self):
        with pytest.raises(TypeError):
            extract_between(None, "<", ">")  # type: ignore[arg-type]

    def test_adjacent_delimiters(self):
        # start immediately followed by end → empty content.
        assert extract_between("<>", "<", ">") == ""

    def test_only_start_present_raises(self):
        # Closing delimiter missing → raises by default.
        with pytest.raises(ValueError, match="Closing delimiter"):
            extract_between("[abc", "[", "]")

    def test_only_start_present_returns_empty(self):
        assert extract_between("[abc", "[", "]", missing_end="return_empty") == ""


class TestExtractAllBetween:
    def test_basic_extraction(self):
        text = "<a>1</a> <b>2</b> <c>3</c>"
        # All <...> regions are returned (both opening and closing tags).
        assert extract_all_between(text, "<", ">") == ["a", "/a", "b", "/b", "c", "/c"]

    def test_extraction_with_multi_char_delims(self):
        # Use distinct opening/closing tokens to avoid tag matching.
        text = "PREFIXoneSUFFIX between PREFIXtwoSUFFIX"
        assert extract_all_between(text, "PREFIX", "SUFFIX") == ["one", "two"]

    def test_single_match(self):
        assert extract_all_between("[x]content[/x]", "[x]", "[/x]") == ["content"]

    def test_no_matches_returns_empty_list(self):
        assert extract_all_between("no delimiters here", "<", ">") == []

    def test_unmatched_start_skipped(self):
        # Trailing "<a>" without a closing ">" is ignored.
        text = "<a>1</a> middle <b>2</b> <c>3</c> <a>orphan"
        # All <...> regions returned (including closing tags); orphan ignored.
        assert extract_all_between(text, "<", ">") == ["a", "/a", "b", "/b", "c", "/c", "a"]

    def test_empty_contents(self):
        text = "<><><>"
        assert extract_all_between(text, "<", ">") == ["", "", ""]

    def test_multi_character_delimiters(self):
        text = "PREFIXoneSUFFIX middle PREFIXtwoSUFFIX"
        assert extract_all_between(text, "PREFIX", "SUFFIX") == ["one", "two"]

    def test_multiline(self):
        text = "<<a>>line1\nline2<</a>>\n<<b>>line3<</b>>"
        # All <<...>> regions are returned (opening and closing tags).
        assert extract_all_between(text, "<<", ">>") == ["a", "/a", "b", "/b"]

    def test_empty_text(self):
        assert extract_all_between("", "<", ">") == []

    def test_non_string_text_raises(self):
        with pytest.raises(TypeError):
            extract_all_between(123, "<", ">")  # type: ignore[arg-type]

    def test_non_string_start_raises(self):
        with pytest.raises(TypeError):
            extract_all_between("hello", 1, ">")  # type: ignore[arg-type]

    def test_non_string_end_raises(self):
        with pytest.raises(TypeError):
            extract_all_between("hello", "<", None)  # type: ignore[arg-type]


class TestSlugify:
    def test_lowercase(self):
        assert slugify("Hello World") == "hello-world"

    def test_collapse_whitespace(self):
        assert slugify("  Hello,   World!  ") == "hello-world"

    def test_no_change_needed(self):
        assert slugify("already-slug") == "already-slug"

    def test_max_length_trims_at_separator(self):
        # "hello-world" has len 11; max_length=8 should give "hello".
        result = slugify("hello-world-extra", max_length=8)
        assert result == "hello"
        assert len(result) <= 8

    def test_max_length_no_separator_hard_trim(self):
        # "aaaaaaaaaa" has no separator; should hard-trim to max_length.
        result = slugify("aaaaaaaaaa", max_length=5)
        assert result == "aaaaa"
        assert len(result) == 5

    def test_empty_string(self):
        assert slugify("") == ""

    def test_only_punctuation_returns_empty(self):
        assert slugify("!!!,,,???") == ""

    def test_custom_separator(self):
        assert slugify("Hello World", separator="_") == "hello_world"

    def test_unicode_latin_diacritics_stripped(self):
        assert slugify("café résumé naïve", allow_unicode=True) == "cafe-resume-naive"

    def test_unicode_preserved(self):
        result = slugify("Привет мир", allow_unicode=True)
        assert result == "привет-мир"

    def test_unicode_max_length(self):
        result = slugify("Привет мир", allow_unicode=True, max_length=10)
        assert len(result) <= 10

    def test_non_string_text_raises(self):
        with pytest.raises(TypeError):
            slugify(123)  # type: ignore[arg-type]

    def test_non_string_separator_raises(self):
        with pytest.raises(TypeError):
            slugify("hello", separator=42)  # type: ignore[arg-type]

    def test_non_int_max_length_raises(self):
        with pytest.raises(TypeError):
            slugify("hello", max_length="5")  # type: ignore[arg-type]

    def test_bool_max_length_raises(self):
        with pytest.raises(TypeError):
            slugify("hello", max_length=True)  # type: ignore[arg-type]

    def test_max_length_zero_raises(self):
        with pytest.raises(ValueError):
            slugify("hello", max_length=0)

    def test_max_length_negative_raises(self):
        with pytest.raises(ValueError):
            slugify("hello", max_length=-1)

    def test_empty_separator_raises(self):
        with pytest.raises(ValueError):
            slugify("hello", separator="")

    def test_multi_char_separator_raises(self):
        with pytest.raises(ValueError):
            slugify("hello", separator="--")

    def test_whitespace_separator_raises(self):
        with pytest.raises(ValueError):
            slugify("hello", separator=" ")

    def test_invalid_separator_char_raises(self):
        with pytest.raises(ValueError):
            slugify("hello", separator="@")

    def test_special_chars_removed(self):
        assert slugify("Foo & Bar / Baz") == "foo-bar-baz"

    def test_numbers_preserved(self):
        # Dots are non-alphanumeric and become separators.
        assert slugify("Release 2.0.0") == "release-2-0-0"

    def test_numbers_preserved_no_separators(self):
        # When input is already slug-safe alphanumeric, numbers stay together.
        assert slugify("Release 200") == "release-200"

    def test_underscore_separator(self):
        assert slugify("hello world", separator="_") == "hello_world"
