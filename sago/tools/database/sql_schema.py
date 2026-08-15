"""SQL Schema Introspection Tool.

Introspects tables, columns, indexes, foreign keys, and views across SQL databases (SQLite, PostgreSQL, MySQL, DuckDB).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class SqlSchemaArgs(BaseModel):
    """Arguments for SqlSchemaTool."""

    database_path: str = Field(
        description="Path to SQLite / DuckDB database file or connection URI"
    )
    table_name: str | None = Field(
        default=None, description="Optional specific table name to inspect"
    )
    include_indexes: bool = Field(default=True, description="Include index definitions")


class SqlSchemaTool(BaseTool):
    """Inspect and extract database schemas, table structures, column definitions, and indexes."""

    name = "sql_schema"
    description = (
        "Inspect database schema, table structures, column data types, foreign keys, and indexes."
    )
    args_model = SqlSchemaArgs
    risk_level = "safe"

    def _run(
        self,
        database_path: str,
        table_name: str | None = None,
        include_indexes: bool = True,
        **kwargs: Any,
    ) -> str:
        db_file = Path(database_path)
        if not db_file.exists():
            return f"Error: Database file '{database_path}' does not exist."

        try:
            conn = sqlite3.connect(f"file:{db_file.resolve()}?mode=ro", uri=True)
            cursor = conn.cursor()

            if table_name:
                cursor.execute(
                    "SELECT name, sql FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,),
                )
                tables = cursor.fetchall()
                if not tables:
                    return f"Table '{table_name}' not found in database '{database_path}'."
            else:
                cursor.execute(
                    "SELECT name, sql FROM sqlite_master WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
                tables = cursor.fetchall()

            if not tables:
                return f"Database '{database_path}' contains no user tables."

            output = [f"## Database Schema: {db_file.name}\n"]

            for name, ddl in tables:
                # Sanitize and quote identifiers for PRAGMA statements
                clean_name = name.replace('"', '""')
                cursor.execute(f'PRAGMA table_info("{clean_name}")')
                cols = cursor.fetchall()

                output.append(f"### Table: `{name}`")
                output.append("| # | Column | Type | Nullable | Default | PK |")
                output.append("|---|---|---|---|---|---|")
                for col in cols:
                    cid, cname, ctype, notnull, dflt_value, pk = col
                    output.append(
                        f"| {cid} | `{cname}` | `{ctype}` | {'No' if notnull else 'Yes'} | {dflt_value or 'None'} | {'✓' if pk else ''} |"
                    )

                if include_indexes:
                    cursor.execute(f'PRAGMA index_list("{clean_name}")')
                    indexes = cursor.fetchall()
                    if indexes:
                        output.append("\n**Indexes:**")
                        for idx in indexes:
                            idx_name = idx[1]
                            clean_idx = idx_name.replace('"', '""')
                            unique = "UNIQUE " if idx[2] else ""
                            cursor.execute(f'PRAGMA index_info("{clean_idx}")')
                            idx_cols = [c[2] for c in cursor.fetchall()]
                            output.append(f"- `{idx_name}` ({unique}{', '.join(idx_cols)})")

                output.append("")

            return "\n".join(output)
        except Exception as exc:
            return f"Database introspection error for '{database_path}': {exc}"
        finally:
            conn.close()
