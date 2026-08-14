"""Unit tests for Project & Data Graph engine and tool."""

import tempfile
import unittest
from pathlib import Path

from sago.memory.project_graph import ProjectGraph
from sago.tools.coding.project_graph_tool import ProjectGraphTool


class TestProjectGraph(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

        # Setup mock files
        py_file = self.tmp_path / "models.py"
        py_file.write_text(
            "from pydantic import BaseModel\n\n"
            "class UserModel(BaseModel):\n"
            "    id: int\n"
            "    name: str\n"
        )

        api_file = self.tmp_path / "api.py"
        api_file.write_text(
            "from models import UserModel\n\n"
            "def get_user() -> UserModel:\n"
            "    return UserModel(id=1, name='Alice')\n"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_project_graph_build(self):
        pg = ProjectGraph(root_dir=self.tmp_path)
        pg.build_graph()

        self.assertGreaterEqual(len(pg.nodes), 2)
        self.assertTrue(any("UserModel" in n.label for n in pg.nodes.values()))
        self.assertTrue(any(e.relation == "imports" for e in pg.edges))

        # Test formats
        ascii_out = pg.to_ascii_tree()
        self.assertIn("models.py", ascii_out)
        self.assertIn("UserModel", ascii_out)

        arch_out = pg.to_architecture_diagram()
        self.assertIn("SYSTEM ARCHITECTURE MAP", arch_out)

        proc_out = pg.to_process_map()
        self.assertIn("EXECUTION & LIFECYCLE PIPELINE", proc_out)

        mermaid_out = pg.to_mermaid()
        self.assertIn("```mermaid", mermaid_out)
        self.assertIn("flowchart TD", mermaid_out)

        llm_out = pg.to_llm_context()
        self.assertIn("### Project Dependency", llm_out)

        dashboard_out = pg.to_curated_dashboard()
        self.assertIn("Architecture Dashboard", dashboard_out)

        json_dict = pg.to_dict()
        self.assertGreaterEqual(json_dict["node_count"], 2)

    def test_project_graph_tool(self):
        tool = ProjectGraphTool()
        res = tool.run(directory=str(self.tmp_path), view="dashboard")
        self.assertIn("Architecture Dashboard", res)

        arch_res = tool.run(directory=str(self.tmp_path), view="arch")
        self.assertIn("SYSTEM ARCHITECTURE MAP", arch_res)


if __name__ == "__main__":
    unittest.main()
