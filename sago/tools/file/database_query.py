"""Database Query Tool - Execute SQL queries on SQLite/PostgreSQL/MySQL."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool

# SQL injection prevention: only allow SELECT statements for queries
_READ_ONLY_KEYWORDS = {
    "DROP",
    "DELETE",
    "UPDATE",
    "INSERT",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "EXEC",
    "EXECUTE",
    "GRANT",
    "REVOKE",
}


def _validate_query(query: str) -> str | None:
    """Validate SQL query for safety. Returns error message or None if safe."""
    query_upper = query.upper().strip()
    # Check for dangerous keywords
    for keyword in _READ_ONLY_KEYWORDS:
        # Match as whole word
        if re.search(r"\b" + keyword + r"\b", query_upper):
            return (
                f"Security: '{keyword}' operation not allowed. Only SELECT queries are permitted."
            )
    return None


class DatabaseQueryArgs(BaseModel):
    """Arguments for database operations."""

    operation: str = Field(description="Operation: query, tables, schema, export")
    connection: str = Field(description="Database connection string or file path")
    query: str = Field(default="", description="SQL query to execute")
    output_format: str = Field(default="table", description="Output format: table, csv, json")
    db_type: str = Field(default="auto", description="Database type: auto, sqlite, postgres, mysql")


class DatabaseQuery(BaseTool):
    """Tool for executing SQL queries on SQLite/PostgreSQL/MySQL databases."""

    name: str = "database_query"
    description: str = (
        "Execute SQL queries on SQLite/PostgreSQL/MySQL databases. "
        "Supports query, tables, schema, export operations. "
        "Only SELECT queries are permitted (no DELETE/DROP/INSERT/UPDATE)."
    )
    args_model: type[BaseModel] = DatabaseQueryArgs

    def _run(
        self,
        operation: str,
        connection: str,
        query: str = "",
        output_format: str = "table",
        db_type: str = "auto",
        **kwargs: Any,
    ) -> str:
        """Execute database operation."""
        try:
            # Auto-detect database type
            if db_type == "auto":
                db_type = self._detect_db_type(connection)

            if db_type == "sqlite":
                return self._run_sqlite(operation, connection, query, output_format)
            elif db_type == "postgres":
                return self._run_postgres(operation, connection, query, output_format)
            elif db_type == "mysql":
                return self._run_mysql(operation, connection, query, output_format)
            else:
                return f"Error: Unsupported database type '{db_type}'. Use: sqlite, postgres, mysql"
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"

    def _detect_db_type(self, connection: str) -> str:
        """Auto-detect database type from connection string."""
        conn_lower = connection.lower()
        if conn_lower.startswith("postgresql://") or conn_lower.startswith("postgres://"):
            return "postgres"
        elif conn_lower.startswith("mysql://") or conn_lower.startswith("mariadb://"):
            return "mysql"
        elif ".db" in conn_lower or ".sqlite" in conn_lower or "/" not in conn_lower:
            return "sqlite"
        return "sqlite"

    def _run_sqlite(self, operation: str, connection: str, query: str, output_format: str) -> str:
        """Execute operation on SQLite database."""
        import json
        import sqlite3

        conn_path = self._expand_path(connection)

        if not conn_path.exists() and operation not in ("query",):
            return f"Error: Database not found: {connection}"

        conn = sqlite3.connect(str(conn_path))
        cursor = conn.cursor()

        try:
            if operation == "tables":
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
                tables = [row[0] for row in cursor.fetchall()]
                return f"Tables ({len(tables)}):\n" + "\n".join(f"  - {t}" for t in tables)

            elif operation == "schema":
                cursor.execute(
                    "SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name"
                )
                schemas = []
                for name, sql in cursor.fetchall():
                    schemas.append(f"-- {name}\n{sql}")
                return "\n\n".join(schemas)

            elif operation in ("query", "export"):
                if not query:
                    return "Error: query parameter required"

                error = _validate_query(query)
                if error:
                    return error

                cursor.execute(query)
                columns = [desc[0] for desc in cursor.description or []]
                rows = cursor.fetchall()

                if output_format == "json" or operation == "export":
                    result = [dict(zip(columns, row)) for row in rows]
                    return json.dumps(result, indent=2, default=str)[:5000]
                elif output_format == "csv":
                    lines = [",".join(columns)]
                    for row in rows:
                        lines.append(",".join(str(v) for v in row))
                    return "\n".join(lines)[:5000]
                else:
                    return self._format_table(columns, rows)

            else:
                return f"Error: Invalid operation '{operation}'. Valid: query, tables, schema, export"

        finally:
            conn.close()

    def _run_postgres(self, operation: str, connection: str, query: str, output_format: str) -> str:
        """Execute operation on PostgreSQL database."""
        try:
            import json

            import psycopg2
        except ImportError:
            return "Error: psycopg2 not installed. Run: pip install psycopg2-binary"

        try:
            conn = psycopg2.connect(connection)
            cursor = conn.cursor()

            try:
                if operation == "tables":
                    cursor.execute(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = 'public' ORDER BY table_name"
                    )
                    tables = [row[0] for row in cursor.fetchall()]
                    return f"Tables ({len(tables)}):\n" + "\n".join(f"  - {t}" for t in tables)

                elif operation == "schema":
                    cursor.execute(
                        "SELECT table_name, column_name, data_type "
                        "FROM information_schema.columns "
                        "WHERE table_schema = 'public' "
                        "ORDER BY table_name, ordinal_position"
                    )
                    schemas: dict[str, list[str]] = {}
                    for table, col, dtype in cursor.fetchall():
                        if table not in schemas:
                            schemas[table] = []
                        schemas[table].append(f"  {col} {dtype}")
                    parts = []
                    for table, cols in schemas.items():
                        parts.append(f"-- {table}\n" + "\n".join(cols))
                    return "\n\n".join(parts)

                elif operation in ("query", "export"):
                    if not query:
                        return "Error: query parameter required"
                    error = _validate_query(query)
                    if error:
                        return error

                    cursor.execute(query)
                    columns = [desc[0] for desc in cursor.description]
                    rows = cursor.fetchall()

                    if output_format == "json" or operation == "export":
                        result = [dict(zip(columns, row)) for row in rows]
                        return json.dumps(result, indent=2, default=str)[:5000]
                    elif output_format == "csv":
                        lines = [",".join(columns)]
                        for row in rows:
                            lines.append(",".join(str(v) for v in row))
                        return "\n".join(lines)[:5000]
                    else:
                        return self._format_table(columns, rows)

                else:
                    return f"Error: Invalid operation '{operation}'"

            finally:
                cursor.close()
                conn.close()

        except Exception as e:
            return f"PostgreSQL error: {e}"

    def _run_mysql(self, operation: str, connection: str, query: str, output_format: str) -> str:
        """Execute operation on MySQL database."""
        try:
            import mysql.connector
        except ImportError:
            return "Error: mysql-connector-python not installed. Run: pip install mysql-connector-python"

        try:
            # Parse connection string
            import urllib.parse

            parsed = urllib.parse.urlparse(connection)
            conn_params = {
                "host": parsed.hostname or "localhost",
                "port": parsed.port or 3306,
                "user": parsed.username or "root",
                "password": parsed.password or "",
                "database": parsed.path.lstrip("/") if parsed.path else None,
            }

            conn = mysql.connector.connect(**conn_params)
            cursor = conn.cursor()

            try:
                if operation == "tables":
                    cursor.execute("SHOW TABLES")
                    tables = [row[0] for row in cursor.fetchall()]
                    return f"Tables ({len(tables)}):\n" + "\n".join(f"  - {t}" for t in tables)

                elif operation == "schema":
                    cursor.execute("SHOW TABLES")
                    tables = [row[0] for row in cursor.fetchall()]
                    schemas = []
                    for table in tables:
                        cursor.execute(f"DESCRIBE `{table}`")
                        cols = [f"  {row[0]} {row[1]}" for row in cursor.fetchall()]
                        schemas.append(f"-- {table}\n" + "\n".join(cols))
                    return "\n\n".join(schemas)

                elif operation in ("query", "export"):
                    if not query:
                        return "Error: query parameter required"
                    error = _validate_query(query)
                    if error:
                        return error

                    cursor.execute(query)
                    columns = [desc[0] for desc in cursor.description]
                    rows = cursor.fetchall()

                    import json

                    if output_format == "json" or operation == "export":
                        result = [dict(zip(columns, row)) for row in rows]
                        return json.dumps(result, indent=2, default=str)[:5000]
                    elif output_format == "csv":
                        lines = [",".join(columns)]
                        for row in rows:
                            lines.append(",".join(str(v) for v in row))
                        return "\n".join(lines)[:5000]
                    else:
                        return self._format_table(columns, rows)

                else:
                    return f"Error: Invalid operation '{operation}'"

            finally:
                cursor.close()
                conn.close()

        except Exception as e:
            return f"MySQL error: {e}"

    def _format_table(self, columns: list[str], rows: list[tuple]) -> str:
        """Format query results as a text table."""
        if not rows:
            return "No results"

        widths = [len(c) for c in columns]
        for row in rows:
            for i, val in enumerate(row):
                if i < len(widths):
                    widths[i] = max(widths[i], len(str(val)[:50]))

        header = " | ".join(c.ljust(widths[i]) for i, c in enumerate(columns))
        separator = "-+-".join("-" * w for w in widths)
        lines = [header, separator]
        for row in rows[:100]:
            line = " | ".join(
                str(val)[:50].ljust(widths[i]) for i, val in enumerate(row) if i < len(widths)
            )
            lines.append(line)

        if len(rows) > 100:
            lines.append(f"... ({len(rows) - 100} more rows)")

        return "\n".join(lines)


def get_tool() -> type[DatabaseQuery]:
    """Get the tool class."""
    return DatabaseQuery
