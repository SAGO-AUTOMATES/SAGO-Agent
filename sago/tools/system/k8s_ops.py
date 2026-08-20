"""Kubernetes Operations Tool - Safe kubectl wrapper for cluster management."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool, ToolCategory, ToolResult

_K8S_TIMEOUT = 60

# Dangerous operations that require confirmation via dry_run first
DESTRUCTIVE_OPS = {"delete", "drain", "taint", "uncordon", "rollout undo"}


class K8sOpsArgs(BaseModel):
    """Arguments for Kubernetes operations."""

    operation: str = Field(
        ...,
        description=(
            "Kubernetes operation: "
            "get, describe, create, apply, delete, logs, exec, "
            "rollout, scale, top, explain, config, cluster-info, "
            "context, namespace, run, expose, patch, label, annotate"
        ),
    )
    resource: str = Field(
        default="",
        description="Resource type and name (e.g. 'pods', 'deployments/myapp', 'services -n kube-system')",
    )
    args: list[str] = Field(
        default_factory=list,
        description="Extra kubectl arguments (e.g. ['-o', 'yaml', '-n', 'default'])",
    )
    namespace: str = Field(
        default="",
        description="Kubernetes namespace (overrides -n in args)",
    )
    output_format: str = Field(
        default="",
        description="Output format: yaml, json, wide, name (appended to command)",
    )
    dry_run: bool = Field(
        default=False,
        description="If true, add --dry-run=client for destructive operations",
    )
    timeout: int = Field(
        default=_K8S_TIMEOUT,
        description="Command timeout in seconds",
    )


class K8sOpsTool(BaseTool):
    """Execute Kubernetes/kubectl operations safely with structured output."""

    name: str = "k8s_ops"
    description: str = (
        "Execute Kubernetes kubectl operations: get, describe, create, apply, delete, "
        "logs, exec, rollout, scale, top, explain, config, cluster-info, run, expose, "
        "patch, label, annotate. Supports namespace targeting, output formatting, "
        "and dry-run mode for destructive operations."
    )
    category: ToolCategory = ToolCategory.SYSTEM
    args_model: type[BaseModel] | None = K8sOpsArgs

    def _run(self, **kwargs: Any) -> str:
        result = self.execute(**kwargs)
        return result.output

    def execute(
        self,
        operation: str,
        resource: str = "",
        args: list[str] | None = None,
        namespace: str = "",
        output_format: str = "",
        dry_run: bool = False,
        timeout: int = _K8S_TIMEOUT,
        **extra: Any,
    ) -> ToolResult:
        op = (operation or "").strip().lower()
        extra_args = list(args or [])

        # Build the command safely with explicit args
        cmd = ["kubectl", op]

        # Add namespace if specified and not already in args
        if namespace and "-n" not in extra_args and "--namespace" not in extra_args:
            cmd.extend(["-n", namespace])

        # Add resource
        if resource:
            cmd.extend(resource.split())

        # Add extra arguments
        cmd.extend(extra_args)

        # Add output format if specified
        if output_format and "-o" not in extra_args and "--output" not in extra_args:
            cmd.extend(["-o", output_format])

        # Add dry-run for destructive operations
        is_destructive = any(op.startswith(d) for d in DESTRUCTIVE_OPS)
        if dry_run and is_destructive:
            cmd.append("--dry-run=client")

        # Validate: block truly dangerous ops without dry-run
        if is_destructive and not dry_run:
            return ToolResult(
                output=(
                    f"BLOCKED: '{op}' is a destructive operation. "
                    f"Set dry_run=true to preview the effect, then re-run without dry_run to execute."
                ),
                success=False,
                error="destructive_operation_blocked",
                metadata={"operation": op, "suggestion": "Use --dry-run=client first"},
            )

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                output=f"kubectl {op} timed out after {timeout}s.",
                success=False,
                error="timeout",
                metadata={"command": cmd, "timeout": timeout},
            )
        except FileNotFoundError:
            return ToolResult(
                output="kubectl not found. Install kubectl or ensure it's in PATH.",
                success=False,
                error="kubectl_not_found",
            )
        except Exception as e:
            return ToolResult(
                output=f"Failed to run kubectl {op}: {e}",
                success=False,
                error=str(e),
                metadata={"command": cmd},
            )

        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        if proc.returncode != 0:
            return ToolResult(
                output=stderr or f"kubectl {op} failed (code {proc.returncode}).",
                success=False,
                error=f"exit_{proc.returncode}",
                metadata={"returncode": proc.returncode, "command": cmd, "stdout": stdout},
            )

        # Try to parse JSON output for structured metadata
        metadata: dict[str, Any] = {"returncode": proc.returncode, "command": cmd}
        if output_format == "json" and stdout:
            try:
                parsed = json.loads(stdout)
                metadata["parsed"] = True
                if isinstance(parsed, dict):
                    metadata["kind"] = parsed.get("kind", "")
                    metadata["name"] = parsed.get("metadata", {}).get("name", "")
                    if "items" in parsed:
                        metadata["item_count"] = len(parsed["items"])
            except (json.JSONDecodeError, ValueError):
                metadata["parsed"] = False

        return ToolResult(
            output=stdout or f"kubectl {op} completed with no output.",
            success=True,
            metadata=metadata,
        )


def get_tool() -> type[K8sOpsTool]:
    """Get the tool class."""
    return K8sOpsTool
