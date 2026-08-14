"""Unit tests for SQL schema, migration, and platform diagnostics tools."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from sago.tools.database.sql_migration import SqlMigrationTool
from sago.tools.database.sql_schema import SqlSchemaTool
from sago.tools.system.platform_diagnostics import PlatformDiagnosticsTool


def test_sql_schema_tool_introspection():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT NOT NULL, age INT);")
        cursor.execute("CREATE INDEX idx_users_email ON users(email);")
        conn.commit()
        conn.close()

        tool = SqlSchemaTool()
        res = tool.run(database_path=db_path)
        assert "users" in res
        assert "email" in res
        assert "idx_users_email" in res
    finally:
        Path(db_path).unlink(missing_ok=True)


def test_sql_migration_tool():
    tool = SqlMigrationTool()
    res = tool.run(
        dialect="postgresql",
        operation="create_table",
        table_name="orders",
        details="user_id INT REFERENCES users(id), amount NUMERIC(10,2)",
    )
    assert "CREATE TABLE IF NOT EXISTS orders" in res
    assert "DROP TABLE IF EXISTS orders" in res


def test_platform_diagnostics_tool():
    tool = PlatformDiagnosticsTool()
    res = tool.run()
    assert "OS / Kernel" in res
    assert "Python" in res
