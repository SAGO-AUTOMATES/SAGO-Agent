"""Hardened unit and integration tests for Project & Data Graph engine and tools."""

import tempfile
import unittest
from pathlib import Path

from sago.memory.project_graph import ProjectGraph
from sago.tools.coding.project_graph_tool import ProjectGraphTool


class TestProjectGraphHardened(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        # 1. Python Models & Routers
        py_models = self.root / "models.py"
        py_models.write_text(
            "from pydantic import BaseModel, Field\n\n"
            "class UserModel(BaseModel):\n"
            "    id: int\n"
            "    username: str\n"
            "    is_active: bool = True\n\n"
            "class OrderSchema(BaseModel):\n"
            "    order_id: str\n"
            "    amount: float\n"
        )

        py_routes = self.root / "routes.py"
        py_routes.write_text(
            "from models import UserModel, OrderSchema\n\n"
            "@app.get('/users')\n"
            "def list_users() -> list[UserModel]:\n"
            "    return []\n"
        )

        # 2. TypeScript Interfaces
        ts_file = self.root / "types.ts"
        ts_file.write_text(
            "export interface ProductDTO {\n"
            "  id: string;\n"
            "  title: string;\n"
            "}\n"
            "export type SessionState = 'active' | 'idle';\n"
            "export async function fetchProducts(): Promise<ProductDTO[]> { return []; }\n"
        )

        # 3. Rust structs & enums
        rs_file = self.root / "engine.rs"
        rs_file.write_text(
            "pub struct NodeConfig {\n"
            "    pub port: u16,\n"
            "}\n"
            "pub enum NodeStatus {\n"
            "    Online,\n"
            "    Offline,\n"
            "}\n"
            "pub fn start_node(cfg: NodeConfig) -> NodeStatus {\n"
            "    NodeStatus::Online\n"
            "}\n"
        )

        # 4. Go structs
        go_file = self.root / "server.go"
        go_file.write_text(
            "package main\n\n"
            "type ServerConfig struct {\n"
            "    Host string\n"
            "    Port int\n"
            "}\n"
            "func StartServer(cfg ServerConfig) error {\n"
            "    return nil\n"
            "}\n"
        )

        # 5. SQL Table
        sql_file = self.root / "schema.sql"
        sql_file.write_text(
            "CREATE TABLE IF NOT EXISTS audit_logs (\n"
            "    id INTEGER PRIMARY KEY,\n"
            "    action TEXT NOT NULL,\n"
            "    created_at TIMESTAMP\n"
            ");\n"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_polyglot_graph_building(self):
        pg = ProjectGraph(root_dir=self.root)
        pg.build_graph()

        # Check nodes across all languages
        self.assertTrue(any("UserModel" in n.label for n in pg.nodes.values()))
        self.assertTrue(any("OrderSchema" in n.label for n in pg.nodes.values()))
        self.assertTrue(any("ProductDTO" in n.label for n in pg.nodes.values()))
        self.assertTrue(any("NodeConfig" in n.label for n in pg.nodes.values()))
        self.assertTrue(any("ServerConfig" in n.label for n in pg.nodes.values()))
        self.assertTrue(any("TABLE audit_logs" in n.label for n in pg.nodes.values()))
        self.assertTrue(any("list_users()" in n.label for n in pg.nodes.values()))

        # Check edges
        self.assertTrue(any(e.relation == "imports" for e in pg.edges))
        self.assertTrue(any(e.relation == "defines" for e in pg.edges))

    def test_er_diagram_generation(self):
        pg = ProjectGraph(root_dir=self.root)
        pg.build_graph()

        er_output = pg.to_er_diagram()
        self.assertIn("ENTITY RELATIONSHIP & DATA MODEL MAP", er_output)
        self.assertIn("UserModel", er_output)
        self.assertIn("id: int", er_output)
        self.assertIn("username: str", er_output)

    def test_architecture_box_diagram(self):
        pg = ProjectGraph(root_dir=self.root)
        pg.build_graph()

        arch = pg.to_architecture_diagram()
        self.assertIn("SAGO SYSTEM ARCHITECTURE MAP", arch)
        self.assertIn("PRESENTATION & INTERFACE", arch)
        self.assertIn("MEMORY, STATE & DATABASE", arch)

    def test_process_map_generation(self):
        pg = ProjectGraph(root_dir=self.root)
        pg.build_graph()

        proc = pg.to_process_map()
        self.assertIn("SAGO END-TO-END AUTONOMOUS PROCESS & EXECUTION PIPELINE", proc)
        self.assertIn("Intent Routing & Delegation", proc)
        self.assertIn("Self-Healing Verification", proc)

    def test_mermaid_focus_filter(self):
        pg = ProjectGraph(root_dir=self.root)
        pg.build_graph()

        mermaid_all = pg.to_mermaid()
        self.assertIn("flowchart TD", mermaid_all)

        mermaid_filtered = pg.to_mermaid(focus_filter="models")
        self.assertIn("flowchart TD", mermaid_filtered)

    def test_empty_workspace_resilience(self):
        empty_dir = self.root / "empty_dir"
        empty_dir.mkdir()
        pg = ProjectGraph(root_dir=empty_dir)
        pg.build_graph()

        self.assertEqual(len(pg.nodes), 0)
        self.assertEqual(len(pg.edges), 0)
        self.assertIn("Topology Metrics", pg.to_curated_dashboard())
        self.assertIn("No explicit data models", pg.to_er_diagram())

    def test_visual_flowchart_generation(self):
        pg = ProjectGraph(root_dir=self.root)
        pg.build_graph()

        flow = pg.to_visual_flowchart()
        self.assertIn("COMPONENT DEPENDENCY & DATA FLOW PIPELINE", flow)
        self.assertIn("routes.py", flow)
        self.assertIn("models.py", flow)

    def test_project_graph_tool_all_views(self):
        tool = ProjectGraphTool()
        views = ["dashboard", "arch", "process", "er", "flow", "tree", "mermaid", "json", "llm"]
        for v in views:
            res = tool.run(directory=str(self.root), view=v)
            self.assertIsInstance(res, str)
            self.assertGreater(len(res), 10)


if __name__ == "__main__":
    unittest.main()
