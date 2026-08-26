"""Hash/Checksum Tool - Generate and verify hashes."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.file.hash_checksum")


class HashChecksumArgs(BaseModel):
    """Arguments for hash/checksum operations."""

    operation: str = Field(description="Operation: hash-file, hash-string, verify")
    target: str = Field(description="File path or string to hash")
    algorithm: str = Field(
        default="sha256", description="Hash algorithm: md5, sha1, sha256, sha512"
    )
    expected_hash: str = Field(default="", description="Expected hash for verify operation")


class HashChecksum(BaseTool):
    """Tool for generating and verifying hashes."""

    name: str = "hash_checksum"
    description: str = "Generate and verify file/string hashes. Supports md5, sha1, sha256, sha512."
    args_model: type[BaseModel] = HashChecksumArgs

    VALID_ALGORITHMS = {"md5", "sha1", "sha256", "sha512", "sha3_256", "sha3_512"}

    def _run(
        self,
        operation: str,
        target: str,
        algorithm: str = "sha256",
        expected_hash: str = "",
        **kwargs: Any,
    ) -> str:
        """Execute hash operation."""
        if algorithm not in self.VALID_ALGORITHMS:
            return f"Error: Invalid algorithm '{algorithm}'. Valid: {', '.join(sorted(self.VALID_ALGORITHMS))}"

        try:
            if operation == "hash-file":
                path = self._expand_path(target)
                if not path.exists():
                    return f"Error: File not found: {target}"
                if not path.is_file():
                    return f"Error: Not a file: {target}"

                h = hashlib.new(algorithm)
                with open(path, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        h.update(chunk)

                file_hash = h.hexdigest()
                return f"File: {path}\nAlgorithm: {algorithm}\nHash: {file_hash}"

            elif operation == "hash-string":
                h = hashlib.new(algorithm)
                h.update(target.encode("utf-8"))
                string_hash = h.hexdigest()
                return f"String: {target[:100]}{'...' if len(target) > 100 else ''}\nAlgorithm: {algorithm}\nHash: {string_hash}"

            elif operation == "verify":
                path = self._expand_path(target)
                if not path.exists():
                    return f"Error: File not found: {target}"

                h = hashlib.new(algorithm)
                with open(path, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        h.update(chunk)

                file_hash = h.hexdigest()
                match = file_hash.lower() == expected_hash.lower()

                return (
                    f"File: {path}\n"
                    f"Algorithm: {algorithm}\n"
                    f"Computed: {file_hash}\n"
                    f"Expected: {expected_hash}\n"
                    f"Match: {'YES' if match else 'NO'}"
                )

            else:
                return (
                    f"Error: Invalid operation '{operation}'. Valid: hash-file, hash-string, verify"
                )

        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"


def get_tool() -> type[HashChecksum]:
    """Get the tool class."""
    return HashChecksum
