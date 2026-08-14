"""Tests for the coding-tools bug fixes.

Covers:
- multi_replace_file: replaces ALL occurrences and returns an accurate count
- linter: --fix flag is actually wired and applies fixes
- scaffold: {project_name} is substituted (no leftover ${project_name})
- lsp_client: hover / references handlers return meaningful data
- file_operations: dirs_exist_ok / force honored for mkdir
"""

from pathlib import Path

from sago.tools.coding.linter import LinterTool
from sago.tools.coding.lsp_client import LSPClient
from sago.tools.coding.scaffold import ScaffoldTool
from sago.tools.file.file_ops import FileOperationsTool
from sago.tools.file.multi_replace_file import MultiReplaceTool


def test_multi_replace_replaces_all_occurrences_and_counts(tmp_path):
    f = tmp_path / "code.py"
    f.write_text("foo = 1\nfoo = 2\nfoo = 3\n", encoding="utf-8")

    tool = MultiReplaceTool()
    res = tool.run(file_path=str(f), chunks=[{"old": "foo", "new": "bar"}])

    assert "Successfully applied 3 replacement(s)" in res
    assert f.read_text(encoding="utf-8") == "bar = 1\nbar = 2\nbar = 3\n"


def test_multi_replace_counts_per_chunk(tmp_path):
    f = tmp_path / "code.py"
    # "a" appears twice, "b" appears three times
    f.write_text("a b a b b\n", encoding="utf-8")

    tool = MultiReplaceTool()
    res = tool.run(
        file_path=str(f),
        chunks=[{"old": "a", "new": "A"}, {"old": "b", "new": "B"}],
    )

    assert "Successfully applied 5 replacement(s)" in res
    assert f.read_text(encoding="utf-8") == "A B A B B\n"


def test_linter_fix_is_wired_and_applies(tmp_path, monkeypatch):
    target = tmp_path / "app.py"
    target.write_text("import os\nprint('hi')\n", encoding="utf-8")

    calls: list[str] = []

    class _FakeResult:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(self, cmd, **kwargs):
        calls.append(cmd)
        # Simulate ruff --fix removing the unused import.
        if "--fix" in cmd:
            p = Path(str(cmd).split()[-1])
            try:
                text = p.read_text(encoding="utf-8")
                p.write_text(text.replace("import os\n", ""))
            except Exception:
                pass
        return _FakeResult()

    monkeypatch.setattr(LinterTool, "_run_command", _fake_run)

    tool = LinterTool()
    tool.run(file_path=str(target), linter="ruff", fix=True)

    assert any("--fix" in c for c in calls), f"--fix command not issued: {calls}"
    assert "import os" not in target.read_text(encoding="utf-8")


def test_linter_no_fix_does_not_modify(tmp_path, monkeypatch):
    target = tmp_path / "app.py"
    target.write_text("import os\nprint('hi')\n", encoding="utf-8")

    calls: list[str] = []

    class _FakeResult:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(self, cmd, **kwargs):
        calls.append(cmd)
        return _FakeResult()

    monkeypatch.setattr(LinterTool, "_run_command", _fake_run)

    tool = LinterTool()
    tool.run(file_path=str(target), linter="ruff", fix=False)

    assert not any("--fix" in c for c in calls)
    assert "import os" in target.read_text(encoding="utf-8")


def test_scaffold_substitutes_project_name(tmp_path):
    tool = ScaffoldTool()
    res = tool.run(
        project_type="python",
        project_name="My_App",
        path=str(tmp_path),
    )
    assert "Created" in res

    init_file = tmp_path / "my_app" / "my_app" / "__init__.py"
    assert init_file.exists()
    content = init_file.read_text(encoding="utf-8")
    assert "my_app" in content
    assert "${project_name}" not in content


def test_lsp_hover_and_references(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    a = tmp_path / "a.py"
    a.write_text("def greet():\n    return 1\ngreet()\n")
    b = tmp_path / "b.py"
    b.write_text("from a import greet\ngreet()\n")

    client = LSPClient()

    hover = client.get_hover(str(a), 1, 5)
    assert hover is not None
    assert hover["symbol"] == "greet"
    assert hover["kind"] == "function"

    refs = client.get_references(str(a), 1, 5)
    # a.py (def + call) and b.py (import + call)
    assert len(refs) >= 3

    diags = client.get_diagnostics(str(a))
    assert isinstance(diags, list)


def test_file_operations_mkdir_dirs_exist_ok(tmp_path):
    tool = FileOperationsTool()
    d = tmp_path / "sub"
    assert "Created" in tool.run(operation="mkdir", source=str(d))

    # Without force/dirs_exist_ok, recreating errors out.
    err = tool.run(operation="mkdir", source=str(d))
    assert "exists" in err.lower()

    # With dirs_exist_ok, it is a no-op success.
    assert "Created" in tool.run(operation="mkdir", source=str(d), dirs_exist_ok=True)
