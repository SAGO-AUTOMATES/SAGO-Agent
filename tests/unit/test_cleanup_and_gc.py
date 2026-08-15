"""Unit tests for Sago Cleanup & Garbage Collection System."""

from __future__ import annotations

import os
import sqlite3
import time

import pytest
from click.testing import CliRunner

from sago.cleanup import (
    CleanResult,
    clean_backups,
    clean_caches,
    clean_checkpoints,
    clean_database,
    clean_logs,
    run_cleanup,
)
from sago.engine.checkpoint import CheckpointManager
from sago.main import cli
from sago.memory.change_tracker import ChangeTracker


@pytest.fixture
def temp_sago_env(tmp_path, monkeypatch):
    """Set up an isolated temporary ~/.sago home directory."""
    sago_home = tmp_path / ".sago"
    sago_home.mkdir(parents=True, exist_ok=True)
    (sago_home / "data").mkdir(parents=True, exist_ok=True)
    (sago_home / "cache" / "hybrid_index").mkdir(parents=True, exist_ok=True)
    (sago_home / "cache" / "project_graphs").mkdir(parents=True, exist_ok=True)
    (sago_home / "backups").mkdir(parents=True, exist_ok=True)
    (sago_home / "logs").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr("sago.paths.get_sago_home", lambda: sago_home)
    monkeypatch.setattr("sago.cleanup.get_sago_home", lambda: sago_home)
    monkeypatch.setattr("sago.paths.get_data_dir", lambda: sago_home / "data")
    monkeypatch.setattr("sago.paths.get_logs_dir", lambda: sago_home / "logs")
    monkeypatch.setattr("sago.cleanup.get_logs_dir", lambda: sago_home / "logs")
    monkeypatch.setattr("sago.paths.get_db_path", lambda: sago_home / "data" / "sago.db")
    monkeypatch.setattr("sago.cleanup.get_db_path", lambda: sago_home / "data" / "sago.db")

    return sago_home


def test_clean_result_human_bytes():
    """Test byte formatting in CleanResult."""
    r1 = CleanResult(category="Test", bytes_reclaimed=500)
    assert r1.human_bytes == "500 B"

    r2 = CleanResult(category="Test", bytes_reclaimed=2048)
    assert "KB" in r2.human_bytes

    r3 = CleanResult(category="Test", bytes_reclaimed=5 * 1024 * 1024)
    assert "MB" in r3.human_bytes

    r4 = CleanResult(category="Test", bytes_reclaimed=2 * 1024 * 1024 * 1024)
    assert "GB" in r4.human_bytes


def test_clean_caches(temp_sago_env):
    """Test purging hybrid index and project graph caches."""
    idx_file = temp_sago_env / "cache" / "hybrid_index" / "idx_test1.json"
    idx_file.write_text('{"terms": 100}', encoding="utf-8")

    graph_file = temp_sago_env / "cache" / "project_graphs" / "graph_test1.json"
    graph_file.write_text('{"nodes": 50}', encoding="utf-8")

    cache_json = temp_sago_env / "cache.json"
    cache_json.write_text('{"entries": []}', encoding="utf-8")

    # Dry-run test
    res_dry = clean_caches(dry_run=True)
    assert res_dry.items_scanned >= 3
    assert res_dry.items_deleted >= 3
    assert idx_file.exists()
    assert graph_file.exists()

    # Actual cleanup
    res = clean_caches(dry_run=False)
    assert res.items_deleted >= 3
    assert res.bytes_reclaimed > 0
    assert not idx_file.exists()
    assert not graph_file.exists()
    assert not cache_json.exists()


def test_clean_backups(temp_sago_env):
    """Test purging old session backups."""
    backups_dir = temp_sago_env / "backups"
    # Create 5 session backup directories
    for i in range(5):
        s_dir = backups_dir / f"session_{i}"
        s_dir.mkdir(parents=True, exist_ok=True)
        (s_dir / f"{i}_app.py.bak").write_text("print('backup')", encoding="utf-8")
        # Artificially shift mtime
        os.utime(s_dir, (time.time() - (5 - i) * 100, time.time() - (5 - i) * 100))

    # Keep newest 2 sessions
    res = clean_backups(dry_run=False, keep_recent_sessions=2)
    assert res.items_scanned == 5
    # 3 old sessions deleted
    remaining = list(backups_dir.iterdir())
    assert len(remaining) == 2


def test_clean_checkpoints(tmp_path):
    """Test pruning workspace snapshots."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    chk_mgr = CheckpointManager(workspace_root=ws)

    # Create dummy source file
    src_file = ws / "main.py"
    src_file.write_text("x = 1", encoding="utf-8")

    # Create 4 checkpoints
    for i in range(4):
        chk_mgr.create_checkpoint(description=f"Snapshot {i}", files=[src_file])
        time.sleep(0.01)

    # Keep newest 2
    res = clean_checkpoints(workspace_root=ws, keep_latest=2, dry_run=False)
    assert res.items_scanned >= 2
    assert res.items_deleted >= 1

    checkpoints_after = chk_mgr.list_checkpoints()
    assert len(checkpoints_after) <= 2


def test_clean_database_empty_and_noise_sessions(temp_sago_env):
    """Test cleaning empty sessions and running VACUUM on sago.db."""
    db_file = temp_sago_env / "data" / "sago.db"
    conn = sqlite3.connect(str(db_file))
    conn.executescript("""
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            title TEXT,
            agent_chain TEXT,
            status TEXT DEFAULT 'active',
            metadata TEXT DEFAULT '{}'
        );
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            parent_task_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            assigned_agent TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            result TEXT,
            context TEXT DEFAULT '{}',
            priority INTEGER DEFAULT 5
        );
        CREATE TABLE messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            task_id TEXT,
            created_at TEXT NOT NULL,
            role TEXT NOT NULL,
            agent_name TEXT,
            content TEXT NOT NULL,
            metadata TEXT DEFAULT '{}'
        );
        CREATE TABLE tool_usage (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            task_id TEXT,
            created_at TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            arguments TEXT,
            result TEXT,
            duration_ms REAL,
            success INTEGER
        );
    """)

    # 1. Valid active session with real conversation
    conn.execute(
        "INSERT INTO sessions (id, created_at, updated_at, title) VALUES ('s_good', '2026-08-16T00:00:00', '2026-08-16T00:00:00', 'Real Session')"
    )
    conn.execute(
        "INSERT INTO messages (id, session_id, created_at, role, content) VALUES ('m1', 's_good', '2026-08-16T00:00:00', 'user', 'Hello assistant!')"
    )

    # 2. Empty session (0 messages)
    conn.execute(
        "INSERT INTO sessions (id, created_at, updated_at, title) VALUES ('s_empty', '2026-08-16T00:00:00', '2026-08-16T00:00:00', 'Empty TUI')"
    )

    # 3. Blank noise session (whitespace only)
    conn.execute(
        "INSERT INTO sessions (id, created_at, updated_at, title) VALUES ('s_blank', '2026-08-16T00:00:00', '2026-08-16T00:00:00', 'Blank Session')"
    )
    conn.execute(
        "INSERT INTO messages (id, session_id, created_at, role, content) VALUES ('m2', 's_blank', '2026-08-16T00:00:00', 'user', '   \n  ')"
    )

    # 4. Orphaned message (references non-existent session)
    conn.execute(
        "INSERT INTO messages (id, session_id, created_at, role, content) VALUES ('m_orphan', 's_nonexistent', '2026-08-16T00:00:00', 'user', 'Orphan')"
    )
    conn.commit()
    conn.close()

    res = clean_database(db_path=db_file, dry_run=False)
    assert res.items_deleted >= 2

    # Verify database state after cleanup
    conn2 = sqlite3.connect(str(db_file))
    cur = conn2.cursor()
    cur.execute("SELECT id FROM sessions")
    remaining_sessions = [r[0] for r in cur.fetchall()]
    assert "s_good" in remaining_sessions
    assert "s_empty" not in remaining_sessions
    assert "s_blank" not in remaining_sessions

    cur.execute("SELECT id FROM messages WHERE id = 'm_orphan'")
    assert cur.fetchone() is None
    conn2.close()


def test_clean_logs(temp_sago_env):
    """Test log rotation and truncation."""
    log_file = temp_sago_env / "daemon.log"
    # Write 6 MB of logs
    chunk = b"A" * (1024 * 1024)
    with open(log_file, "wb") as f:
        for _ in range(6):
            f.write(chunk)

    assert log_file.stat().st_size >= 6 * 1024 * 1024

    res = clean_logs(dry_run=False, max_size_mb=4.0)
    assert res.items_deleted >= 1
    assert res.bytes_reclaimed > 0
    assert log_file.stat().st_size <= 4 * 1024 * 1024


def test_run_cleanup_orchestration(temp_sago_env):
    """Test unified run_cleanup."""
    results = run_cleanup(
        clean_cache=True,
        clean_backup=True,
        clean_chkpt=False,
        clean_db=False,
        clean_log=True,
    )
    assert len(results) == 3
    categories = [r.category for r in results]
    assert any("Caches" in c for c in categories)
    assert any("Backups" in c for c in categories)
    assert any("Logs" in c for c in categories)


def test_cli_clean_command(temp_sago_env):
    """Test click CLI sago clean command."""
    runner = CliRunner()
    res = runner.invoke(cli, ["clean", "--dry-run"])
    assert res.exit_code == 0
    assert "Sago Garbage Collection & Cleanup Summary" in res.output
    assert "Dry-run complete" in res.output


def test_change_tracker_auto_pruning(temp_sago_env, tmp_path):
    """Test ChangeTracker auto-pruning of excessive backups."""
    f = tmp_path / "test_file.txt"
    f.write_text("v0", encoding="utf-8")

    ct = ChangeTracker(session_id="test_session")
    ct._MAX_SESSION_BACKUPS = 5

    for i in range(10):
        old_val = f.read_text(encoding="utf-8")
        f.write_text(f"v{i + 1}", encoding="utf-8")
        ct.track_modify(str(f), old_val, f"v{i + 1}")

    baks = list((temp_sago_env / "backups" / "test_session").glob("*.bak"))
    assert len(baks) <= 5
