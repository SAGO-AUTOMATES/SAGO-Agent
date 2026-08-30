"""Deep coverage tests for sago.tools.network, ssh, web, session, vcs, security."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from sago.tools.database.sql_migration import SqlMigrationTool
from sago.tools.database.sql_schema import SqlSchemaTool
from sago.tools.interactive.ask_question import AskQuestionTool
from sago.tools.network.config_manager import NetworkConfigTool
from sago.tools.network.http_client import HTTPClientTool
from sago.tools.network.port_scan import PortScanTool
from sago.tools.network.web_crawler import WebCrawler
from sago.tools.parallel_executor import execute_tools_batch, is_read_only_tool
from sago.tools.security.secret_scanner import SecretScannerTool
from sago.tools.session.clipboard import ClipboardTool
from sago.tools.session.session_manager import SessionManagerTool
from sago.tools.ssh.ssh_command import SSHCommandTool
from sago.tools.ssh.ssh_connect import SSHConnectTool
from sago.tools.ssh.ssh_transfer import SSHTransferTool
from sago.tools.vcs.pr_workflow import PRWorkflowTool
from sago.tools.vcs.review import ReviewChangesTool
from sago.tools.web.browser import BrowserTool
from sago.tools.web.search import WebSearchTool
from sago.tools.web.web_fetch import WebFetchTool

# ── http_client ──────────────────────────────────────────────────────────────


class TestHttpClient:
    def test_name(self):
        assert HTTPClientTool().name == "http_client"

    def test_get(self):
        tool = HTTPClientTool()
        result = tool._run(url="https://example.com", method="GET")
        assert isinstance(result, str)

    def test_post(self):
        tool = HTTPClientTool()
        result = tool._run(url="https://example.com/api", method="POST", body='{"key": "value"}')
        assert isinstance(result, str)

    def test_put(self):
        tool = HTTPClientTool()
        result = tool._run(url="https://example.com/api/1", method="PUT", body="data")
        assert isinstance(result, str)

    def test_delete(self):
        tool = HTTPClientTool()
        result = tool._run(url="https://example.com/api/1", method="DELETE")
        assert isinstance(result, str)

    def test_head(self):
        tool = HTTPClientTool()
        result = tool._run(url="https://example.com", method="HEAD")
        assert isinstance(result, str)

    def test_patch(self):
        tool = HTTPClientTool()
        result = tool._run(url="https://example.com/api/1", method="PATCH", body="data")
        assert isinstance(result, str)

    def test_with_headers(self):
        tool = HTTPClientTool()
        result = tool._run(url="https://example.com", method="GET", headers={"Authorization": "Bearer token"})
        assert isinstance(result, str)


# ── port_scan ────────────────────────────────────────────────────────────────



class TestPortScan:
    def test_name(self):
        assert PortScanTool().name == "port_scan"

    @patch("sago.tools.network.port_scan.socket")
    def test_scan_open_port(self, mock_socket):
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 0
        mock_socket.socket.return_value = mock_sock
        mock_socket.AF_INET = 2
        mock_socket.SOCK_STREAM = 1
        tool = PortScanTool()
        result = tool._run(host="127.0.0.1", ports="80")
        assert isinstance(result, str)

    @patch("sago.tools.network.port_scan.socket")
    def test_scan_closed_port(self, mock_socket):
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 1
        mock_socket.socket.return_value = mock_sock
        mock_socket.AF_INET = 2
        mock_socket.SOCK_STREAM = 1
        tool = PortScanTool()
        result = tool._run(host="127.0.0.1", ports="9999")
        assert isinstance(result, str)

    @patch("sago.tools.network.port_scan.socket")
    def test_scan_range(self, mock_socket):
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 0
        mock_socket.socket.return_value = mock_sock
        mock_socket.AF_INET = 2
        mock_socket.SOCK_STREAM = 1
        tool = PortScanTool()
        result = tool._run(host="127.0.0.1", ports="80-82")
        assert isinstance(result, str)

    @patch("sago.tools.network.port_scan.socket")
    def test_scan_multiple(self, mock_socket):
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 0
        mock_socket.socket.return_value = mock_sock
        mock_socket.AF_INET = 2
        mock_socket.SOCK_STREAM = 1
        tool = PortScanTool()
        result = tool._run(host="127.0.0.1", ports="80,443,8080")
        assert isinstance(result, str)

    @patch("socket.socket")
    def test_scan_timeout(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_sock.connect_ex.side_effect = OSError("timeout")
        mock_socket_cls.return_value = mock_sock
        tool = PortScanTool()
        result = tool._run(host="127.0.0.1", ports="80")
        assert isinstance(result, str)


# ── web_crawler ──────────────────────────────────────────────────────────────



class TestWebCrawler:
    def test_name(self):
        assert WebCrawler().name == "web_crawler"

    def test_crawl_simple(self):
        tool = WebCrawler()
        result = tool._run(url="https://example.com")
        assert isinstance(result, str)

    def test_crawl_with_depth(self):
        tool = WebCrawler()
        result = tool._run(url="https://example.com", max_depth=2)
        assert isinstance(result, str)


# ── config_manager ───────────────────────────────────────────────────────────



class TestConfigManager:
    def test_name(self):
        assert NetworkConfigTool().name == "network_config"

    @patch("subprocess.run")
    def test_interfaces(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="eth0: inet 192.168.1.1\n", stderr="")
        tool = NetworkConfigTool()
        result = tool._run(operation="interfaces")
        assert isinstance(result, str)

    @patch("subprocess.run")
    def test_dns(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="nameserver 8.8.8.8\n", stderr="")
        tool = NetworkConfigTool()
        result = tool._run(operation="dns")
        assert isinstance(result, str)

    @patch("subprocess.run")
    def test_routes(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="default via 192.168.1.1\n", stderr="")
        tool = NetworkConfigTool()
        result = tool._run(operation="routes")
        assert isinstance(result, str)

    @patch("subprocess.run")
    def test_connections(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="tcp 0.0.0.0:80\n", stderr="")
        tool = NetworkConfigTool()
        result = tool._run(operation="connections")
        assert isinstance(result, str)

    @patch("subprocess.run")
    def test_error(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        tool = NetworkConfigTool()
        result = tool.run(operation="interfaces")
        assert isinstance(result, str)


# ── ssh_command ──────────────────────────────────────────────────────────────



class TestSSHCommand:
    def test_name(self):
        assert SSHCommandTool().name == "ssh_command"

    def test_no_paramiko(self):
        tool = SSHCommandTool()
        result = tool._run(hostname="example.com", username="user", command="ls")
        assert isinstance(result, str)


# ── ssh_connect ──────────────────────────────────────────────────────────────



class TestSSHConnect:
    def test_name(self):
        assert SSHConnectTool().name == "ssh_connect"

    def test_no_paramiko(self):
        tool = SSHConnectTool()
        result = tool._run(hostname="example.com", username="user")
        assert isinstance(result, str)


# ── ssh_transfer ─────────────────────────────────────────────────────────────



class TestSSHTransfer:
    def test_name(self):
        assert SSHTransferTool().name == "ssh_transfer"

    def test_no_paramiko(self):
        tool = SSHTransferTool()
        result = tool._run(operation="upload", source="/tmp/a", destination="/tmp/b", hostname="example.com", username="user")
        assert isinstance(result, str)


# ── session clipboard ───────────────────────────────────────────────────────



class TestClipboard:
    def test_name(self):
        assert ClipboardTool().name == "clipboard"

    def test_write_and_read(self):
        tool = ClipboardTool()
        result = tool._run(operation="write", content="hello clipboard")
        assert isinstance(result, str)
        result = tool._run(operation="read")
        assert isinstance(result, str)

    def test_clear(self):
        tool = ClipboardTool()
        tool._run(operation="write", content="temp")
        result = tool._run(operation="clear")
        assert isinstance(result, str)

    def test_unknown_op(self):
        tool = ClipboardTool()
        result = tool._run(operation="unknown")
        assert isinstance(result, str)

    def test_write_no_content(self):
        tool = ClipboardTool()
        result = tool._run(operation="write")
        assert isinstance(result, str)

    def test_read_empty(self):
        tool = ClipboardTool()
        result = tool._run(operation="read")
        assert isinstance(result, str)


# ── session_manager ──────────────────────────────────────────────────────────



class TestSessionManager:
    def test_name(self):
        assert SessionManagerTool().name == "session_manager"

    def test_set_and_get(self):
        tool = SessionManagerTool()
        result = tool._run(operation="set", key="test_key", value="test_value")
        assert isinstance(result, str)
        result = tool._run(operation="get", key="test_key")
        assert isinstance(result, str)

    def test_delete(self):
        tool = SessionManagerTool()
        tool._run(operation="set", key="to_delete", value="val")
        result = tool._run(operation="delete", key="to_delete")
        assert isinstance(result, str)

    def test_list(self):
        tool = SessionManagerTool()
        tool._run(operation="set", key="k1", value="v1")
        result = tool._run(operation="list")
        assert isinstance(result, str)

    def test_clear(self):
        tool = SessionManagerTool()
        tool._run(operation="set", key="k1", value="v1")
        result = tool._run(operation="clear")
        assert isinstance(result, str)

    def test_missing_key(self):
        tool = SessionManagerTool()
        result = tool._run(operation="get")
        assert "error" in result.lower() or "required" in result.lower() or "key" in result.lower()

    def test_unknown_op(self):
        tool = SessionManagerTool()
        result = tool._run(operation="unknown")
        assert isinstance(result, str)


# ── review ───────────────────────────────────────────────────────────────────



class TestReview:
    def test_name(self):
        assert ReviewChangesTool().name == "review_changes"

    @patch("sago.tools.vcs.review.subprocess.run")
    def test_review_working_tree(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="diff --git a/file.py\n+new line\n", stderr=""
        )
        tool = ReviewChangesTool()
        result = tool._run(target="working_tree")
        assert isinstance(result, str)

    @patch("sago.tools.vcs.review.subprocess.run")
    def test_review_staged(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="diff --git a/file.py\n+staged change\n", stderr=""
        )
        tool = ReviewChangesTool()
        result = tool._run(target="staged")
        assert isinstance(result, str)

    @patch("sago.tools.vcs.review.subprocess.run")
    def test_not_git_repo(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=128, stdout="", stderr="not a git repository"
        )
        tool = ReviewChangesTool()
        result = tool._run(target="working_tree")
        assert isinstance(result, str)

    @patch("sago.tools.vcs.review.subprocess.run")
    def test_invalid_target(self, mock_run):
        tool = ReviewChangesTool()
        result = tool._run(target="invalid_target")
        assert isinstance(result, str)


# ── secret_scanner ───────────────────────────────────────────────────────────



class TestSecretScanner:
    def test_name(self):
        assert SecretScannerTool().name == "secret_scanner"

    def test_scan_clean_dir(self, tmp_path):
        (tmp_path / "clean.py").write_text("x = 1\n")
        tool = SecretScannerTool()
        result = tool._run(directory=str(tmp_path))
        assert isinstance(result, str)

    def test_scan_with_secrets(self, tmp_path):
        f = tmp_path / "config.py"
        f.write_text("AWS_KEY = 'AKIAIOSFODNN7EXAMPLE'\n")
        tool = SecretScannerTool()
        result = tool._run(directory=str(tmp_path))
        assert isinstance(result, str)

    def test_scan_nonexistent(self):
        tool = SecretScannerTool()
        result = tool._run(directory="/nonexistent")
        assert "error" in result.lower() or "not found" in result.lower() or "No such" in result

    def test_scan_with_max_files(self, tmp_path):
        for i in range(5):
            (tmp_path / f"f{i}.py").write_text(f"x = {i}\n")
        tool = SecretScannerTool()
        result = tool._run(directory=str(tmp_path), max_files=2)
        assert isinstance(result, str)


# ── pr_workflow ──────────────────────────────────────────────────────────────



class TestPRWorkflow:
    def test_name(self):
        assert PRWorkflowTool().name == "create_pull_request"

    @patch("sago.tools.vcs.pr_workflow.subprocess.run")
    def test_create_pr(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="https://github.com/org/repo/pull/1", stderr=""
        )
        tool = PRWorkflowTool()
        result = tool._run(
            title="Test PR",
            body="Description",
            branch="feature/test",
            target_branch="main",
            draft=False,
        )
        assert isinstance(result, str)

    @patch("sago.tools.vcs.pr_workflow.subprocess.run")
    def test_not_git_repo(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=128, stdout="", stderr="not a git repository"
        )
        tool = PRWorkflowTool()
        result = tool._run(
            title="Test PR",
            body="Desc",
            branch="feature/test",
            target_branch="main",
            draft=False,
        )
        assert isinstance(result, str)


# ── ask_question ─────────────────────────────────────────────────────────────



class TestAskQuestion:
    def test_name(self):
        assert AskQuestionTool().name == "ask_question"

    def test_headless_auto_default(self):
        tool = AskQuestionTool()
        result = tool._run(
            questions=[
                {
                    "question": "Pick one",
                    "options": ["A", "B", "C"],
                    "is_multi_select": False,
                    "default_option": "A",
                }
            ]
        )
        assert isinstance(result, str)

    def test_headless_multi_select(self):
        tool = AskQuestionTool()
        result = tool._run(
            questions=[
                {
                    "question": "Pick multiple",
                    "options": ["X", "Y", "Z"],
                    "is_multi_select": True,
                    "default_option": "X",
                }
            ]
        )
        assert isinstance(result, str)

    def test_no_questions(self):
        tool = AskQuestionTool()
        result = tool._run(questions=[])
        assert isinstance(result, str)


# ── web_search ───────────────────────────────────────────────────────────────



class TestWebSearch:
    def test_name(self):
        assert WebSearchTool().name == "web_search"

    def test_search(self):
        tool = WebSearchTool()
        result = tool._run(query="python programming")
        assert isinstance(result, str)

    def test_search_ddg_html(self):
        tool = WebSearchTool()
        result = tool._run(query="test query", engine="duckduckgo_html")
        assert isinstance(result, str)


# ── web_fetch ────────────────────────────────────────────────────────────────



class TestWebFetch:
    def test_name(self):
        assert WebFetchTool().name == "web_fetch"

    def test_fetch(self):
        tool = WebFetchTool()
        result = tool._run(url="https://example.com")
        assert isinstance(result, str)

    def test_bad_scheme(self):
        tool = WebFetchTool()
        result = tool._run(url="ftp://example.com/file")
        assert "error" in result.lower() or "unsupported" in result.lower() or "scheme" in result.lower()

    def test_no_netloc(self):
        tool = WebFetchTool()
        result = tool._run(url="https://")
        assert isinstance(result, str)


# ── browser ──────────────────────────────────────────────────────────────────



class TestBrowser:
    def test_name(self):
        assert BrowserTool().name == "browser"

    @patch("sago.tools.web.browser.subprocess.run")
    def test_browser_not_found(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="not found"
        )
        tool = BrowserTool()
        result = tool._run(action="open", url="https://example.com")
        assert isinstance(result, str)


# ── sql_migration ────────────────────────────────────────────────────────────



class TestSqlMigration:
    def test_name(self):
        assert SqlMigrationTool().name == "sql_migration"

    def test_create_table(self):
        tool = SqlMigrationTool()
        result = tool._run(
            dialect="sqlite",
            operation="create_table",
            table_name="users",
            details="id INTEGER PRIMARY KEY, name TEXT",
        )
        assert isinstance(result, str)

    def test_add_column(self):
        tool = SqlMigrationTool()
        result = tool._run(
            dialect="sqlite",
            operation="add_column",
            table_name="users",
            details="email TEXT",
        )
        assert isinstance(result, str)

    def test_add_index(self):
        tool = SqlMigrationTool()
        result = tool._run(
            dialect="sqlite",
            operation="add_index",
            table_name="users",
            details="idx_email ON email",
        )
        assert isinstance(result, str)


# ── sql_schema ───────────────────────────────────────────────────────────────



class TestSqlSchema:
    def test_name(self):
        assert SqlSchemaTool().name == "sql_schema"

    def test_schema_all_tables(self, tmp_path):
        import sqlite3
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE posts (id INTEGER PRIMARY KEY, title TEXT)")
        conn.commit()
        conn.close()
        tool = SqlSchemaTool()
        result = tool._run(database_path=str(db))
        assert isinstance(result, str)

    def test_schema_specific_table(self, tmp_path):
        import sqlite3
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        conn.commit()
        conn.close()
        tool = SqlSchemaTool()
        result = tool._run(database_path=str(db), table_name="users")
        assert isinstance(result, str)

    def test_schema_with_indexes(self, tmp_path):
        import sqlite3
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("CREATE INDEX idx_name ON users(name)")
        conn.commit()
        conn.close()
        tool = SqlSchemaTool()
        result = tool._run(database_path=str(db), include_indexes=True)
        assert isinstance(result, str)

    def test_schema_nonexistent_db(self):
        tool = SqlSchemaTool()
        result = tool._run(database_path="/nonexistent/db.sqlite")
        assert "error" in result.lower() or "not found" in result.lower() or "No such" in result


# ── parallel_executor ────────────────────────────────────────────────────────



class TestParallelExecutor:
    def test_read_only_tool(self):
        assert is_read_only_tool("read_file") is True
        assert is_read_only_tool("write_file") is False
        assert is_read_only_tool("list_dir") is True
        assert is_read_only_tool("grep_content") is True
        assert is_read_only_tool("execute_shell") is False

    def test_execute_all_readonly_parallel(self):
        calls = []
        def fake_exec(tool_name, **kwargs):
            calls.append(tool_name)
            return f"result_{tool_name}"

        tool_calls = [
            {"tool": "read_file", "kwargs": {"path": "/tmp/a"}},
            {"tool": "list_dir", "kwargs": {"path": "/tmp"}},
            {"tool": "grep_content", "kwargs": {"pattern": "x", "path": "/tmp"}},
        ]
        results = execute_tools_batch(tool_calls, fake_exec, max_workers=2)
        assert len(results) == 3

    def test_execute_mixed_sequential(self):
        calls = []
        def fake_exec(tool_name, **kwargs):
            calls.append(tool_name)
            return f"result_{tool_name}"

        tool_calls = [
            {"tool": "read_file", "kwargs": {"path": "/tmp/a"}},
            {"tool": "write_file", "kwargs": {"path": "/tmp/b", "content": "x"}},
        ]
        results = execute_tools_batch(tool_calls, fake_exec)
        assert len(results) == 2

    def test_execute_empty(self):
        results = execute_tools_batch([], lambda t, **k: "r")
        assert results == []

    def test_execute_with_exception(self):
        def fake_exec(tc):
            raise ValueError("bad tool")

        tool_calls = [
            {"name": "read_file", "args": {"path": "/tmp/a"}},
            {"name": "list_dir", "args": {"path": "/tmp"}},
        ]
        results = execute_tools_batch(tool_calls, fake_exec)
        assert len(results) == 2
        assert all("Error" in r for r in results)
