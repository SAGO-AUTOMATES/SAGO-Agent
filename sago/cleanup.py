"""Sago Cleanup & Garbage Collection System.

Safely purges regenerable caches, stale workspace checkpoints, unneeded edit backups,
empty/noise database sessions, and oversized logs across ~/.sago and project .sago directories,
while strictly preserving user configuration, credentials, and active data.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sago.paths import get_db_path, get_logs_dir, get_sago_home

logger = logging.getLogger(__name__)

# Essential user configuration files that must NEVER be deleted during cleanup
PRESERVED_USER_FILES = {
    "settings.json",
    "permissions.json",
    "config.yaml",
    "daemon.key",
    "config.sago.json",
    ".sago.yaml",
}


@dataclass
class CleanResult:
    """Result of a specific cleanup phase."""

    category: str
    items_scanned: int = 0
    items_deleted: int = 0
    bytes_reclaimed: int = 0
    details: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def human_bytes(self) -> str:
        """Format reclaimed bytes into human-readable unit."""
        b = self.bytes_reclaimed
        if b < 1024:
            return f"{b} B"
        elif b < 1024 * 1024:
            return f"{b / 1024:.1f} KB"
        elif b < 1024 * 1024 * 1024:
            return f"{b / (1024 * 1024):.2f} MB"
        else:
            return f"{b / (1024 * 1024 * 1024):.2f} GB"


def _get_dir_size_and_count(path: Path) -> tuple[int, int]:
    """Calculate total size in bytes and file count under a directory."""
    if not path.exists():
        return 0, 0
    if path.is_file():
        try:
            return path.stat().st_size, 1
        except OSError:
            return 0, 0

    total_bytes = 0
    total_files = 0
    try:
        for root, _, files in os.walk(path):
            for f in files:
                try:
                    fp = os.path.join(root, f)
                    total_bytes += os.path.getsize(fp)
                    total_files += 1
                except OSError:
                    continue
    except OSError:
        pass
    return total_bytes, total_files


def _force_rmtree(path: Path | str) -> None:
    """Recursively remove a directory tree cross-platform, handling Windows readonly files."""
    import stat

    def _onerror(func, p, exc_info):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass

    try:
        shutil.rmtree(path, onerror=_onerror)
    except Exception:
        try:
            shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass


def clean_caches(
    workspace_root: Path | str | None = None,
    dry_run: bool = False,
    max_age_days: float | None = None,
) -> CleanResult:
    """Purge regenerable index & project graph caches and standalone cache files.

    Cleans:
    - ~/.sago/cache/ (hybrid_index, project_graphs)
    - ~/.sago/codebase_index.json (search index cache)
    - ~/.sago/models.json (cached model catalog)
    - ~/.sago/cache.json
    - <workspace>/.sago/cache/
    - Empty temporary directories in ~/.sago (e.g. empty prompts/, sessions/)
    """
    res = CleanResult(category="Caches (Search Index, AST Graphs & Model Catalog)")
    now = time.time()
    cutoff_ts = (now - max_age_days * 86400) if max_age_days is not None else None

    sago_home = get_sago_home()
    cache_dirs = [
        sago_home / "cache" / "hybrid_index",
        sago_home / "cache" / "project_graphs",
        sago_home / "cache",
    ]

    if workspace_root:
        ws_cache = Path(workspace_root) / ".sago" / "cache"
        if ws_cache.exists():
            cache_dirs.append(ws_cache)

    seen_files: set[Path] = set()

    for cdir in cache_dirs:
        if not cdir.exists():
            continue
        try:
            for item in cdir.rglob("*"):
                if not item.is_file() or item in seen_files:
                    continue
                seen_files.add(item)
                res.items_scanned += 1

                try:
                    stat = item.stat()
                    file_size = stat.st_size
                    mtime = stat.st_mtime
                except OSError:
                    continue

                if cutoff_ts is not None and mtime > cutoff_ts:
                    continue

                if not dry_run:
                    try:
                        item.unlink(missing_ok=True)
                    except OSError as e:
                        logger.debug("Failed to delete cache file %s: %s", item, e)
                        continue

                res.items_deleted += 1
                res.bytes_reclaimed += file_size

            # Clean empty subdirs
            if not dry_run:
                for root, dirs, _ in os.walk(cdir, topdown=False):
                    for d in dirs:
                        dp = Path(root) / d
                        try:
                            if dp.exists() and not any(dp.iterdir()):
                                dp.rmdir()
                        except OSError:
                            pass
        except Exception as e:
            res.error = str(e)
            logger.error("Error during cache cleanup: %s", e)

    # Standalone cache files in ~/.sago/ root (regenerable caches)
    standalone_cache_files = [
        sago_home / "cache.json",
        sago_home / "codebase_index.json",
        sago_home / "models.json",
    ]

    for sc_file in standalone_cache_files:
        if sc_file.is_file():
            res.items_scanned += 1
            try:
                sz = sc_file.stat().st_size
                mtime = sc_file.stat().st_mtime
                if cutoff_ts is None or mtime <= cutoff_ts:
                    if not dry_run:
                        sc_file.unlink(missing_ok=True)
                    res.items_deleted += 1
                    res.bytes_reclaimed += sz
            except OSError:
                pass

    # Clean empty temporary folders in sago home
    if not dry_run:
        for empty_cand in ("prompts", "sessions"):
            d = sago_home / empty_cand
            if d.exists() and d.is_dir():
                try:
                    if not any(d.iterdir()):
                        d.rmdir()
                except OSError:
                    pass

    res.details.append(f"Deleted {res.items_deleted} cache files ({res.human_bytes})")
    return res


def clean_backups(
    dry_run: bool = False,
    max_age_days: float | None = None,
    keep_recent_sessions: int = 1,
) -> CleanResult:
    """Purge stale session edit backups from ~/.sago/backups/.

    Keeps the most recent `keep_recent_sessions` session backups if specified,
    or removes backups older than `max_age_days`.
    """
    res = CleanResult(category="File Edit Backups (~/.sago/backups)")
    backups_root = get_sago_home() / "backups"
    if not backups_root.exists():
        res.details.append("No backup directory found.")
        return res

    now = time.time()
    cutoff_ts = (now - max_age_days * 86400) if max_age_days is not None else None

    try:
        session_dirs = [d for d in backups_root.iterdir() if d.is_dir()]
        session_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        res.items_scanned = len(session_dirs)

        to_delete: list[Path] = []

        if max_age_days is not None and cutoff_ts is not None:
            for sdir in session_dirs:
                if sdir.stat().st_mtime <= cutoff_ts:
                    to_delete.append(sdir)
        else:
            to_delete = session_dirs[keep_recent_sessions:]

        for sdir in to_delete:
            sz, count = _get_dir_size_and_count(sdir)
            if not dry_run:
                try:
                    _force_rmtree(sdir)
                except OSError as e:
                    logger.debug("Failed to remove backup dir %s: %s", sdir, e)
                    continue
            res.items_deleted += count
            res.bytes_reclaimed += sz

        res.details.append(
            f"Removed {len(to_delete)} session directories ({res.items_deleted} files, {res.human_bytes})"
        )
    except Exception as e:
        res.error = str(e)
        logger.error("Error during backup cleanup: %s", e)

    return res


def clean_checkpoints(
    workspace_root: Path | str | None = None,
    keep_latest: int = 3,
    max_age_days: float | None = None,
    dry_run: bool = False,
) -> CleanResult:
    """Purge stale workspace checkpoints (.sago/checkpoints/).

    Keeps the most recent `keep_latest` snapshots and purges older ones.
    """
    res = CleanResult(category="Workspace Checkpoints (.sago/checkpoints)")
    root = Path(workspace_root) if workspace_root else Path.cwd()
    candidate_dirs = [
        root / ".sago" / "checkpoints",
        get_sago_home() / "checkpoints",
    ]

    seen_dirs: set[Path] = set()
    now = time.time()
    cutoff_ts = (now - max_age_days * 86400) if max_age_days is not None else None

    total_scanned = 0
    total_purged = 0

    for chk_dir in candidate_dirs:
        if not chk_dir.exists() or chk_dir in seen_dirs:
            continue
        seen_dirs.add(chk_dir)

        try:
            snapshots = [d for d in chk_dir.iterdir() if d.is_dir()]
            snapshots.sort(key=lambda p: p.name, reverse=True)
            total_scanned += len(snapshots)

            to_delete: list[Path] = []
            if max_age_days is not None and cutoff_ts is not None:
                for snap in snapshots:
                    if snap.stat().st_mtime <= cutoff_ts:
                        to_delete.append(snap)
            else:
                to_delete = snapshots[keep_latest:]

            for snap in to_delete:
                sz, count = _get_dir_size_and_count(snap)
                if not dry_run:
                    try:
                        _force_rmtree(snap)
                    except OSError as e:
                        logger.debug("Failed to remove snapshot %s: %s", snap, e)
                        continue
                res.items_deleted += 1
                res.bytes_reclaimed += sz
                total_purged += 1
        except Exception as e:
            res.error = str(e)
            logger.error("Error during checkpoint cleanup in %s: %s", chk_dir, e)

    res.items_scanned = total_scanned
    if total_scanned == 0:
        res.details.append("No checkpoint directories found.")
    else:
        res.details.append(
            f"Purged {total_purged} checkpoints across {len(seen_dirs)} locations, kept newest {total_scanned - total_purged} ({res.human_bytes} reclaimed)"
        )

    return res


def clean_plans(dry_run: bool = False) -> CleanResult:
    """Clean completed / stale task plans from ~/.sago/task_plans.json."""
    res = CleanResult(category="Task Plans (~/.sago/task_plans.json)")
    plans_file = get_sago_home() / "task_plans.json"
    if not plans_file.exists():
        res.details.append("No task plans file found.")
        return res

    try:
        sz_before = plans_file.stat().st_size
        res.items_scanned = 1
        with open(plans_file, encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            # Prune plans that are completed or empty
            active_plans = {}
            for pid, plan in data.items():
                if isinstance(plan, dict):
                    status = plan.get("status", "")
                    todos = plan.get("todos", [])
                    # Keep only actively pending/in_progress plans with uncompleted todos
                    is_done = status == "completed" or (
                        todos and all(t.get("status") == "completed" for t in todos)
                    )
                    if not is_done:
                        active_plans[pid] = plan
            pruned_count = len(data) - len(active_plans)

            if not dry_run:
                with open(plans_file, "w", encoding="utf-8") as f:
                    json.dump(active_plans, f, indent=2)
                sz_after = plans_file.stat().st_size
                res.bytes_reclaimed = max(0, sz_before - sz_after)
            res.items_deleted = pruned_count
            res.details.append(
                f"Pruned {pruned_count} completed task plans ({res.human_bytes} reclaimed)"
            )
    except Exception as e:
        res.error = str(e)
        logger.error("Error cleaning task plans: %s", e)

    return res


def clean_database(
    db_path: Path | None = None,
    dry_run: bool = False,
    remove_empty_only: bool = False,
    keep_recent_sessions: int = 10,
    max_age_days: float | None = None,
    min_session_age_days: float = 7.0,  # Only delete sessions older than this
) -> CleanResult:
    """Clean empty and stale test sessions from ~/.sago/data/sago.db and VACUUM.

    Finds and removes:
    1. Empty sessions (0 messages or all blank content) older than min_session_age_days
    2. Abandoned test runs (generic 'Session <hex>' or 'Test...' titles with <= 2 messages)
       only if older than min_session_age_days and beyond keep_recent
    3. Stale sessions older than max_age_days or beyond keep_recent_sessions
    4. Orphaned records referencing non-existent sessions
    5. Runs VACUUM and PRAGMA optimize to defragment SQLite and reclaim physical disk space.

    Safety: By default, only sessions older than min_session_age_days (7 days) are considered
    for deletion. Set min_session_age_days=0 to disable this safety check.
    """
    res = CleanResult(category="Database Sessions & Integrity (sago.db)")
    target_db = db_path or get_db_path()

    if not target_db.exists():
        res.details.append("Database file not found.")
        return res

    size_before = target_db.stat().st_size

    # Calculate cutoff timestamp for minimum session age
    min_age_cutoff = (
        datetime.fromtimestamp(time.time() - min_session_age_days * 86400, tz=UTC).isoformat()
        if min_session_age_days > 0
        else None
    )

    try:
        conn = sqlite3.connect(str(target_db), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        cur = conn.cursor()

        # 1. Total sessions
        cur.execute("SELECT COUNT(*) FROM sessions")
        total_sessions = cur.fetchone()[0]
        res.items_scanned = total_sessions

        # 2. Empty / ghost sessions (no valid messages and no tasks) - only old ones
        if min_age_cutoff:
            cur.execute(
                """
                SELECT s.id FROM sessions s
                WHERE (
                    SELECT COUNT(*) FROM messages m
                    WHERE m.session_id = s.id
                    AND TRIM(m.content, ' ' || CHAR(9) || CHAR(10) || CHAR(13)) != ''
                ) = 0
                AND (
                    SELECT COUNT(*) FROM tasks t
                    WHERE t.session_id = s.id
                ) = 0
                AND s.created_at < ?
            """,
                (min_age_cutoff,),
            )
        else:
            cur.execute("""
                SELECT s.id FROM sessions s
                WHERE (
                    SELECT COUNT(*) FROM messages m
                    WHERE m.session_id = s.id
                    AND TRIM(m.content, ' ' || CHAR(9) || CHAR(10) || CHAR(13)) != ''
                ) = 0
                AND (
                    SELECT COUNT(*) FROM tasks t
                    WHERE t.session_id = s.id
                ) = 0
            """)
        empty_session_ids = [row[0] for row in cur.fetchall()]

        # 3. Abandoned / test sessions and stale sessions beyond retention
        stale_session_ids: list[str] = []
        if not remove_empty_only:
            # Fetch all sessions ordered by updated_at / created_at desc
            cur.execute("""
                SELECT s.id, s.title, s.created_at, s.updated_at,
                       (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) as msg_count
                FROM sessions s
                ORDER BY s.created_at DESC
            """)
            all_rows = cur.fetchall()

            # Identify sessions eligible for pruning beyond keep_recent_sessions
            for idx, r in enumerate(all_rows):
                sid = r[0]
                title = (r[1] or "").lower()
                msg_count = r[4]
                created_at = r[2]
                updated_at = r[3]

                # Skip recent sessions (within min_session_age_days)
                if min_age_cutoff and created_at and created_at >= min_age_cutoff:
                    continue
                if min_age_cutoff and updated_at and updated_at >= min_age_cutoff:
                    continue

                # If beyond the recent sessions threshold
                if idx >= keep_recent_sessions:
                    # Only mark as stale if it's actually old
                    if not min_age_cutoff or (created_at and created_at < min_age_cutoff):
                        stale_session_ids.append(sid)
                elif (
                    msg_count <= 2
                    and (
                        title.startswith("session ")
                        or "test" in title
                        or title in ("tui session", "chat session", "")
                    )
                    and idx >= 3
                ):
                    # Minor test/abandoned sessions kept only if in top 3 and old enough
                    if not min_age_cutoff or (created_at and created_at < min_age_cutoff):
                        stale_session_ids.append(sid)

        if max_age_days is not None:
            cutoff_iso = datetime.fromtimestamp(
                time.time() - max_age_days * 86400, tz=UTC
            ).isoformat()
            cur.execute("SELECT id FROM sessions WHERE created_at < ?", (cutoff_iso,))
            for row in cur.fetchall():
                stale_session_ids.append(row[0])

        all_target_ids = list(set(empty_session_ids + stale_session_ids))

        # 4. Find orphaned records across secondary tables
        cur.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id NOT IN (SELECT id FROM sessions)"
        )
        orphaned_msgs = cur.fetchone()[0]

        cur.execute(
            "SELECT COUNT(*) FROM tool_usage WHERE session_id NOT IN (SELECT id FROM sessions)"
        )
        orphaned_tools = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM tasks WHERE session_id NOT IN (SELECT id FROM sessions)")
        orphaned_tasks = cur.fetchone()[0]

        orphaned_total = orphaned_msgs + orphaned_tools + orphaned_tasks

        if not dry_run:
            if all_target_ids:
                placeholders = ",".join("?" * len(all_target_ids))
                cur.execute(f"DELETE FROM sessions WHERE id IN ({placeholders})", all_target_ids)

            if orphaned_msgs > 0:
                cur.execute(
                    "DELETE FROM messages WHERE session_id NOT IN (SELECT id FROM sessions)"
                )
            if orphaned_tools > 0:
                cur.execute(
                    "DELETE FROM tool_usage WHERE session_id NOT IN (SELECT id FROM sessions)"
                )
            if orphaned_tasks > 0:
                cur.execute("DELETE FROM tasks WHERE session_id NOT IN (SELECT id FROM sessions)")

            conn.commit()
            conn.execute("VACUUM")
            conn.execute("PRAGMA optimize")
            conn.close()

            size_after = target_db.stat().st_size
            res.bytes_reclaimed = max(0, size_before - size_after)
        else:
            conn.close()

        res.items_deleted = len(all_target_ids) + orphaned_total
        res.details.append(
            f"Pruned {len(all_target_ids)} empty/stale sessions (retained top {min(keep_recent_sessions, total_sessions - len(all_target_ids))}), {orphaned_total} orphaned records ({res.human_bytes} reclaimed)"
        )
        if dry_run:
            res.details.append("DRY RUN - no changes made")
    except Exception as e:
        res.error = str(e)
        logger.error("Error during database cleanup: %s", e)

    return res


def clean_logs(
    workspace_root: Path | str | None = None,
    dry_run: bool = False,
    max_age_days: float | None = None,
    max_size_mb: float = 5.0,
) -> CleanResult:
    """Clean / rotate oversized and old logs in ~/.sago/logs and project logs."""
    res = CleanResult(category="Logs & Daemon Traces")
    log_files: list[Path] = []

    # Home daemon log
    daemon_log = get_sago_home() / "daemon.log"
    if daemon_log.exists():
        log_files.append(daemon_log)

    # Home logs dir
    logs_dir = get_logs_dir()
    if logs_dir.exists():
        log_files.extend([f for f in logs_dir.glob("*.log") if f.is_file()])

    # Project logs dir
    if workspace_root:
        proj_logs = Path(workspace_root) / ".sago" / "logs"
        if proj_logs.exists():
            log_files.extend([f for f in proj_logs.glob("*.log") if f.is_file()])

    now = time.time()
    cutoff_ts = (now - max_age_days * 86400) if max_age_days is not None else None
    max_bytes = int(max_size_mb * 1024 * 1024)

    for lf in log_files:
        res.items_scanned += 1
        try:
            stat = lf.stat()
            sz = stat.st_size
            mtime = stat.st_mtime

            # Delete if older than cutoff
            if cutoff_ts is not None and mtime <= cutoff_ts:
                if not dry_run:
                    lf.unlink(missing_ok=True)
                res.items_deleted += 1
                res.bytes_reclaimed += sz
                continue

            # Truncate if larger than max_size_mb
            if sz > max_bytes:
                reclaimed = sz - (max_bytes // 2)
                if not dry_run:
                    try:
                        with open(lf, "rb") as fp:
                            fp.seek(reclaimed)
                            tail = fp.read()
                        with open(lf, "wb") as fp:
                            fp.write(tail)
                    except OSError:
                        pass
                res.items_deleted += 1
                res.bytes_reclaimed += reclaimed
        except OSError:
            continue

    res.details.append(f"Cleaned {res.items_deleted} log files ({res.human_bytes} reclaimed)")
    return res


def run_cleanup(
    workspace_root: Path | str | None = None,
    clean_cache: bool = True,
    clean_backup: bool = True,
    clean_chkpt: bool = True,
    clean_plan: bool = True,
    clean_db: bool = True,
    clean_log: bool = True,
    keep_checkpoints: int = 3,
    keep_recent_backups: int = 1,
    keep_recent_sessions: int = 10,
    max_age_days: float | None = None,
    dry_run: bool = False,
) -> list[CleanResult]:
    """Run selected cleanup routines and return the summary results."""
    results: list[CleanResult] = []

    if clean_cache:
        results.append(
            clean_caches(
                workspace_root=workspace_root,
                dry_run=dry_run,
                max_age_days=max_age_days,
            )
        )

    if clean_backup:
        results.append(
            clean_backups(
                dry_run=dry_run,
                max_age_days=max_age_days,
                keep_recent_sessions=keep_recent_backups,
            )
        )

    if clean_chkpt:
        results.append(
            clean_checkpoints(
                workspace_root=workspace_root,
                keep_latest=keep_checkpoints,
                max_age_days=max_age_days,
                dry_run=dry_run,
            )
        )

    if clean_plan:
        results.append(clean_plans(dry_run=dry_run))

    if clean_db:
        results.append(
            clean_database(
                dry_run=dry_run,
                remove_empty_only=False,
                keep_recent_sessions=keep_recent_sessions,
                max_age_days=max_age_days,
            )
        )

    if clean_log:
        results.append(
            clean_logs(
                workspace_root=workspace_root,
                dry_run=dry_run,
                max_age_days=max_age_days,
            )
        )

    return results
