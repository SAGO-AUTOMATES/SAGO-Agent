"""Hardline Security Approval and Safety Gates.

Enforces non-bypassable restrictions for catastrophic system commands and
protected file system paths regardless of user execution mode (including YOLO).
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger("sago.security.approval")

# Regex patterns for catastrophic system commands that must NEVER be executed
HARDLINE_COMMAND_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # rm -rf / or rm -fr / (isolated root, not /tmp or /var)
    (
        re.compile(
            r"\brm\s+(?:[^\n;|&]*\s+)?-(?:[a-zA-Z]*r[a-zA-Z]*f|[a-zA-Z]*f[a-zA-Z]*r)\s+/(?:\s|$|;|\&|\||\))"
        ),
        "rm -rf / (root filesystem deletion)",
    ),
    (
        re.compile(
            r"\brm\s+(?:[^\n;|&]*\s+)?-(?:[a-zA-Z]*r[a-zA-Z]*f|[a-zA-Z]*f[a-zA-Z]*r)\s+/\*(?:\s|$|;|\&|\||\))"
        ),
        "rm -rf /* (root filesystem deletion)",
    ),
    (
        re.compile(
            r"\brm\s+(?:[^\n;|&]*\s+)?-(?:[a-zA-Z]*r[a-zA-Z]*f|[a-zA-Z]*f[a-zA-Z]*r)\s+~(?:\s|/|$|;|\&|\||\))"
        ),
        "rm -rf ~ (home directory deletion)",
    ),
    (
        re.compile(
            r"\brm\s+(?:[^\n;|&]*\s+)?-(?:[a-zA-Z]*r[a-zA-Z]*f|[a-zA-Z]*f[a-zA-Z]*r)\s+\$HOME(?:\s|/|$|;|\&|\||\))"
        ),
        "rm -rf $HOME (home directory deletion)",
    ),
    (
        re.compile(
            r"\brm\s+(?:[^\n;|&]*\s+)?-(?:[a-zA-Z]*r[a-zA-Z]*f|[a-zA-Z]*f[a-zA-Z]*r)\s+/home(?:/[a-zA-Z0-9_-]+)?(?:\s|/|$|;|\&|\||\))"
        ),
        "rm -rf /home (home directory deletion)",
    ),
    (re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"), "fork bomb"),
    (re.compile(r"\bmkfs(?:\.[a-zA-Z0-9_-]+)?\s+"), "filesystem format"),
    (
        re.compile(r"\bdd\s+.*of=/dev/(?:sd[a-z]|nvme[0-9]n[0-9]|hd[a-z]|vd[a-z]|disk[0-9])"),
        "raw disk write via dd",
    ),
    (
        re.compile(r">\s*/dev/(?:sd[a-z]|nvme[0-9]n[0-9]|hd[a-z]|vd[a-z]|disk[0-9])"),
        "raw disk overwrite",
    ),
    (
        re.compile(r"\b(shutdown|reboot|poweroff|halt)\b(?:\s+-[a-zA-Z0-9]+|\s+now)?"),
        "system shutdown/reboot",
    ),
    (re.compile(r"\bkill\s+-9\s+-1\b"), "kill all processes"),
    (
        re.compile(r"\bchmod\s+(?:-[a-zA-Z]*R[a-zA-Z]*\s+)?(?:777|000)\s+/(?:\s|$|;|\&|\||\))"),
        "unrestricted root chmod",
    ),
    (
        re.compile(r"\bchown\s+(?:-[a-zA-Z]*R[a-zA-Z]*\s+)?[a-zA-Z0-9_:-]+\s+/(?:\s|$|;|\&|\||\))"),
        "root directory ownership alteration",
    ),
]

# Sensitive paths and prefixes that must never be overwritten
PROTECTED_WRITE_PATHS: set[str] = {
    "/etc/passwd",
    "/etc/shadow",
    "/etc/sudoers",
    "/etc/ld.so.preload",
    "/etc/ld.so.conf",
    "/etc/fstab",
}

PROTECTED_WRITE_PREFIXES: list[str] = [
    "~/.ssh/",
    "~/.aws/",
    "~/.gnupg/",
    "~/.kube/",
    "/etc/sudoers.d/",
    "/etc/systemd/",
    "/etc/pam.d/",
]


def check_hardline_command(command: str) -> str | None:
    """Check if a command matches catastrophic patterns that cannot be executed.

    Args:
        command: The shell command to evaluate.

    Returns:
        Reason string if blocked, None if permitted.
    """
    if not command or not command.strip():
        return None

    cmd = command.strip()
    for pattern, description in HARDLINE_COMMAND_PATTERNS:
        if pattern.search(cmd):
            logger.critical(
                "Hardline command blocker triggered: %s | command: %s", description, command
            )
            return f"HARDLINE SECURITY BLOCK: Command matched prohibited pattern: {description}"

    return None


def check_write_safety(path: str | Path) -> str | None:
    """Check if a file target path is protected from write/overwrite.

    Args:
        path: Target file path.

    Returns:
        Reason string if write is blocked, None if safe.
    """
    try:
        target_path = Path(os.path.expandvars(os.path.expanduser(str(path)))).resolve()
        target_str = str(target_path)
    except Exception as e:
        logger.debug("Failed to resolve target write path '%s': %s", path, e)
        target_str = str(path)

    # Check exact forbidden files
    for protected in PROTECTED_WRITE_PATHS:
        try:
            prot_resolved = str(Path(protected).resolve())
            if target_str == prot_resolved or str(path) == protected:
                logger.critical("Protected file write blocked: %s", target_str)
                return (
                    f"HARDLINE SECURITY BLOCK: Write denied to protected system path: {protected}"
                )
        except Exception:
            if target_str == protected:
                return (
                    f"HARDLINE SECURITY BLOCK: Write denied to protected system path: {protected}"
                )

    # Check protected directory prefixes
    for prefix in PROTECTED_WRITE_PREFIXES:
        try:
            prot_prefix = str(Path(os.path.expandvars(os.path.expanduser(prefix))).resolve())
            if target_str.startswith(prot_prefix + os.sep) or target_str == prot_prefix:
                logger.critical("Protected prefix write blocked: %s for %s", prefix, target_str)
                return f"HARDLINE SECURITY BLOCK: Write denied to protected directory: {prefix}"
        except Exception:
            if target_str.startswith(prefix):
                return f"HARDLINE SECURITY BLOCK: Write denied to protected directory: {prefix}"

    return None
