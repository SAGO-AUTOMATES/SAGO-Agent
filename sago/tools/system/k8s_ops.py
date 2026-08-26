"""Kubernetes Operations Tool - Safe kubectl wrapper with k3s auto-install.

Prefers k3s (lightweight, ~50MB) over full k8s. Auto-installs k3s/kubectl if missing.
"""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool, ToolCategory, ToolResult
from sago.tools.ensure_dep import ensure_binary, is_available

logger = logging.getLogger("sago.tools.system.k8s_ops")


_K8S_TIMEOUT = 60
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
        default="", description="Resource type and name (e.g. 'pods', 'deployments/myapp')"
    )
    args: list[str] = Field(default_factory=list, description="Extra kubectl arguments")
    namespace: str = Field(default="", description="Kubernetes namespace")
    output_format: str = Field(default="", description="Output format: yaml, json, wide, name")
    dry_run: bool = Field(
        default=False, description="Add --dry-run=client for destructive operations"
    )
    timeout: int = Field(default=_K8S_TIMEOUT, description="Command timeout in seconds")
    auto_install: bool = Field(default=True, description="Auto-install k3s/kubectl if missing")


class K8sOpsTool(BaseTool):
    """Execute Kubernetes/kubectl operations safely. Prefers k3s (lightweight)."""

    name: str = "k8s_ops"
    description: str = (
        "Execute Kubernetes kubectl operations: get, describe, create, apply, delete, "
        "logs, exec, rollout, scale, top, explain, config, cluster-info, run, expose, "
        "patch, label, annotate. Prefers k3s (lightweight, ~50MB) over full k8s. "
        "Auto-installs k3s on Linux if missing. Supports dry-run for destructive ops."
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
        auto_install: bool = True,
        **extra: Any,
    ) -> ToolResult:
        op = (operation or "").strip().lower()
        logger.debug(
            "k8s_ops called: operation=%s, resource=%s, namespace=%s", op, resource, namespace
        )

        # Ensure kubectl/k3s is available - prefer k3s on Linux
        kubectl_cmd = self._resolve_kubectl(auto_install)
        if not kubectl_cmd:
            logger.warning("kubectl/k3s not found on system")
            return ToolResult(
                output=(
                    "kubectl/k3s not found.\n"
                    "Auto-install k3s (lightweight, recommended):\n"
                    "  curl -sfL https://get.k3s.io | sh -\n\n"
                    "Or install kubectl manually:\n"
                    "  https://kubernetes.io/docs/tasks/tools/"
                ),
                success=False,
                error="kubectl_not_found",
            )

        extra_args = list(args or [])
        cmd = [kubectl_cmd, op]

        if namespace and "-n" not in extra_args and "--namespace" not in extra_args:
            cmd.extend(["-n", namespace])

        if resource:
            cmd.extend(resource.split())

        cmd.extend(extra_args)

        if output_format and "-o" not in extra_args and "--output" not in extra_args:
            cmd.extend(["-o", output_format])

        is_destructive = any(op.startswith(d) for d in DESTRUCTIVE_OPS)
        if dry_run and is_destructive:
            cmd.append("--dry-run=client")

        if is_destructive and not dry_run:
            logger.warning("Destructive K8s operation blocked: operation=%s", op)
            return ToolResult(
                output=f"BLOCKED: '{op}' is destructive. Set dry_run=true to preview first.",
                success=False,
                error="destructive_operation_blocked",
                metadata={"operation": op},
            )

        logger.info("Executing k8s command: %s", " ".join(cmd))

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
            logger.error("K8s command timed out: operation=%s, timeout=%d", op, timeout)
            return ToolResult(
                output=f"kubectl {op} timed out after {timeout}s.", success=False, error="timeout"
            )
        except FileNotFoundError:
            logger.error("kubectl binary not found during execution")
            return ToolResult(output="kubectl not found.", success=False, error="kubectl_not_found")
        except Exception as e:
            logger.error("K8s command failed: operation=%s, error=%s", op, e)
            return ToolResult(
                output=f"Failed to run kubectl {op}: {e}", success=False, error=str(e)
            )

        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        if proc.returncode != 0:
            logger.error(
                "K8s command failed: operation=%s, returncode=%d, stderr=%s",
                op,
                proc.returncode,
                stderr[:200],
            )
            return ToolResult(
                output=stderr or f"kubectl {op} failed (code {proc.returncode}).",
                success=False,
                error=f"exit_{proc.returncode}",
                metadata={"returncode": proc.returncode, "command": cmd},
            )

        logger.info("K8s command succeeded: operation=%s, returncode=%d", op, proc.returncode)

        metadata: dict[str, Any] = {
            "returncode": proc.returncode,
            "command": cmd,
            "kubectl": kubectl_cmd,
        }
        if output_format == "json" and stdout:
            try:
                parsed = json.loads(stdout)
                metadata["parsed"] = True
                if isinstance(parsed, dict):
                    metadata["kind"] = parsed.get("kind", "")
                    if "items" in parsed:
                        metadata["item_count"] = len(parsed["items"])
            except (json.JSONDecodeError, ValueError):
                metadata["parsed"] = False

        return ToolResult(
            output=stdout or f"kubectl {op} completed.", success=True, metadata=metadata
        )

    def _resolve_kubectl(self, auto_install: bool) -> str | None:
        """Find kubectl or k3s, auto-installing if needed."""
        # Check for existing kubectl
        path = is_available("kubectl")
        if path:
            return "kubectl"

        # Check for k3s (lightweight, includes kubectl)
        if is_available("k3s"):
            return "k3s"

        # Auto-install: prefer k3s on Linux
        if auto_install:
            ok, msg = ensure_binary("k3s", auto_install=True)
            if ok and is_available("k3s"):
                return "k3s"

            # Fallback to standalone kubectl
            ok, msg = ensure_binary("kubectl", auto_install=True)
            if ok and is_available("kubectl"):
                return "kubectl"

        return None


def get_tool() -> type[K8sOpsTool]:
    """Get the tool class."""
    return K8sOpsTool
