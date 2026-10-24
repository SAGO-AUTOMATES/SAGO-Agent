"""Unit tests for Phase 1 (Git-aware incremental indexing) and Phase 2 (Tree-Sitter AST & Multi-language)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from sago.memory.codebase_indexer import CodebaseIndexer
from sago.memory.hybrid_indexer import HybridCodeIndexer
from sago.memory.symbol_graph import SymbolGraph
from sago.memory.tree_sitter_parser import (
    generate_skeleton,
    is_available,
    parse_symbols,
)


def test_ignore_filters() -> None:
    """Test lockfiles, minified files, and binaries are correctly ignored."""
    assert HybridCodeIndexer.should_ignore_file("package-lock.json") is True
    assert HybridCodeIndexer.should_ignore_file("Cargo.lock") is True
    assert HybridCodeIndexer.should_ignore_file("poetry.lock") is True
    assert HybridCodeIndexer.should_ignore_file("app.min.js") is True
    assert HybridCodeIndexer.should_ignore_file("styles.min.css") is True
    assert HybridCodeIndexer.should_ignore_file("bundle.map") is True
    assert HybridCodeIndexer.should_ignore_file("service.pb.go") is True
    assert HybridCodeIndexer.should_ignore_file("module.wasm") is True
    assert HybridCodeIndexer.should_ignore_file("main.py") is False
    assert HybridCodeIndexer.should_ignore_file("index.ts") is False

    assert CodebaseIndexer.should_ignore_file("pnpm-lock.yaml") is True
    assert CodebaseIndexer.should_ignore_file("lib.min.js") is True
    assert CodebaseIndexer.should_ignore_file("server.go") is False


def test_git_aware_file_detection() -> None:
    """Test git-aware enumeration methods on HybridCodeIndexer."""
    indexer = HybridCodeIndexer()
    git_root = indexer.find_git_root(Path.cwd())
    assert git_root is not None
    assert (git_root / ".git").exists()

    git_files = indexer.get_git_files(max_files=100)
    assert git_files is not None
    assert len(git_files) > 0
    assert any("sago" in str(p) for p in git_files)

    status = indexer.get_git_status_files()
    assert status is not None
    changed, deleted = status
    assert isinstance(changed, set)
    assert isinstance(deleted, set)


def test_incremental_indexing_and_removal() -> None:
    """Test index_files_incremental and remove_files_from_index."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        f1 = root / "module1.py"
        f1.write_text("def alpha():\n    return 42\n")

        f2 = root / "module2.py"
        f2.write_text("def beta():\n    return 'hello'\n")

        indexer = HybridCodeIndexer(root)
        indexed = indexer.index_project()
        assert indexed > 0

        # Incrementally add f3
        f3 = root / "module3.py"
        f3.write_text("def gamma():\n    return True\n")

        updated = indexer.index_files_incremental([f3])
        assert updated > indexed
        res = indexer.search("gamma", limit=2)
        assert any("gamma" in r.chunk.content for r in res)

        # Remove f3
        removed_count = indexer.remove_files_from_index([f3])
        assert removed_count < updated
        res_after = indexer.search("gamma", limit=2)
        assert not any("gamma" in r.chunk.content for r in res_after)


def test_tree_sitter_multi_language_availability() -> None:
    """Verify tree-sitter grammars are available for polyglot languages."""
    for lang in ("python", "javascript", "typescript", "rust", "go", "java", "c", "cpp"):
        assert is_available(lang) is True


def test_tree_sitter_parse_symbols() -> None:
    """Test parse_symbols across Python, Rust, Go, Java."""
    py_code = """
def calculate_metrics(values: list[int]) -> float:
    return sum(values) / len(values)

class DataProcessor:
    def process(self):
        pass
"""
    py_syms = parse_symbols("python", py_code)
    names = [s["name"] for s in py_syms]
    assert "calculate_metrics" in names
    assert "DataProcessor" in names
    assert "process" in names

    rust_code = """
pub struct TaskQueue {
    pub capacity: usize,
}

impl TaskQueue {
    pub fn enqueue(&mut self, item: String) -> bool {
        true
    }
}
"""
    rust_syms = parse_symbols("rust", rust_code)
    rust_names = [s["name"] for s in rust_syms]
    assert "TaskQueue" in rust_names
    assert "enqueue" in rust_names

    go_code = """
package worker

type JobRunner struct {
    ID string
}

func (j *JobRunner) Execute(ctx context.Context) error {
    return nil
}
"""
    go_syms = parse_symbols("go", go_code)
    go_names = [s["name"] for s in go_syms]
    assert "JobRunner" in go_names
    assert "Execute" in go_names

    java_code = """
public class CustomerService {
    public void registerCustomer() {}
}
"""
    java_syms = parse_symbols("java", java_code)
    assert any(s["name"] == "CustomerService" for s in java_syms)

    ts_code = """
interface UserService {
    getUser(id: string): User;
}
function fetchUser(id: string) {
    return null;
}
"""
    ts_syms = parse_symbols("typescript", ts_code)
    assert any(s["name"] == "UserService" for s in ts_syms)
    assert any(s["name"] == "fetchUser" for s in ts_syms)

    # Empty and unknown language handling
    assert parse_symbols("", "") == []
    assert parse_symbols("unknown_lang", "code") == []


def test_tree_sitter_generate_skeleton() -> None:
    """Test AST skeleton generation omitting internal function bodies."""
    rust_code = """
pub struct Config {
    pub port: u16,
}
impl Config {
    pub fn new(port: u16) -> Self {
        println!("initializing complex state");
        Self { port }
    }
}
"""
    skel = generate_skeleton("rust", rust_code)
    assert "pub struct Config" in skel
    assert "pub fn new(port: u16) -> Self" in skel
    assert "initializing complex state" not in skel
    assert "{ ... }" in skel

    py_code = """
def compute_sum(a: int, b: int) -> int:
    result = a + b
    return result
"""
    py_skel = generate_skeleton("python", py_code)
    assert "def compute_sum(a: int, b: int) -> int:" in py_skel
    assert "result = a + b" not in py_skel

    # Unknown language fallback
    fallback_skel = generate_skeleton("custom_lang", "fn main() { do_work(); }")
    assert "fn main()" in fallback_skel


def test_symbol_graph_generic_extraction_and_skeleton() -> None:
    """Test SymbolGraph integration with tree-sitter and skeleton generator."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        rs_file = root / "lib.rs"
        rs_file.write_text(
            "pub fn run_daemon() -> Result<(), ()> { Ok(()) }\npub struct State {}\n"
        )

        sg = SymbolGraph(root)
        fs = sg.scan_file(rs_file)
        assert fs is not None
        names = [s.name for s in fs.symbols]
        assert "run_daemon" in names
        assert "State" in names

        skel = sg.generate_skeleton(rs_file)
        assert "run_daemon" in skel
