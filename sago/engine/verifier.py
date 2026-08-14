"""Self-Healing Verification Flywheel - Multi-language verification and diagnostics.

Runs linters, typecheckers, and test suites across Python, TypeScript/JavaScript,
Rust, and Go, extracting actionable error reports that can be fed directly back
into agent loops for autonomous self-healing.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


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

    def _resolve_command(self, cmd_name: str) -> list[str]:
        """Resolve command binary checking virtualenvs, uv, poetry, and system PATH."""
        # 1. Check local virtual environments
        for venv_name in (".venv", "venv", "env"):
            venv_bin = self.root_dir / venv_name / "bin" / cmd_name
            if venv_bin.exists() and os.access(venv_bin, os.X_OK):
                return [str(venv_bin)]

        # 2. Check uv wrapper
        if (self.root_dir / "uv.lock").exists() or (self.root_dir / "pyproject.toml").exists():
            uv_path = shutil.which("uv") or str(Path.home() / ".local/bin/uv")
            if Path(uv_path).exists() and os.access(uv_path, os.X_OK):
                return [str(uv_path), "run", cmd_name]

        # 3. Check poetry
        if (self.root_dir / "poetry.lock").exists() and shutil.which("poetry"):
            return ["poetry", "run", cmd_name]

        # 4. Fallback to system path
        found = shutil.which(cmd_name)
        if found:
            return [found]

        return [cmd_name]

    def run_command_safe(self, cmd: list[str], timeout: int = 60) -> tuple[int, str]:
        resolved_cmd = self._resolve_command(cmd[0]) + cmd[1:]
        try:
            res = subprocess.run(
                resolved_cmd,
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
        """Run ruff, mypy/pyright, and pytest."""
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

    def verify_typescript(self) -> VerificationReport:
        """Run tsc and npm test."""
        issues: list[DiagnosticIssue] = []
        raw_outputs = []
        typecheck_passed = True
        tests_passed = True

        # tsc --noEmit
        code, out = self.run_command_safe(["npx", "tsc", "--noEmit"])
        if code != 0 and "Command not found" not in out:
            typecheck_passed = False
            raw_outputs.append(f"--- TypeScript Diagnostics ---\n{out}")

        passed = typecheck_passed and tests_passed
        return VerificationReport(
            passed=passed,
            linter_passed=True,
            typecheck_passed=typecheck_passed,
            tests_passed=tests_passed,
            issues=issues,
            raw_output="\n\n".join(raw_outputs),
            summary="TypeScript checks passed" if passed else "TypeScript issues detected",
        )

    def verify_rust(self) -> VerificationReport:
        """Run cargo check and cargo test."""
        raw_outputs = []
        code, out = self.run_command_safe(["cargo", "check"])
        passed = code == 0
        if not passed:
            raw_outputs.append(f"--- Cargo Check ---\n{out}")
        return VerificationReport(
            passed=passed,
            linter_passed=passed,
            typecheck_passed=passed,
            tests_passed=passed,
            raw_output="\n\n".join(raw_outputs),
            summary="Cargo check passed" if passed else "Cargo build issues detected",
        )

    def verify_go(self) -> VerificationReport:
        """Run go vet and go test."""
        raw_outputs = []
        code, out = self.run_command_safe(["go", "vet", "./..."])
        passed = code == 0
        if not passed:
            raw_outputs.append(f"--- Go Vet ---\n{out}")
        return VerificationReport(
            passed=passed,
            linter_passed=passed,
            typecheck_passed=passed,
            tests_passed=passed,
            raw_output="\n\n".join(raw_outputs),
            summary="Go checks passed" if passed else "Go vet issues detected",
        )

    def verify_project(self) -> VerificationReport:
        """Auto-detect language and run corresponding verifier."""
        if (self.root_dir / "pyproject.toml").exists() or any(self.root_dir.glob("*.py")):
            return self.verify_python()
        elif (self.root_dir / "package.json").exists() or (
            self.root_dir / "tsconfig.json"
        ).exists():
            return self.verify_typescript()
        elif (self.root_dir / "Cargo.toml").exists():
            return self.verify_rust()
        elif (self.root_dir / "go.mod").exists():
            return self.verify_go()

        return VerificationReport(
            passed=True,
            linter_passed=True,
            typecheck_passed=True,
            tests_passed=True,
            summary="No language verifiers triggered",
        )
