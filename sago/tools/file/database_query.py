"""Database Query Tool - Execute SQL queries."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class DatabaseQueryArgs(BaseModel):
    """Arguments for database operations."""

    operation: str = Field(description="Operation: query, tables, schema, export")
    connection: str = Field(description="Database connection string or path")
    query: str = Field(default="", description="SQL query to execute")
    output_format: str = Field(default="table", description="Output format: table, csv, json")


class DatabaseQuery(BaseTool):
    """Tool for executing SQL queries on databases."""

    name: str = "database_query"
    description: str = (
        "Execute SQL queries on SQLite/PostgreSQL/MySQL databases. "
        "Supports query, tables, schema, export operations."
    )
    args_model: type[BaseModel] = DatabaseQueryArgs

    def _run(
        self,
        operation: str,
        connection: str,
        query: str = "",
        output_format: str = "table",
        **kwargs: Any,
    ) -> str:
        """Execute database operation."""
        try:
            import sqlite3

            # For SQLite, connection is a file path
            conn_path = self._expand_path(connection)

            if not conn_path.exists() and operation != "query":
                return f"Error: Database not found: {connection}"

            conn = sqlite3.connect(str(conn_path))
            cursor = conn.cursor()

            try:
                if operation == "tables":
                    cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                    )
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

                elif operation == "query":
                    if not query:
                        return "Error: query parameter required"

                    cursor.execute(query)
                    columns = [desc[0] for desc in cursor.description or []]
                    rows = cursor.fetchall()

                    if output_format == "json":
                        import json
                        result = [dict(zip(columns, row)) for row in rows]
                        return json.dumps(result, indent=2, default=str)[:5000]

                    elif output_format == "csv":
                        lines = [",".join(columns)]
                        for row in rows:
                            lines.append(",".join(str(v) for v in row))
                        return "\n".join(lines)[:5000]

                    else:  # table format
                        if not rows:
                            return "No results"

                        # Calculate column widths
                        widths = [len(c) for c in columns]
                        for row in rows:
                            for i, val in enumerate(row):
                                widths[i] = max(widths[i], len(str(val)[:50]))

                        # Format table
                        header = " | ".join(c.ljust(widths[i]) for i, c in enumerate(columns))
                        separator = "-+-".join("-" * w for w in widths)
                        lines = [header, separator]
                        for row in rows[:100]:  # Limit rows
                            line = " | ".join(
                                str(val)[:50].ljust(widths[i])
                                for i, val in enumerate(row)
                            )
                            lines.append(line)

                        if len(rows) > 100:
                            lines.append(f"... ({len(rows) - 100} more rows)")

                        return "\n".join(lines)

                elif operation == "export":
                    if not query:
                        return "Error: query parameter required"

                    cursor.execute(query)
                    columns = [desc[0] for desc in cursor.description or []]
                    rows = cursor.fetchall()

                    import json
                    result = [dict(zip(columns, row)) for row in rows]
                    return json.dumps(result, indent=2, default=str)[:5000]

                else:
                    return f"Error: Invalid operation '{operation}'. Valid: query, tables, schema, export"

            finally:
                conn.close()

        except sqlite3.Error as e:
            return f"SQLite error: {e}"
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"


def get_tool() -> type[DatabaseQuery]:
    """Get the tool class."""
    return DatabaseQuery
