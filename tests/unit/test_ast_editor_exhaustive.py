"""Exhaustive unit test suite for sago/tools/coding/ast_editor.py.

Validates multi-language structure analysis (Python, JS/TS, Go, Rust, Java, C/C++),
syntax validation, structural diffing, function insertion/replacement, symbol
renaming, cross-file symbol resolution, and dataclass serialization.
"""

from __future__ import annotations

from pathlib import Path

from sago.tools.coding.ast_editor import (
    ASTEditor,
    CodeNode,
    StructuralDiff,
    SymbolInfo,
    ValidationResult,
    detect_language,
    get_ast_editor,
)


def test_ast_editor_dataclasses() -> None:
    # 1. CodeNode
    node = CodeNode(
        name="calculate",
        node_type="function",
        start_line=1,
        end_line=5,
        signature="def calculate(x: int) -> int",
        return_type="int",
        type_annotations={"x": "int"},
        defaults={"x": "0"},
        is_async=True,
        is_private=False,
        is_static=False,
        is_classmethod=False,
        is_property=False,
        base_classes=["Base"],
        imports_from=["typing"],
        complexity_estimate=2,
    )
    d = node.to_dict()
    assert d["name"] == "calculate"
    assert d["is_async"] is True
    assert d["return_type"] == "int"

    # 2. ValidationResult
    vr = ValidationResult(
        success=False, errors=["Error on line 3"], warnings=["Warn"], line=3, column=5
    )
    vr_d = vr.to_dict()
    assert vr_d["success"] is False
    assert vr_d["line"] == 3

    # 3. SymbolInfo
    sym = SymbolInfo(
        name="User", file_path="models.py", line=10, kind="class", references=[("main.py", 20)]
    )
    sym_d = sym.to_dict()
    assert sym_d["name"] == "User"
    assert len(sym_d["references"]) == 1

    # 4. StructuralDiff
    diff = StructuralDiff(
        added_functions=["fn1"],
        removed_functions=["fn2"],
        modified_functions=["fn3"],
        added_classes=["Cls1"],
        removed_classes=["Cls2"],
        modified_classes=["Cls3"],
        added_imports=["os"],
        removed_imports=["sys"],
    )
    assert diff.has_changes() is True
    summary = diff.summary()
    assert "Added 1 function" in summary
    assert "Removed 1 function" in summary
    assert "Modified 1 class" in summary

    empty_diff = StructuralDiff()
    assert empty_diff.has_changes() is False
    assert empty_diff.summary() == "No structural changes"


def test_detect_language_and_singleton() -> None:
    assert detect_language("app.py") == "python"
    assert detect_language("index.js") == "javascript"
    assert detect_language("component.tsx") == "typescript"
    assert detect_language("main.go") == "go"
    assert detect_language("lib.rs") == "rust"
    assert detect_language("App.java") == "java"
    assert detect_language("engine.c") == "c"
    assert detect_language("header.h") == "c"
    assert detect_language("core.cpp") == "cpp"
    assert detect_language("data.bin") == "unknown"

    editor1 = get_ast_editor()
    editor2 = get_ast_editor()
    assert editor1 is editor2


def test_analyze_python_deep() -> None:
    editor = ASTEditor()
    py_code = """
import os
from typing import Optional, List

CONSTANT_VAL = 42

class BaseEntity:
    pass

class EntityManager(BaseEntity):
    \"\"\"Manages entities.\"\"\"
    def __init__(self, name: str = 'default'):
        self.name = name

    @property
    def entity_name(self) -> str:
        return self.name

    @staticmethod
    def create_empty():
        return EntityManager()

    @classmethod
    def from_dict(cls, data: dict):
        return cls()

    async def fetch_async(self, timeout: int = 10, *args, **kwargs) -> Optional[dict]:
        if timeout > 0:
            return {"status": "ok"}
        return None

def standalone_helper(x: int = 1, *extra, flag: bool = False, **opts):
    return x
"""
    nodes = editor.analyze(py_code, language="python")
    names = {n.name: n for n in nodes}

    assert "BaseEntity" in names
    assert names["BaseEntity"].node_type == "class"

    assert "EntityManager" in names
    assert "BaseEntity" in names["EntityManager"].signature

    assert "__init__" in names
    assert names["__init__"].node_type == "method"
    assert names["__init__"].parent == "EntityManager"

    assert "entity_name" in names
    assert names["entity_name"].is_property is True

    assert "create_empty" in names
    assert names["create_empty"].is_static is True

    assert "from_dict" in names
    assert names["from_dict"].is_classmethod is True

    assert "fetch_async" in names
    assert names["fetch_async"].is_async is True
    assert names["fetch_async"].return_type == "Optional[dict]"

    assert "standalone_helper" in names
    assert names["standalone_helper"].node_type == "function"
    assert names["standalone_helper"].parent is None

    # Syntax error fallback
    assert editor.analyze("def broken(:", language="python") == []


def test_analyze_multilingual() -> None:
    editor = ASTEditor()

    # 1. JavaScript / TypeScript
    js_code = """
import React from 'react';
const config = require('./config');

export class TaskService extends BaseService {
    constructor() {}
}

function processTask(id, options) {
    return true;
}

const formatTask = (item) => {
    return item.name;
};
"""
    js_nodes = editor.analyze(js_code, language="javascript")
    js_names = {n.name for n in js_nodes}
    assert "TaskService" in js_names
    assert "processTask" in js_names
    assert "formatTask" in js_names

    # 2. Go
    go_code = """
package main

import "fmt"

type ServerConfig struct {
    Port int
}

func NewServer() *ServerConfig {
    return &ServerConfig{Port: 8080}
}

func (s *ServerConfig) ListenAndServe() error {
    return nil
}
"""
    go_nodes = editor.analyze(go_code, language="go")
    go_names = {n.name for n in go_nodes}
    assert "ServerConfig" in go_names
    assert "NewServer" in go_names
    assert "ListenAndServe" in go_names

    # 3. Rust
    rs_code = """
use std::collections::HashMap;

pub struct DatabasePool {
    size: usize,
}

pub enum DbStatus {
    Connected,
    Disconnected,
}

impl DatabasePool {
    pub fn new(size: usize) -> Self {
        DatabasePool { size }
    }
}

fn connect_db() -> bool {
    true
}
"""
    rs_nodes = editor.analyze(rs_code, language="rust")
    rs_names = {n.name for n in rs_nodes}
    assert "DatabasePool" in rs_names
    assert "DbStatus" in rs_names
    assert "new" in rs_names or "connect_db" in rs_names

    # 4. Java
    java_code = """
package com.sago.app;

import java.util.List;

public class OrderManager extends BaseManager {
    private int orderCount;

    public void processOrder(int orderId) {
        System.out.println(orderId);
    }
}
"""
    java_nodes = editor.analyze(java_code, language="java")
    java_names = {n.name for n in java_nodes}
    assert "OrderManager" in java_names
    assert "processOrder" in java_names

    # 5. C / C++
    c_code = """
#include <stdio.h>

class GraphicRenderer : public BaseRenderer {
    int width;
};

struct Point {
    int x;
    int y;
};

int render_frame(int frame_id) {
    return frame_id * 2;
}
"""
    c_nodes = editor.analyze(c_code, language="cpp")
    c_names = {n.name for n in c_nodes}
    assert "GraphicRenderer" in c_names
    assert "Point" in c_names
    assert "render_frame" in c_names


def test_validate_syntax_and_edit() -> None:
    editor = ASTEditor()

    # Python
    assert editor.validate_syntax("x = 10\nprint(x)", language="python").success is True
    res_py_err = editor.validate_syntax("def bad_syntax(:", language="python")
    assert res_py_err.success is False
    assert res_py_err.line is not None

    # JS/TS
    assert (
        editor.validate_syntax("function ok() { return (1 + 2); }", language="javascript").success
        is True
    )
    assert (
        editor.validate_syntax("function bad() { return (1 + 2;", language="javascript").success
        is False
    )
    assert (
        editor.validate_syntax("function bad() { return 1; }}", language="javascript").success
        is False
    )

    # Go
    assert (
        editor.validate_syntax('func main() { fmt.Println("ok") }', language="go").success is True
    )
    assert editor.validate_syntax('func main() { fmt.Println("ok")', language="go").success is False

    # Rust
    assert editor.validate_syntax('fn main() { println!("ok"); }', language="rust").success is True
    assert editor.validate_syntax('fn main() { println!("ok");', language="rust").success is False

    # Java
    assert editor.validate_syntax("public class A { void m() {} }", language="java").success is True
    assert editor.validate_syntax("public class A { void m() {}", language="java").success is False

    # C
    assert editor.validate_syntax("int main() { return 0; }", language="c").success is True
    assert editor.validate_syntax("int main() { return 0;", language="c").success is False

    # validate_edit
    edit_valid = editor.validate_edit("def a(): pass", "def a(): return 1", language="python")
    assert edit_valid.success is True

    edit_invalid = editor.validate_edit("def a(): pass", "def a(): return :", language="python")
    assert edit_invalid.success is False
    assert "Edit introduced syntax errors:" in edit_invalid.errors[0]


def test_diff_structures() -> None:
    editor = ASTEditor()
    v1 = """
import os

def helper_one():
    return 1

class User:
    pass
"""
    v2 = """
import os
import sys

def helper_two():
    return 2

class User:
    def get_id(self):
        return 1

class Profile:
    pass
"""
    diff = editor.diff_structures(v1, v2, language="python")
    assert "helper_two" in diff.added_functions
    assert "helper_one" in diff.removed_functions
    assert "Profile" in diff.added_classes
    assert diff.has_changes() is True


def test_replace_and_insert_function() -> None:
    editor = ASTEditor()

    # 1. Replace function in Python
    code_py = """
def original_fn(x):
    return x * 10

def second_fn():
    return True
"""
    replaced_py = editor.replace_function(
        code=code_py,
        function_name="original_fn",
        new_body="return x * 20",
        language="python",
    )
    assert "return x * 20" in replaced_py
    assert "return x * 10" not in replaced_py

    # 2. Insert function with after in Python
    inserted_py = editor.insert_function(
        code=code_py,
        function_name="third_fn",
        args=["a", "b"],
        body="return a + b",
        language="python",
        after="original_fn",
    )
    assert "def third_fn(a, b):" in inserted_py
    assert "return a + b" in inserted_py

    # 3. Insert function in multilingual (Go, Rust, JS, Java, C)
    assert "func goFn(x) {" in editor.insert_function("", "goFn", ["x"], "return x", language="go")
    assert "fn rsFn(x) {" in editor.insert_function("", "rsFn", ["x"], "return x", language="rust")
    assert "function jsFn(x) {" in editor.insert_function(
        "", "jsFn", ["x"], "return x", language="javascript"
    )
    assert "public void javaFn(x) {" in editor.insert_function(
        "", "javaFn", ["x"], "System.out.println(x);", language="java"
    )
    assert "void cFn(x) {" in editor.insert_function("", "cFn", ["x"], "return;", language="c")


def test_add_import_and_rename_symbol() -> None:
    editor = ASTEditor()

    # Add import (Python, JS, Go, Rust, Java, C)
    py_c = "import math\n\ndef run(): pass"
    assert "import json" in editor.add_import(py_c, "import json", language="python")
    # Idempotent if already exists
    assert editor.add_import(py_c, "import math", language="python") == py_c

    js_c = "import React from 'react';\nfunction App() {}"
    assert "import axios from 'axios';" in editor.add_import(
        js_c, "import axios from 'axios';", language="javascript"
    )

    go_c = 'import "fmt"\nfunc main() {}'
    assert 'import "os"' in editor.add_import(go_c, 'import "os"', language="go")

    rs_c = "use std::io;\nfn main() {}"
    assert "use std::fs;" in editor.add_import(rs_c, "use std::fs;", language="rust")

    java_c = "import java.util.List;\nclass App {}"
    assert "import java.util.Map;" in editor.add_import(
        java_c, "import java.util.Map;", language="java"
    )

    c_c = "#include <stdio.h>\nint main() {}"
    assert "#include <stdlib.h>" in editor.add_import(c_c, "#include <stdlib.h>", language="c")

    # Rename symbol
    renamed = editor.rename_symbol("def foo():\n    return foo() + 1", "foo", "bar")
    assert "def bar():" in renamed
    assert "return bar() + 1" in renamed


def test_find_node_and_resolve_symbol(tmp_path: Path) -> None:
    editor = ASTEditor()
    code = "class SearchService:\n    def execute_query(self):\n        pass\n"

    # find_node
    node = editor.find_node(code, "SearchService", language="python")
    assert node is not None
    assert node.node_type == "class"

    missing = editor.find_node(code, "NonExistentService", language="python")
    assert missing is None

    # resolve_symbol across project files
    py_file = tmp_path / "service.py"
    py_file.write_text("class Authenticator:\n    def verify(self): pass\n", encoding="utf-8")

    js_file = tmp_path / "client.ts"
    js_file.write_text("function connectGateway(url) { return url; }\n", encoding="utf-8")

    sym1 = editor.resolve_symbol("Authenticator", root_dir=tmp_path)
    assert sym1 is not None
    assert sym1.name == "Authenticator"
    assert sym1.file_path == "service.py"

    sym2 = editor.resolve_symbol("connectGateway", root_dir=tmp_path)
    assert sym2 is not None
    assert sym2.name == "connectGateway"
    assert sym2.file_path == "client.ts"

    sym_none = editor.resolve_symbol("NeverDefinedSymbol", root_dir=tmp_path)
    assert sym_none is None


def test_ast_editor_regex_replacement_and_symbol_resolution(tmp_path: Path) -> None:
    editor = ASTEditor()

    # 1. Regex replacement in JS
    js_code = "function computeTax(rate) {\n    const base = 100;\n    return base * rate;\n}\n"
    res_js = editor.replace_function(
        js_code, "computeTax", "return rate * 105;", language="javascript"
    )
    assert "return rate * 105;" in res_js

    # 2. Modified function and class in diff_structures
    v1 = "import sys\ndef fn(a): pass\nclass MyClass(A): pass\n"
    v2 = "def fn(a, b): pass\nclass MyClass(B): pass\n"
    diff = editor.diff_structures(v1, v2, language="python")
    assert "fn" in diff.modified_functions
    assert "MyClass" in diff.modified_classes
    assert "sys" in diff.removed_imports

    # 3. Symbol resolution in Go, Rust, and Java
    go_file = tmp_path / "server.go"
    go_file.write_text("package main\nfunc StartWebServer() {}\n", encoding="utf-8")

    rs_file = tmp_path / "lib.rs"
    rs_file.write_text("pub fn run_coordinator() {}\n", encoding="utf-8")

    java_file = tmp_path / "Main.java"
    java_file.write_text("public class AppRunner {}\n", encoding="utf-8")

    sym_go = editor.resolve_symbol("StartWebServer", root_dir=tmp_path)
    assert sym_go is not None
    assert sym_go.name == "StartWebServer"

    sym_rs = editor.resolve_symbol("run_coordinator", root_dir=tmp_path)
    assert sym_rs is not None
    assert sym_rs.name == "run_coordinator"

    sym_java = editor.resolve_symbol("AppRunner", root_dir=tmp_path)
    assert sym_java is not None
    assert sym_java.name == "AppRunner"
