"""Deep coverage tests for sago.tools.coding modules."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from sago.tools.coding.ast_grep import AstGrepTool
from sago.tools.coding.code_search_tool import CodeSearchTool
from sago.tools.coding.debugger import DebuggerTool
from sago.tools.coding.formatter import FormatterTool
from sago.tools.coding.git_blame import GitBlameTool
from sago.tools.coding.hybrid_search_tool import HybridSearchTool
from sago.tools.coding.linter import LinterTool
from sago.tools.coding.log_analyzer import LogAnalyzerTool
from sago.tools.coding.repo_map_tool import RepoMapTool
from sago.tools.coding.scaffold import ScaffoldTool
from sago.tools.coding.search_symbol_tool import SearchSymbolsTool
from sago.tools.coding.test_runner import TestRunnerTool
from sago.tools.coding.text_summarizer import TextSummarizer
from sago.tools.coding.type_check_tool import TypeCheckTool


class TestTestRunner:
    def test_name(self):
        assert TestRunnerTool().name == "test_runner"

    @patch("subprocess.run")
    def test_run_pytest(self, mock_run, tmp_path):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="2 passed", stderr=""
        )
        tool = TestRunnerTool()
        result = tool._run(path=str(tmp_path), framework="pytest")
        assert isinstance(result, str)

    @patch("subprocess.run")
    def test_run_npm(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="all tests passed", stderr=""
        )
        tool = TestRunnerTool()
        result = tool._run(path="/tmp", framework="npm")
        assert isinstance(result, str)

    @patch("subprocess.run")
    def test_run_failure(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="error occurred"
        )
        tool = TestRunnerTool()
        result = tool._run(path="/tmp", framework="pytest")
        assert isinstance(result, str)


class TestLogAnalyzer:
    def test_name(self):
        assert LogAnalyzerTool().name == "log_analyzer"

    def test_analyze_log_content(self, tmp_path):
        log_file = tmp_path / "app.log"
        log_file.write_text(
            "2024-01-01 ERROR Something broke\n"
            "2024-01-01 WARNING Slow query\n"
            "2024-01-01 INFO All good\n"
            "Traceback (most recent call last):\n"
            "  File 'app.py', line 10\n"
            "ValueError: bad value\n"
        )
        tool = LogAnalyzerTool()
        result = tool._run(file_path=str(log_file))
        assert isinstance(result, str)

    def test_analyze_nonexistent_file(self):
        tool = LogAnalyzerTool()
        result = tool._run(file_path="/nonexistent/log.txt")
        assert isinstance(result, str)

    def test_analyze_empty_log(self, tmp_path):
        log_file = tmp_path / "empty.log"
        log_file.write_text("")
        tool = LogAnalyzerTool()
        result = tool._run(file_path=str(log_file))
        assert isinstance(result, str)

    def test_with_pattern(self, tmp_path):
        log_file = tmp_path / "app.log"
        log_file.write_text("ERROR line\nINFO line\nWARNING line\n")
        tool = LogAnalyzerTool()
        result = tool._run(file_path=str(log_file), pattern="ERROR")
        assert isinstance(result, str)

    def test_with_severity(self, tmp_path):
        log_file = tmp_path / "app.log"
        log_file.write_text("ERROR line\nINFO line\n")
        tool = LogAnalyzerTool()
        result = tool._run(file_path=str(log_file), severity="error")
        assert isinstance(result, str)


class TestTypeCheckTool:
    def test_name(self):
        assert TypeCheckTool().name == "type_check"

    @patch("subprocess.run")
    def test_run_check(self, mock_run, tmp_path):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="Success: no issues found", stderr=""
        )
        tool = TypeCheckTool()
        result = tool._run(file_path=str(tmp_path))
        assert isinstance(result, str)

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_checker_not_installed(self, mock_run):
        tool = TypeCheckTool()
        result = tool._run(file_path="/tmp")
        assert isinstance(result, str)

    @patch("subprocess.run")
    def test_run_with_errors(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="error: Incompatible types", stderr=""
        )
        tool = TypeCheckTool()
        result = tool._run(file_path="/tmp")
        assert isinstance(result, str)


class TestTextSummarizer:
    def test_name(self):
        assert TextSummarizer().name == "text_summarizer"

    def test_summarize_text(self):
        tool = TextSummarizer()
        result = tool._run(
            operation="summarize", text="Hello world. This is a test. Another sentence."
        )
        assert isinstance(result, str)

    def test_summarize_empty(self):
        tool = TextSummarizer()
        result = tool._run(operation="summarize", text="")
        assert isinstance(result, str)

    def test_extract_keywords(self):
        tool = TextSummarizer()
        result = tool._run(
            operation="keywords", text="Python programming language is great for coding"
        )
        assert isinstance(result, str)

    def test_extract_entities(self):
        tool = TextSummarizer()
        result = tool._run(
            operation="entities", text="Apple is based in Cupertino and Google in Mountain View"
        )
        assert isinstance(result, str)

    def test_with_max_sentences(self):
        tool = TextSummarizer()
        result = tool._run(
            operation="summarize", text="One. Two. Three. Four. Five.", max_sentences=2
        )
        assert isinstance(result, str)


class TestDebugger:
    def test_name(self):
        assert DebuggerTool().name == "debugger"

    @patch("subprocess.run")
    def test_debug_python(self, mock_run, tmp_path):
        src = tmp_path / "buggy.py"
        src.write_text("x = 1/0\n")
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="ZeroDivisionError", stderr=""
        )
        tool = DebuggerTool()
        result = tool._run(file_path=str(src))
        assert isinstance(result, str)

    def test_debug_nonexistent_file(self):
        tool = DebuggerTool()
        result = tool._run(file_path="/nonexistent.py")
        assert isinstance(result, str)

    @patch("subprocess.run")
    def test_debug_with_code_snippet(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="output", stderr=""
        )
        tool = DebuggerTool()
        result = tool._run(code_snippet="x = 1/0")
        assert isinstance(result, str)

    @patch("subprocess.run")
    def test_debug_with_error_message(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="analysis", stderr=""
        )
        tool = DebuggerTool()
        result = tool._run(error_message="ValueError: bad value")
        assert isinstance(result, str)

    @patch("subprocess.run")
    def test_debug_with_command(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="output", stderr=""
        )
        tool = DebuggerTool()
        result = tool._run(command="python script.py")
        assert isinstance(result, str)

    def test_no_input(self):
        tool = DebuggerTool()
        result = tool._run()
        assert isinstance(result, str)


class TestAstGrep:
    def test_name(self):
        assert AstGrepTool().name == "ast_grep"

    def test_search_functions(self, tmp_path):
        src = tmp_path / "code.py"
        src.write_text("def foo(): pass\ndef bar(): pass\nclass Foo: pass\n")
        tool = AstGrepTool()
        result = tool._run(pattern_type="function", name_pattern="foo", directory=str(tmp_path))
        assert isinstance(result, str)

    def test_search_classes(self, tmp_path):
        src = tmp_path / "code.py"
        src.write_text("class MyClass:\n    pass\n")
        tool = AstGrepTool()
        result = tool._run(pattern_type="class", name_pattern="MyClass", directory=str(tmp_path))
        assert isinstance(result, str)

    def test_search_imports(self, tmp_path):
        src = tmp_path / "code.py"
        src.write_text("import os\nfrom pathlib import Path\n")
        tool = AstGrepTool()
        result = tool._run(pattern_type="import", name_pattern="os", directory=str(tmp_path))
        assert isinstance(result, str)

    def test_search_decorators(self, tmp_path):
        src = tmp_path / "code.py"
        src.write_text("@decorator\ndef func(): pass\n")
        tool = AstGrepTool()
        result = tool._run(
            pattern_type="decorator", name_pattern="decorator", directory=str(tmp_path)
        )
        assert isinstance(result, str)

    def test_search_nonexistent_path(self):
        tool = AstGrepTool()
        result = tool._run(pattern_type="function", name_pattern="foo", directory="/nonexistent")
        assert isinstance(result, str)


class TestCodeSearchTool:
    def test_name(self):
        assert CodeSearchTool().name == "code_search"

    @patch("sago.memory.codebase_indexer.get_indexer")
    def test_index_action(self, mock_get_indexer):
        mock_indexer = MagicMock()
        mock_indexer.index_directory.return_value = 42
        mock_get_indexer.return_value = mock_indexer
        tool = CodeSearchTool()
        result = tool._run(action="index", path="/tmp")
        assert isinstance(result, str)

    @patch("sago.memory.codebase_indexer.get_indexer")
    def test_search_action(self, mock_get_indexer):
        mock_indexer = MagicMock()
        result_obj = MagicMock()
        result_obj.to_dict.return_value = {
            "file": "a.py",
            "start": 1,
            "end": 5,
            "score": 0.9,
            "line": 1,
            "type": "function",
            "name": "foo",
            "preview": "def foo(): pass",
        }
        mock_indexer.search.return_value = [result_obj]
        mock_get_indexer.return_value = mock_indexer
        tool = CodeSearchTool()
        result = tool._run(action="search", query="def foo")
        assert isinstance(result, str)

    @patch("sago.memory.codebase_indexer.get_indexer")
    def test_stats_action(self, mock_get_indexer):
        mock_indexer = MagicMock()
        mock_indexer.get_stats.return_value = {
            "total_chunks": 100,
            "languages": {"python": 80},
            "indexed_at": "2024-01-01",
        }
        mock_get_indexer.return_value = mock_indexer
        tool = CodeSearchTool()
        result = tool._run(action="stats")
        assert isinstance(result, str)

    def test_file_context_action(self, tmp_path):
        src = tmp_path / "code.py"
        src.write_text("def foo():\n    pass\n")
        tool = CodeSearchTool()
        result = tool._run(action="file_context", file_path=str(src))
        assert isinstance(result, str)


class TestFormatter:
    def test_name(self):
        assert FormatterTool().name == "formatter"

    @patch("subprocess.run")
    def test_format_python(self, mock_run, tmp_path):
        src = tmp_path / "code.py"
        src.write_text("x=1\n")
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="reformatted", stderr=""
        )
        tool = FormatterTool()
        result = tool._run(file_path=str(src))
        assert isinstance(result, str)

    def test_format_nonexistent(self):
        tool = FormatterTool()
        result = tool._run(file_path="/nonexistent.py")
        assert isinstance(result, str)

    @patch("subprocess.run")
    def test_format_with_formatter(self, mock_run, tmp_path):
        src = tmp_path / "code.py"
        src.write_text("x = 1\n")
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="reformatted", stderr=""
        )
        tool = FormatterTool()
        result = tool._run(file_path=str(src), formatter="ruff")
        assert isinstance(result, str)


class TestGitBlame:
    def test_name(self):
        assert GitBlameTool().name == "git_blame"

    @patch("subprocess.run")
    def test_blame(self, mock_run, tmp_path):
        (tmp_path / "file.py").write_text("line1\nline2\n")
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="abc1234 (Author 2024-01-01) line content\n", stderr=""
        )
        tool = GitBlameTool()
        result = tool._run(path=str(tmp_path / "file.py"))
        assert isinstance(result, str)

    def test_blame_not_found(self):
        tool = GitBlameTool()
        result = tool._run(path="/nonexistent/file.py")
        assert "Error" in result or "does not exist" in result

    @patch("subprocess.run")
    def test_blame_not_git(self, mock_run, tmp_path):
        (tmp_path / "file.py").write_text("line1\n")
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=128, stdout="", stderr="not a git repository"
        )
        tool = GitBlameTool()
        result = tool._run(path=str(tmp_path / "file.py"))
        assert isinstance(result, str)


class TestHybridSearch:
    def test_name(self):
        assert HybridSearchTool().name == "hybrid_code_search"

    @patch("sago.tools.coding.hybrid_search_tool.get_hybrid_code_indexer")
    def test_search(self, mock_get):
        mock_indexer = MagicMock()
        mock_indexer.search.return_value = [{"file": "a.py", "score": 0.8}]
        mock_get.return_value = mock_indexer
        tool = HybridSearchTool()
        result = tool._run(query="function that parses JSON")
        assert isinstance(result, str)

    @patch("sago.tools.coding.hybrid_search_tool.get_hybrid_code_indexer")
    def test_index(self, mock_get):
        mock_indexer = MagicMock()
        mock_indexer.index_directory.return_value = 50
        mock_get.return_value = mock_indexer
        tool = HybridSearchTool()
        result = tool._run(action="index", path="/tmp")
        assert isinstance(result, str)


class TestLinter:
    def test_name(self):
        assert LinterTool().name == "linter"

    @patch("subprocess.run")
    def test_lint_python(self, mock_run, tmp_path):
        src = tmp_path / "code.py"
        src.write_text("import os\n")
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="All checks passed", stderr=""
        )
        tool = LinterTool()
        result = tool._run(file_path=str(src))
        assert isinstance(result, str)

    def test_lint_nonexistent(self):
        tool = LinterTool()
        result = tool._run(file_path="/nonexistent.py")
        assert isinstance(result, str)

    @patch("subprocess.run")
    def test_lint_with_fix(self, mock_run, tmp_path):
        src = tmp_path / "code.py"
        src.write_text("x=1\n")
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="Fixed 1 issue", stderr=""
        )
        tool = LinterTool()
        result = tool._run(file_path=str(src), fix=True)
        assert isinstance(result, str)

    @patch("subprocess.run")
    def test_lint_with_linter(self, mock_run, tmp_path):
        src = tmp_path / "code.py"
        src.write_text("x = 1\n")
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="passed", stderr=""
        )
        tool = LinterTool()
        result = tool._run(file_path=str(src), linter="ruff")
        assert isinstance(result, str)


class TestScaffold:
    def test_name(self):
        assert ScaffoldTool().name == "scaffold_project"

    def test_scaffold_python(self, tmp_path):
        tool = ScaffoldTool()
        result = tool._run(project_type="python", project_name="myproject", path=str(tmp_path))
        assert isinstance(result, str)

    def test_scaffold_node(self, tmp_path):
        tool = ScaffoldTool()
        result = tool._run(project_type="node", project_name="myapp", path=str(tmp_path))
        assert isinstance(result, str)

    def test_scaffold_rust(self, tmp_path):
        tool = ScaffoldTool()
        result = tool._run(project_type="rust", project_name="myrust", path=str(tmp_path))
        assert isinstance(result, str)

    def test_scaffold_go(self, tmp_path):
        tool = ScaffoldTool()
        result = tool._run(project_type="go", project_name="mygo", path=str(tmp_path))
        assert isinstance(result, str)


class TestSearchSymbols:
    def test_name(self):
        assert SearchSymbolsTool().name == "search_symbols"

    @patch("sago.tools.coding.search_symbol_tool.PersistentSymbolIndex")
    def test_search(self, MockIndex):
        mock_idx = MagicMock()
        mock_idx.search_symbols.return_value = [
            {"file_path": "a.py", "type": "function", "name": "foo"}
        ]
        MockIndex.return_value = mock_idx
        tool = SearchSymbolsTool()
        result = tool._run(query="foo")
        assert isinstance(result, str)

    def test_empty_query(self):
        tool = SearchSymbolsTool()
        result = tool._run(query="")
        assert isinstance(result, str)


class TestRepoMap:
    def test_name(self):
        assert RepoMapTool().name == "repo_map"

    @patch("sago.tools.coding.repo_map_tool.SymbolGraph")
    def test_generate(self, MockGraph):
        mock_graph = MagicMock()
        mock_graph.generate_repo_map.return_value = "class Foo:\n    def bar(self): ..."
        MockGraph.return_value = mock_graph
        tool = RepoMapTool()
        result = tool._run(path="/tmp")
        assert isinstance(result, str)
