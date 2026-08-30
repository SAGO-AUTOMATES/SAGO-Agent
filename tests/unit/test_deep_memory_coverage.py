"""Tests for sago.memory.symbol_index and sago.memory.codebase_indexer."""

from __future__ import annotations

import sqlite3

import pytest

from sago.memory.codebase_indexer import CodebaseIndexer, CodeChunk, SearchResult
from sago.memory.symbol_index import PersistentSymbolIndex

# ── symbol_index ─────────────────────────────────────────────────────────────

class TestPersistentSymbolIndex:
    def test_init_creates_db(self, tmp_path):
        db_path = tmp_path / "test_symbols.db"
        PersistentSymbolIndex(workspace_root=tmp_path, db_path=db_path)
        assert db_path.exists()
        conn = sqlite3.connect(db_path)
        tables = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        assert "files" in tables
        conn.close()

    def test_search_symbols_empty(self, tmp_path):
        db_path = tmp_path / "test.db"
        psi = PersistentSymbolIndex(workspace_root=tmp_path, db_path=db_path)
        results = psi.search_symbols("anything")
        assert results == []

    def test_update_index_basic(self, tmp_path):
        src = tmp_path / "hello.py"
        src.write_text("def greet():\n    '''Say hello.'''\n    pass\n")
        db_path = tmp_path / "test.db"
        psi = PersistentSymbolIndex(workspace_root=tmp_path, db_path=db_path)
        stats = psi.update_index()
        assert stats["scanned"] >= 1
        assert stats["indexed"] >= 1

    def test_update_index_caches(self, tmp_path):
        src = tmp_path / "hello.py"
        src.write_text("def greet(): pass\n")
        db_path = tmp_path / "test.db"
        psi = PersistentSymbolIndex(workspace_root=tmp_path, db_path=db_path)
        psi.update_index()
        stats2 = psi.update_index()
        assert stats2["cached"] >= 1

    def test_update_index_max_files(self, tmp_path):
        for i in range(5):
            (tmp_path / f"file{i}.py").write_text(f"def f{i}(): pass\n")
        db_path = tmp_path / "test.db"
        psi = PersistentSymbolIndex(workspace_root=tmp_path, db_path=db_path)
        stats = psi.update_index(max_files=2)
        assert stats["scanned"] <= 2

    def test_search_symbols_after_index(self, tmp_path):
        src = tmp_path / "mymodule.py"
        src.write_text('def my_function():\n    """A test function."""\n    pass\n')
        db_path = tmp_path / "test.db"
        psi = PersistentSymbolIndex(workspace_root=tmp_path, db_path=db_path)
        psi.update_index()
        results = psi.search_symbols("my_function")
        assert len(results) >= 1
        assert results[0]["name"] == "my_function"

    def test_get_ranked_repo_map_empty(self, tmp_path):
        db_path = tmp_path / "test.db"
        psi = PersistentSymbolIndex(workspace_root=tmp_path, db_path=db_path)
        result = psi.get_ranked_repo_map(query="nonexistent")
        assert "No symbols found" in result

    def test_get_ranked_repo_map_no_query(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("class MyClass:\n    def method(self): pass\n")
        db_path = tmp_path / "test.db"
        psi = PersistentSymbolIndex(workspace_root=tmp_path, db_path=db_path)
        psi.update_index()
        result = psi.get_ranked_repo_map()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_ranked_repo_map_with_query(self, tmp_path):
        src = tmp_path / "auth.py"
        src.write_text("def authenticate():\n    pass\n")
        db_path = tmp_path / "test.db"
        psi = PersistentSymbolIndex(workspace_root=tmp_path, db_path=db_path)
        psi.update_index()
        result = psi.get_ranked_repo_map(query="authenticate")
        assert isinstance(result, str)

    def test_search_symbols_special_chars(self, tmp_path):
        db_path = tmp_path / "test.db"
        psi = PersistentSymbolIndex(workspace_root=tmp_path, db_path=db_path)
        results = psi.search_symbols("!@#$%")
        assert results == []

    def test_search_symbols_dotted_query(self, tmp_path):
        db_path = tmp_path / "test.db"
        psi = PersistentSymbolIndex(workspace_root=tmp_path, db_path=db_path)
        results = psi.search_symbols("os.path.join")
        assert results == []


# ── codebase_indexer ─────────────────────────────────────────────────────────

class TestCodeChunk:
    def test_auto_hash(self):
        chunk = CodeChunk(
            file_path="test.py", start_line=1, end_line=5,
            content="hello", language="python", chunk_type="function",
        )
        assert chunk.hash
        assert len(chunk.hash) == 12

    def test_to_dict(self):
        chunk = CodeChunk(
            file_path="test.py", start_line=1, end_line=5,
            content="x = 1\ny = 2", language="python", chunk_type="block",
        )
        d = chunk.to_dict()
        assert d["file"] == "test.py"
        assert d["start"] == 1
        assert d["end"] == 5
        assert d["type"] == "block"
        assert "x = 1" in d["preview"]

    def test_to_dict_with_name(self):
        chunk = CodeChunk(
            file_path="test.py", start_line=1, end_line=3,
            content="def foo(): pass", language="python",
            chunk_type="function", name="foo",
        )
        d = chunk.to_dict()
        assert d["name"] == "foo"


class TestSearchResult:
    def test_to_dict(self):
        chunk = CodeChunk("f.py", 1, 2, "code", "python", "function")
        sr = SearchResult(chunk=chunk, score=0.87654)
        d = sr.to_dict()
        assert d["score"] == 0.8765
        assert d["file"] == "f.py"


class TestCodebaseIndexer:
    def _make_indexer(self):
        indexer = CodebaseIndexer.__new__(CodebaseIndexer)
        indexer._chunks = []
        indexer._idf = {}
        indexer._tf_cache = {}
        indexer._indexed_at = 0
        return indexer

    def test_detect_language(self):
        indexer = self._make_indexer()
        assert indexer._detect_language("main.py") == "python"
        assert indexer._detect_language("app.js") == "javascript"
        assert indexer._detect_language("mod.ts") == "typescript"
        assert indexer._detect_language("lib.go") == "go"
        assert indexer._detect_language("index.html") == "html"
        assert indexer._detect_language("data.csv") == "csv"
        assert indexer._detect_language("readme.md") == "markdown"
        assert indexer._detect_language("unknown.xyz") == "unknown"

    def test_tokenize(self):
        indexer = self._make_indexer()
        tokens = indexer._tokenize("check_permission")
        assert "check_permission" in tokens
        assert "check" in tokens
        assert "permission" in tokens

    def test_tokenize_simple(self):
        indexer = self._make_indexer()
        tokens = indexer._tokenize("hello world")
        assert "hello" in tokens
        assert "world" in tokens

    def test_compute_tf(self):
        indexer = self._make_indexer()
        tf = indexer._compute_tf("hello world hello")
        assert tf["hello"] == pytest.approx(2 / 3)
        assert tf["world"] == pytest.approx(1 / 3)

    def test_compute_tf_empty(self):
        indexer = self._make_indexer()
        assert indexer._compute_tf("") == {}

    def test_build_idf(self):
        indexer = self._make_indexer()
        indexer._chunks = [
            CodeChunk("a.py", 1, 1, "hello world", "python", "block"),
            CodeChunk("b.py", 1, 1, "hello there", "python", "block"),
        ]
        indexer._build_idf()
        assert "hello" in indexer._idf
        assert "world" in indexer._idf
        assert indexer._idf["world"] > indexer._idf["hello"]

    def test_search_empty(self):
        indexer = self._make_indexer()
        assert indexer.search("anything") == []

    def test_search_with_language_filter(self):
        indexer = self._make_indexer()
        indexer._chunks = [
            CodeChunk("a.py", 1, 1, "hello world", "python", "block"),
            CodeChunk("b.js", 1, 1, "hello world", "javascript", "block"),
        ]
        indexer._build_idf()
        results = indexer.search("hello", language_filter="python")
        assert all(r.chunk.language == "python" for r in results)

    def test_search_with_file_filter(self):
        indexer = self._make_indexer()
        indexer._chunks = [
            CodeChunk("foo/bar.py", 1, 1, "hello world", "python", "block"),
            CodeChunk("baz/qux.py", 1, 1, "hello world", "python", "block"),
        ]
        indexer._build_idf()
        results = indexer.search("hello", file_filter="bar")
        assert all("bar" in r.chunk.file_path for r in results)

    def test_get_stats(self):
        indexer = self._make_indexer()
        indexer._chunks = [
            CodeChunk("a.py", 1, 1, "x", "python", "block"),
            CodeChunk("b.py", 1, 1, "x", "python", "block"),
            CodeChunk("c.js", 1, 1, "x", "javascript", "block"),
        ]
        indexer._indexed_at = 42.0
        stats = indexer.get_stats()
        assert stats["total_chunks"] == 3
        assert stats["languages"]["python"] == 2
        assert stats["languages"]["javascript"] == 1
        assert "indexed_at" in stats

    def test_get_file_context_nonexistent(self):
        indexer = self._make_indexer()
        result = indexer.get_file_context("/nonexistent/file.py")
        assert "Could not read" in result

    def test_get_file_context_short_file(self, tmp_path):
        f = tmp_path / "short.py"
        f.write_text("line1\nline2\n")
        indexer = self._make_indexer()
        result = indexer.get_file_context(str(f), max_lines=200)
        assert "line1" in result
        assert "line2" in result

    def test_chunk_python_syntax_error_fallback(self):
        indexer = self._make_indexer()
        bad_code = "def broken(\n    pass"
        chunks = indexer._chunk_python(bad_code, "bad.py", bad_code.split("\n"))
        assert len(chunks) >= 1
        assert chunks[0].chunk_type == "block"

    def test_chunk_js(self):
        indexer = self._make_indexer()
        js_code = "function hello() {}\nclass Foo {}"
        lines = js_code.split("\n")
        chunks = indexer._chunk_js(js_code, "app.js", lines)
        names = {c.name for c in chunks}
        assert "hello" in names
        assert "Foo" in names

    def test_index_directory(self, tmp_path):
        src = tmp_path / "mod.py"
        src.write_text("def foo():\n    pass\n")
        indexer = CodebaseIndexer()
        count = indexer.index_directory(str(tmp_path))
        assert count >= 1

    def test_search_after_index(self, tmp_path):
        src = tmp_path / "auth.py"
        src.write_text("def authenticate():\n    '''Auth user.'''\n    pass\n")
        indexer = CodebaseIndexer()
        indexer.index_directory(str(tmp_path))
        results = indexer.search("authenticate")
        assert len(results) >= 1
        assert results[0].score > 0

    def test_chunk_python_function(self):
        indexer = self._make_indexer()
        code = "def hello():\n    '''Say hello.'''\n    pass\n"
        chunks = indexer._chunk_python(code, "hello.py", code.split("\n"))
        func_chunks = [c for c in chunks if c.chunk_type == "function"]
        assert len(func_chunks) >= 1
        assert func_chunks[0].name == "hello"

    def test_chunk_python_class(self):
        indexer = self._make_indexer()
        code = "class MyClass:\n    pass\n"
        chunks = indexer._chunk_python(code, "cls.py", code.split("\n"))
        class_chunks = [c for c in chunks if c.chunk_type == "class"]
        assert len(class_chunks) >= 1
        assert class_chunks[0].name == "MyClass"
