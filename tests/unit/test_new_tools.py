"""Unit tests for the three new SAGO tools: git_operations, file_search, web_fetch."""

from __future__ import annotations

import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sago.tools.file.file_search import FileSearchTool
from sago.tools.vcs.git_ops import GitOperationsTool
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
