"""Archive Tool - Compress and extract archives."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class ArchiveArgs(BaseModel):
    """Arguments for archive operations."""

    operation: str = Field(description="Operation: create, extract, list")
    path: str = Field(description="Archive path or directory to archive")
    format: str = Field(default="zip", description="Archive format: zip, tar, tar.gz, tar.bz2")
    output: str = Field(default="", description="Output path for extract/create")


class Archive(BaseTool):
    """Tool for creating and extracting archives."""

    name: str = "archive"
    description: str = "Create, extract, and list archives. Supports zip, tar, tar.gz, tar.bz2."
    args_model: type[BaseModel] = ArchiveArgs

    def _run(
        self,
        operation: str,
        path: str,
        format: str = "zip",
        output: str = "",
        **kwargs: Any,
    ) -> str:
        """Execute archive operation."""
        import tarfile
        import zipfile

        target = self._expand_path(path)

        try:
            if operation == "create":
                if not target.exists():
                    return f"Error: Path not found: {path}"

                out_path = Path(output) if output else Path(f"{target.name}.{format}")

                if format == "zip":
                    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
                        if target.is_file():
                            zf.write(target, target.name)
                        else:
                            for file in target.rglob("*"):
                                if file.is_file():
                                    zf.write(file, file.relative_to(target.parent))

                elif format.startswith("tar"):
                    mode = "w"
                    if format == "tar.gz":
                        mode = "w:gz"
                    elif format == "tar.bz2":
                        mode = "w:bz2"

                    with tarfile.open(out_path, mode) as tf:
                        tf.add(target, arcname=target.name)

                else:
                    return f"Error: Unsupported format '{format}'"

                size = out_path.stat().st_size / 1024
                return f"Created: {out_path} ({size:.1f} KB)"

            elif operation == "extract":
                if not target.exists():
                    return f"Error: Archive not found: {path}"

                out_dir = Path(output) if output else target.parent / target.stem

                if target.suffix == ".zip":
                    with zipfile.ZipFile(target, "r") as zf:
                        # Zip Slip protection
                        for member in zf.namelist():
                            member_path = (out_dir / member).resolve()
                            if not str(member_path).startswith(str(out_dir.resolve())):
                                return f"Error: Archive contains path traversal: {member}"
                        zf.extractall(out_dir)
                        files = zf.namelist()

                elif target.suffix in (".tar", ".gz", ".bz2") or ".tar." in target.name:
                    with tarfile.open(target, "r:*") as tf:
                        # Tar Slip protection
                        for member in tf.getmembers():
                            member_path = (out_dir / member.name).resolve()
                            if not str(member_path).startswith(str(out_dir.resolve())):
                                return f"Error: Archive contains path traversal: {member.name}"
                        tf.extractall(out_dir)
                        files = [m.name for m in tf.getmembers()]

                else:
                    return "Error: Unsupported archive format"

                return f"Extracted {len(files)} files to: {out_dir}"

            elif operation == "list":
                if not target.exists():
                    return f"Error: Archive not found: {path}"

                if target.suffix == ".zip":
                    with zipfile.ZipFile(target, "r") as zf:
                        files = zf.namelist()
                        info = [f"{f.filename} ({f.file_size} bytes)" for f in zf.infolist()]

                elif target.suffix in (".tar", ".gz", ".bz2") or ".tar." in target.name:
                    with tarfile.open(target, "r:*") as tf:
                        files = [m.name for m in tf.getmembers()]
                        info = [f"{m.name} ({m.size} bytes)" for m in tf.getmembers()]

                else:
                    return "Error: Unsupported archive format"

                return f"Archive contents ({len(files)} files):\n" + "\n".join(info[:50])

            else:
                return f"Error: Invalid operation '{operation}'. Valid: create, extract, list"

        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"


def get_tool() -> type[Archive]:
    """Get the tool class."""
    return Archive
