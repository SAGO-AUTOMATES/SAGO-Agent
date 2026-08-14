"""Tests for new features: learning, change_tracker, indexer, ast_editor, project_instructions, lsp_client, compaction."""


import pytest


class TestLearningStore:
    """Tests for the learning system."""

    def test_record_success(self, tmp_path):
        from sago.learning import LearningStore
        store = LearningStore()
        store._path = tmp_path / "learning.json"
        store._data = {"successful_patterns": {}, "failed_patterns": {}, "tool_effectiveness": {}, "language_patterns": {}, "error_fixes": {}}

        store.record_success("create", ["write_file", "execute_shell"], "Created Flask app")
        assert "create" in store._data["successful_patterns"]
        assert len(store._data["successful_patterns"]["create"]) == 1
        assert store._data["successful_patterns"]["create"][0]["tools"] == ["write_file", "execute_shell"]

    def test_record_failure(self, tmp_path):
        from sago.learning import LearningStore
        store = LearningStore()
        store._path = tmp_path / "learning.json"
        store._data = {"successful_patterns": {}, "failed_patterns": {}, "tool_effectiveness": {}, "language_patterns": {}, "error_fixes": {}}

        store.record_failure("fix", "ImportError: module not found", "Missing dependency")
        assert "fix" in store._data["failed_patterns"]
        assert store._data["failed_patterns"]["fix"][0]["error"] == "ImportError: module not found"

    def test_record_error_fix(self, tmp_path):
        from sago.learning import LearningStore
        store = LearningStore()
        store._path = tmp_path / "learning.json"
        store._data = {"successful_patterns": {}, "failed_patterns": {}, "tool_effectiveness": {}, "language_patterns": {}, "error_fixes": {}}

        store.record_error_fix("ImportError: module not found", "pip install the module")
        assert len(store._data["error_fixes"]) == 1

    def test_get_known_fixes(self, tmp_path):
        from sago.learning import LearningStore
        store = LearningStore()
        store._path = tmp_path / "learning.json"
        store._data = {"successful_patterns": {}, "failed_patterns": {}, "tool_effectiveness": {}, "language_patterns": {}, "error_fixes": {}}

        store.record_error_fix("ImportError: module not found", "pip install the module")
        fix = store.get_known_fixes("ImportError: module not found in code")
        assert fix == "pip install the module"

    def test_tool_effectiveness(self, tmp_path):
        from sago.learning import LearningStore
        store = LearningStore()
        store._path = tmp_path / "learning.json"
        store._data = {"successful_patterns": {}, "failed_patterns": {}, "tool_effectiveness": {}, "language_patterns": {}, "error_fixes": {}}

        store.record_tool_effectiveness("write_file", True)
        store.record_tool_effectiveness("write_file", True)
        store.record_tool_effectiveness("write_file", False)

        stats = store.get_tool_stats()
        assert stats["write_file"]["total_uses"] == 3
        assert stats["write_file"]["success_rate"] == pytest.approx(0.667, abs=0.01)

    def test_suggest_approach(self, tmp_path):
        from sago.learning import LearningStore
        store = LearningStore()
        store._path = tmp_path / "learning.json"
        store._data = {"successful_patterns": {}, "failed_patterns": {}, "tool_effectiveness": {}, "language_patterns": {}, "error_fixes": {}}

        store.record_success("create", ["write_file", "execute_shell"], "Created Flask app")
        suggestion = store.suggest_approach("create", ["write_file", "execute_shell"])
        assert suggestion == "Created Flask app"


class TestChangeTracker:
    """Tests for the change tracking system."""

    def test_track_create(self, tmp_path):
        from sago.memory.change_tracker import ChangeTracker
        tracker = ChangeTracker(session_id="test")
        tracker._backup_dir = tmp_path / "backups"

        change = tracker.track_create(str(tmp_path / "test.txt"), "hello")
        assert change.action == "create"
        assert change.content_after == "hello"
        assert len(tracker.changes) == 1

    def test_track_modify(self, tmp_path):
        from sago.memory.change_tracker import ChangeTracker
        tracker = ChangeTracker(session_id="test")
        tracker._backup_dir = tmp_path / "backups"

        test_file = tmp_path / "test.txt"
        test_file.write_text("original")

        change = tracker.track_modify(str(test_file), "original", "modified")
        assert change.action == "modify"
        assert change.content_before == "original"
        assert change.content_after == "modified"
        assert change.backup_path is not None

    def test_undo_create(self, tmp_path):
        from sago.memory.change_tracker import ChangeTracker
        tracker = ChangeTracker(session_id="test")
        tracker._backup_dir = tmp_path / "backups"

        test_file = tmp_path / "test.txt"
        test_file.write_text("created")

        tracker.track_create(str(test_file), "created")
        assert test_file.exists()

        undone = tracker.undo_last()
        assert undone == str(test_file)
        assert not test_file.exists()

    def test_undo_modify(self, tmp_path):
        from sago.memory.change_tracker import ChangeTracker
        tracker = ChangeTracker(session_id="test")
        tracker._backup_dir = tmp_path / "backups"

        test_file = tmp_path / "test.txt"
        test_file.write_text("original")

        tracker.track_modify(str(test_file), "original", "modified")
        test_file.write_text("modified")

        undone = tracker.undo_last()
        assert undone == str(test_file)
        assert test_file.read_text() == "original"

    def test_get_summary(self, tmp_path):
        from sago.memory.change_tracker import ChangeTracker
        tracker = ChangeTracker(session_id="test")
        tracker._backup_dir = tmp_path / "backups"

        tracker.track_create(str(tmp_path / "a.txt"), "a")
        tracker.track_modify(str(tmp_path / "b.txt"), "old", "new")

        summary = tracker.get_summary()
        assert summary["total"] == 2
        assert summary["created"] == 1
        assert summary["modified"] == 1


class TestCodebaseIndexer:
    """Tests for the codebase indexer."""

    def test_index_directory(self, tmp_path):
        from sago.memory.codebase_indexer import CodebaseIndexer
        indexer = CodebaseIndexer()

        (tmp_path / "test.py").write_text("def hello():\n    print('hi')\n\ndef world():\n    print('world')")
        (tmp_path / "app.js").write_text("function greet() {\n    console.log('hello');\n}")

        count = indexer.index_directory(str(tmp_path))
        assert count > 0

    def test_search(self, tmp_path):
        from sago.memory.codebase_indexer import CodebaseIndexer
        indexer = CodebaseIndexer()

        (tmp_path / "auth.py").write_text("def check_permission(user):\n    return user.is_admin")
        (tmp_path / "main.py").write_text("def main():\n    run_app()")

        indexer.index_directory(str(tmp_path))
        results = indexer.search("permission check")
        assert len(results) > 0
        assert "auth" in results[0].chunk.file_path

    def test_python_chunking(self, tmp_path):
        from sago.memory.codebase_indexer import CodebaseIndexer
        indexer = CodebaseIndexer()

        code = "import os\n\ndef hello():\n    pass\n\nclass Foo:\n    pass"
        (tmp_path / "test.py").write_text(code)

        indexer.index_directory(str(tmp_path))
        names = [c.name for c in indexer._chunks if c.name]
        assert "hello" in names
        assert "Foo" in names


class TestASTEditor:
    """Tests for the AST editor."""

    def test_analyze_python(self):
        from sago.tools.coding.ast_editor import ASTEditor
        editor = ASTEditor()

        code = "def hello():\n    pass\n\nclass Foo:\n    def bar(self):\n        pass"
        nodes = editor.analyze(code, "python")

        assert len(nodes) >= 2
        names = [n.name for n in nodes]
        assert "hello" in names
        assert "Foo" in names

    def test_replace_function_python(self):
        from sago.tools.coding.ast_editor import ASTEditor
        editor = ASTEditor()

        code = "def hello():\n    print('old')\n"
        result = editor.replace_function(code, "hello", "print('new')")

        assert result is not None
        assert "print('new')" in result
        assert "def hello():" in result

    def test_replace_function_javascript(self):
        from sago.tools.coding.ast_editor import ASTEditor
        editor = ASTEditor()

        code = "function hello() {\n    console.log('old');\n}"
        result = editor.replace_function(code, "hello", "console.log('new');", language="javascript")

        assert result is not None
        assert "console.log('new')" in result
        assert "function hello()" in result

    def test_replace_function_go(self):
        from sago.tools.coding.ast_editor import ASTEditor
        editor = ASTEditor()

        code = "func hello() {\n\tfmt.Println(\"old\")\n}"
        result = editor.replace_function(code, "hello", 'fmt.Println("new")', language="go")

        assert result is not None
        assert "fmt.Println" in result

    def test_replace_function_rust(self):
        from sago.tools.coding.ast_editor import ASTEditor
        editor = ASTEditor()

        code = "fn hello() {\n    println!(\"old\");\n}"
        result = editor.replace_function(code, "hello", 'println!("new");', language="rust")

        assert result is not None
        assert "println!" in result

    def test_replace_function_java(self):
        from sago.tools.coding.ast_editor import ASTEditor
        editor = ASTEditor()

        code = "public void hello() {\n    System.out.println(\"old\");\n}"
        result = editor.replace_function(code, "hello", 'System.out.println("new");', language="java")

        assert result is not None
        assert "System.out.println" in result

    def test_rename_symbol(self):
        from sago.tools.coding.ast_editor import ASTEditor
        editor = ASTEditor()

        code = "def old_name():\n    return old_name()"
        result = editor.rename_symbol(code, "old_name", "new_name")

        assert "new_name" in result
        assert "old_name" not in result

    def test_add_import(self):
        from sago.tools.coding.ast_editor import ASTEditor
        editor = ASTEditor()

        code = "def main():\n    pass"
        result = editor.add_import(code, "import os")

        assert "import os" in result
        assert "def main():" in result

    def test_add_import_javascript(self):
        from sago.tools.coding.ast_editor import ASTEditor
        editor = ASTEditor()

        code = "function main() {}"
        result = editor.add_import(code, 'import React from "react";', language="javascript")

        assert 'import React' in result

    def test_add_import_go(self):
        from sago.tools.coding.ast_editor import ASTEditor
        editor = ASTEditor()

        code = 'package main\n\nfunc main() {}'
        result = editor.add_import(code, '"fmt"', language="go")

        assert '"fmt"' in result

    def test_add_import_rust(self):
        from sago.tools.coding.ast_editor import ASTEditor
        editor = ASTEditor()

        code = "fn main() {}"
        result = editor.add_import(code, "use std::io;", language="rust")

        assert "use std::io;" in result

    def test_add_import_java(self):
        from sago.tools.coding.ast_editor import ASTEditor
        editor = ASTEditor()

        code = "public class Main {}"
        result = editor.add_import(code, "import java.util.List;", language="java")

        assert "import java.util.List;" in result

    def test_add_import_cpp(self):
        from sago.tools.coding.ast_editor import ASTEditor
        editor = ASTEditor()

        code = "int main() {}"
        result = editor.add_import(code, "#include <iostream>", language="cpp")

        assert "#include <iostream>" in result

    def test_analyze_javascript(self):
        from sago.tools.coding.ast_editor import ASTEditor
        editor = ASTEditor()

        code = "function hello() {}\nconst greet = () => {}"
        nodes = editor.analyze(code, "javascript")

        assert len(nodes) >= 1

    def test_analyze_go(self):
        from sago.tools.coding.ast_editor import ASTEditor
        editor = ASTEditor()

        code = 'func hello() {}\ntype Foo struct {}'
        nodes = editor.analyze(code, "go")

        assert len(nodes) >= 2
        names = [n.name for n in nodes]
        assert "hello" in names
        assert "Foo" in names

    def test_analyze_rust(self):
        from sago.tools.coding.ast_editor import ASTEditor
        editor = ASTEditor()

        code = "fn hello() {}\nstruct Foo {}\nenum Bar {}\ntrait Baz {}"
        nodes = editor.analyze(code, "rust")

        assert len(nodes) >= 4
        names = [n.name for n in nodes]
        assert "hello" in names
        assert "Foo" in names
        assert "Bar" in names
        assert "Baz" in names

    def test_analyze_java(self):
        from sago.tools.coding.ast_editor import ASTEditor
        editor = ASTEditor()

        code = 'public class Foo extends Bar implements Baz {\n    public void hello() {}\n}'
        nodes = editor.analyze(code, "java")

        assert len(nodes) >= 2
        names = [n.name for n in nodes]
        assert "Foo" in names
        assert "hello" in names

    def test_analyze_cpp(self):
        from sago.tools.coding.ast_editor import ASTEditor
        editor = ASTEditor()

        code = "int main() {\n    return 0;\n}\nstruct Foo {}"
        nodes = editor.analyze(code, "cpp")

        assert len(nodes) >= 2


class TestProjectInstructions:
    """Tests for project instructions loading."""

    def test_find_instruction_file(self, tmp_path):
        from sago.memory.project_instructions import ProjectInstructions

        (tmp_path / "CLAUDE.md").write_text("# Instructions\nDo stuff")

        pi = ProjectInstructions(cwd=str(tmp_path))
        result = pi.load()

        assert "Instructions" in result

    def test_loads_all_md_files(self, tmp_path):
        from sago.memory.project_instructions import ProjectInstructions

        (tmp_path / "README.md").write_text("# My Project\nThis is a project.")
        (tmp_path / "AGENTS.md").write_text("# Agent Rules\nBe helpful.")
        (tmp_path / "CONTRIBUTING.md").write_text("# Contributing\nFollow PEP 8.")

        pi = ProjectInstructions(cwd=str(tmp_path))
        result = pi.load()

        assert "My Project" in result
        assert "Agent Rules" in result
        assert "Contributing" in result

    def test_priority_files_loaded_first(self, tmp_path):
        from sago.memory.project_instructions import ProjectInstructions

        # Create files in reverse order
        (tmp_path / "README.md").write_text("README content")
        (tmp_path / "CLAUDE.md").write_text("CLAUDE content")

        pi = ProjectInstructions(cwd=str(tmp_path))
        result = pi.load()

        # CLAUDE.md should appear before README.md
        claude_pos = result.find("CLAUDE content")
        readme_pos = result.find("README content")
        assert claude_pos < readme_pos

    def test_loads_sago_instructions(self, tmp_path):
        from sago.memory.project_instructions import ProjectInstructions

        sago_dir = tmp_path / ".sago"
        sago_dir.mkdir()
        (sago_dir / "instructions.md").write_text("# Sago Rules\nUse sago conventions.")

        pi = ProjectInstructions(cwd=str(tmp_path))
        result = pi.load()

        assert "Sago Rules" in result

    def test_no_instruction_file(self, tmp_path):
        from sago.memory.project_instructions import ProjectInstructions

        pi = ProjectInstructions(cwd=str(tmp_path))
        result = pi.load()

        assert result == ""

    def test_get_for_prompt(self, tmp_path):
        from sago.memory.project_instructions import ProjectInstructions

        (tmp_path / "CLAUDE.md").write_text("# Rules\nBe helpful")

        pi = ProjectInstructions(cwd=str(tmp_path))
        prompt = pi.get_for_prompt()

        assert "PROJECT INSTRUCTIONS" in prompt
        assert "Be helpful" in prompt

    def test_create_default(self, tmp_path):
        from sago.memory.project_instructions import ProjectInstructions

        path = ProjectInstructions.create_default("python", str(tmp_path))
        assert path.exists()
        assert "PEP 8" in path.read_text()

    def test_get_metadata(self, tmp_path):
        from sago.memory.project_instructions import ProjectInstructions

        (tmp_path / "README.md").write_text("# Project\nDescription")
        (tmp_path / "CLAUDE.md").write_text("# Rules\nRule 1")

        pi = ProjectInstructions(cwd=str(tmp_path))
        pi.load()
        meta = pi.get_metadata()

        assert meta["file_count"] == 2
        assert meta["total_size"] > 0


class TestLSPClient:
    """Tests for the LSP client."""

    def test_detect_language_python(self):
        from sago.tools.coding.lsp_client import _detect_language
        assert _detect_language("test.py") == "python"

    def test_detect_language_javascript(self):
        from sago.tools.coding.lsp_client import _detect_language
        assert _detect_language("app.js") == "javascript"
        assert _detect_language("app.jsx") == "javascript"

    def test_detect_language_typescript(self):
        from sago.tools.coding.lsp_client import _detect_language
        assert _detect_language("app.ts") == "typescript"
        assert _detect_language("app.tsx") == "typescript"

    def test_detect_language_go(self):
        from sago.tools.coding.lsp_client import _detect_language
        assert _detect_language("main.go") == "go"

    def test_detect_language_rust(self):
        from sago.tools.coding.lsp_client import _detect_language
        assert _detect_language("main.rs") == "rust"

    def test_detect_language_java(self):
        from sago.tools.coding.lsp_client import _detect_language
        assert _detect_language("Main.java") == "java"

    def test_detect_language_c(self):
        from sago.tools.coding.lsp_client import _detect_language
        assert _detect_language("main.c") == "c"
        assert _detect_language("main.h") == "c"

    def test_detect_language_cpp(self):
        from sago.tools.coding.lsp_client import _detect_language
        assert _detect_language("main.cpp") == "cpp"
        assert _detect_language("main.hpp") == "cpp"

    def test_check_types_nonexistent(self):
        from sago.tools.coding.lsp_client import LSPClient
        client = LSPClient()
        result = client.check_types("/nonexistent/file.py")
        assert result == []

    def test_get_completions(self):
        from sago.tools.coding.lsp_client import LSPClient
        client = LSPClient()
        # Basic test - completions from file content
        result = client.get_completions("/nonexistent/file.py", 1, 0)
        assert isinstance(result, list)

    def test_format_code_unsupported(self):
        from sago.tools.coding.lsp_client import LSPClient
        client = LSPClient()
        result = client.format_code("/nonexistent/file.xyz")
        assert result is None

    def test_all_language_servers_configured(self):
        from sago.tools.coding.lsp_client import LANGUAGE_SERVERS
        expected_langs = ["python", "javascript", "typescript", "go", "rust", "java", "c", "cpp"]
        for lang in expected_langs:
            assert lang in LANGUAGE_SERVERS
            assert "cli_check" in LANGUAGE_SERVERS[lang]
            assert "ext" in LANGUAGE_SERVERS[lang]


class TestSessionCompaction:
    """Tests for session compaction."""

    def test_compaction_not_needed(self):
        from sago.memory.compaction import SessionCompactor
        compactor = SessionCompactor(max_context_tokens=1000)

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        result = compactor.build_context_window(messages, system_prompt="You are helpful", max_tokens=1000)
        assert len(result) == 3  # system + 2 messages

    def test_compaction_needed(self):
        from sago.memory.compaction import SessionCompactor
        compactor = SessionCompactor(max_context_tokens=100)

        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "x " * 1000},
            {"role": "assistant", "content": "y " * 1000},
            {"role": "user", "content": "z " * 1000},
        ]
        result = compactor.build_context_window(messages, max_tokens=100)
        # Should have system + compacted context + recent messages
        assert len(result) < len(messages) + 1

    def test_should_compact(self):
        from sago.memory.compaction import SessionCompactor
        compactor = SessionCompactor(max_context_tokens=100)

        short_messages = [{"role": "user", "content": "hello"}]
        assert not compactor.should_compact(short_messages)

        long_messages = [{"role": "user", "content": "x " * 1000}]
        assert compactor.should_compact(long_messages)

    def test_compact_messages(self):
        from sago.memory.compaction import SessionCompactor
        compactor = SessionCompactor(max_context_tokens=100)

        messages = [
            {"role": "user", "content": "Decided to use Python"},
            {"role": "assistant", "content": "OK"},
            {"role": "user", "content": "Will implement the feature"},
            {"role": "assistant", "content": "Done"},
        ]
        result = compactor.compact_messages(messages)
        assert result.summary != ""
        assert result.original_length > 0

    def test_input_summarizer(self):
        from sago.memory.compaction import InputSummarizer
        summarizer = InputSummarizer()

        short_text = "Hello world"
        assert not summarizer.should_summarize(short_text)
        assert summarizer.summarize_input(short_text) == short_text

        long_text = "error: something failed\n" * 100 + "line\n" * 500
        assert summarizer.should_summarize(long_text)
        summary = summarizer.summarize_input(long_text)
        assert "error" in summary.lower() or "Error" in summary
