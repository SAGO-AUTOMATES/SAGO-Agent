"""Code Execution Sandbox - Secure isolated code execution for Python, JS, Shell."""

from __future__ import annotations

import os
import subprocess
import tempfile
import venv
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool, ToolCategory, ToolResult

_SANDBOX_TIMEOUT = 30
_MAX_OUTPUT = 100_000  # 100KB output limit


class CodeSandboxArgs(BaseModel):
    """Arguments for code sandbox execution."""

    language: str = Field(
        ...,
        description="Language: python, javascript, bash, shell",
    )
    code: str = Field(
        ...,
        description="Code to execute",
    )
    timeout: int = Field(
        default=_SANDBOX_TIMEOUT,
        description="Execution timeout in seconds",
    )
    packages: list[str] = Field(
        default_factory=list,
        description="Python packages to install before execution (e.g. ['requests', 'pandas'])",
    )
    env_vars: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables to set (keys only, values from env if needed)",
    )
    capture_output: bool = Field(
        default=True,
        description="Capture stdout/stderr (if false, streams to console)",
    )


class CodeSandboxTool(BaseTool):
    """Execute code in an isolated sandbox with resource limits."""

    name: str = "code_sandbox"
    description: str = (
        "Execute code in a sandboxed environment with resource limits. "
        "Supports Python, JavaScript (Node.js), and Bash/Shell. "
        "Python gets an isolated venv with optional package installation. "
        "All execution has timeout and output size limits."
    )
    category: ToolCategory = ToolCategory.CODING
    args_model: type[BaseModel] | None = CodeSandboxArgs

    def _run(self, **kwargs: Any) -> str:
        result = self.execute(**kwargs)
        return result.output

    def execute(
        self,
        language: str,
        code: str,
        timeout: int = _SANDBOX_TIMEOUT,
        packages: list[str] | None = None,
        env_vars: dict[str, str] | None = None,
        capture_output: bool = True,
        **extra: Any,
    ) -> ToolResult:
        lang = (language or "").strip().lower()

        # Sanitize env vars
        exec_env = os.environ.copy()
        exec_env["PYTHONDONTWRITEBYTECODE"] = "1"
        if env_vars:
            for k, v in env_vars.items():
                if k.isidentifier() and k.upper() not in {
                    "LD_PRELOAD",
                    "LD_LIBRARY_PATH",
                    "PYTHONPATH",
                }:
                    exec_env[k] = v

        # Write code to temp file
        suffix_map = {"python": ".py", "javascript": ".js", "bash": ".sh", "shell": ".sh"}
        suffix = suffix_map.get(lang, ".txt")
        tmpfile = Path(tempfile.mktemp(suffix=suffix, prefix="sago_sandbox_"))

        try:
            tmpfile.write_text(code, encoding="utf-8")

            if lang == "python":
                return self._run_python(
                    tmpfile, code, timeout, packages or [], exec_env, capture_output
                )
            elif lang in ("javascript", "js"):
                return self._run_javascript(tmpfile, timeout, exec_env, capture_output)
            elif lang in ("bash", "shell", "sh"):
                return self._run_shell(tmpfile, timeout, exec_env, capture_output)
            else:
                return ToolResult(
                    output=f"Unsupported language: '{lang}'. Supported: python, javascript, bash",
                    success=False,
                    error="unsupported_language",
                )
        finally:
            tmpfile.unlink(missing_ok=True)

    def _run_python(
        self,
        tmpfile: Path,
        code: str,
        timeout: int,
        packages: list[str],
        env: dict[str, str],
        capture_output: bool,
    ) -> ToolResult:
        """Execute Python code in an isolated virtualenv."""
        venv_dir = Path(tempfile.mkdtemp(prefix="sago_venv_"))
        try:
            # Create isolated venv
            builder = venv.EnvBuilder(
                system_site_packages=False,
                with_pip=True,
                clear=True,
                symlinks=False,
            )
            builder.create(venv_dir)

            pip_cmd = [
                str(venv_dir / "bin" / "pip"),
                "install",
                "--quiet",
                "--disable-pip-version-check",
            ]
            python_cmd = str(venv_dir / "bin" / "python")

            # Install packages if requested
            if packages:
                install_result = subprocess.run(
                    [*pip_cmd, *packages],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env=env,
                )
                if install_result.returncode != 0:
                    return ToolResult(
                        output=f"Package installation failed:\n{install_result.stderr}",
                        success=False,
                        error="package_install_failed",
                        metadata={"packages": packages},
                    )

            # Execute code
            cmd = [python_cmd, str(tmpfile)]
            proc = subprocess.run(
                cmd,
                capture_output=capture_output,
                text=True,
                timeout=timeout,
                env=env,
                cwd=str(venv_dir),
            )

            stdout = (proc.stdout or "")[:_MAX_OUTPUT]
            stderr = (proc.stderr or "")[:_MAX_OUTPUT]

            if proc.returncode != 0:
                return ToolResult(
                    output=f"Exit code {proc.returncode}\n\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}",
                    success=False,
                    error=f"exit_{proc.returncode}",
                    metadata={"returncode": proc.returncode, "packages": packages},
                )

            output = stdout
            if stderr:
                output += f"\n\nSTDERR:\n{stderr}" if stdout else f"STDERR:\n{stderr}"

            return ToolResult(
                output=output or "Code executed successfully (no output).",
                success=True,
                metadata={"returncode": 0, "packages": packages},
            )

        finally:
            import shutil

            shutil.rmtree(venv_dir, ignore_errors=True)

    def _run_javascript(
        self, tmpfile: Path, timeout: int, env: dict[str, str], capture_output: bool
    ) -> ToolResult:
        """Execute JavaScript with Node.js."""
        # Check for node
        for node_bin in ["node", "nodejs"]:
            try:
                proc = subprocess.run(
                    [node_bin, str(tmpfile)],
                    capture_output=capture_output,
                    text=True,
                    timeout=timeout,
                    env=env,
                )
                stdout = (proc.stdout or "")[:_MAX_OUTPUT]
                stderr = (proc.stderr or "")[:_MAX_OUTPUT]

                if proc.returncode != 0:
                    return ToolResult(
                        output=f"Exit code {proc.returncode}\n\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}",
                        success=False,
                        error=f"exit_{proc.returncode}",
                    )

                output = stdout
                if stderr:
                    output += f"\n\nSTDERR:\n{stderr}" if stdout else f"STDERR:\n{stderr}"
                return ToolResult(
                    output=output or "Code executed successfully (no output).",
                    success=True,
                )
            except FileNotFoundError:
                continue

        return ToolResult(
            output="Node.js not found. Install Node.js or use language='python' or 'bash'.",
            success=False,
            error="node_not_found",
        )

    def _run_shell(
        self, tmpfile: Path, timeout: int, env: dict[str, str], capture_output: bool
    ) -> ToolResult:
        """Execute shell script with resource limits."""
        # Make executable
        tmpfile.chmod(0o755)

        # Set resource limits via ulimit before execution
        limited_cmd = f"ulimit -t {timeout} -f 100000 -u 50 2>/dev/null; bash {tmpfile}"

        proc = subprocess.run(
            ["bash", "-c", limited_cmd],
            capture_output=capture_output,
            text=True,
            timeout=timeout + 5,  # Extra time for ulimit wrapper
            env=env,
        )

        stdout = (proc.stdout or "")[:_MAX_OUTPUT]
        stderr = (proc.stderr or "")[:_MAX_OUTPUT]

        if proc.returncode != 0:
            return ToolResult(
                output=f"Exit code {proc.returncode}\n\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}",
                success=False,
                error=f"exit_{proc.returncode}",
            )

        output = stdout
        if stderr:
            output += f"\n\nSTDERR:\n{stderr}" if stdout else f"STDERR:\n{stderr}"
        return ToolResult(
            output=output or "Script executed successfully (no output).",
            success=True,
        )


def get_tool() -> type[CodeSandboxTool]:
    """Get the tool class."""
    return CodeSandboxTool
