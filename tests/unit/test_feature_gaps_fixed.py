"""Tests for the medium-severity feature gaps that were fixed:

- Multi-language symbol extraction (Java/C/C++/SQL) in SymbolGraph
- Real go-to-definition lookup in LSPClient.get_definitions
- HierarchicalMemoryPyramid wired into SessionCompactor context building
"""

from __future__ import annotations

from pathlib import Path

from sago.memory.compaction import SessionCompactor
from sago.memory.symbol_graph import SymbolGraph
from sago.tools.coding.lsp_client import LSPClient


def test_symbol_graph_extracts_java_symbols(tmp_path: Path) -> None:
    f = tmp_path / "Example.java"
    f.write_text("public class Example {\n    private int count;\n}\n")
    graph = SymbolGraph(root_dir=tmp_path)
    fs = graph.scan_file(f)
    assert fs is not None
    assert fs.language == "java"
    assert any(s.name == "Example" for s in fs.symbols)


def test_symbol_graph_extracts_c_symbols(tmp_path: Path) -> None:
    f = tmp_path / "thing.c"
    f.write_text("struct thing {\n    int x;\n};\n")
    graph = SymbolGraph(root_dir=tmp_path)
    fs = graph.scan_file(f)
    assert fs is not None
    assert fs.language == "c"
    assert any(s.name == "thing" for s in fs.symbols)


def test_symbol_graph_extracts_sql_symbols(tmp_path: Path) -> None:
    f = tmp_path / "schema.sql"
    f.write_text("CREATE TABLE users (id INTEGER);\nCREATE VIEW active AS SELECT 1;\n")
    graph = SymbolGraph(root_dir=tmp_path)
    fs = graph.scan_file(f)
    assert fs is not None
    assert fs.language == "sql"
    names = {s.name for s in fs.symbols}
    assert "users" in names
    assert "active" in names


def test_lsp_get_definitions_finds_real_definition(tmp_path: Path) -> None:
    f = tmp_path / "mod.py"
    f.write_text("import os\n\ndef my_helper():\n    return 42\n\nmy_helper()\n")
    client = LSPClient()
    # Cursor positioned on the call site of my_helper (line 6, anywhere in name)
    defs = client.get_definitions(str(f), line=6, column=0)
    assert defs, "expected at least one definition candidate"
    # Must point at the real definition line, not echo the input position.
    assert any(d.line == 3 for d in defs)
    assert all(d.line != 6 for d in defs)


def test_lsp_get_definitions_does_not_echo_input(tmp_path: Path) -> None:
    f = tmp_path / "call.py"
    f.write_text("def alpha(): pass\nalpha()\n")
    client = LSPClient()
    # Input reports line 2 (the call site); a correct lookup returns the
    # definition on line 1 rather than echoing the input position.
    defs = client.get_definitions(str(f), line=2, column=0)
    assert defs, "expected the definition of 'alpha' to be found"
    assert all(d.line == 1 for d in defs)


def test_compaction_uses_hierarchical_pyramid(tmp_path: Path) -> None:
    compactor = SessionCompactor(max_context_tokens=10_000)
    messages = [
        {"role": "user", "content": "Goal: Build a payments service with Stripe."},
        {"role": "assistant", "content": "We decided to use idempotency keys for safety."},
    ]
    # Add enough filler messages to exceed the <=10 short-circuit branch.
    for i in range(12):
        messages.append({"role": "user", "content": f"step {i} " + "word " * 30})

    result = compactor.build_context_window(messages, max_tokens=10_000)
    joined = "\n".join(block.get("content", "") for block in result)
    assert "[ARCHITECTURAL MEMORY PYRAMID - TIER 1]" in joined
    assert "payments service" in joined
