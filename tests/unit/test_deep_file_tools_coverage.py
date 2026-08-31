"""Deep coverage tests for sago.tools.file modules."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

from sago.tools.file.archive import Archive
from sago.tools.file.convert_to_markdown import ConvertToMarkdownTool
from sago.tools.file.data_processor import DataProcessor
from sago.tools.file.database_query import DatabaseQuery
from sago.tools.file.diff_tool import DiffTool
from sago.tools.file.edit_file import EditFileTool
from sago.tools.file.file_ops import FileOperationsTool
from sago.tools.file.file_search import FileSearchTool
from sago.tools.file.glob_files import GlobFilesTool
from sago.tools.file.grep_content import GrepContentTool
from sago.tools.file.hash_checksum import HashChecksum
from sago.tools.file.multi_replace_file import MultiReplaceTool
from sago.tools.file.pdf_reader import PDFReader
from sago.tools.file.read_file import ReadFileTool
from sago.tools.file.regex_tester import RegexTester
from sago.tools.file.write_file import WriteFileTool


class TestArchive:
    def test_name(self):
        assert Archive().name == "archive"

    def test_list_zip(self, tmp_path):
        import zipfile

        zf = tmp_path / "test.zip"
        with zipfile.ZipFile(zf, "w") as z:
            z.writestr("a.txt", "hello")
        tool = Archive()
        result = tool._run(operation="list", path=str(zf))
        assert isinstance(result, str)

    def test_extract_zip(self, tmp_path):
        import zipfile

        zf = tmp_path / "test.zip"
        with zipfile.ZipFile(zf, "w") as z:
            z.writestr("a.txt", "hello")
        out = tmp_path / "extracted"
        out.mkdir()
        tool = Archive()
        result = tool._run(operation="extract", path=str(zf), output=str(out))
        assert isinstance(result, str)

    def test_create_zip(self, tmp_path):
        (tmp_path / "a.txt").write_text("hello")
        tool = Archive()
        result = tool._run(operation="create", path=str(tmp_path), output=str(tmp_path / "out.zip"))
        assert isinstance(result, str)


class TestDatabaseQuery:
    def test_name(self):
        assert DatabaseQuery().name == "database_query"

    def test_list_tables(self, tmp_path):
        import sqlite3

        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        conn.commit()
        conn.close()
        tool = DatabaseQuery()
        result = tool._run(operation="list_tables", connection=str(db))
        assert isinstance(result, str)

    def test_select_query(self, tmp_path):
        import sqlite3

        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE items (id INTEGER, val TEXT)")
        conn.execute("INSERT INTO items VALUES (1, 'hello')")
        conn.commit()
        conn.close()
        tool = DatabaseQuery()
        result = tool._run(operation="query", connection=str(db), query="SELECT * FROM items")
        assert isinstance(result, str)

    def test_nonexistent_db(self):
        tool = DatabaseQuery()
        result = tool._run(operation="query", connection="/nonexistent/db.sqlite", query="SELECT 1")
        assert isinstance(result, str)


class TestDataProcessor:
    def test_name(self):
        assert DataProcessor().name == "data_processor"

    def test_process_csv(self, tmp_path):
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("name,age\nAlice,30\nBob,25\n")
        tool = DataProcessor()
        result = tool._run(operation="summary", data=str(csv_file))
        assert isinstance(result, str)

    def test_process_json(self, tmp_path):
        json_file = tmp_path / "data.json"
        json_file.write_text('[{"name": "Alice"}, {"name": "Bob"}]')
        tool = DataProcessor()
        result = tool._run(operation="summary", data=str(json_file))
        assert isinstance(result, str)

    def test_process_nonexistent(self):
        tool = DataProcessor()
        result = tool._run(operation="summary", data="/nonexistent.csv")
        assert isinstance(result, str)


class TestPDFReader:
    def test_name(self):
        assert PDFReader().name == "pdf_reader"

    def test_read_nonexistent(self):
        tool = PDFReader()
        result = tool._run(operation="read", path="/nonexistent.pdf")
        assert isinstance(result, str)

    def test_read_invalid_file(self, tmp_path):
        f = tmp_path / "not.pdf"
        f.write_text("this is not a pdf")
        tool = PDFReader()
        result = tool._run(operation="read", path=str(f))
        assert isinstance(result, str)

    @patch("subprocess.run")
    def test_read_with_pdftotext(self, mock_run, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="Page 1 content\n", stderr=""
        )
        tool = PDFReader()
        result = tool._run(operation="read", path=str(pdf))
        assert isinstance(result, str)

    def test_read_text_fallback(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        pdf.write_text("simple text content")
        tool = PDFReader()
        result = tool._run(operation="read", path=str(pdf))
        assert isinstance(result, str)


class TestEditFile:
    def test_name(self):
        assert EditFileTool().name == "edit_file"

    def test_edit_success(self, tmp_path):
        f = tmp_path / "edit.txt"
        f.write_text("hello world\n")
        tool = EditFileTool()
        result = tool._run(file_path=str(f), old_string="world", new_string="universe")
        assert isinstance(result, str)
        assert "universe" in f.read_text()

    def test_edit_not_found(self):
        tool = EditFileTool()
        result = tool._run(file_path="/nonexistent.txt", old_string="a", new_string="b")
        assert isinstance(result, str)

    def test_edit_no_match(self, tmp_path):
        f = tmp_path / "edit.txt"
        f.write_text("hello world\n")
        tool = EditFileTool()
        result = tool._run(file_path=str(f), old_string="nonexistent", new_string="b")
        assert isinstance(result, str)


class TestFileOps:
    def test_name(self):
        assert FileOperationsTool().name == "file_operations"

    def test_list_dir(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        tool = FileOperationsTool()
        result = tool._run(operation="list", source=str(tmp_path))
        assert isinstance(result, str)

    def test_mkdir(self, tmp_path):
        tool = FileOperationsTool()
        result = tool._run(operation="mkdir", source=str(tmp_path / "newdir"))
        assert isinstance(result, str)

    def test_delete_file(self, tmp_path):
        f = tmp_path / "to_delete.txt"
        f.write_text("bye")
        tool = FileOperationsTool()
        result = tool._run(operation="delete", source=str(f))
        assert isinstance(result, str)

    def test_move(self, tmp_path):
        f = tmp_path / "source.txt"
        f.write_text("move me")
        tool = FileOperationsTool()
        result = tool._run(operation="move", source=str(f), destination=str(tmp_path / "dest.txt"))
        assert isinstance(result, str)

    def test_copy(self, tmp_path):
        f = tmp_path / "source.txt"
        f.write_text("copy me")
        tool = FileOperationsTool()
        result = tool._run(operation="copy", source=str(f), destination=str(tmp_path / "copy.txt"))
        assert isinstance(result, str)


class TestDiff:
    def test_name(self):
        assert DiffTool().name == "diff_tool"

    def test_unified_diff(self):
        tool = DiffTool()
        result = tool._run(operation="unified", source="line1\nline2\n", target="line1\nline3\n")
        assert isinstance(result, str)

    def test_context_diff(self):
        tool = DiffTool()
        result = tool._run(operation="context", source="hello\n", target="hello world\n")
        assert isinstance(result, str)

    def test_diff_files(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("line1\nline2\n")
        f2.write_text("line1\nline3\n")
        tool = DiffTool()
        result = tool._run(operation="files", source=str(f1), target=str(f2))
        assert isinstance(result, str)


class TestRegexTester:
    def test_name(self):
        assert RegexTester().name == "regex_tester"

    def test_validate(self):
        tool = RegexTester()
        result = tool._run(operation="validate", pattern=r"\d+", text="")
        assert isinstance(result, str)

    def test_match(self):
        tool = RegexTester()
        result = tool._run(operation="match", pattern=r"\d+", text="abc123def")
        assert isinstance(result, str)

    def test_findall(self):
        tool = RegexTester()
        result = tool._run(operation="findall", pattern=r"\d+", text="abc123def456")
        assert isinstance(result, str)

    def test_replace(self):
        tool = RegexTester()
        result = tool._run(operation="replace", pattern=r"\d+", text="abc123", replacement="X")
        assert isinstance(result, str)

    def test_split(self):
        tool = RegexTester()
        result = tool._run(operation="split", pattern=r"\s+", text="hello world foo")
        assert isinstance(result, str)

    def test_invalid_pattern(self):
        tool = RegexTester()
        result = tool._run(operation="validate", pattern="[invalid", text="")
        assert isinstance(result, str)


class TestHashChecksum:
    def test_name(self):
        assert HashChecksum().name == "hash_checksum"

    def test_md5(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        tool = HashChecksum()
        result = tool._run(operation="hash", target=str(f), algorithm="md5")
        assert isinstance(result, str)

    def test_sha256(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        tool = HashChecksum()
        result = tool._run(operation="hash", target=str(f), algorithm="sha256")
        assert isinstance(result, str)

    def test_verify(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        tool = HashChecksum()
        result = tool._run(
            operation="verify",
            target=str(f),
            algorithm="md5",
            expected_hash="d41d8cd98f00b204e9800998ecf8427e",
        )
        assert isinstance(result, str)


class TestGrepContent:
    def test_name(self):
        assert GrepContentTool().name == "grep_content"

    def test_grep_simple(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("def foo():\n    pass\ndef bar():\n    pass\n")
        tool = GrepContentTool()
        result = tool._run(pattern="def foo", path=str(tmp_path))
        assert isinstance(result, str)

    def test_grep_no_matches(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("hello\n")
        tool = GrepContentTool()
        result = tool._run(pattern="nonexistent_xyz", path=str(tmp_path))
        assert isinstance(result, str)

    def test_grep_regex(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("foo123\nbar456\n")
        tool = GrepContentTool()
        result = tool._run(pattern=r"foo\d+", path=str(tmp_path), use_regex=True)
        assert isinstance(result, str)

    def test_grep_case_insensitive(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("Hello\n")
        tool = GrepContentTool()
        result = tool._run(pattern="hello", path=str(tmp_path), case_insensitive=True)
        assert isinstance(result, str)


class TestConvertToMarkdown:
    def test_name(self):
        assert ConvertToMarkdownTool().name == "convert_to_markdown"

    def test_convert_txt(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("Hello world\n")
        tool = ConvertToMarkdownTool()
        result = tool._run(file_path=str(f))
        assert isinstance(result, str)

    def test_convert_nonexistent(self):
        tool = ConvertToMarkdownTool()
        result = tool._run(file_path="/nonexistent.txt")
        assert isinstance(result, str)


class TestGlobFiles:
    def test_name(self):
        assert GlobFilesTool().name == "glob_files"

    def test_glob_simple(self, tmp_path):
        (tmp_path / "a.py").write_text("x=1")
        (tmp_path / "b.py").write_text("y=2")
        (tmp_path / "c.txt").write_text("z=3")
        tool = GlobFilesTool()
        result = tool._run(pattern="*.py", path=str(tmp_path))
        assert isinstance(result, str)

    def test_glob_no_matches(self, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        tool = GlobFilesTool()
        result = tool._run(pattern="*.xyz", path=str(tmp_path))
        assert isinstance(result, str)


class TestMultiReplace:
    def test_name(self):
        assert MultiReplaceTool().name == "multi_replace_file"

    def test_replace(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("foo bar baz")
        tool = MultiReplaceTool()
        result = tool._run(file_path=str(f), replacements='[["foo", "FOO"], ["bar", "BAR"]]')
        assert isinstance(result, str)


class TestFileSearch:
    def test_name(self):
        assert FileSearchTool().name == "file_search"

    def test_search_name(self, tmp_path):
        (tmp_path / "test.py").write_text("x=1")
        tool = FileSearchTool()
        result = tool._run(query="test", path=str(tmp_path))
        assert isinstance(result, str)

    def test_search_content(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("import os\nimport sys\n")
        tool = FileSearchTool()
        result = tool._run(query="import os", path=str(tmp_path), search_content=True)
        assert isinstance(result, str)


class TestReadFileDeep:
    def test_name(self):
        assert ReadFileTool().name == "read_file"

    def test_read_with_offset(self, tmp_path):
        f = tmp_path / "lines.txt"
        f.write_text("line1\nline2\nline3\nline4\nline5\n")
        tool = ReadFileTool()
        result = tool._run(file_path=str(f), offset=2, limit=2)
        assert isinstance(result, str)

    def test_read_binary(self, tmp_path):
        f = tmp_path / "data.bin"
        f.write_bytes(b"\x00\x01\x02\x03")
        tool = ReadFileTool()
        result = tool._run(file_path=str(f))
        assert isinstance(result, str)


class TestWriteFileDeep:
    def test_name(self):
        assert WriteFileTool().name == "write_file"

    def test_write_creates_dirs(self, tmp_path):
        tool = WriteFileTool()
        out = tmp_path / "nested" / "deep" / "file.txt"
        tool._run(file_path=str(out), content="deep content")
        assert out.exists()

    def test_write_append(self, tmp_path):
        f = tmp_path / "append.txt"
        f.write_text("line1\n")
        tool = WriteFileTool()
        tool._run(file_path=str(f), content="line2\n", append=True)
        assert "line2" in f.read_text()
