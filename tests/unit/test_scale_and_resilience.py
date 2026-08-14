"""Unit tests for large-scale codebase indexing, resilient editing, and verification."""

import tempfile
from pathlib import Path

from sago.engine.project_synthesizer import FileSpec, ProjectSynthesizer
from sago.engine.verifier import DiagnosticIssue, VerificationReport
from sago.memory.symbol_graph import SymbolGraph
from sago.tools.file.multi_replace_file import MultiReplaceTool
from sago.tools.file.resilient_editor import ResilientEditor


def test_resilient_editor_exact_and_fuzzy():
    content = """def calculate_total(items):\n    subtotal = sum(items)\n    tax = subtotal * 0.1\n    return subtotal + tax\n"""

    # Test exact replacement
    ok, new_c, msg = ResilientEditor.apply_replacement(
        content,
        "tax = subtotal * 0.1",
        "tax = subtotal * 0.15",
    )
    assert ok is True
    assert "tax = subtotal * 0.15" in new_c

    # Test whitespace-tolerant / normalized replacement
    ok, new_c2, msg2 = ResilientEditor.apply_replacement(
        content,
        "subtotal = sum(items)   \ntax = subtotal * 0.1",
        "subtotal = sum(items)\ntax = subtotal * 0.2",
    )
    assert ok is True
    assert "0.2" in new_c2


def test_multi_replace_tool():
    with tempfile.TemporaryDirectory() as tmpdir:
        fpath = Path(tmpdir) / "app.py"
        fpath.write_text("A = 1\nB = 2\nC = 3\n", encoding="utf-8")

        tool = MultiReplaceTool()
        res = tool.run(
            file_path=str(fpath),
            chunks=[
                {"old": "A = 1", "new": "A = 10"},
                {"old": "C = 3", "new": "C = 30"},
            ],
        )
        assert "Successfully applied 2 replacement(s)" in res
        updated = fpath.read_text(encoding="utf-8")
        assert "A = 10" in updated
        assert "B = 2" in updated
        assert "C = 30" in updated


def test_symbol_graph_and_repo_map():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        p1 = root / "service.py"
        p1.write_text(
            "class UserService:\n    def get_user(self, user_id):\n        '''Fetch user.'''\n        return user_id\n",
            encoding="utf-8",
        )
        p2 = root / "api.ts"
        p2.write_text("export interface UserResponse { id: string; }\n", encoding="utf-8")

        graph = SymbolGraph(root_dir=root)
        rmap = graph.generate_repo_map()

        assert "service.py" in rmap
        assert "UserService" in rmap
        assert "api.ts" in rmap
        assert "UserResponse" in rmap


def test_project_synthesizer_plan():
    with tempfile.TemporaryDirectory() as tmpdir:
        synth = ProjectSynthesizer(root_dir=tmpdir)
        plan = synth.plan_project("Build E-commerce Microservice")
        plan.files.append(
            FileSpec(
                path="models/user.py",
                phase=2,
                purpose="User database entity",
                key_symbols=["User"],
            )
        )
        saved_path = synth.save_plan(plan)
        assert saved_path.exists()

        loaded = synth.load_plan()
        assert loaded is not None
        assert loaded.project_name == Path(tmpdir).name
        assert len(loaded.files) == 1
        assert loaded.files[0].path == "models/user.py"


def test_verifier_report_formatting():
    report = VerificationReport(
        passed=False,
        linter_passed=False,
        typecheck_passed=True,
        tests_passed=True,
        issues=[
            DiagnosticIssue(
                file_path="main.py",
                line=12,
                column=5,
                severity="error",
                rule="F401",
                message="'os' imported but unused",
            )
        ],
        summary="1 issue detected",
    )
    feedback = report.to_prompt_feedback()
    assert "VERIFICATION FAILED" in feedback
    assert "main.py:12 [ERROR] (F401)" in feedback
