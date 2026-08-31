"""Comprehensive unit tests for sago tools: ssh, session, web, vcs, system, file modules."""

import json
import os
import platform
import re
import tempfile
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, Mock, mock_open, patch, call

import pytest


# ---------------------------------------------------------------------------
# SSH Command
# ---------------------------------------------------------------------------


class TestSSHCommandTool:
    def _make(self):
        from sago.tools.ssh.ssh_command import SSHCommandTool

        return SSHCommandTool()

    def test_name_and_description(self):
        t = self._make()
        assert t.name == "ssh_command"
        assert "remote" in t.description.lower()

    @patch("sago.tools.ssh.ssh_command.SSHCommandTool._expand_path")
    def test_run_paramiko_not_installed(self, mock_expand):
        with patch.dict("sys.modules", {"paramiko": None}):
            t = self._make()
            result = t._run(hostname="h", username="u", command="ls")
            assert "paramiko is not installed" in result

    @patch("sago.tools.ssh.ssh_command.SSHCommandTool._expand_path")
    def test_run_auth_failure(self, mock_expand):
        mock_paramiko = MagicMock()
        mock_client = MagicMock()
        mock_paramiko.SSHClient.return_value = mock_client
        mock_paramiko.AutoAddPolicy.return_value = MagicMock()
        mock_paramiko.AuthenticationException = type("AuthenticationException", (Exception,), {})
        mock_client.connect.side_effect = mock_paramiko.AuthenticationException("auth fail")

        with patch.dict("sys.modules", {"paramiko": mock_paramiko}):
            t = self._make()
            result = t._run(hostname="h", username="u", command="ls", password="pw")
            assert "Authentication failed" in result

    @patch("sago.tools.ssh.ssh_command.SSHCommandTool._expand_path")
    def test_run_success(self, mock_expand):
        mock_paramiko = MagicMock()
        mock_client = MagicMock()
        mock_paramiko.SSHClient.return_value = mock_client
        mock_paramiko.AutoAddPolicy.return_value = MagicMock()

        mock_stdout = MagicMock()
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stdout.read.return_value = b"output"
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b"err"
        mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

        with patch.dict("sys.modules", {"paramiko": mock_paramiko}):
            t = self._make()
            result = t._run(hostname="h", username="u", command="echo hi")
            assert "Exit code: 0" in result
            assert "output" in result

    @patch("sago.tools.ssh.ssh_command.SSHCommandTool._expand_path")
    def test_run_exception(self, mock_expand):
        mock_paramiko = MagicMock()
        mock_client = MagicMock()
        mock_paramiko.SSHClient.return_value = mock_client
        mock_paramiko.AuthenticationException = type("AuthenticationException", (Exception,), {})
        mock_client.connect.side_effect = OSError("connection refused")

        with patch.dict("sys.modules", {"paramiko": mock_paramiko}):
            t = self._make()
            result = t._run(hostname="h", username="u", command="ls")
            assert "Error" in result


# ---------------------------------------------------------------------------
# SSH Connect
# ---------------------------------------------------------------------------


class TestSSHConnectTool:
    def _make(self):
        from sago.tools.ssh.ssh_connect import SSHConnectTool

        return SSHConnectTool()

    def test_name(self):
        assert self._make().name == "ssh_connect"

    @patch("sago.tools.ssh.ssh_connect.SSHConnectTool._expand_path")
    def test_connect_success(self, mock_expand):
        mock_paramiko = MagicMock()
        mock_client = MagicMock()
        mock_paramiko.SSHClient.return_value = mock_client
        mock_paramiko.AutoAddPolicy.return_value = MagicMock()

        transport = MagicMock()
        transport.getpeername.return_value = ("1.2.3.4", 22)
        mock_client.get_transport.return_value = transport

        mock_stdout = MagicMock()
        mock_stdout.read.return_value = b"Linux host 5.4"
        mock_client.exec_command.return_value = (MagicMock(), mock_stdout, MagicMock())

        with patch.dict("sys.modules", {"paramiko": mock_paramiko}):
            t = self._make()
            result = t._run(hostname="h", username="u")
            assert "successful" in result.lower()
            assert "1.2.3.4" in result

    @patch("sago.tools.ssh.ssh_connect.SSHConnectTool._expand_path")
    def test_connect_auth_failure(self, mock_expand):
        mock_paramiko = MagicMock()
        mock_client = MagicMock()
        mock_paramiko.SSHClient.return_value = mock_client
        mock_paramiko.AuthenticationException = type("AuthenticationException", (Exception,), {})
        mock_client.connect.side_effect = mock_paramiko.AuthenticationException()

        with patch.dict("sys.modules", {"paramiko": mock_paramiko}):
            t = self._make()
            assert "Authentication failed" in t._run(hostname="h", username="u", password="x")

    @patch("sago.tools.ssh.ssh_connect.SSHConnectTool._expand_path")
    def test_connect_ssh_exception(self, mock_expand):
        mock_paramiko = MagicMock()
        mock_client = MagicMock()
        mock_paramiko.SSHClient.return_value = mock_client
        SSHExc = type("SSHException", (Exception,), {})
        mock_paramiko.SSHException = SSHExc
        AuthExc = type("AuthenticationException", (Exception,), {})
        mock_paramiko.AuthenticationException = AuthExc
        mock_client.connect.side_effect = SSHExc("timeout")

        with patch.dict("sys.modules", {"paramiko": mock_paramiko}):
            t = self._make()
            assert "SSH connection failed" in t._run(hostname="h", username="u")


# ---------------------------------------------------------------------------
# SSH Transfer
# ---------------------------------------------------------------------------


class TestSSHTransferTool:
    def _make(self):
        from sago.tools.ssh.ssh_transfer import SSHTransferTool

        return SSHTransferTool()

    def test_name(self):
        assert self._make().name == "ssh_transfer"

    @patch("sago.tools.ssh.ssh_transfer.SSHTransferTool._expand_path")
    def test_upload_success(self, mock_expand):
        mock_paramiko = MagicMock()
        mock_client = MagicMock()
        mock_paramiko.SSHClient.return_value = mock_client
        mock_paramiko.AutoAddPolicy.return_value = MagicMock()
        sftp = MagicMock()
        mock_client.open_sftp.return_value = sftp
        mock_expand.side_effect = lambda p: Path(p)

        with patch.dict("sys.modules", {"paramiko": mock_paramiko}):
            t = self._make()
            result = t._run(
                operation="upload",
                source="/tmp/f.txt",
                destination="/remote/f.txt",
                hostname="h",
                username="u",
            )
            assert "Uploaded" in result
            sftp.put.assert_called_once()

    @patch("sago.tools.ssh.ssh_transfer.SSHTransferTool._expand_path")
    def test_download_success(self, mock_expand):
        mock_paramiko = MagicMock()
        mock_client = MagicMock()
        mock_paramiko.SSHClient.return_value = mock_client
        mock_paramiko.AutoAddPolicy.return_value = MagicMock()
        sftp = MagicMock()
        mock_client.open_sftp.return_value = sftp
        mock_expand.side_effect = lambda p: Path(p)

        with patch.dict("sys.modules", {"paramiko": mock_paramiko}):
            t = self._make()
            result = t._run(
                operation="download",
                source="/remote/f.txt",
                destination="/tmp/f.txt",
                hostname="h",
                username="u",
            )
            assert "Downloaded" in result
            sftp.get.assert_called_once()

    @patch("sago.tools.ssh.ssh_transfer.SSHTransferTool._expand_path")
    def test_upload_exception(self, mock_expand):
        mock_paramiko = MagicMock()
        mock_client = MagicMock()
        mock_paramiko.SSHClient.return_value = mock_client
        mock_paramiko.AuthenticationException = type("AuthenticationException", (Exception,), {})
        mock_client.connect.side_effect = OSError("connection refused")

        with patch.dict("sys.modules", {"paramiko": mock_paramiko}):
            t = self._make()
            result = t._run(
                operation="upload",
                source="/tmp/f.txt",
                destination="/r/f.txt",
                hostname="h",
                username="u",
            )
            assert "Error" in result


# ---------------------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------------------


class TestClipboardTool:
    def _make(self):
        from sago.tools.session.clipboard import ClipboardTool

        return ClipboardTool()

    def test_name(self):
        assert self._make().name == "clipboard"

    def test_write_no_content(self):
        t = self._make()
        result = t._run(operation="write")
        assert "content required" in result

    @patch("sago.tools.session.clipboard.ClipboardTool._is_macos", return_value=False)
    @patch("sago.tools.session.clipboard.ClipboardTool._is_windows", return_value=False)
    @patch("subprocess.Popen")
    def test_write_linux(self, mock_popen, mock_win, mock_mac):
        proc = MagicMock()
        proc.communicate.return_value = (b"", b"")
        proc.returncode = 0
        mock_popen.return_value = proc

        t = self._make()
        result = t._run(operation="write", content="hello")
        assert "Clipboard updated" in result

    @patch("sago.tools.session.clipboard.ClipboardTool._is_macos", return_value=False)
    @patch("sago.tools.session.clipboard.ClipboardTool._is_windows", return_value=False)
    @patch("subprocess.Popen")
    def test_clear(self, mock_popen, mock_win, mock_mac):
        proc = MagicMock()
        proc.communicate.return_value = (b"", b"")
        proc.returncode = 0
        mock_popen.return_value = proc

        t = self._make()
        result = t._run(operation="clear")
        assert "Clipboard cleared" in result

    def test_unknown_operation(self):
        t = self._make()
        result = t._run(operation="foobar")
        assert "Unknown operation" in result

    @patch("sago.tools.session.clipboard.ClipboardTool._is_macos", return_value=True)
    @patch("subprocess.run")
    def test_read_macos(self, mock_run, mock_mac):
        mock_run.return_value = Mock(returncode=0, stdout="clipboard text")
        t = self._make()
        result = t._run(operation="read")
        assert "clipboard text" in result

    @patch("sago.tools.session.clipboard.ClipboardTool._is_macos", return_value=True)
    @patch("subprocess.run")
    def test_read_macos_empty(self, mock_run, mock_mac):
        mock_run.return_value = Mock(returncode=0, stdout="")
        t = self._make()
        result = t._run(operation="read")
        assert "empty" in result.lower()


# ---------------------------------------------------------------------------
# Session Manager
# ---------------------------------------------------------------------------


class TestSessionManagerTool:
    def _make(self, tmp_path):
        from sago.tools.session.session_manager import SessionManagerTool

        with patch("sago.paths.get_sago_home", return_value=tmp_path):
            t = SessionManagerTool()
        t._session_dir = tmp_path
        return t

    def test_set_and_get(self, tmp_path):
        t = self._make(tmp_path)
        t._run(operation="set", key="k", value="v", session_id="s1")
        result = t._run(operation="get", key="k", session_id="s1")
        assert result == "v"

    def test_get_missing_key(self, tmp_path):
        t = self._make(tmp_path)
        result = t._run(operation="get", key="missing", session_id="s1")
        assert "not found" in result

    def test_delete(self, tmp_path):
        t = self._make(tmp_path)
        t._run(operation="set", key="k", value="v", session_id="s1")
        result = t._run(operation="delete", key="k", session_id="s1")
        assert "Deleted" in result
        assert "not found" in t._run(operation="get", key="k", session_id="s1")

    def test_list(self, tmp_path):
        t = self._make(tmp_path)
        t._run(operation="set", key="a", value="1", session_id="s1")
        result = t._run(operation="list", session_id="s1")
        assert "a" in result

    def test_list_empty(self, tmp_path):
        t = self._make(tmp_path)
        result = t._run(operation="list", session_id="empty")
        assert "empty" in result.lower()

    def test_clear(self, tmp_path):
        t = self._make(tmp_path)
        t._run(operation="set", key="a", value="1", session_id="s1")
        t._run(operation="clear", session_id="s1")
        result = t._run(operation="list", session_id="s1")
        assert "empty" in result.lower()

    def test_persistence(self, tmp_path):
        t1 = self._make(tmp_path)
        t1._run(operation="set", key="persist", value="yes", session_id="s2")
        t2 = self._make(tmp_path)
        result = t2._run(operation="get", key="persist", session_id="s2")
        assert result == "yes"

    def test_get_requires_key(self, tmp_path):
        t = self._make(tmp_path)
        result = t._run(operation="get", session_id="s1")
        assert "key required" in result

    def test_set_requires_key_and_value(self, tmp_path):
        t = self._make(tmp_path)
        result = t._run(operation="set", key="k", session_id="s1")
        assert "key and value required" in result

    def test_unknown_operation(self, tmp_path):
        t = self._make(tmp_path)
        result = t._run(operation="unknown", session_id="s1")
        assert "Unknown operation" in result


# ---------------------------------------------------------------------------
# Browser
# ---------------------------------------------------------------------------


class TestBrowserTool:
    def _make(self):
        from sago.tools.web.browser import BrowserTool

        return BrowserTool()

    def test_name(self):
        assert self._make().name == "browser"

    @patch("sago.tools.web.browser.BrowserTool._chromium_fallback")
    @patch("sago.tools.web.browser.BrowserTool.__init__", lambda self: None)
    def test_execute_fallback(self, mock_fb):
        mock_fb.return_value = Mock(output="fallback", success=True)
        t = self._make()
        result = t.execute(action="screenshot", url="http://x", auto_install=False)
        assert result.output == "fallback"


# ---------------------------------------------------------------------------
# Web Fetch
# ---------------------------------------------------------------------------


class TestWebFetchTool:
    def _make(self):
        from sago.tools.web.web_fetch import WebFetchTool

        return WebFetchTool()

    def test_name(self):
        assert self._make().name == "web_fetch"

    def test_validate_url_bad_scheme(self):
        ok, err = self._make()._validate_url("ftp://example.com")
        assert not ok
        assert "http" in err.lower()

    def test_validate_url_no_netloc(self):
        ok, err = self._make()._validate_url("http://")
        assert not ok

    def test_validate_url_valid(self):
        ok, _ = self._make()._validate_url("https://example.com")
        assert ok

    @patch("sago.tools.web.web_fetch.urllib.request.urlopen")
    def test_execute_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.__enter__ = Mock(return_value=mock_resp)
        mock_resp.__exit__ = Mock(return_value=False)
        mock_resp.url = "https://example.com"
        mock_resp.status = 200
        mock_headers = MagicMock()
        mock_headers.__getitem__ = Mock(
            side_effect=lambda k: {"Content-Type": "text/plain", "Content-Length": "11"}[k]
        )
        mock_headers.get = Mock(
            side_effect=lambda k, d=None: {
                "Content-Type": "text/plain",
                "Content-Length": "11",
            }.get(k, d)
        )
        mock_headers.get_content_charset.return_value = "utf-8"
        mock_resp.headers = mock_headers
        mock_resp.read.return_value = b"hello world"
        mock_urlopen.return_value = mock_resp

        t = self._make()
        result = t.execute(url="https://example.com", as_text=False)
        assert result.success
        assert "hello world" in result.output

    def test_execute_invalid_url(self):
        t = self._make()
        result = t.execute(url="not-a-url")
        assert not result.success
        assert result.error is not None
        assert "invalid_url" in result.error

    @patch("sago.tools.web.web_fetch.urllib.request.urlopen")
    def test_execute_http_404(self, mock_urlopen):
        import urllib.error

        mock_urlopen.side_effect = urllib.error.URLError("HTTP Error 404")
        t = self._make()
        result = t.execute(url="https://example.com/missing", max_retries=1)
        assert not result.success
        assert result.error is not None


# ---------------------------------------------------------------------------
# Review Changes
# ---------------------------------------------------------------------------


class TestReviewChangesTool:
    def _make(self):
        from sago.tools.vcs.review import ReviewChangesTool

        return ReviewChangesTool()

    def test_name(self):
        assert self._make().name == "review_changes"

    @patch("sago.tools.vcs.review.ReviewChangesTool.__init__", lambda self: None)
    def test_not_a_repo(self):
        t = self._make()
        result = t.execute(repo_path="/nonexistent")
        assert not result.success
        assert "Not a git repository" in result.output

    @patch("sago.tools.vcs.review._run_git")
    @patch("sago.tools.vcs.review.ReviewChangesTool.__init__", lambda self: None)
    def test_working_tree(self, mock_git):
        mock_git.return_value = (True, "## main\n M file.py\n")
        t = self._make()
        result = t.execute(target="working_tree", repo_path=".")
        assert result.success
        assert "working_tree" in result.output.lower()

    @patch("sago.tools.vcs.review._run_git")
    @patch("sago.tools.vcs.review.ReviewChangesTool.__init__", lambda self: None)
    def test_staged(self, mock_git):
        mock_git.return_value = (True, "")
        t = self._make()
        result = t.execute(target="staged", repo_path=".")
        assert result.success

    def test_invalid_target(self):
        t = self._make()
        with patch.object(t, "execute") as mock_exec:
            from sago.tools.base import ToolResult

            mock_exec.return_value = ToolResult(
                output="Unknown target", success=False, error="invalid target"
            )
            result = t.execute(target="invalid", repo_path=".")
            assert not result.success


# ---------------------------------------------------------------------------
# Docker Ops
# ---------------------------------------------------------------------------


class TestDockerOps:
    def _make(self):
        from sago.tools.system.docker_ops import DockerOps

        return DockerOps()

    def test_name(self):
        assert self._make().name == "docker_ops"

    @patch("sago.tools.system.docker_ops.is_available", return_value=False)
    @patch("sago.tools.system.docker_ops.ensure_binary", return_value=(False, "not found"))
    def test_docker_not_found(self, mock_ensure, mock_avail):
        t = self._make()
        result = t.execute(operation="ps", auto_install=True)
        assert not result.success
        assert result.error is not None
        assert "docker_not_found" in result.error

    @patch("sago.tools.system.docker_ops.subprocess.run")
    @patch("sago.tools.system.docker_ops.is_available", return_value=True)
    def test_ps_success(self, mock_avail, mock_run):
        mock_run.return_value = Mock(returncode=0, stdout="container1", stderr="")
        t = self._make()
        result = t.execute(operation="ps")
        assert result.success
        assert "container1" in result.output

    def test_build_cmd_ps(self):
        t = self._make()
        cmd = t._build_cmd("ps", [], "", "", "", "", "", "", False)
        assert cmd[0] == "docker"
        assert "ps" in cmd

    def test_build_cmd_unknown(self):
        from sago.tools.base import ToolResult

        t = self._make()
        result = t._build_cmd("nonexistent", [], "", "", "", "", "", "", False)
        assert isinstance(result, ToolResult)
        assert not result.success

    def test_build_cmd_compose_up(self):
        t = self._make()
        cmd = t._build_cmd("compose-up", [], "", "", "", "docker-compose.yml", "myapp", "", False)
        assert "compose" in cmd
        assert "up" in cmd


# ---------------------------------------------------------------------------
# K8s Ops
# ---------------------------------------------------------------------------


class TestK8sOpsTool:
    def _make(self):
        from sago.tools.system.k8s_ops import K8sOpsTool

        return K8sOpsTool()

    def test_name(self):
        assert self._make().name == "k8s_ops"

    @patch("sago.tools.system.k8s_ops.K8sOpsTool._resolve_kubectl", return_value=None)
    def test_kubectl_not_found(self, mock_resolve):
        t = self._make()
        result = t.execute(operation="get", resource="pods")
        assert not result.success
        assert result.error is not None
        assert "kubectl_not_found" in result.error

    @patch("sago.tools.system.k8s_ops.subprocess.run")
    @patch("sago.tools.system.k8s_ops.K8sOpsTool._resolve_kubectl", return_value="kubectl")
    def test_get_pods(self, mock_resolve, mock_run):
        mock_run.return_value = Mock(returncode=0, stdout="pod1\npod2", stderr="")
        t = self._make()
        result = t.execute(operation="get", resource="pods")
        assert result.success
        assert "pod1" in result.output

    @patch("sago.tools.system.k8s_ops.K8sOpsTool._resolve_kubectl", return_value="kubectl")
    def test_destructive_blocked(self, mock_resolve):
        t = self._make()
        result = t.execute(operation="delete", resource="pod/x", dry_run=False)
        assert not result.success
        assert "BLOCKED" in result.output

    @patch("sago.tools.system.k8s_ops.subprocess.run")
    @patch("sago.tools.system.k8s_ops.K8sOpsTool._resolve_kubectl", return_value="kubectl")
    def test_destructive_dry_run(self, mock_resolve, mock_run):
        mock_run.return_value = Mock(returncode=0, stdout="deleted (dry run)", stderr="")
        t = self._make()
        result = t.execute(operation="delete", resource="pod/x", dry_run=True)
        assert result.success

    @patch("sago.tools.system.k8s_ops.subprocess.run")
    @patch("sago.tools.system.k8s_ops.K8sOpsTool._resolve_kubectl", return_value="kubectl")
    def test_namespace_added(self, mock_resolve, mock_run):
        mock_run.return_value = Mock(returncode=0, stdout="ok", stderr="")
        t = self._make()
        result = t.execute(operation="get", resource="pods", namespace="kube-system")
        cmd = mock_run.call_args[0][0]
        assert "-n" in cmd
        assert "kube-system" in cmd


# ---------------------------------------------------------------------------
# OS Detector
# ---------------------------------------------------------------------------


class TestOSDetectorTool:
    def _make(self):
        from sago.tools.system.os_detector import OSDetectorTool

        return OSDetectorTool()

    def test_name(self):
        assert self._make().name == "os_detector"

    def test_basic_output(self):
        t = self._make()
        result = t._run(detailed=False)
        assert "System Information" in result
        assert platform.system() in result

    def test_detailed_output(self):
        t = self._make()
        result = t._run(detailed=True)
        assert "Detailed Info" in result
        assert "CPU count" in result


# ---------------------------------------------------------------------------
# Edit File
# ---------------------------------------------------------------------------


class TestEditFileTool:
    def _make(self):
        from sago.tools.file.edit_file import EditFileTool

        return EditFileTool()

    def test_name(self):
        assert self._make().name == "edit_file"

    @patch("sago.tools.file.edit_file.EditFileTool._expand_path")
    def test_file_not_found(self, mock_expand, tmp_path):
        f = tmp_path / "nonexistent.txt"
        mock_expand.return_value = f
        t = self._make()
        with patch("sago.security.approval.check_write_safety", return_value=None):
            result = t._run(file_path=str(f), old_string="a", new_string="b")
            assert "File not found" in result

    @patch("sago.tools.file.edit_file.EditFileTool._expand_path")
    def test_not_a_file(self, mock_expand, tmp_path):
        mock_expand.return_value = tmp_path
        t = self._make()
        with patch("sago.security.approval.check_write_safety", return_value=None):
            result = t._run(file_path=str(tmp_path), old_string="a", new_string="b")
            assert "Not a file" in result

    @patch("sago.tools.file.edit_file.EditFileTool._expand_path")
    def test_edit_success(self, mock_expand, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("hello world")
        mock_expand.return_value = f
        t = self._make()
        with patch("sago.security.approval.check_write_safety", return_value=None):
            result = t._run(file_path=str(f), old_string="hello", new_string="bye")
            assert "Successfully edited" in result
            assert f.read_text() == "bye world"

    @patch("sago.tools.file.edit_file.EditFileTool._expand_path")
    def test_edit_write_safety_blocked(self, mock_expand, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("content")
        mock_expand.return_value = f
        t = self._make()
        with patch("sago.security.approval.check_write_safety", return_value="Blocked path"):
            result = t._run(file_path=str(f), old_string="x", new_string="y")
            assert "Error" in result
            assert "Blocked path" in result


# ---------------------------------------------------------------------------
# File Operations
# ---------------------------------------------------------------------------


class TestFileOperationsTool:
    def _make(self):
        from sago.tools.file.file_ops import FileOperationsTool

        return FileOperationsTool()

    def test_name(self):
        assert self._make().name == "file_operations"

    def test_list_directory(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.py").write_text("b")
        t = self._make()
        result = t._run(operation="list", source=str(tmp_path))
        assert "a.txt" in result
        assert "b.py" in result

    def test_list_not_found(self):
        t = self._make()
        result = t._run(operation="list", source="/nonexistent")
        assert "not found" in result.lower()

    def test_list_not_a_dir(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        t = self._make()
        result = t._run(operation="list", source=str(f))
        assert "Not a directory" in result

    def test_mkdir(self, tmp_path):
        t = self._make()
        new_dir = tmp_path / "newdir"
        result = t._run(operation="mkdir", source=str(new_dir))
        assert new_dir.exists()
        assert "Created directory" in result

    def test_mkdir_already_exists(self, tmp_path):
        t = self._make()
        result = t._run(operation="mkdir", source=str(tmp_path))
        assert "Directory exists" in result

    def test_mkdir_dirs_exist_ok(self, tmp_path):
        t = self._make()
        result = t._run(operation="mkdir", source=str(tmp_path), dirs_exist_ok=True)
        assert "Created directory" in result

    def test_delete_file(self, tmp_path):
        f = tmp_path / "to_delete.txt"
        f.write_text("bye")
        t = self._make()
        result = t._run(operation="delete", source=str(f))
        assert not f.exists()
        assert "Deleted file" in result

    def test_delete_dir_recursive(self, tmp_path):
        d = tmp_path / "del_dir"
        d.mkdir()
        (d / "f.txt").write_text("x")
        t = self._make()
        result = t._run(operation="delete", source=str(d), recursive=True)
        assert not d.exists()
        assert "Deleted directory" in result

    def test_delete_dir_not_recursive(self, tmp_path):
        d = tmp_path / "del_dir"
        d.mkdir()
        t = self._make()
        result = t._run(operation="delete", source=str(d))
        assert "recursive=true" in result

    def test_move(self, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("data")
        dst = tmp_path / "dst.txt"
        t = self._make()
        result = t._run(operation="move", source=str(src), destination=str(dst))
        assert dst.exists()
        assert not src.exists()

    def test_move_dest_exists_no_force(self, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("a")
        dst = tmp_path / "dst.txt"
        dst.write_text("b")
        t = self._make()
        result = t._run(operation="move", source=str(src), destination=str(dst))
        assert "Destination exists" in result

    def test_copy(self, tmp_path):
        src = tmp_path / "src.txt"
        src.write_text("data")
        dst = tmp_path / "dst.txt"
        t = self._make()
        result = t._run(operation="copy", source=str(src), destination=str(dst))
        assert dst.exists()
        assert src.exists()
        assert dst.read_text() == "data"

    def test_copy_dir(self, tmp_path):
        src = tmp_path / "src_dir"
        src.mkdir()
        (src / "f.txt").write_text("hi")
        dst = tmp_path / "dst_dir"
        t = self._make()
        result = t._run(operation="copy", source=str(src), destination=str(dst), recursive=True)
        assert dst.exists()
        assert (dst / "f.txt").read_text() == "hi"

    def test_rename(self, tmp_path):
        src = tmp_path / "old.txt"
        src.write_text("x")
        dst = tmp_path / "new.txt"
        t = self._make()
        result = t._run(operation="rename", source=str(src), destination=str(dst))
        assert dst.exists()
        assert not src.exists()


# ---------------------------------------------------------------------------
# Diff Tool
# ---------------------------------------------------------------------------


class TestDiffTool:
    def _make(self):
        from sago.tools.file.diff_tool import DiffTool

        return DiffTool()

    def test_name(self):
        assert self._make().name == "diff_tool"

    def test_unified_diff(self):
        t = self._make()
        result = t._run(operation="unified", source="line1\nline2\n", target="line1\nline3\n")
        assert "---" in result or "+++" in result or "No differences" in result

    def test_text_diff(self):
        t = self._make()
        result = t._run(operation="text", source="aaa\n", target="bbb\n")
        assert "Change" in result or "replace" in result or "No differences" in result

    def test_context_diff(self):
        t = self._make()
        result = t._run(operation="context", source="a\n", target="b\n")
        assert isinstance(result, str)

    def test_files_similarity(self):
        t = self._make()
        result = t._run(operation="files", source="hello\nworld\n", target="hello\nworld\n")
        assert "100.0%" in result

    def test_invalid_operation(self):
        t = self._make()
        result = t._run(operation="bad", source="a", target="b")
        assert "Invalid operation" in result

    def test_file_input(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f1.write_text("line1\nline2\n")
        f2 = tmp_path / "b.txt"
        f2.write_text("line1\nline3\n")
        t = self._make()
        result = t._run(operation="unified", source=str(f1), target=str(f2))
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Regex Tester
# ---------------------------------------------------------------------------


class TestRegexTester:
    def _make(self):
        from sago.tools.file.regex_tester import RegexTester

        return RegexTester()

    def test_name(self):
        assert self._make().name == "regex_tester"

    def test_validate(self):
        t = self._make()
        result = t._run(operation="validate", pattern=r"\d+", text="abc")
        assert "valid" in result.lower()

    def test_match(self):
        t = self._make()
        result = t._run(operation="match", pattern=r"\d+", text="abc123def456")
        assert "2 match" in result.lower()
        assert "123" in result

    def test_match_no_matches(self):
        t = self._make()
        result = t._run(operation="match", pattern=r"\d+", text="no numbers here")
        assert "No matches" in result

    def test_findall(self):
        t = self._make()
        result = t._run(operation="findall", pattern=r"\d+", text="1 and 2 and 3")
        assert "3 match" in result.lower()

    def test_replace(self):
        t = self._make()
        result = t._run(operation="replace", pattern=r"\d+", text="abc123", replacement="X")
        assert "Replaced" in result
        assert "abcX" in result

    def test_split(self):
        t = self._make()
        result = t._run(operation="split", pattern=r"\s+", text="a b  c")
        assert "Split" in result

    def test_invalid_pattern(self):
        t = self._make()
        result = t._run(operation="match", pattern="[invalid", text="x")
        assert "Regex error" in result

    def test_ignorecase_flag(self):
        t = self._make()
        result = t._run(operation="match", pattern=r"hello", text="HELLO world", flags="i")
        assert "1 match" in result.lower()

    def test_multiline_flag(self):
        t = self._make()
        result = t._run(operation="findall", pattern=r"^line", text="line1\nline2", flags="m")
        assert "2 match" in result.lower()

    def test_invalid_operation(self):
        t = self._make()
        result = t._run(operation="bad", pattern="x", text="y")
        assert "Invalid operation" in result


# ---------------------------------------------------------------------------
# Resilient Editor
# ---------------------------------------------------------------------------


class TestResilientEditor:
    def test_normalize_newlines(self):
        from sago.tools.file.resilient_editor import ResilientEditor

        assert ResilientEditor.normalize_newlines("a\r\nb\rc") == "a\nb\nc"

    def test_find_best_match_exact(self):
        from sago.tools.file.resilient_editor import ResilientEditor

        result = ResilientEditor.find_best_match("hello world", "world")
        assert result.found
        assert result.match_tier == "exact"
        assert result.confidence == 1.0

    def test_find_best_match_normalized(self):
        from sago.tools.file.resilient_editor import ResilientEditor

        content = "def foo():\n    pass\n"
        target = "def foo():\n        pass\n"
        result = ResilientEditor.find_best_match(content, target)
        assert result.found
        assert result.match_tier in ("exact", "normalized_lines")

    def test_find_best_match_fuzzy(self):
        from sago.tools.file.resilient_editor import ResilientEditor

        content = "def foo():\n    return 42\n"
        target = "def foo():\n    retun 42\n"
        result = ResilientEditor.find_best_match(content, target)
        assert result.found
        assert result.match_tier == "fuzzy"

    def test_find_best_match_not_found(self):
        from sago.tools.file.resilient_editor import ResilientEditor

        result = ResilientEditor.find_best_match("hello", "xyz")
        assert not result.found

    def test_apply_replacement_exact(self):
        from sago.tools.file.resilient_editor import ResilientEditor

        ok, content, msg = ResilientEditor.apply_replacement("hello world", "world", "python")
        assert ok
        assert "python" in content
        assert "exact" in msg.lower()

    def test_apply_replacement_replace_all(self):
        from sago.tools.file.resilient_editor import ResilientEditor

        ok, content, msg = ResilientEditor.apply_replacement(
            "a b a b a", "a", "x", replace_all=True
        )
        assert ok
        assert content == "x b x b x"

    def test_apply_replacement_not_found(self):
        from sago.tools.file.resilient_editor import ResilientEditor

        ok, content, msg = ResilientEditor.apply_replacement("hello", "xyz", "abc")
        assert not ok
        assert "not found" in msg.lower()

    def test_syntax_guard_python_valid(self):
        from sago.tools.file.resilient_editor import ResilientEditor

        original = "x = 1\n"
        modified = "x = 2\n"
        ok, msg = ResilientEditor.syntax_guard(original, modified, "test.py")
        assert ok

    def test_syntax_guard_python_reject(self):
        from sago.tools.file.resilient_editor import ResilientEditor

        original = "def foo():\n    return 1\n"
        modified = "def foo():\n    return 1\n    :\n"  # colon after return = syntax error
        ok, msg = ResilientEditor.syntax_guard(original, modified, "test.py")
        assert not ok
        assert "REJECTED" in msg

    def test_syntax_guard_no_path(self):
        from sago.tools.file.resilient_editor import ResilientEditor

        ok, msg = ResilientEditor.syntax_guard("a", "b", None)
        assert ok

    def test_syntax_guard_same_content(self):
        from sago.tools.file.resilient_editor import ResilientEditor

        ok, msg = ResilientEditor.syntax_guard("x", "x", "test.py")
        assert ok

    def test_syntax_guard_non_python(self):
        from sago.tools.file.resilient_editor import ResilientEditor

        ok, msg = ResilientEditor.syntax_guard("<html>", "<div>", "test.html")
        assert ok

    def test_apply_multi_replace(self):
        from sago.tools.file.resilient_editor import ResilientEditor

        chunks = [
            {"old": "hello", "new": "bye"},
            {"old": "world", "new": "earth"},
        ]
        ok, content, logs, count = ResilientEditor.apply_multi_replace("hello world", chunks)
        assert ok
        assert "bye" in content
        assert "earth" in content
        assert count == 2

    def test_apply_multi_replace_chunk_fails(self):
        from sago.tools.file.resilient_editor import ResilientEditor

        chunks = [
            {"old": "hello", "new": "bye"},
            {"old": "nonexistent_xyz", "new": "x"},
        ]
        ok, content, logs, count = ResilientEditor.apply_multi_replace("hello world", chunks)
        assert not ok

    def test_apply_multi_replace_empty_chunk(self):
        from sago.tools.file.resilient_editor import ResilientEditor

        chunks = [{"old": "", "new": "x"}]
        ok, content, logs, count = ResilientEditor.apply_multi_replace("abc", chunks)
        assert ok
        assert count == 0


# ---------------------------------------------------------------------------
# MatchResult dataclass
# ---------------------------------------------------------------------------


class TestMatchResult:
    def test_defaults(self):
        from sago.tools.file.resilient_editor import MatchResult

        m = MatchResult(found=False)
        assert not m.found
        assert m.start_idx == -1
        assert m.end_idx == -1
        assert m.confidence == 0.0
        assert m.matched_text == ""
        assert m.match_tier == "none"
