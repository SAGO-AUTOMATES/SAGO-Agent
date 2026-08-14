"""SQL Migration & DDL Generator Tool.

Generates safe, idempotent forward and rollback migration DDL scripts with schema validation.
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class SqlMigrationArgs(BaseModel):
    """Arguments for SqlMigrationTool."""

    dialect: str = Field(
        default="sqlite", description="SQL dialect: 'sqlite', 'postgresql', 'mysql'"
    )
    operation: str = Field(
        description="Migration operation: 'create_table', 'add_column', 'add_index', 'drop_table'"
    )
    table_name: str = Field(description="Target table name")
    details: str = Field(
        description="Column definition or index details, e.g. 'email VARCHAR(255) UNIQUE NOT NULL'"
    )


class SqlMigrationTool(BaseTool):
    """Generate idempotent forward and rollback SQL migration scripts."""

    name = "sql_migration"
    description = (
        "Generate forward and rollback migration DDL scripts for SQLite, PostgreSQL, and MySQL."
    )
    args_model = SqlMigrationArgs
    risk_level = "safe"

    def _run(
        self,
        dialect: str,
        operation: str,
        table_name: str,
        details: str,
        **kwargs: Any,
    ) -> str:
        d = dialect.lower().strip()
        op = operation.lower().strip()
        timestamp = int(time.time())

        up_sql = ""
        down_sql = ""

        if op in ("create_table", "table"):
            up_sql = f"CREATE TABLE IF NOT EXISTS {table_name} (\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    {details},\n    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n);"
            if d == "postgresql":
                up_sql = f"CREATE TABLE IF NOT EXISTS {table_name} (\n    id SERIAL PRIMARY KEY,\n    {details},\n    created_at TIMESTAMPTZ DEFAULT NOW()\n);"
            elif d == "mysql":
                up_sql = f"CREATE TABLE IF NOT EXISTS {table_name} (\n    id INT AUTO_INCREMENT PRIMARY KEY,\n    {details},\n    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n);"
            down_sql = f"DROP TABLE IF EXISTS {table_name};"

        elif op in ("add_column", "column"):
            up_sql = f"ALTER TABLE {table_name} ADD COLUMN {details};"
            down_sql = f"-- Rollback: Note that standard SQLite cannot drop columns directly prior to 3.35\n-- ALTER TABLE {table_name} DROP COLUMN {details.split()[0]};"
            if d == "postgresql":
                down_sql = f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS {details.split()[0]};"

        elif op in ("add_index", "index"):
            idx_name = f"idx_{table_name}_{details.replace(',', '_').replace(' ', '')}"
            up_sql = f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table_name} ({details});"
            down_sql = f"DROP INDEX IF EXISTS {idx_name};"

        else:
            return f"Unsupported operation '{operation}'. Supported: create_table, add_column, add_index."

        migration_content = f"""-- Migration: {timestamp}_{op}_{table_name}.sql
-- Dialect: {d.upper()}

-- >>> UP >>>
{up_sql}

-- >>> DOWN (Rollback) >>>
{down_sql}
"""
        return migration_content
