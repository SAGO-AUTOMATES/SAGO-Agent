"""Sago Log Viewer — Rich-based interactive log display with dashboard.

Provides formatted log viewing, statistics dashboards, and real-time
follow mode. All output uses Rich for clean terminal rendering.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from sago.log_manager import LogManager, LogStats

logger = logging.getLogger("sago.log_viewer")
console = Console()

# Level color mapping
_LEVEL_COLORS = {
    "DEBUG": "dim",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "bold red",
    "CRITICAL": "bold white on red",
}


def _colorize_level(level: str) -> Text:
    """Return a Rich Text with the level name colorized."""
    style = _LEVEL_COLORS.get(level, "")
    return Text(level, style=style)


def _parse_since(since_str: str) -> float | None:
    """Parse a relative time string like '1h', '30m', '7d', '2w' into a Unix timestamp."""
    if not since_str:
        return None

    since_str = since_str.strip().lower()
    now = time.time()

    multipliers = {
        "m": 60,
        "h": 3600,
        "d": 86400,
        "w": 604800,
    }

    for suffix, mult in multipliers.items():
        if since_str.endswith(suffix):
            try:
                val = float(since_str[:-1])
                return now - (val * mult)
            except ValueError:
                return None

    # Try ISO date format
    try:
        dt = datetime.fromisoformat(since_str)
        return dt.timestamp()
    except ValueError:
        return None


def display_logs(
    manager: LogManager,
    level: str | None = None,
    session_id: str | None = None,
    module: str | None = None,
    search: str | None = None,
    since: str | None = None,
    limit: int = 100,
    errors_only: bool = False,
) -> None:
    """Display filtered log lines in a formatted table."""
    logger.debug(
        "display_logs: level=%s, session_id=%s, module=%s, search=%s, since=%s, limit=%d, errors_only=%s",
        level,
        session_id,
        module,
        search,
        since,
        limit,
        errors_only,
    )
    since_ts = _parse_since(since) if since else None

    all_lines = []
    for path in manager.get_log_files():
        lines = manager.read_lines(
            path,
            level=level,
            session_id=session_id,
            module=module,
            search=search,
            since=since_ts,
            errors_only=errors_only,
        )
        all_lines.extend(lines)

    # Sort by timestamp
    all_lines.sort(key=lambda line: line.timestamp)

    if not all_lines:
        logger.debug("No matching log lines found for query")
        console.print("[dim]No matching log lines found.[/dim]")
        return

    # Apply limit
    if len(all_lines) > limit:
        all_lines = all_lines[-limit:]

    table = Table(
        title=f"Logs ({len(all_lines)} lines)",
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("Time", style="dim", width=19)
    table.add_column("Level", width=10)
    table.add_column("Session", width=12, style="dim")
    table.add_column("Module", width=30)
    table.add_column("Message", ratio=1)

    for line in all_lines:
        table.add_row(
            line.timestamp,
            _colorize_level(line.level),
            line.session_id,
            line.module,
            line.message[:200],  # Truncate very long messages
        )

    console.print(table)


def display_stats(manager: LogManager, quick: bool = False) -> None:
    """Display a rich statistics dashboard."""
    from sago.logging_config import get_log_level

    stats = manager.get_stats(quick=quick)
    current_level = get_log_level().upper()

    # Header panel
    header = Text()
    header.append("Sago Log Dashboard", style="bold cyan")
    header.append(
        f"\n{stats.total_files} files  |  {stats.size_human}  |  {stats.total_lines:,} lines  |  {stats.total_sessions} sessions",
        style="dim",
    )
    header.append("\nLog Level: ", style="dim")
    level_style = {
        "DEBUG": "dim",
        "INFO": "green",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "bold red",
    }.get(current_level, "white")
    header.append(current_level, style=level_style)
    header.append("  (change with: sago logs level --set <level>)", style="dim")
    if stats.date_range:
        header.append(f"\nDate range: {stats.date_range[0]} — {stats.date_range[1]}", style="dim")

    console.print(Panel(header, border_style="cyan"))

    if quick:
        # Just show file listing
        _display_file_list(stats)
        return

    # Level breakdown
    level_table = Table(title="Log Levels", show_header=True, header_style="bold")
    level_table.add_column("Level", style="bold")
    level_table.add_column("Count", justify="right")
    level_table.add_column("%", justify="right")
    level_table.add_column("Bar", ratio=1)

    total_level_lines = (
        stats.debug_lines + stats.info_lines + stats.warning_lines + stats.error_lines
    )
    if total_level_lines > 0:
        for label, count, color in [
            ("DEBUG", stats.debug_lines, "dim"),
            ("INFO", stats.info_lines, "green"),
            ("WARNING", stats.warning_lines, "yellow"),
            ("ERROR", stats.error_lines, "red"),
        ]:
            pct = (count / total_level_lines) * 100
            bar_len = int(pct / 2)
            bar = "█" * bar_len + "░" * (50 - bar_len)
            level_table.add_row(
                Text(label, style=color),
                f"{count:,}",
                f"{pct:.1f}%",
                Text(bar, style=color),
            )

    console.print(level_table)

    # Top modules
    if stats.top_modules:
        mod_table = Table(title="Top Modules", show_header=True, header_style="bold")
        mod_table.add_column("Module", style="bold")
        mod_table.add_column("Lines", justify="right")
        mod_table.add_column("%", justify="right")

        for mod_name, mod_count in stats.top_modules[:10]:
            pct = (mod_count / total_level_lines * 100) if total_level_lines else 0
            mod_table.add_row(mod_name, f"{mod_count:,}", f"{pct:.1f}%")

        console.print(mod_table)

    # Top errors
    if stats.top_errors:
        err_tree = Tree("[bold red]Top Error Messages[/bold red]")
        for err_msg, err_count in stats.top_errors[:10]:
            err_tree.add(f"[red]({err_count}x)[/red] {err_msg[:120]}")
        console.print(Panel(err_tree, border_style="red"))

    # File details
    _display_file_list(stats)


def _display_file_list(stats: LogStats) -> None:
    """Display file listing table."""
    if not stats.files:
        return

    file_table = Table(title="Log Files", show_header=True, header_style="bold")
    file_table.add_column("File", style="bold")
    file_table.add_column("Size", justify="right")
    file_table.add_column("Age", justify="right")
    file_table.add_column("Modified")

    for finfo in sorted(stats.files, key=lambda f: f.modified_time, reverse=True):
        age_str = f"{finfo.age_days:.0f}d" if finfo.age_days >= 1 else f"{finfo.age_days * 24:.0f}h"
        mod_str = datetime.fromtimestamp(finfo.modified_time).strftime("%Y-%m-%d %H:%M")
        file_table.add_row(finfo.path.name, finfo.size_human, age_str, mod_str)

    console.print(file_table)


def display_sessions(manager: LogManager) -> None:
    """Display all session IDs found in logs."""
    sessions = manager.get_sessions()
    if not sessions:
        console.print("[dim]No session IDs found in logs.[/dim]")
        return

    table = Table(title=f"Sessions ({len(sessions)})", show_header=True, header_style="bold")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Session ID", style="bold cyan")

    for i, sid in enumerate(sessions, 1):
        table.add_row(str(i), sid)

    console.print(table)


def follow_logs(manager: LogManager, interval: float = 1.0) -> None:
    """Real-time log following (tail -f style)."""
    import os

    logger.info("Starting real-time log follow mode with interval %.2fs", interval)
    console.print("[bold cyan]Following logs (Ctrl+C to stop)...[/bold cyan]\n")

    log_files = manager.get_log_files()
    if not log_files:
        logger.debug("No log files found to follow")
        console.print("[dim]No log files found.[/dim]")
        return

    # Track file positions
    positions: dict[str, int] = {}
    for f in log_files:
        try:
            positions[str(f)] = os.path.getsize(str(f))
        except OSError:
            positions[str(f)] = 0

    try:
        while True:
            for path in manager.get_log_files():
                pos = positions.get(str(path), 0)
                try:
                    current_size = os.path.getsize(str(path))
                    if current_size > pos:
                        with open(path, encoding="utf-8", errors="replace") as f:
                            f.seek(pos)
                            new_data = f.read()
                            for line in new_data.splitlines():
                                if line.strip():
                                    parsed = manager.parse_line(line)
                                    if parsed:
                                        level_text = _colorize_level(parsed.level)
                                        console.print(
                                            f"[dim]{parsed.timestamp}[/dim] {level_text} "
                                            f"[dim]{parsed.session_id}[/dim] {parsed.module} "
                                            f"{parsed.message[:150]}"
                                        )
                        positions[str(path)] = current_size
                    elif current_size < pos:
                        # File was rotated
                        logger.debug("Detected log rotation for %s, resetting position", path)
                        positions[str(path)] = 0
                except OSError as e:
                    logger.debug("Error reading %s during follow: %s", path, e)
            time.sleep(interval)
    except KeyboardInterrupt:
        logger.info("Log follow mode stopped by user")
        console.print("\n[dim]Stopped following logs.[/dim]")


def export_logs(
    manager: LogManager,
    output_path: str,
    level: str | None = None,
    session_id: str | None = None,
    module: str | None = None,
    search: str | None = None,
    since: str | None = None,
    errors_only: bool = False,
) -> None:
    """Export filtered logs to a file."""
    from pathlib import Path

    since_ts = _parse_since(since) if since else None
    out = Path(output_path)
    logger.info("Exporting logs to %s", out)

    count = 0
    try:
        with open(out, "w", encoding="utf-8") as f:
            for path in manager.get_log_files():
                lines = manager.read_lines(
                    path,
                    level=level,
                    session_id=session_id,
                    module=module,
                    search=search,
                    since=since_ts,
                    errors_only=errors_only,
                )
                for line in lines:
                    f.write(
                        f"{line.timestamp} | {line.level:8s} | {line.session_id} | {line.module} | {line.message}\n"
                    )
                    count += 1
    except OSError as e:
        logger.error("Failed to export logs to %s: %s", out, e)
        raise

    logger.info("Successfully exported %d log lines to %s", count, out)
    console.print(f"[green]Exported {count} log lines to {out}[/green]")
