# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""
Vambery AI Agent Database Tools.

These tools allow the AI agent to introspect database schemas and execute
SQL queries during its reasoning process.
Uses Superset's Database model for all database operations, respecting
security permissions and row-level security.
"""

from __future__ import annotations

import logging
from typing import Any

from superset.extensions import db
from superset.models.core import Database
from superset.sql.parse import Table

logger = logging.getLogger(__name__)


def _extract_result_data(result: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Extract rows (as list of dicts) and column names from a QueryResult.

    The QueryResult from database.execute() stores results in
    result.statements[i].data as a Pandas DataFrame.
    """
    rows: list[dict[str, Any]] = []
    columns: list[str] = []
    try:
        if hasattr(result, "statements") and result.statements:
            stmt = result.statements[0]
            df = stmt.data
            if df is not None and hasattr(df, "to_dict"):
                # Pandas DataFrame
                rows = df.to_dict(orient="records")
                columns = list(df.columns)
            elif df is not None and hasattr(df, "keys"):
                # dict-like
                rows = [df] if not isinstance(df, list) else df
                columns = list(df.keys()) if isinstance(df, dict) else []
    except Exception as ex:
        logger.debug("Could not extract result data: %s", ex)

    # Fallback: legacy result format
    if not rows:
        if hasattr(result, "data") and result.data:
            rows = result.data if isinstance(result.data, list) else []
        elif hasattr(result, "rows") and hasattr(result, "columns"):
            columns = result.columns
            rows = [dict(zip(columns, row, strict=False)) for row in result.rows]

    return rows, columns


# --------------------------------------------------------------------------
# OpenAI function/tool definitions (sent to the LLM)
# --------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_schemas",
            "description": (
                "List all available schemas in the connected database. "
                "Use this first to understand the database structure."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tables",
            "description": (
                "List all tables in a specific schema. "
                "Use this to discover which tables are available."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "schema_name": {
                        "type": "string",
                        "description": "The schema name to list tables from",
                    },
                },
                "required": ["schema_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_table_columns",
            "description": (
                "Get the column names, data types, and nullable info for a table. "
                "Use this to understand the structure of a table before writing queries."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Name of the table",
                    },
                    "schema_name": {
                        "type": "string",
                        "description": "Schema the table belongs to",
                    },
                },
                "required": ["table_name", "schema_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sample_table_data",
            "description": (
                "Get a sample of rows from a table (up to 20 rows). "
                "Use this to understand what kind of data a table contains."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Name of the table",
                    },
                    "schema_name": {
                        "type": "string",
                        "description": "Schema the table belongs to",
                    },
                },
                "required": ["table_name", "schema_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_distinct_values",
            "description": (
                "Get distinct/unique values for a specific column in a table. "
                "Use this to understand the domain of a column (e.g., categories, statuses)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Name of the table",
                    },
                    "schema_name": {
                        "type": "string",
                        "description": "Schema the table belongs to",
                    },
                    "column_name": {
                        "type": "string",
                        "description": "Name of the column to get distinct values for",
                    },
                },
                "required": ["table_name", "schema_name", "column_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_sql",
            "description": (
                "Execute an arbitrary SQL SELECT query and return results (max 50 rows). "
                "Use this to test queries, explore data, or verify results. "
                "Only SELECT statements are allowed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "The SQL SELECT query to execute",
                    },
                },
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_editor_sql",
            "description": (
                "Set the SQL query in the user's SQL editor. "
                "Use this when you have the final, tested query ready for the user. "
                "This replaces the content of the active SQL editor tab."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "The SQL query to place in the editor",
                    },
                },
                "required": ["sql"],
            },
        },
    },
]


# --------------------------------------------------------------------------
# Tool execution functions
# --------------------------------------------------------------------------


def _get_database(database_id: int) -> Database:
    """Load a Database model by ID, raising ValueError if not found."""
    database = db.session.query(Database).filter_by(id=database_id).first()
    if not database:
        raise ValueError(f"Database with id={database_id} not found")
    return database


def tool_list_schemas(database_id: int, catalog: str | None = None) -> dict[str, Any]:
    """List all schemas in the database."""
    try:
        database = _get_database(database_id)
        schemas = database.get_all_schema_names(catalog=catalog)
        return {"schemas": sorted(schemas)}
    except Exception as ex:
        logger.error("Error listing schemas for db %s: %s", database_id, ex)
        return {"error": str(ex)}


def tool_list_tables(
    database_id: int, schema_name: str, catalog: str | None = None
) -> dict[str, Any]:
    """List all tables in a specific schema."""
    try:
        database = _get_database(database_id)
        tables = database.get_all_table_names_in_schema(
            catalog=catalog, schema=schema_name
        )
        # tables is a set of (table_name, schema, catalog) tuples
        table_names = sorted(t[0] for t in tables)
        return {"tables": table_names, "schema": schema_name}
    except Exception as ex:
        logger.error(
            "Error listing tables for db %s, schema %s: %s",
            database_id,
            schema_name,
            ex,
        )
        return {"error": str(ex)}


def tool_get_table_columns(
    database_id: int,
    table_name: str,
    schema_name: str,
    catalog: str | None = None,
) -> dict[str, Any]:
    """Get column metadata for a table."""
    try:
        database = _get_database(database_id)
        table = Table(table=table_name, schema=schema_name, catalog=catalog)
        columns = database.get_columns(table)
        # Format columns for readability
        col_info = []
        for col in columns:
            col_info.append(
                {
                    "name": col.get("column_name") or col.get("name", "unknown"),
                    "type": str(col.get("type", "unknown")),
                    "nullable": col.get("nullable", True),
                }
            )
        return {"table": table_name, "schema": schema_name, "columns": col_info}
    except Exception as ex:
        logger.error(
            "Error getting columns for %s.%s in db %s: %s",
            schema_name,
            table_name,
            database_id,
            ex,
        )
        return {"error": str(ex)}


def tool_sample_table_data(
    database_id: int,
    table_name: str,
    schema_name: str,
    catalog: str | None = None,
    max_rows: int = 20,
) -> dict[str, Any]:
    """Get sample data from a table."""
    try:
        database = _get_database(database_id)
        # Use TOP for MSSQL, LIMIT for others
        db_engine = database.db_engine_spec.__name__ if database.db_engine_spec else ""
        if "mssql" in db_engine.lower() or "MSSql" in db_engine:
            sql = f"SELECT TOP {max_rows} * FROM [{schema_name}].[{table_name}]"
        else:
            sql = f'SELECT * FROM "{schema_name}"."{table_name}" LIMIT {max_rows}'

        from superset_core.api.types import QueryOptions

        options = QueryOptions(
            catalog=catalog,
            schema=schema_name,
            limit=max_rows,
        )
        result = database.execute(sql, options)
        rows, _ = _extract_result_data(result)
        rows = rows[:max_rows]

        return {
            "table": table_name,
            "schema": schema_name,
            "row_count": len(rows),
            "data": rows,
        }
    except Exception as ex:
        logger.error(
            "Error sampling data from %s.%s in db %s: %s",
            schema_name,
            table_name,
            database_id,
            ex,
        )
        return {"error": str(ex)}


def tool_get_distinct_values(
    database_id: int,
    table_name: str,
    schema_name: str,
    column_name: str,
    catalog: str | None = None,
    max_values: int = 50,
) -> dict[str, Any]:
    """Get distinct values for a specific column."""
    try:
        database = _get_database(database_id)
        db_engine = database.db_engine_spec.__name__ if database.db_engine_spec else ""
        if "mssql" in db_engine.lower() or "MSSql" in db_engine:
            sql = (
                f"SELECT DISTINCT TOP {max_values} [{column_name}] "
                f"FROM [{schema_name}].[{table_name}] "
                f"WHERE [{column_name}] IS NOT NULL "
                f"ORDER BY [{column_name}]"
            )
        else:
            sql = (
                f'SELECT DISTINCT "{column_name}" '
                f'FROM "{schema_name}"."{table_name}" '
                f'WHERE "{column_name}" IS NOT NULL '
                f'ORDER BY "{column_name}" LIMIT {max_values}'
            )

        from superset_core.api.types import QueryOptions

        options = QueryOptions(
            catalog=catalog,
            schema=schema_name,
            limit=max_values,
        )
        result = database.execute(sql, options)

        rows, _ = _extract_result_data(result)
        values = []
        for row in rows[:max_values]:
            val = list(row.values())[0] if isinstance(row, dict) else row
            values.append(str(val) if val is not None else None)

        return {
            "table": table_name,
            "column": column_name,
            "distinct_count": len(values),
            "values": values,
        }
    except Exception as ex:
        logger.error(
            "Error getting distinct values for %s.%s.%s in db %s: %s",
            schema_name,
            table_name,
            column_name,
            database_id,
            ex,
        )
        return {"error": str(ex)}


def tool_execute_sql(
    database_id: int,
    sql: str,
    schema_name: str | None = None,
    catalog: str | None = None,
    max_rows: int = 50,
) -> dict[str, Any]:
    """Execute an arbitrary SQL query."""
    try:
        # Basic safety check - only allow SELECT
        sql_stripped = sql.strip().upper()
        if not sql_stripped.startswith("SELECT") and not sql_stripped.startswith(
            "WITH"
        ):
            return {
                "error": "Only SELECT and WITH (CTE) queries are allowed for safety"
            }

        database = _get_database(database_id)

        from superset_core.api.types import QueryOptions

        options = QueryOptions(
            catalog=catalog,
            schema=schema_name,
            limit=max_rows,
        )
        result = database.execute(sql, options)
        rows, columns = _extract_result_data(result)
        rows = rows[:max_rows]

        return {
            "columns": columns,
            "row_count": len(rows),
            "data": rows,
        }
    except Exception as ex:
        logger.error("Error executing SQL in db %s: %s\nSQL: %s", database_id, ex, sql)
        return {"error": str(ex), "sql": sql}


# --------------------------------------------------------------------------
# Tool dispatcher
# --------------------------------------------------------------------------

# Actions that are passed back to the frontend (not executed on backend)
FRONTEND_ACTIONS = {"set_editor_sql"}


def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    database_id: int,
    schema_name: str | None = None,
    catalog: str | None = None,
    max_sample_rows: int = 20,
) -> dict[str, Any]:
    """
    Execute a tool by name and return the result.

    For frontend actions (like set_editor_sql), returns an action descriptor
    instead of executing server-side.
    """
    logger.debug("Executing tool: %s with args: %s", tool_name, arguments)

    if tool_name in FRONTEND_ACTIONS:
        # These actions are relayed to the frontend
        return {"action": tool_name, **arguments}

    if tool_name == "list_schemas":
        return tool_list_schemas(database_id, catalog=catalog)

    if tool_name == "list_tables":
        return tool_list_tables(
            database_id,
            schema_name=arguments["schema_name"],
            catalog=catalog,
        )

    if tool_name == "get_table_columns":
        return tool_get_table_columns(
            database_id,
            table_name=arguments["table_name"],
            schema_name=arguments["schema_name"],
            catalog=catalog,
        )

    if tool_name == "sample_table_data":
        return tool_sample_table_data(
            database_id,
            table_name=arguments["table_name"],
            schema_name=arguments["schema_name"],
            catalog=catalog,
            max_rows=max_sample_rows,
        )

    if tool_name == "get_distinct_values":
        return tool_get_distinct_values(
            database_id,
            table_name=arguments["table_name"],
            schema_name=arguments["schema_name"],
            column_name=arguments["column_name"],
            catalog=catalog,
        )

    if tool_name == "execute_sql":
        return tool_execute_sql(
            database_id,
            sql=arguments["sql"],
            schema_name=schema_name,
            catalog=catalog,
        )

    return {"error": f"Unknown tool: {tool_name}"}
