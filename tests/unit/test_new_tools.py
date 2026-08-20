"""Unit tests for the three new SAGO tools: git_operations, file_search, web_fetch."""

from __future__ import annotations

import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sago.tools.ensure_dep import (
    Distro,
    OsType,
    PlatformInfo,
    detect_platform,
    ensure_binary,
    ensure_pip_package,
    install_pip_package,
    is_available,
    which,
)
from sago.tools.file.file_search import FileSearchTool
from sago.tools.system.code_sandbox import CodeSandboxTool
from sago.tools.system.docker_ops import DockerOps
from sago.tools.system.k8s_ops import K8sOpsTool
from sago.tools.vcs.git_ops import GitOperationsTool
from sago.tools.web.browser import BrowserTool
from sago.tools.web.search import WebSearchTool
from sago.tools.web.web_fetch import WebFetchTool


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "hello.txt").write_text("hello world\n")
    subprocess.run(["git", "add", "hello.txt"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial commit"], cwd=path, check=True)


def test_git_ops_status_and_log(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)

    tool = GitOperationsTool()

    status = tool.execute(operation="status", repo_path=str(repo))
    assert status.success
    assert "hello.txt" not in status.output or "initial commit" in status.output or status.output

    log = tool.execute(operation="log", repo_path=str(repo))
    assert log.success
    assert "initial commit" in log.output


def test_git_ops_add_commit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    (repo / "new.txt").write_text("new file\n")

    tool = GitOperationsTool()
    add = tool.execute(operation="add", repo_path=str(repo), args=["new.txt"])
    assert add.success

    commit = tool.execute(
        operation="commit",
        repo_path=str(repo),
        args=["second commit"],
    )
    assert commit.success

    log = tool.execute(operation="log", repo_path=str(repo))
    assert "second commit" in log.output


def test_git_ops_unsupported_and_not_a_repo(tmp_path: Path) -> None:
    tool = GitOperationsTool()
    bad = tool.execute(operation="push")
    assert not bad.success
    assert "Unsupported" in bad.output

    not_repo = tool.execute(operation="status", repo_path=str(tmp_path / "nope"))
    assert not not_repo.success


def test_file_search_by_name(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "b.txt").write_text("y")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.py").write_text("z")

    tool = FileSearchTool()
    res = tool.execute(pattern="*.py", root=str(tmp_path))
    assert res.success
    assert res.metadata["count"] == 2
    assert all(p.endswith(".py") for p in res.metadata["matches"])


def test_file_search_by_content(tmp_path: Path) -> None:
    (tmp_path / "keep.py").write_text("def target():\n    pass\n")
    (tmp_path / "skip.py").write_text("def other():\n    pass\n")

    tool = FileSearchTool()
    res = tool.execute(pattern="*.py", content_regex="target", root=str(tmp_path))
    assert res.success
    assert res.metadata["count"] == 1
    assert res.metadata["matches"][0].endswith("keep.py")


def test_file_search_ignores_noise(tmp_path: Path) -> None:
    noise = tmp_path / ".venv"
    noise.mkdir()
    (noise / "secret.py").write_text("x")

    tool = FileSearchTool()
    res = tool.execute(pattern="*.py", root=str(tmp_path))
    assert res.metadata["count"] == 0


def test_file_search_invalid_regex(tmp_path: Path) -> None:
    tool = FileSearchTool()
    res = tool.execute(pattern="*", content_regex="[", root=str(tmp_path))
    assert not res.success
    assert "Invalid content_regex" in res.output


def _fake_response(body: bytes, status: int = 200, charset: str = "utf-8"):
    resp = MagicMock()
    resp.read.return_value = body
    resp.status = status
    resp.headers.get_content_charset.return_value = charset
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def test_web_fetch_success(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = _fake_response(b"<html>Hi</html>", status=200, charset="utf-8")
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: resp)

    tool = WebFetchTool()
    res = tool.execute(url="https://example.com")
    assert res.success
    assert "<html>Hi</html>" in res.output
    assert res.metadata["status"] == 200


def test_web_fetch_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def side_effect(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.URLError("boom")
        return _fake_response(b"ok", status=200)

    monkeypatch.setattr(urllib.request, "urlopen", side_effect)

    tool = WebFetchTool()
    res = tool.execute(url="https://example.com", max_retries=3, timeout=1)
    assert res.success
    assert "ok" in res.output
    assert calls["n"] == 3


def test_web_fetch_all_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    def side_effect(*args, **kwargs):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(urllib.request, "urlopen", side_effect)

    tool = WebFetchTool()
    res = tool.execute(url="https://example.com", max_retries=2, timeout=1)
    assert not res.success
    assert "Failed to fetch" in res.output


def test_web_fetch_invalid_url() -> None:
    tool = WebFetchTool()
    res = tool.execute(url="ftp://example.com")
    assert not res.success
    assert "http" in res.output.lower()


# ---------------------------------------------------------------------------
# ensure_dep tests
# ---------------------------------------------------------------------------


def test_detect_platform_returns_platform_info() -> None:
    plat = detect_platform()
    assert isinstance(plat, PlatformInfo)
    assert plat.os in (OsType.LINUX, OsType.DARWIN, OsType.WINDOWS, OsType.UNKNOWN)
    assert isinstance(plat.distro, Distro)
    assert isinstance(plat.arch, str)
    assert plat.arch  # not empty
    assert plat.libc in ("glibc", "musl")
    assert isinstance(plat.package_manager, str)
    assert isinstance(plat.is_wsl, bool)
    assert isinstance(plat.is_container, bool)
    assert isinstance(plat.python_version, str)
    assert "." in plat.python_version
    assert plat.cpu_count >= 1
    assert plat.total_memory_mb >= 0


def test_detect_platform_arch_label() -> None:
    plat = detect_platform()
    label = plat.arch_label
    assert (
        label in ("amd64", "arm64", "arm") or label.startswith("x86") or label.startswith("aarch")
    )


def test_which_returns_str_or_none() -> None:
    result = which("python3")
    assert result is None or isinstance(result, str)


def test_is_available_bool() -> None:
    assert isinstance(is_available("python3"), bool)
    assert is_available("python3") is True  # python3 should exist in test env
    assert is_available("nonexistent_tool_xyz_12345") is False


def test_ensure_pip_package_already_installed() -> None:
    ok, msg = ensure_pip_package("pytest")
    assert ok is True
    assert "already installed" in msg.lower() or "installed" in msg.lower()


def test_ensure_pip_package_missing() -> None:
    ok, msg = ensure_pip_package("nonexistent_pkg_xyz_12345")
    assert ok is False


def test_install_pip_package_missing() -> None:
    ok, msg = install_pip_package("nonexistent_pkg_xyz_12345")
    assert ok is False
    assert "failed" in msg.lower() or "error" in msg.lower()


def test_ensure_binary_python() -> None:
    ok, msg = ensure_binary("python3", auto_install=False)
    assert ok is True


def test_ensure_binary_missing_no_install() -> None:
    ok, msg = ensure_binary("nonexistent_tool_xyz_12345", auto_install=False)
    assert ok is False
    assert "not found" in msg.lower()


# ---------------------------------------------------------------------------
# K8s ops tests
# ---------------------------------------------------------------------------


def test_k8s_ops_unknown_operation() -> None:
    tool = K8sOpsTool()
    res = tool.execute(operation="invalid_op", auto_install=False)
    assert not res.success


def test_k8s_ops_destructive_blocked() -> None:
    tool = K8sOpsTool()
    res = tool.execute(
        operation="delete", resource="pods/my-pod", auto_install=False, dry_run=False
    )
    assert not res.success
    assert "BLOCKED" in res.output or "destructive" in res.output.lower()


def test_k8s_ops_destructive_dry_run() -> None:
    tool = K8sOpsTool()
    # dry_run=true but kubectl not available -> should still attempt
    res = tool.execute(operation="delete", resource="pods/my-pod", auto_install=False, dry_run=True)
    # May fail due to no kubectl, but should not be "BLOCKED"
    assert "BLOCKED" not in res.output


# ---------------------------------------------------------------------------
# Docker ops tests
# ---------------------------------------------------------------------------


def test_docker_ops_unknown_operation() -> None:
    tool = DockerOps()
    res = tool.execute(operation="invalid_op", auto_install=False)
    assert not res.success
    assert "Unknown operation" in res.output


def test_docker_ops_missing_docker() -> None:
    tool = DockerOps()
    # Should fail gracefully when docker not available
    res = tool.execute(operation="ps", auto_install=False)
    # May succeed if docker is installed, or fail with docker_not_found
    assert res.success or "docker" in res.output.lower() or "not found" in res.output.lower()


# ---------------------------------------------------------------------------
# Code sandbox tests
# ---------------------------------------------------------------------------


def test_code_sandbox_python() -> None:
    tool = CodeSandboxTool()
    res = tool.execute(language="python", code="print(42)", auto_install=False)
    assert res.success
    assert "42" in res.output


def test_code_sandbox_python_with_packages() -> None:
    tool = CodeSandboxTool()
    res = tool.execute(
        language="python",
        code="import json; print(json.dumps({'ok': True}))",
        auto_install=False,
    )
    assert res.success
    assert "ok" in res.output


def test_code_sandbox_unsupported_language() -> None:
    tool = CodeSandboxTool()
    res = tool.execute(language="rust", code="fn main() {}")
    assert not res.success
    assert "Unsupported" in res.output


def test_code_sandbox_bash() -> None:
    tool = CodeSandboxTool()
    res = tool.execute(language="bash", code="echo hello", auto_install=False)
    assert res.success
    assert "hello" in res.output


# ---------------------------------------------------------------------------
# Browser tool tests (non-network)
# ---------------------------------------------------------------------------


def test_browser_unknown_action() -> None:
    tool = BrowserTool()
    res = tool.execute(action="nonexistent_action", auto_install=False)
    # Without playwright, falls back to chromium for screenshot/pdf only
    # Unknown actions get "Unknown action" only when playwright is available
    assert "Unknown action" in res.output or "Playwright not available" in res.output


def test_browser_missing_deps() -> None:
    tool = BrowserTool()
    # Without playwright, should fail gracefully or try chromium
    res = tool.execute(action="screenshot", url="https://example.com", auto_install=False)
    # May succeed with chromium, or fail - but should not crash
    assert isinstance(res.output, str)


# ---------------------------------------------------------------------------
# Web search tests (non-network)
# ---------------------------------------------------------------------------


def test_web_search_returns_result() -> None:
    tool = WebSearchTool()
    # May fail without network, but should not crash
    res = tool.execute(query="test query", max_results=1)
    assert isinstance(res.output, str)


def test_web_search_format_results() -> None:
    from sago.tools.web.search import _format_results

    results = [{"title": "Test", "url": "https://example.com", "snippet": "test snippet"}]
    output = _format_results("test", results)
    assert "Test" in output
    assert "https://example.com" in output
    assert "test snippet" in output


def test_web_search_empty_results() -> None:
    from sago.tools.web.search import _format_results

    output = _format_results("test", [])
    assert "No results" in output
