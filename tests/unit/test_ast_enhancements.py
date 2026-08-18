"""Tests for AST editor enhancements."""

from __future__ import annotations

import tempfile
from pathlib import Path


class TestPythonASTAnalysis:
    """Test enhanced Python AST analysis."""

    def test_analyze_extracts_type_annotations(self) -> None:
        """Verify type annotations are extracted from function signatures."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        code = """
def greet(name: str, count: int = 1) -> str:
    return name * count
"""
        nodes = editor.analyze(code, "python")
        func_nodes = [n for n in nodes if n.node_type == "function"]
        assert len(func_nodes) == 1
        func = func_nodes[0]
        assert func.name == "greet"
        assert func.return_type == "str"
        assert "name" in func.type_annotations
        assert func.type_annotations["name"] == "str"
        assert "count" in func.type_annotations
        assert func.type_annotations["count"] == "int"

    def test_analyze_extracts_defaults(self) -> None:
        """Verify default values are extracted."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        code = """
def connect(host: str = "localhost", port: int = 8080) -> None:
    pass
"""
        nodes = editor.analyze(code, "python")
        func = [n for n in nodes if n.node_type == "function"][0]
        assert "host" in func.defaults
        assert func.defaults["host"] == "'localhost'"
        assert "port" in func.defaults
        assert func.defaults["port"] == "8080"

    def test_analyze_detects_async_functions(self) -> None:
        """Verify async functions are detected."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        code = """
async def fetch_data() -> dict:
    return {}
"""
        nodes = editor.analyze(code, "python")
        func = [n for n in nodes if n.node_type == "function"][0]
        assert func.is_async is True
        assert "async" in func.signature

    def test_analyze_detects_private_functions(self) -> None:
        """Verify private functions are detected."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        code = """
def _internal_helper() -> None:
    pass

def public_api() -> None:
    pass
"""
        nodes = editor.analyze(code, "python")
        funcs = {n.name: n for n in nodes if n.node_type == "function"}
        assert funcs["_internal_helper"].is_private is True
        assert funcs["public_api"].is_private is False

    def test_analyze_detects_decorators(self) -> None:
        """Verify decorators are extracted."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        code = """
@property
def value(self) -> int:
    return 42

@staticmethod
def helper() -> None:
    pass
"""
        nodes = editor.analyze(code, "python")
        funcs = {n.name: n for n in nodes if n.node_type in ("function", "method")}
        assert "property" in funcs["value"].decorators
        assert "staticmethod" in funcs["helper"].decorators

    def test_analyze_detects_class_methods(self) -> None:
        """Verify methods inside classes are tracked with parent."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        code = """
class MyClass:
    def method(self) -> None:
        pass
"""
        nodes = editor.analyze(code, "python")
        methods = [n for n in nodes if n.node_type == "method"]
        assert len(methods) == 1
        assert methods[0].parent == "MyClass"

    def test_analyze_extracts_base_classes(self) -> None:
        """Verify base classes are extracted."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        code = """
class Child(ParentA, ParentB):
    pass
"""
        nodes = editor.analyze(code, "python")
        classes = [n for n in nodes if n.node_type == "class"]
        assert len(classes) == 1
        assert classes[0].base_classes == ["ParentA", "ParentB"]

    def test_analyze_extracts_variables(self) -> None:
        """Verify variable assignments are extracted."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        code = """
MAX_SIZE = 100
count: int = 0
"""
        nodes = editor.analyze(code, "python")
        vars = [n for n in nodes if n.node_type == "variable"]
        assert len(vars) >= 1
        names = [v.name for v in vars]
        assert "MAX_SIZE" in names

    def test_analyze_estimates_complexity(self) -> None:
        """Verify complexity estimation works."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        code = """
def simple():
    return 1

def complex_func(x):
    if x > 0:
        for i in range(x):
            if i % 2 == 0:
                pass
    elif x < 0:
        while x < 0:
            x += 1
    return x
"""
        nodes = editor.analyze(code, "python")
        funcs = {n.name: n for n in nodes if n.node_type == "function"}
        assert funcs["simple"].complexity_estimate == 1
        assert funcs["complex_func"].complexity_estimate > 3


class TestSyntaxValidation:
    """Test syntax validation methods."""

    def test_valid_python_syntax(self) -> None:
        """Valid Python should pass validation."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        result = editor.validate_syntax("def foo():\n    return 1", "python")
        assert result.success is True
        assert len(result.errors) == 0

    def test_invalid_python_syntax(self) -> None:
        """Invalid Python should fail with line info."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        result = editor.validate_syntax("def foo(\n    return 1", "python")
        assert result.success is False
        assert len(result.errors) > 0

    def test_validate_edit_introduces_errors(self) -> None:
        """Edit that breaks syntax should be detected."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        original = "def foo():\n    return 1"
        edited = "def foo(\n    return 1"
        result = editor.validate_edit(original, edited, "python")
        assert result.success is False

    def test_validate_edit_preserves_syntax(self) -> None:
        """Edit that preserves syntax should pass."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        original = "def foo():\n    return 1"
        edited = "def foo():\n    return 2"
        result = editor.validate_edit(original, edited, "python")
        assert result.success is True

    def test_js_balanced_braces(self) -> None:
        """JS with balanced braces should pass."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        result = editor.validate_syntax("function foo() { return 1; }", "javascript")
        assert result.success is True

    def test_js_unbalanced_braces(self) -> None:
        """JS with unbalanced braces should fail."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        result = editor.validate_syntax("function foo() { return 1;", "javascript")
        assert result.success is False


class TestStructuralDiff:
    """Test structural diffing between code versions."""

    def test_detect_added_function(self) -> None:
        """Should detect when a function is added."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        old = "def existing():\n    pass"
        new = "def existing():\n    pass\n\ndef new_func():\n    pass"
        diff = editor.diff_structures(old, new, "python")
        assert "new_func" in diff.added_functions

    def test_detect_removed_function(self) -> None:
        """Should detect when a function is removed."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        old = "def existing():\n    pass\n\ndef removed():\n    pass"
        new = "def existing():\n    pass"
        diff = editor.diff_structures(old, new, "python")
        assert "removed" in diff.removed_functions

    def test_detect_modified_function(self) -> None:
        """Should detect when a function signature changes."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        old = "def func(x: int) -> int:\n    return x"
        new = "def func(x: int, y: int) -> int:\n    return x + y"
        diff = editor.diff_structures(old, new, "python")
        assert "func" in diff.modified_functions

    def test_detect_added_class(self) -> None:
        """Should detect when a class is added."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        old = ""
        new = "class NewClass:\n    pass"
        diff = editor.diff_structures(old, new, "python")
        assert "NewClass" in diff.added_classes

    def test_detect_added_import(self) -> None:
        """Should detect when an import is added."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        old = "import os"
        new = "import os\nimport sys"
        diff = editor.diff_structures(old, new, "python")
        assert "sys" in diff.added_imports

    def test_has_changes(self) -> None:
        """has_changes should return True when there are changes."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        old = "def foo():\n    pass"
        new = "def bar():\n    pass"
        diff = editor.diff_structures(old, new, "python")
        assert diff.has_changes() is True

    def test_no_changes(self) -> None:
        """has_changes should return False when identical."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        code = "def foo():\n    pass"
        diff = editor.diff_structures(code, code, "python")
        assert diff.has_changes() is False

    def test_summary(self) -> None:
        """Summary should provide human-readable diff."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        old = "def removed():\n    pass"
        new = "def added():\n    pass"
        diff = editor.diff_structures(old, new, "python")
        summary = diff.summary()
        assert "Added" in summary
        assert "Removed" in summary


class TestSymbolResolution:
    """Test cross-file symbol resolution."""

    def test_resolve_python_class(self) -> None:
        """Should resolve a Python class definition."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "module.py"
            test_file.write_text("class MyClass:\n    pass\n", encoding="utf-8")
            result = editor.resolve_symbol("MyClass", tmpdir)
            assert result is not None
            assert result.name == "MyClass"
            assert result.kind == "class"

    def test_resolve_python_function(self) -> None:
        """Should resolve a Python function definition."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "utils.py"
            test_file.write_text("def helper() -> None:\n    pass\n", encoding="utf-8")
            result = editor.resolve_symbol("helper", tmpdir)
            assert result is not None
            assert result.name == "helper"
            assert result.kind == "function"

    def test_resolve_nonexistent_symbol(self) -> None:
        """Should return None for non-existent symbol."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "module.py"
            test_file.write_text("def foo():\n    pass\n", encoding="utf-8")
            result = editor.resolve_symbol("bar", tmpdir)
            assert result is None

    def test_resolve_across_files(self) -> None:
        """Should find symbol in any file in the directory."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "a.py").write_text("def func_a():\n    pass\n", encoding="utf-8")
            (Path(tmpdir) / "b.py").write_text("def func_b():\n    pass\n", encoding="utf-8")
            result = editor.resolve_symbol("func_b", tmpdir)
            assert result is not None
            assert result.file_path == "b.py"


class TestMultiLanguageParsing:
    """Test improved multi-language parsing."""

    def test_javascript_functions(self) -> None:
        """Should parse JS functions with return types."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        code = "function add(x, y) { return x + y; }"
        nodes = editor.analyze(code, "javascript")
        funcs = [n for n in nodes if n.node_type == "function"]
        assert len(funcs) >= 1
        assert funcs[0].name == "add"

    def test_javascript_arrow_functions(self) -> None:
        """Should parse JS arrow functions."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        code = "const multiply = (a, b) => a * b;"
        nodes = editor.analyze(code, "javascript")
        funcs = [n for n in nodes if n.node_type == "function"]
        assert len(funcs) >= 1
        assert funcs[0].name == "multiply"

    def test_javascript_classes(self) -> None:
        """Should parse JS classes with extends."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        code = "class Child extends Parent { }"
        nodes = editor.analyze(code, "javascript")
        classes = [n for n in nodes if n.node_type == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "Child"
        assert "Parent" in classes[0].base_classes

    def test_go_functions(self) -> None:
        """Should parse Go functions."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        code = "func Add(x int, y int) int { return x + y }"
        nodes = editor.analyze(code, "go")
        funcs = [n for n in nodes if n.node_type == "function"]
        assert len(funcs) >= 1
        assert funcs[0].name == "Add"

    def test_rust_functions(self) -> None:
        """Should parse Rust functions."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        code = "pub fn add(x: i32, y: i32) -> i32 { x + y }"
        nodes = editor.analyze(code, "rust")
        funcs = [n for n in nodes if n.node_type == "function"]
        assert len(funcs) >= 1
        assert funcs[0].name == "add"

    def test_java_classes(self) -> None:
        """Should parse Java classes."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        code = "public class MyClass extends BaseClass { }"
        nodes = editor.analyze(code, "java")
        classes = [n for n in nodes if n.node_type == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "MyClass"

    def test_cpp_classes(self) -> None:
        """Should parse C++ classes."""
        from sago.tools.coding.ast_editor import ASTEditor

        editor = ASTEditor()
        code = "class Derived : public Base { };"
        nodes = editor.analyze(code, "cpp")
        classes = [n for n in nodes if n.node_type == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "Derived"
