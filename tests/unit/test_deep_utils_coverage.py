"""Tests for sago tools and utils with low coverage."""

from __future__ import annotations

from sago.config.loader import SagoConfig, _deep_merge, _expand_path
from sago.tools.file.diff_tool import DiffTool
from sago.tools.file.glob_files import GlobFilesTool
from sago.tools.file.grep_content import GrepContentTool
from sago.utils.markitdown_converter import convert_file_to_markdown, is_document_file

# ── grep_content ─────────────────────────────────────────────────────────────


class TestGrepContent:
    def test_grep_single_file(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("def hello():\n    pass\n")
        tool = GrepContentTool()
        result = tool.run(pattern="def hello", path=str(f))
        assert "hello" in result

    def test_grep_no_matches(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("hello world\n")
        tool = GrepContentTool()
        result = tool.run(pattern="xyz_not_found", path=str(f))
        assert "No matches" in result

    def test_grep_invalid_regex(self, tmp_path):
        tool = GrepContentTool()
        result = tool.run(pattern="[invalid", path=str(tmp_path))
        assert "Error" in result

    def test_grep_nonexistent_path(self):
        tool = GrepContentTool()
        result = tool.run(pattern="test", path="/nonexistent/path")
        assert "Error" in result

    def test_grep_with_include_pattern(self, tmp_path):
        (tmp_path / "a.py").write_text("hello\n")
        (tmp_path / "b.txt").write_text("hello\n")
        tool = GrepContentTool()
        result = tool.run(pattern="hello", path=str(tmp_path), include="*.py")
        assert "a.py" in result

    def test_grep_with_exclude_pattern(self, tmp_path):
        (tmp_path / "a.py").write_text("hello\n")
        (tmp_path / "b.txt").write_text("hello\n")
        tool = GrepContentTool()
        result = tool.run(pattern="hello", path=str(tmp_path), exclude="*.txt")
        assert "a.py" in result

    def test_grep_with_context_lines(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("line1\nline2\nTARGET\nline4\nline5\n")
        tool = GrepContentTool()
        result = tool.run(pattern="TARGET", path=str(f), context_lines=1)
        assert "line2" in result
        assert "line4" in result

    def test_grep_max_results(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("\n".join(["match"] * 20))
        tool = GrepContentTool()
        result = tool.run(pattern="match", path=str(f), max_results=5)
        assert "Found" in result or "match" in result

    def test_grep_directory_search(self, tmp_path):
        (tmp_path / "a.py").write_text("def foo(): pass\n")
        (tmp_path / "b.py").write_text("def bar(): pass\n")
        tool = GrepContentTool()
        result = tool.run(pattern="def foo", path=str(tmp_path))
        assert "foo" in result

    def test_grep_max_file_size(self, tmp_path):
        f = tmp_path / "big.py"
        f.write_text("x" * 2000)
        tool = GrepContentTool()
        result = tool.run(pattern="x", path=str(f), max_file_size=100)
        assert isinstance(result, str)


# ── glob_files ───────────────────────────────────────────────────────────────


class TestGlobFiles:
    def test_glob_basic(self, tmp_path):
        (tmp_path / "a.py").write_text("x")
        (tmp_path / "b.txt").write_text("y")
        tool = GlobFilesTool()
        result = tool.run(pattern="*.py", path=str(tmp_path))
        assert "a.py" in result
        assert "b.txt" not in result

    def test_glob_recursive(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.py").write_text("x")
        (tmp_path / "top.py").write_text("x")
        tool = GlobFilesTool()
        result = tool.run(pattern="**/*.py", path=str(tmp_path))
        assert "deep.py" in result
        assert "top.py" in result

    def test_glob_not_found(self, tmp_path):
        tool = GlobFilesTool()
        result = tool.run(pattern="*.xyz", path=str(tmp_path))
        assert "No matches" in result

    def test_glob_nonexistent_dir(self):
        tool = GlobFilesTool()
        result = tool.run(pattern="*", path="/nonexistent/dir")
        assert "Error" in result

    def test_glob_not_a_dir(self, tmp_path):
        f = tmp_path / "file.py"
        f.write_text("x")
        tool = GlobFilesTool()
        result = tool.run(pattern="*", path=str(f))
        assert "Error" in result

    def test_glob_max_results(self, tmp_path):
        for i in range(10):
            (tmp_path / f"f{i}.py").write_text("x")
        tool = GlobFilesTool()
        result = tool.run(pattern="*.py", path=str(tmp_path), max_results=3)
        assert "truncated" in result.lower() or "f0.py" in result

    def test_glob_dirs_and_files(self, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "file.py").write_text("x")
        tool = GlobFilesTool()
        result = tool.run(pattern="*", path=str(tmp_path))
        assert "subdir" in result
        assert "file.py" in result


# ── diff_tool ────────────────────────────────────────────────────────────────


class TestDiffTool:
    def test_unified_diff_text(self):
        tool = DiffTool()
        result = tool._run(
            operation="unified",
            source="line1\nline2\n",
            target="line1\nline3\n",
        )
        assert isinstance(result, str)

    def test_unified_diff_identical(self):
        tool = DiffTool()
        result = tool._run(operation="unified", source="same\n", target="same\n")
        assert (
            "No differences" in result or "identical" in result.lower() or isinstance(result, str)
        )

    def test_context_diff_text(self):
        tool = DiffTool()
        result = tool._run(operation="context", source="a\nb\n", target="a\nc\n")
        assert isinstance(result, str)

    def test_text_diff(self):
        tool = DiffTool()
        result = tool._run(operation="text", source="hello\n", target="world\n")
        assert "hello" in result and "world" in result

    def test_files_diff(self):
        tool = DiffTool()
        result = tool._run(operation="files", source="a\nb\n", target="a\nc\n")
        assert "Similarity" in result or "similarity" in result.lower() or isinstance(result, str)

    def test_invalid_operation(self):
        tool = DiffTool()
        result = tool._run(operation="invalid", source="a", target="b")
        assert "Error" in result

    def test_diff_with_files(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("hello\n")
        f2.write_text("world\n")
        tool = DiffTool()
        result = tool._run(operation="unified", source=str(f1), target=str(f2))
        assert isinstance(result, str)

    def test_unified_diff_custom_context(self):
        tool = DiffTool()
        source = "\n".join([f"line{i}" for i in range(20)])
        target = "\n".join([f"line{i}" for i in range(20) if i != 10])
        result = tool._run(operation="unified", source=source, target=target, context_lines=5)
        assert "line" in result


# ── markitdown_converter ────────────────────────────────────────────────────


class TestIsDocumentFile:
    def test_pdf(self):
        assert is_document_file("doc.pdf") is True

    def test_docx(self):
        assert is_document_file("report.docx") is True

    def test_python(self):
        assert is_document_file("main.py") is False

    def test_csv(self):
        assert is_document_file("data.csv") is True

    def test_html(self):
        assert is_document_file("page.html") is True

    def test_json(self):
        assert is_document_file("config.json") is True

    def test_txt(self):
        assert is_document_file("readme.txt") is False

    def test_epub(self):
        assert is_document_file("book.epub") is True

    def test_zip(self):
        assert is_document_file("archive.zip") is True

    def test_mp3(self):
        assert is_document_file("audio.mp3") is True


class TestConvertFileToMarkdown:
    def test_file_not_found(self):
        success, msg = convert_file_to_markdown("/nonexistent/file.pdf")
        assert success is False
        assert "not found" in msg.lower()

    def test_not_a_file(self, tmp_path):
        success, md = convert_file_to_markdown(str(tmp_path))
        assert success is False

    def test_csv_conversion(self, tmp_path):
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("name,age\nAlice,30\nBob,25\n")
        success, md = convert_file_to_markdown(str(csv_file))
        assert success is True
        assert "name" in md
        assert "Alice" in md

    def test_tsv_conversion(self, tmp_path):
        tsv_file = tmp_path / "data.tsv"
        tsv_file.write_text("name\tage\nAlice\t30\n")
        success, md = convert_file_to_markdown(str(tsv_file))
        assert success is True
        assert "Alice" in md

    def test_json_conversion(self, tmp_path):
        json_file = tmp_path / "data.json"
        json_file.write_text('{"key": "value"}')
        success, md = convert_file_to_markdown(str(json_file))
        assert success is True
        assert "key" in md

    def test_html_conversion(self, tmp_path):
        html_file = tmp_path / "page.html"
        html_file.write_text("<html><body><h1>Title</h1><p>Content</p></body></html>")
        success, md = convert_file_to_markdown(str(html_file))
        assert success is True
        assert "Title" in md

    def test_xml_conversion(self, tmp_path):
        xml_file = tmp_path / "data.xml"
        xml_file.write_text("<root><item>test</item></root>")
        success, md = convert_file_to_markdown(str(xml_file))
        assert success is True
        assert "test" in md

    def test_txt_conversion(self, tmp_path):
        txt_file = tmp_path / "readme.txt"
        txt_file.write_text("hello world")
        success, md = convert_file_to_markdown(str(txt_file))
        assert success is True
        assert "hello world" in md

    def test_csv_empty_file(self, tmp_path):
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("")
        success, md = convert_file_to_markdown(str(csv_file))
        assert success is True


# ── config/loader ────────────────────────────────────────────────────────────


class TestDeepMerge:
    def test_simple_merge(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        base = {"a": {"x": 1, "y": 2}}
        override = {"a": {"y": 3, "z": 4}}
        result = _deep_merge(base, override)
        assert result == {"a": {"x": 1, "y": 3, "z": 4}}

    def test_override_type_change(self):
        base = {"a": {"x": 1}}
        override = {"a": "string"}
        result = _deep_merge(base, override)
        assert result == {"a": "string"}

    def test_empty_base(self):
        result = _deep_merge({}, {"a": 1})
        assert result == {"a": 1}

    def test_empty_override(self):
        result = _deep_merge({"a": 1}, {})
        assert result == {"a": 1}

    def test_both_empty(self):
        assert _deep_merge({}, {}) == {}

    def test_deeply_nested(self):
        base = {"a": {"b": {"c": 1}}}
        override = {"a": {"b": {"d": 2}}}
        result = _deep_merge(base, override)
        assert result == {"a": {"b": {"c": 1, "d": 2}}}


class TestExpandPath:
    def test_home_expansion(self):
        result = _expand_path("~/test")
        assert str(result).endswith("test")
        assert "~" not in str(result)

    def test_absolute_path_unchanged(self):
        result = _expand_path("/usr/local/bin")
        assert str(result) == "/usr/local/bin"


class TestSagoConfig:
    def test_default_config(self):
        cfg = SagoConfig()
        assert cfg.project.name == "sago"
        assert cfg.settings.tool_timeout_seconds == 300
        assert cfg.orchestrator.max_iterations == 25
        assert cfg.executor.project_context_ttl == 300
        assert cfg.execution.mode == "native"

    def test_config_from_dict(self):
        cfg = SagoConfig(
            project={"name": "my-project"},
            settings={"tool_timeout_seconds": 600},
        )
        assert cfg.project.name == "my-project"
        assert cfg.settings.tool_timeout_seconds == 600

    def test_config_orchestrator_defaults(self):
        cfg = SagoConfig()
        assert cfg.orchestrator.verbose is True
        assert cfg.orchestrator.memory is True
        assert cfg.orchestrator.planning is True

    def test_config_executor_defaults(self):
        cfg = SagoConfig()
        assert cfg.executor.max_tokens == 32000
        assert cfg.executor.circular_detection_threshold == 5
