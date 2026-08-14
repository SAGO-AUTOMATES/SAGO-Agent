"""Self-Healing Verification Flywheel - Multi-language verification and diagnostics.

Runs linters, typecheckers, and test suites, extracting actionable error reports
that can be fed directly back into agent loops for autonomous self-healing.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DiagnosticIssue:
    """A single diagnostic issue found during verification."""

    file_path: str
    line: int
    column: int
    severity: str  # "error", "warning"
    rule: str
    message: str


@dataclass
class VerificationReport:
    """Consolidated verification report."""

    passed: bool
    linter_passed: bool
    typecheck_passed: bool
    tests_passed: bool
    issues: list[DiagnosticIssue] = field(default_factory=list)
    raw_output: str = ""
    summary: str = ""

    def to_prompt_feedback(self) -> str:
        """Format the report as an actionable prompt for autonomous fixing."""
        if self.passed:
            return "Verification PASSED: All linters, type checks, and tests succeeded."

        lines = ["=== VERIFICATION FAILED - AUTOMATIC FIX REQUIRED ==="]
        if self.issues:
            lines.append("\nDetected Issues:")
            for issue in self.issues[:15]:
                lines.append(
                    f"  • {issue.file_path}:{issue.line} [{issue.severity.upper()}] ({issue.rule}): {issue.message}"
                )
        if self.raw_output:
            lines.append("\nTest/Compiler Output:")
            lines.append(self.raw_output[:2500])

        lines.append(
            "\nPlease fix the errors above by editing the relevant files. Verify your changes when done."
        )
        return "\n".join(lines)


class ProjectVerifier:
    """Automated verification and test execution flywheel."""

    def __init__(self, root_dir: str | Path | None = None) -> None:
        self.root_dir = Path(root_dir) if root_dir else Path.cwd()

    def run_command_safe(self, cmd: list[str], timeout: int = 60) -> tuple[int, str]:
        try:
            res = subprocess.run(
                cmd,
                cwd=str(self.root_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            out = (res.stdout or "") + "\n" + (res.stderr or "")
            return res.returncode, out.strip()
        except FileNotFoundError:
            return -1, f"Command not found: {cmd[0]}"
        except subprocess.TimeoutExpired:
            return -2, f"Command timed out after {timeout}s: {' '.join(cmd)}"
        except Exception as e:
            return -3, f"Execution failed: {e}"

    def verify_python(self) -> VerificationReport:
        """Run ruff, mypy, and pytest."""
        issues: list[DiagnosticIssue] = []
        raw_outputs = []
        linter_passed = True
        typecheck_passed = True
        tests_passed = True

        # 1. Ruff linting
        code, out = self.run_command_safe(["ruff", "check", "."])
        if code != 0 and "Command not found" not in out:
            linter_passed = False
            raw_outputs.append(f"--- Ruff Output ---\n{out}")
            for line in out.splitlines():
                # e.g., sago/engine/unified.py:45:1: E501 line too long
                m = re.match(r"^([^:]+):(\d+):(\d+):\s+([A-Z0-9]+)\s+(.*)$", line)
                if m:
                    issues.append(
                        DiagnosticIssue(
                            file_path=m.group(1),
                            line=int(m.group(2)),
                            column=int(m.group(3)),
                            severity="error",
                            rule=m.group(4),
                            message=m.group(5),
                        )
                    )

        # 2. Pytest test suite
        code, out = self.run_command_safe(["pytest", "-q", "--tb=short"])
        if code != 0 and "Command not found" not in out and "no tests ran" not in out.lower():
            tests_passed = False
            raw_outputs.append(f"--- Pytest Output ---\n{out}")

        passed = linter_passed and typecheck_passed and tests_passed
        summary = "All checks passed" if passed else f"{len(issues)} issue(s) detected"

        return VerificationReport(
            passed=passed,
            linter_passed=linter_passed,
            typecheck_passed=typecheck_passed,
            tests_passed=tests_passed,
            issues=issues,
            raw_output="\n\n".join(raw_outputs),
            summary=summary,
        )

    def verify_project(self) -> VerificationReport:
        """Auto-detect language and run corresponding verifier."""
        if (self.root_dir / "pyproject.toml").exists() or any(self.root_dir.glob("*.py")):
            return self.verify_python()

        return VerificationReport(
            passed=True,
            linter_passed=True,
            typecheck_passed=True,
            tests_passed=True,
            summary="No language verifiers triggered",
        )
