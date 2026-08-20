"""Code Execution Sandbox - Secure isolated code execution for Python, JS, Shell.

Auto-installs Node.js if missing for JavaScript execution.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import venv
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool, ToolCategory, ToolResult
from sago.tools.ensure_dep import ensure_binary

_SANDBOX_TIMEOUT = 30
_MAX_OUTPUT = 100_000


class CodeSandboxArgs(BaseModel):
    """Arguments for code sandbox execution."""

    language: str = Field(description="Language: python, javascript, bash, shell")
    code: str = Field(description="Code to execute")
    timeout: int = Field(default=_SANDBOX_TIMEOUT, description="Execution timeout in seconds")
    packages: list[str] = Field(
        default_factory=list, description="Python packages to install before execution"
    )
    env_vars: dict[str, str] = Field(
        default_factory=dict, description="Environment variables to set"
    )
    capture_output: bool = Field(default=True, description="Capture stdout/stderr")
    auto_install: bool = Field(default=True, description="Auto-install missing runtimes")


class CodeSandboxTool(BaseTool):
    """Execute code in an isolated sandbox with resource limits."""

    name: str = "code_sandbox"
    description: str = (
        "Execute code in a sandboxed environment with resource limits. "
        "Supports Python, JavaScript (Node.js), and Bash/Shell. "
        "Python gets an isolated venv with optional package installation. "
        "Auto-installs Node.js if missing for JavaScript execution."
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
        auto_install: bool = True,
        **extra: Any,
    ) -> ToolResult:
        lang = (language or "").strip().lower()

        exec_env = os.environ.copy()
        exec_env["PYTHONDONTWRITEBYTECODE"] = "1"
        if env_vars:
            for k, v in env_vars.items():
                if k.isidentifier() and k.upper() not in {"LD_PRELOAD", "LD_LIBRARY_PATH"}:
                    exec_env[k] = v

        suffix_map = {
            "python": ".py",
            "javascript": ".js",
            "bash": ".sh",
            "shell": ".sh",
            "js": ".js",
        }
        suffix = suffix_map.get(lang, ".txt")
        tmpfile = Path(tempfile.mktemp(suffix=suffix, prefix="sago_sandbox_"))

        try:
            tmpfile.write_text(code, encoding="utf-8")

            if lang == "python":
                return self._run_python(tmpfile, timeout, packages or [], exec_env, capture_output)
            elif lang in ("javascript", "js"):
                return self._run_javascript(
                    tmpfile, timeout, exec_env, capture_output, auto_install
                )
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
        timeout: int,
        packages: list[str],
        env: dict[str, str],
        capture_output: bool,
    ) -> ToolResult:
        venv_dir = Path(tempfile.mkdtemp(prefix="sago_venv_"))
        try:
            builder = venv.EnvBuilder(
                system_site_packages=False, with_pip=True, clear=True, symlinks=False
            )
            builder.create(venv_dir)

            pip_cmd = [
                str(venv_dir / "bin" / "pip"),
                "install",
                "--quiet",
                "--disable-pip-version-check",
            ]
            python_cmd = str(venv_dir / "bin" / "python")

            if packages:
                install_result = subprocess.run(
                    [*pip_cmd, *packages], capture_output=True, text=True, timeout=60, env=env
                )
                if install_result.returncode != 0:
                    return ToolResult(
                        output=f"Package installation failed:\n{install_result.stderr}",
                        success=False,
                        error="package_install_failed",
                        metadata={"packages": packages},
                    )

            proc = subprocess.run(
                [python_cmd, str(tmpfile)],
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
                )

            output = stdout
            if stderr:
                output += f"\n\nSTDERR:\n{stderr}" if stdout else f"STDERR:\n{stderr}"
            return ToolResult(
                output=output or "Code executed successfully (no output).",
                success=True,
                metadata={"packages": packages},
            )

        finally:
            import shutil

            shutil.rmtree(venv_dir, ignore_errors=True)

    def _run_javascript(
        self,
        tmpfile: Path,
        timeout: int,
        env: dict[str, str],
        capture_output: bool,
        auto_install: bool,
    ) -> ToolResult:
        # Check for node, auto-install if missing
        if not auto_install or not any(_find_binary(n) for n in ["node", "nodejs"]):
            if auto_install:
                ok, msg = ensure_binary("node", auto_install=True)
                if not ok:
                    return ToolResult(output=msg, success=False, error="node_not_found")
            else:
                return ToolResult(
                    output="Node.js not found. Install: sudo apt-get install -y nodejs  OR  brew install node",
                    success=False,
                    error="node_not_found",
                )

        for node_bin in ["node", "nodejs"]:
            path = _find_binary(node_bin)
            if path:
                proc = subprocess.run(
                    [path, str(tmpfile)],
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
                    output=output or "Code executed successfully (no output).", success=True
                )

        return ToolResult(output="Node.js not found.", success=False, error="node_not_found")

    def _run_shell(
        self, tmpfile: Path, timeout: int, env: dict[str, str], capture_output: bool
    ) -> ToolResult:
        tmpfile.chmod(0o755)
        proc = subprocess.run(
            ["bash", "-c", f"ulimit -t {timeout} -f 100000 -u 50 2>/dev/null; bash {tmpfile}"],
            capture_output=capture_output,
            text=True,
            timeout=timeout + 5,
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
            output=output or "Script executed successfully (no output).", success=True
        )


def _find_binary(name: str) -> str | None:
    import shutil

    return shutil.which(name)


def get_tool() -> type[CodeSandboxTool]:
    """Get the tool class."""
    return CodeSandboxTool
