"""Tests for sago/tui/helpers.py utility functions."""

from sago.tui.helpers import _render_markdown, _safe_static, _summarize_tool_result


class TestSafeStatic:
    def test_valid_markup(self):
        s = _safe_static("[bold]Hello[/bold]")
        assert s is not None

    def test_invalid_markup_falls_back(self):
        s = _safe_static("'][/white] invalid markup")
        assert s is not None

    def test_markup_disabled(self):
        s = _safe_static("[bold]Hello[/bold]", markup=False)
        assert s is not None

    def test_empty(self):
        s = _safe_static("")
        assert s is not None


class TestRenderMarkdown:
    def test_headers(self):
        result = _render_markdown("## Header")
        assert "Header" in result

    def test_bold(self):
        result = _render_markdown("**bold text**")
        assert "bold text" in result

    def test_italic(self):
        result = _render_markdown("*italic text*")
        assert "italic text" in result

    def test_inline_code(self):
        result = _render_markdown("`code`")
        assert "code" in result

    def test_unordered_list(self):
        result = _render_markdown("- item one\n- item two")
        assert "item one" in result
        assert "item two" in result

    def test_numbered_list(self):
        result = _render_markdown("1. first\n2. second")
        assert "first" in result
        assert "second" in result

    def test_markup_escaped(self):
        result = _render_markdown("[bold]not markup[/bold]")
        # Should escape Rich markup tags
        assert "bold" in result

    def test_empty(self):
        result = _render_markdown("")
        assert result == ""


class TestSummarizeToolResult:
    def test_empty(self):
        result = _summarize_tool_result("")
        assert "empty" in result

    def test_none(self):
        result = _summarize_tool_result(None)
        assert "empty" in result

    def test_short_result(self):
        result = _summarize_tool_result("Found 5 files matching *.py")
        assert "Found 5 files" in result

    def test_long_file_listing(self):
        lines = [f"sago/tools/file/file{i}.py" for i in range(100)]
        result = _summarize_tool_result("\n".join(lines))
        assert "File listing" in result or "100 lines" in result

    def test_long_json(self):
        json_data = '{"key": "value", "data": ' + '"' + "x" * 2000 + '"}'
        result = _summarize_tool_result(json_data)
        assert "JSON" in result or "chars" in result

    def test_long_code(self):
        code = "def main():\n" + "    pass\n" * 200
        result = _summarize_tool_result(code)
        assert "Code" in result or "lines" in result

    def test_long_error(self):
        error = "Error: file not found\nTraceback:\n" + "  line\n" * 200
        result = _summarize_tool_result(error)
        assert "Error" in result or "lines" in result
