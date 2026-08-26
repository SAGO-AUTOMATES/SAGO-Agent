"""Log Manager — Smart log lifecycle management for Sago.

Handles log file discovery, statistics, session extraction,
smart pruning, and error extraction. Used by the CLI log viewer
and the cleanup system.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from sago.paths import get_logs_dir, get_sago_home

logger = logging.getLogger("sago.log_manager")

# Log line format: 2025-01-15 10:30:45 | INFO     | abc123def456 | sago.config | message
_LOG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*\|\s*(\w+)\s*\|\s*(\w{12})\s*\|\s*([\w.]+)\s*\|\s*(.+)$"
)


@dataclass
class LogFileInfo:
    """Metadata for a single log file."""

    path: Path
    size_bytes: int
    modified_time: float
    line_count: int = 0
    date_range: tuple[str, str] | None = None
    error_count: int = 0
    session_ids: set[str] = field(default_factory=set)

    @property
    def age_days(self) -> float:
        """Age of file in days."""
        return (time.time() - self.modified_time) / 86400

    @property
    def size_human(self) -> str:
        """Human-readable size."""
        b = self.size_bytes
        if b < 1024:
            return f"{b} B"
        elif b < 1024 * 1024:
            return f"{b / 1024:.1f} KB"
        else:
            return f"{b / (1024 * 1024):.2f} MB"


@dataclass
class LogStats:
    """Aggregate statistics across all log files."""

    total_files: int = 0
    total_lines: int = 0
    total_size_bytes: int = 0
    total_sessions: int = 0
    error_lines: int = 0
    warning_lines: int = 0
    info_lines: int = 0
    debug_lines: int = 0
    date_range: tuple[str, str] | None = None
    top_errors: list[tuple[str, int]] = field(default_factory=list)
    top_modules: list[tuple[str, int]] = field(default_factory=list)
    files: list[LogFileInfo] = field(default_factory=list)

    @property
    def size_human(self) -> str:
        """Human-readable total size."""
        b = self.total_size_bytes
        if b < 1024:
            return f"{b} B"
        elif b < 1024 * 1024:
            return f"{b / 1024:.1f} KB"
        else:
            return f"{b / (1024 * 1024):.2f} MB"


@dataclass
class LogLine:
    """Parsed log line."""

    timestamp: str
    level: str
    session_id: str
    module: str
    message: str


class LogManager:
    """Manages Sago log files — discovery, parsing, stats, and cleanup."""

    def __init__(self, log_dir: Path | None = None) -> None:
        self.log_dir = log_dir or get_logs_dir()

    def get_log_files(self) -> list[Path]:
        """Get all log files (main + rotated + errors)."""
        files: list[Path] = []
        if self.log_dir.exists():
            files.extend(self.log_dir.glob("*.log"))
            files.extend(self.log_dir.glob("*.log.*"))
        # Also include daemon log
        daemon_log = get_sago_home() / "daemon.log"
        if daemon_log.exists():
            files.append(daemon_log)
        return sorted(files, key=lambda f: f.stat().st_mtime)

    def get_file_info(self, path: Path) -> LogFileInfo:
        """Get metadata for a single log file (fast, no line parsing)."""
        stat = path.stat()
        return LogFileInfo(
            path=path,
            size_bytes=stat.st_size,
            modified_time=stat.st_mtime,
        )

    def parse_line(self, line: str) -> LogLine | None:
        """Parse a single log line into structured data."""
        m = _LOG_PATTERN.match(line.strip())
        if m:
            return LogLine(
                timestamp=m.group(1),
                level=m.group(2),
                session_id=m.group(3),
                module=m.group(4),
                message=m.group(5),
            )
        return None

    def read_lines(
        self,
        path: Path,
        level: str | None = None,
        session_id: str | None = None,
        module: str | None = None,
        search: str | None = None,
        since: float | None = None,
        limit: int | None = None,
        errors_only: bool = False,
    ) -> list[LogLine]:
        """Read and filter log lines from a file.

        Args:
            path: Log file to read.
            level: Filter by log level (e.g., 'ERROR', 'INFO').
            session_id: Filter by session ID.
            module: Filter by module name (partial match).
            search: Full-text search in messages.
            since: Unix timestamp — only lines after this time.
            limit: Max lines to return.
            errors_only: If True, only return ERROR+ lines.
        """
        lines: list[LogLine] = []
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for raw in f:
                    parsed = self.parse_line(raw)
                    if parsed is None:
                        continue

                    # Apply filters
                    if errors_only and parsed.level not in ("ERROR", "CRITICAL"):
                        continue
                    if level and parsed.level != level.upper():
                        continue
                    if session_id and parsed.session_id != session_id:
                        continue
                    if module and module.lower() not in parsed.module.lower():
                        continue
                    if search and search.lower() not in parsed.message.lower():
                        continue
                    if since:
                        try:
                            ts = time.mktime(time.strptime(parsed.timestamp, "%Y-%m-%d %H:%M:%S"))
                            if ts < since:
                                continue
                        except ValueError:
                            continue

                    lines.append(parsed)
                    if limit and len(lines) >= limit:
                        break
        except OSError:
            pass
        return lines

    def get_stats(self, quick: bool = False) -> LogStats:
        """Compute aggregate statistics across all log files.

        Args:
            quick: If True, only scan file metadata (no line parsing).
        """
        stats = LogStats()
        all_sessions: set[str] = set()
        error_messages: dict[str, int] = {}
        module_counts: dict[str, int] = {}
        min_date: str | None = None
        max_date: str | None = None

        for path in self.get_log_files():
            finfo = self.get_file_info(path)
            stats.total_files += 1
            stats.total_size_bytes += finfo.size_bytes

            if quick:
                stats.files.append(finfo)
                continue

            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    for raw in f:
                        stats.total_lines += 1
                        parsed = self.parse_line(raw)
                        if parsed is None:
                            continue

                        all_sessions.add(parsed.session_id)
                        module_counts[parsed.module] = module_counts.get(parsed.module, 0) + 1

                        if parsed.level == "ERROR" or parsed.level == "CRITICAL":
                            stats.error_lines += 1
                            # Normalize error message (truncate long ones)
                            err_key = parsed.message[:120]
                            error_messages[err_key] = error_messages.get(err_key, 0) + 1
                        elif parsed.level == "WARNING":
                            stats.warning_lines += 1
                        elif parsed.level == "INFO":
                            stats.info_lines += 1
                        elif parsed.level == "DEBUG":
                            stats.debug_lines += 1

                        # Track date range
                        if min_date is None or parsed.timestamp < min_date:
                            min_date = parsed.timestamp
                        if max_date is None or parsed.timestamp > max_date:
                            max_date = parsed.timestamp
            except OSError:
                pass

            stats.files.append(finfo)

        stats.total_sessions = len(all_sessions)
        stats.date_range = (min_date, max_date) if (min_date and max_date) else None
        stats.top_errors = sorted(error_messages.items(), key=lambda x: -x[1])[:20]
        stats.top_modules = sorted(module_counts.items(), key=lambda x: -x[1])[:20]
        return stats

    def extract_errors(self, output_path: Path | None = None) -> int:
        """Extract ERROR+ lines to a separate file. Returns count of errors extracted."""
        out = output_path or (self.log_dir / "errors.log")
        count = 0
        try:
            with open(out, "w", encoding="utf-8") as out_f:
                for path in self.get_log_files():
                    try:
                        with open(path, encoding="utf-8", errors="replace") as f:
                            for raw in f:
                                parsed = self.parse_line(raw)
                                if parsed and parsed.level in ("ERROR", "CRITICAL"):
                                    out_f.write(raw)
                                    count += 1
                    except OSError:
                        continue
        except OSError:
            pass
        return count

    def get_sessions(self) -> list[str]:
        """Get all unique session IDs found in logs, most recent first."""
        sessions: set[str] = set()
        for path in self.get_log_files():
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    for raw in f:
                        parsed = self.parse_line(raw)
                        if parsed and parsed.session_id:
                            sessions.add(parsed.session_id)
            except OSError:
                continue
        return sorted(sessions)

    def prune(
        self,
        max_total_mb: float = 100.0,
        max_age_days: float | None = None,
        keep_rotated: int = 0,
        max_file_mb: float = 5.0,
        dry_run: bool = False,
    ) -> tuple[int, int]:
        """Smart pruning — clean rotated log files, respect age limits, enforce budget.

        Strategy:
        1. Delete rotated files (sago.log.2025-01-14) keeping only `keep_rotated` most recent
        2. Truncate active log files exceeding `max_file_mb` (keep last 50%)
        3. Delete files older than `max_age_days` if specified
        4. If still over `max_total_mb` budget, delete oldest until under

        Returns (files_deleted, bytes_reclaimed).
        """
        files = self.get_log_files()
        now = time.time()
        deleted = 0
        reclaimed = 0

        # Identify the main (active) log file vs rotated backups
        # Active file: sago.log, daemon.log, errors.log (no date suffix)
        # Rotated: sago.log.2025-01-14, sago.log.2.gz, etc.
        import re

        rotated_pattern = re.compile(r"\.log\.\d{4}-\d{2}-\d{2}|\.log\.\d+|\.log\.gz")
        main_files: list[Path] = []
        rotated_files: list[Path] = []

        for path in files:
            if rotated_pattern.search(path.name):
                rotated_files.append(path)
            else:
                main_files.append(path)

        # Sort rotated files newest first
        rotated_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        # Step 1: Delete oldest rotated files, keep only `keep_rotated` most recent
        to_delete_rotated = rotated_files[keep_rotated:]
        for path in to_delete_rotated:
            sz = path.stat().st_size
            if not dry_run:
                path.unlink(missing_ok=True)
            deleted += 1
            reclaimed += sz

        # Recalculate remaining files
        remaining = main_files + rotated_files[:keep_rotated]

        # Step 2: Truncate active log files exceeding max_file_mb (keep last 50%)
        max_file_bytes = int(max_file_mb * 1024 * 1024)
        for path in main_files:
            try:
                sz = path.stat().st_size
                if sz > max_file_bytes:
                    reclaimed_t = sz - (max_file_bytes // 2)
                    if not dry_run:
                        with open(path, "rb") as fp:
                            fp.seek(reclaimed_t)
                            tail = fp.read()
                        with open(path, "wb") as fp:
                            fp.write(tail)
                    deleted += 1
                    reclaimed += reclaimed_t
            except OSError:
                continue

        # Step 3: Delete by age
        if max_age_days is not None:
            cutoff = now - (max_age_days * 86400)
            for path in remaining[:]:
                try:
                    if path.stat().st_mtime <= cutoff:
                        sz = path.stat().st_size
                        if not dry_run:
                            path.unlink(missing_ok=True)
                        deleted += 1
                        reclaimed += sz
                        remaining.remove(path)
                except OSError:
                    continue

        # Step 4: Enforce total size budget
        total = sum(f.stat().st_size for f in remaining if f.is_file())
        max_bytes = int(max_total_mb * 1024 * 1024)
        remaining.sort(key=lambda f: f.stat().st_mtime)
        while total > max_bytes and len(remaining) > 1:
            oldest = remaining.pop(0)
            try:
                sz = oldest.stat().st_size
                if not dry_run:
                    oldest.unlink(missing_ok=True)
                deleted += 1
                reclaimed += sz
                total -= sz
            except OSError:
                continue

        return deleted, reclaimed
