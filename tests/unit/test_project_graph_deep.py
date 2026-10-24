"""Deep unit test suite for sago/memory/project_graph.py.

Validates monorepo workspace detection, multilingual AST parsing (Java, C++, SQL),
rich diagram generators (ASCII tree, dashboard, topological summary, AI synthesis),
and full serialization roundtrips.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from sago.memory.project_graph import (
    GraphEdge,
    GraphNode,
    ProjectGraph,
    get_cached_project_graph,
)


def test_graph_node_and_edge_serialization() -> None:
    node = GraphNode(
        id="file:app.py",
        label="app.py",
        node_type="file",
        language="python",
        file_path="app.py",
        line_number=1,
        metadata={"size": 1024},
    )
    d = node.to_dict()
    assert d["id"] == "file:app.py"
    assert d["metadata"]["size"] == 1024

    edge = GraphEdge(
        source="file:app.py",
        target="file:config.py",
        relation="imports",
        weight=2,
        metadata={"line": 5},
    )
    e_d = edge.to_dict()
    assert e_d["relation"] == "imports"
    assert e_d["weight"] == 2


def test_detect_workspaces_monorepos(tmp_path: Path) -> None:
    # 1. npm list workspaces
    pkg_dir = tmp_path / "packages" / "ui"
    pkg_dir.mkdir(parents=True)
    pkg_json = tmp_path / "package.json"
    pkg_json.write_text(json.dumps({"name": "root", "workspaces": ["packages/*"]}))

    pg = ProjectGraph(root_dir=tmp_path)
    ws = pg.detect_workspaces()
    assert any(w.name == "ui" for w in ws)

    # 2. Yarn dict workspaces
    app_dir = tmp_path / "apps" / "web"
    app_dir.mkdir(parents=True)
    pkg_json.write_text(json.dumps({"name": "root", "workspaces": {"packages": ["apps/*"]}}))
    ws2 = pg.detect_workspaces()
    assert any(w.name == "web" for w in ws2)

    # 3. Cargo workspace
    crate_dir = tmp_path / "crates" / "core"
    crate_dir.mkdir(parents=True)
    cargo_toml = tmp_path / "Cargo.toml"
    cargo_toml.write_text('[workspace]\nmembers = ["crates/*"]\n')
    ws3 = pg.detect_workspaces()
    assert any(w.name == "core" for w in ws3)

    # 4. Lerna/Turbo config
    srv_dir = tmp_path / "services" / "auth"
    srv_dir.mkdir(parents=True)
    lerna_json = tmp_path / "lerna.json"
    lerna_json.write_text(json.dumps({"packages": ["services/*"]}))
    ws4 = pg.detect_workspaces()
    assert any(w.name == "auth" for w in ws4)


def test_multilingual_parsing_java_cpp_sql(tmp_path: Path) -> None:
    # 1. Java file with Spring endpoint and entity
    java_file = tmp_path / "UserController.java"
    java_file.write_text(
        """
package com.example.api;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class UserController {
    @GetMapping("/api/users")
    public List<User> getUsers() {
        return null;
    }
}
class UserEntity {
    private Long id;
    private String email;
}
""",
        encoding="utf-8",
    )

    # 2. C++ file with class and struct
    cpp_file = tmp_path / "renderer.cpp"
    cpp_file.write_text(
        """
#include <iostream>
class SceneRenderer : public BaseRenderer {
    int maxDepth;
};
struct Vertex {
    float x, y, z;
};
void init_engine() {}
""",
        encoding="utf-8",
    )

    # 3. SQL file with CREATE TABLE
    sql_file = tmp_path / "schema.sql"
    sql_file.write_text(
        """
CREATE TABLE accounts (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    created_at TIMESTAMP
);
""",
        encoding="utf-8",
    )

    pg = ProjectGraph(root_dir=tmp_path)
    pg.build_graph(include_symbols=True)

    node_labels = {n.label for n in pg.nodes.values()}
    assert "UserController.java" in node_labels
    assert "renderer.cpp" in node_labels
    assert "schema.sql" in node_labels
    assert "accounts" in pg.data_models or any("accounts" in m for m in pg.data_models)


def test_graph_export_and_diagrams(tmp_path: Path) -> None:
    # Set up sample python architecture
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("import utils\ndef run(): pass\n")
    (src_dir / "utils.py").write_text("class ConfigHelper: pass\n")
    (src_dir / "models.py").write_text("class AccountModel:\n    id: int\n    name: str\n")

    pg = ProjectGraph(root_dir=tmp_path)
    pg.build_graph()

    # 1. to_ascii_tree
    tree = pg.to_ascii_tree()
    assert "Project Topology Graph" in tree
    assert len(tree.splitlines()) > 3

    # 2. to_detailed_llm_blueprint
    bp = pg.to_detailed_llm_blueprint()
    assert "Directory Structure & Source Files" in bp

    # 3. to_topological_architectural_summary
    summary = pg.to_topological_architectural_summary()
    assert "Architecture & Topology Breakdown" in summary

    # 4. to_curated_dashboard
    dash = pg.to_curated_dashboard()
    assert "System Architecture Map" in dash
    assert "Execution & Lifecycle Pipeline" in dash

    # 5. to_ai_architectural_analysis (with mock and fallback)
    with patch("sago.llm.tui_providers.generate_with_provider") as mock_gen:
        mock_gen.return_value = "### 🏛️ System Architecture\nClean architecture detected."
        ai_rep = pg.to_ai_architectural_analysis(provider="mock", model="mock-model")
        assert "Clean architecture detected" in ai_rep

        # Fallback branch on exception
        mock_gen.side_effect = RuntimeError("LLM offline")
        fallback_rep = pg.to_ai_architectural_analysis()
        assert "Architecture & Topology Breakdown" in fallback_rep


def test_project_graph_serialization_roundtrip(tmp_path: Path) -> None:
    f1 = tmp_path / "service.py"
    f1.write_text("import db\nclass Service:\n    pass\n")
    f2 = tmp_path / "db.py"
    f2.write_text("class Database:\n    pass\n")

    pg = ProjectGraph(root_dir=tmp_path)
    pg.build_graph()

    d = pg.to_dict()
    assert d["root"] == str(tmp_path)
    assert d["node_count"] >= 2

    # Reconstruct from dict
    pg_reconstructed = ProjectGraph.from_dict(d)
    assert len(pg_reconstructed.nodes) == len(pg.nodes)
    assert len(pg_reconstructed.edges) == len(pg.edges)


def test_get_cached_project_graph(tmp_path: Path) -> None:
    f1 = tmp_path / "module.py"
    f1.write_text("x = 10\n")

    # First load (builds & caches)
    g1 = get_cached_project_graph(root_dir=tmp_path, ttl_seconds=60)
    assert g1 is not None

    # Second load (cached hit)
    g2 = get_cached_project_graph(root_dir=tmp_path, ttl_seconds=60)
    assert g2 is g1

    # Force reload
    g3 = get_cached_project_graph(root_dir=tmp_path, ttl_seconds=60, force_refresh=True)
    assert g3 is not None
