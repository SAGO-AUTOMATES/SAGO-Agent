"""Tests for Mesh protocol security, MultiReplaceTool, LSPClient, and network/admin tools."""

from __future__ import annotations

import time
from pathlib import Path

from sago.peers.mesh import MeshCoordinator, MeshMessage, MeshNetwork, MeshNode
from sago.tools.admin.software_install import SoftwareInstallTool
from sago.tools.admin.sudo_executor import SudoExecutorTool
from sago.tools.coding.ast_editor import ASTEditor
from sago.tools.coding.debugger import DebuggerTool
from sago.tools.coding.lsp_client import LSPClient
from sago.tools.file.multi_replace_file import MultiReplaceTool
from sago.tools.network.port_scan import PortScanTool
from sago.tools.network.web_crawler import WebCrawler
from sago.tools.system.screenshot import Screenshot


def test_mesh_message_signing_and_verification():
    secret = "test-secret-key-12345"
    msg = MeshMessage(
        type="task_request",
        sender="node-a",
        receiver="node-b",
        payload={"task": "run analysis", "agent": "coder"},
        timestamp=time.time(),
    )
    assert msg.verify(secret) is False  # not signed yet

    msg.sign(secret)
    assert msg.signature is not None
    assert msg.verify(secret) is True

    # Tampering payload invalidates signature
    msg.payload["task"] = "malicious task"
    assert msg.verify(secret) is False

    # Invalid secret fails verification
    assert msg.verify("wrong-secret") is False


def test_mesh_network_node_management():
    net = MeshNetwork(node_id="local-node", auth_secret="sec123")
    node = MeshNode(
        id="peer-1",
        hostname="peer1.local",
        ip_address="192.168.1.50",
        port=7654,
        last_heartbeat=time.time(),
        load=15.0,
    )
    net.nodes[node.id] = node
    assert node.is_alive is True

    best = net.get_best_node()
    assert best is not None
    assert best.id == "peer-1"

    node_dict = node.to_dict()
    assert node_dict["id"] == "peer-1"
    assert node_dict["load"] == 15.0

    coord = MeshCoordinator()
    status = coord.get_status()
    assert "node_id" in status
    assert "total_nodes" in status


def test_multi_replace_tool_success_and_errors(tmp_path: Path):
    tool = MultiReplaceTool()
    # Missing args
    assert "Error: file_path is required" in tool.run()
    assert "Error: chunks list is required" in tool.run(file_path="some_path.txt")

    # Nonexistent file
    assert "Error: File not found" in tool.run(
        file_path=str(tmp_path / "missing.txt"),
        chunks=[{"old": "a", "new": "b"}],
    )

    # Valid multi-replace
    f = tmp_path / "code.py"
    f.write_text("def alpha():\n    return 1\n\ndef beta():\n    return 2\n")

    res = tool.run(
        file_path=str(f),
        chunks=[
            {"old_string": "return 1", "new_string": "return 10"},
            {"old": "return 2", "new": "return 20"},
        ],
    )
    assert "Successfully applied 2 replacement(s)" in res
    assert "return 10" in f.read_text()
    assert "return 20" in f.read_text()


def test_lsp_client_symbol_and_definitions(tmp_path: Path):
    lsp = LSPClient()
    source_file = tmp_path / "example.py"
    source_file.write_text(
        "def compute_total(a, b):\n    return a + b\n\ntotal = compute_total(10, 20)\n"
    )

    defs = lsp.get_definitions(str(source_file), line=3, column=10)
    assert isinstance(defs, list)

    hover = lsp.get_hover(str(source_file), line=1, column=6)
    assert hover is not None
    assert hover["symbol"] == "compute_total"
    assert hover["kind"] == "function"

    diagnostics = lsp.get_diagnostics(str(source_file))
    assert isinstance(diagnostics, list)


def test_ast_editor_python_and_multilang():
    editor = ASTEditor()
    py_code = "class Calculator:\n    def add(self, a, b):\n        return a + b\n"
    nodes = editor.analyze(py_code, language="python")
    assert any(n.name == "Calculator" and n.node_type == "class" for n in nodes)
    assert any(n.name == "add" and n.node_type == "function" for n in nodes)

    js_code = "function calculateSum(x, y) {\n    return x + y;\n}\n"
    js_nodes = editor.analyze(js_code, language="javascript")
    assert any(n.name == "calculateSum" for n in js_nodes)

    # Rename symbol
    renamed = editor.rename_symbol(py_code, "Calculator", "AdvancedCalculator")
    assert "class AdvancedCalculator:" in renamed

    # Add import
    with_import = editor.add_import(py_code, "import math", language="python")
    assert "import math" in with_import


def test_debugger_static_and_error_analysis():
    dbg = DebuggerTool()
    err_analysis = dbg.run(
        error_message="TypeError: unsupported operand type(s) for +: 'int' and 'str'"
    )
    assert "Type Error" in err_analysis

    syntax_err_analysis = dbg.run(error_message="SyntaxError: invalid syntax (test.py, line 42)")
    assert "Syntax Error" in syntax_err_analysis
    assert "42" in syntax_err_analysis

    code_analysis = dbg.run(
        code_snippet="def bad_func(val=[]):\n    try:\n        pass\n    except:\n        pass\n"
    )
    assert "Mutable default argument" in code_analysis
    assert "Bare except" in code_analysis


def test_port_scan_tool_parsing():
    scanner = PortScanTool()
    ports = scanner._parse_ports("80,443,8000-8002")
    assert ports == [80, 443, 8000, 8001, 8002]


def test_web_crawler_html_parsing():
    crawler = WebCrawler()
    # Test on invalid scheme / mock behavior without crashing
    res = crawler.run(url="http://127.0.0.1:9", max_depth=0, max_pages=1)
    assert isinstance(res, str)


def test_software_install_and_sudo_tools():
    pkg_tool = SoftwareInstallTool()
    assert pkg_tool.name == "software_install"
    assert "apt" in pkg_tool._MANAGER_COMMANDS

    sudo_tool = SudoExecutorTool()
    assert sudo_tool.name == "sudo_executor"


def test_screenshot_tool_metadata():
    tool = Screenshot()
    assert tool.name == "screenshot"
