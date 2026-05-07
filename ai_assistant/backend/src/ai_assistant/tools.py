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
import re
from datetime import datetime
from typing import Any

from superset.connectors.sqla.models import SqlaTable
from superset.extensions import db
from superset.models.core import Database
from superset.sql.parse import Table

logger = logging.getLogger(__name__)


def _ai_resource_name(topic: str) -> str:
    """Generate a standardised AI resource name: ai_YYYYMMDD_HHMM_Topic."""
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    # Keep only alphanumeric, spaces, hyphens, underscores; then convert spaces to _
    safe = re.sub(r"[^\w\s-]", "", topic).strip()
    safe = re.sub(r"\s+", "_", safe)[:60]
    return f"ai_{ts}_{safe}"


def _get_superset_dataset_metadata(
    database_id: int,
    table_name: str,
    schema_name: str | None = None,
) -> dict[str, Any]:
    """
    Look up the Superset dataset (SqlaTable) for a given table and return
    enriched metadata: column descriptions, verbose_names, and predefined metrics.
    Returns empty dicts if no dataset is registered for this table.
    """
    query = db.session.query(SqlaTable).filter(
        SqlaTable.database_id == database_id,
        SqlaTable.table_name == table_name,
    )
    if schema_name:
        query = query.filter(SqlaTable.schema == schema_name)
    dataset = query.first()

    if not dataset:
        return {"table_description": None, "column_meta": {}, "metrics": []}

    # Column-level metadata keyed by column_name
    column_meta: dict[str, dict[str, str | None]] = {}
    for col in dataset.columns:
        meta: dict[str, str | None] = {}
        if col.verbose_name:
            meta["verbose_name"] = col.verbose_name
        if col.description:
            meta["description"] = col.description
        if meta:
            column_meta[col.column_name] = meta

    # Predefined metrics
    metrics_info = []
    for m in dataset.metrics:
        metric_entry: dict[str, str | None] = {
            "name": m.metric_name,
            "expression": m.expression,
        }
        if m.verbose_name:
            metric_entry["verbose_name"] = m.verbose_name
        if m.description:
            metric_entry["description"] = m.description
        metrics_info.append(metric_entry)

    return {
        "table_description": dataset.description or None,
        "column_meta": column_meta,
        "metrics": metrics_info,
    }


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
                "List all tables (NOT views) in a specific schema. "
                "Use this to discover which tables are available. "
                "To also see database views, use list_views separately."
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
            "name": "list_views",
            "description": (
                "List all database views in a specific schema. "
                "Views are pre-defined SQL queries stored in the database — they often "
                "contain important aggregations, joins, or filtered data. "
                "Always check views alongside tables when exploring a schema. "
                "You can use get_table_columns, sample_table_data, and execute_sql on views "
                "the same way you would on tables."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "schema_name": {
                        "type": "string",
                        "description": "The schema name to list views from",
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
                "Get column names, data types, nullable info, and metadata for a table or view. "
                "Returns column comments/descriptions, verbose names, table comment, "
                "and any predefined Superset metrics. "
                "Use this to understand the structure AND business meaning of a table or view."
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
                "Get a sample of rows from a table or view (up to 20 rows). "
                "Use this to understand what kind of data a table or view contains."
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
                "The SQL is validated by executing it against the database first. "
                "If the SQL has errors (wrong column names, syntax errors, etc.), "
                "this tool returns an error and the query is NOT placed in the editor. "
                "In that case, fix the SQL and call this tool again. "
                "Use this when you have the final query ready for the user."
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
    {
        "type": "function",
        "function": {
            "name": "create_chart",
            "description": (
                "Create a chart visualization from query results. "
                "Creates an interactive chart in Superset's Explore view. "
                "By default creates a preview (user can customize and save). "
                "Set save_chart=true to persist the chart permanently. "
                "Use this after running a query that produces data worth visualizing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_name": {
                        "type": "string",
                        "description": "A descriptive name for the chart",
                    },
                    "viz_type": {
                        "type": "string",
                        "enum": ["bar", "line", "pie", "table"],
                        "description": (
                            "Chart type: 'bar' for bar chart, 'line' for line/time series, "
                            "'pie' for pie/donut chart, 'table' for data table"
                        ),
                    },
                    "sql": {
                        "type": "string",
                        "description": "The SQL query that produces the data for the chart",
                    },
                    "x_column": {
                        "type": "string",
                        "description": (
                            "Column for X axis / grouping (bar: category axis, "
                            "line: time/x axis, pie: slice labels)"
                        ),
                    },
                    "y_column": {
                        "type": "string",
                        "description": (
                            "Column for Y axis / metric values (bar: bar height, "
                            "line: line value, pie: slice size)"
                        ),
                    },
                    "y_aggregate": {
                        "type": "string",
                        "enum": ["SUM", "COUNT", "AVG", "MAX", "MIN"],
                        "description": (
                            "Aggregate function for the Y column metric. "
                            "Default: SUM. Use COUNT for counting rows."
                        ),
                    },
                    "group_by": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Additional columns to group by (for multi-series charts). "
                            "Optional."
                        ),
                    },
                    "save_chart": {
                        "type": "boolean",
                        "description": (
                            "If true, saves the chart permanently. "
                            "Default: false (preview only, user can save manually)."
                        ),
                    },
                },
                "required": ["chart_name", "viz_type", "sql", "x_column", "y_column"],
            },
        },
    },
    # ------------------------------------------------------------------
    # Dataset management tools
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "list_datasets",
            "description": (
                "List Superset datasets (registered tables/views/SQL). "
                "Returns id, name, type (physical or virtual), schema, and database name. "
                "Use this to find existing datasets before creating new ones, or to see "
                "what data sources are already configured in Superset."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "search": {
                        "type": "string",
                        "description": (
                            "Optional search term to filter dataset names (case-insensitive). "
                            "Leave empty to list all datasets for the current database."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dataset",
            "description": (
                "Get full details of a Superset dataset by its ID. "
                "Returns columns (with descriptions, verbose names), metrics, "
                "SQL (for virtual datasets), description, and database info. "
                "Use this to inspect how a dataset is configured before using or editing it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_id": {
                        "type": "integer",
                        "description": "The Superset dataset ID (from list_datasets)",
                    },
                },
                "required": ["dataset_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_dataset",
            "description": (
                "Update an existing Superset dataset. Can modify description, "
                "column descriptions/verbose_names, SQL (for virtual datasets), "
                "and metrics. ONLY use this when the user explicitly asks to edit "
                "a dataset. All changes are logged."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dataset_id": {
                        "type": "integer",
                        "description": "The Superset dataset ID to update",
                    },
                    "description": {
                        "type": "string",
                        "description": "New description for the dataset. Optional.",
                    },
                    "sql": {
                        "type": "string",
                        "description": (
                            "New SQL for virtual datasets. Only works on virtual datasets. Optional."
                        ),
                    },
                    "columns": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "column_name": {"type": "string"},
                                "verbose_name": {"type": "string"},
                                "description": {"type": "string"},
                            },
                            "required": ["column_name"],
                        },
                        "description": (
                            "Column metadata updates. Only specified fields are changed. Optional."
                        ),
                    },
                },
                "required": ["dataset_id"],
            },
        },
    },
    # ------------------------------------------------------------------
    # Chart management tools
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "list_charts",
            "description": (
                "List existing Superset charts/visualizations. "
                "Returns id, name, viz_type, dataset info, and last modified date. "
                "Use this to find charts the user wants to inspect or modify."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "search": {
                        "type": "string",
                        "description": (
                            "Optional search term to filter chart names (case-insensitive)."
                        ),
                    },
                    "dataset_id": {
                        "type": "integer",
                        "description": (
                            "Optional: filter charts by dataset ID to find charts "
                            "using a specific data source."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_chart",
            "description": (
                "Get full details of a Superset chart by its ID. "
                "Returns chart name, viz_type, params (form_data), datasource info, "
                "description, and the explore URL. "
                "Use this to understand how a chart is configured."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_id": {
                        "type": "integer",
                        "description": "The Superset chart ID (from list_charts)",
                    },
                },
                "required": ["chart_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_chart",
            "description": (
                "Update an existing Superset chart. Can modify name, description, "
                "viz_type, params (form_data), and datasource. ONLY use this when "
                "the user explicitly asks to edit a chart. All changes are logged."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_id": {
                        "type": "integer",
                        "description": "The Superset chart ID to update",
                    },
                    "chart_name": {
                        "type": "string",
                        "description": "New name for the chart. Optional.",
                    },
                    "description": {
                        "type": "string",
                        "description": "New description for the chart. Optional.",
                    },
                    "viz_type": {
                        "type": "string",
                        "enum": ["bar", "line", "pie", "table"],
                        "description": "New chart type. Optional.",
                    },
                    "params": {
                        "type": "object",
                        "description": (
                            "Partial params/form_data to merge into the existing chart config. "
                            "Only specified keys are overwritten. Optional."
                        ),
                    },
                    "datasource_id": {
                        "type": "integer",
                        "description": "New dataset ID for the chart. Optional.",
                    },
                },
                "required": ["chart_id"],
            },
        },
    },
    # ------------------------------------------------------------------
    # Dashboard creation
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "create_dashboard",
            "description": (
                "Create a Superset dashboard from a list of saved chart IDs. "
                "The charts will be arranged in a responsive grid layout. "
                "Use this AFTER creating and saving charts with create_chart(save_chart=true). "
                "The dashboard is saved permanently and accessible from the Dashboards menu."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_title": {
                        "type": "string",
                        "description": "Title for the dashboard (e.g. '[AI] HUNIKA Kft - Pénzügyi áttekintés')",
                    },
                    "chart_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of saved chart IDs to include in the dashboard.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional description for the dashboard.",
                    },
                },
                "required": ["dashboard_title", "chart_ids"],
            },
        },
    },
    # ------------------------------------------------------------------
    # Interactive tools (frontend-only actions)
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": (
                "Ask the user a clarification question with predefined options. "
                "Use this when the request is ambiguous, there are multiple valid "
                "approaches, or you need confirmation before a significant action. "
                "The user will see clickable option buttons and their choice will "
                "be sent back to you as their next message."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The question to ask the user.",
                    },
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {
                                    "type": "string",
                                    "description": "Short identifier for this option.",
                                },
                                "label": {
                                    "type": "string",
                                    "description": "Human-readable label shown on the button.",
                                },
                            },
                            "required": ["id", "label"],
                        },
                        "description": "The options to present to the user (2-5 options).",
                    },
                },
                "required": ["question", "options"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_todo",
            "description": (
                "Create or update a visible task checklist for the user. "
                "Use this at the start of any multi-step task to show your plan, "
                "and update it as you complete each step. The user sees this as a "
                "real-time progress indicator. Each item has an id, text, and status."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {
                                    "type": "string",
                                    "description": "Unique identifier for this todo item.",
                                },
                                "text": {
                                    "type": "string",
                                    "description": "Description of the task step.",
                                },
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "done", "error"],
                                    "description": "Current status of this step.",
                                },
                            },
                            "required": ["id", "text", "status"],
                        },
                        "description": (
                            "The full todo list. Send ALL items each time (not just changed ones). "
                            "Update statuses as you progress through steps."
                        ),
                    },
                },
                "required": ["items"],
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


def tool_list_views(
    database_id: int, schema_name: str, catalog: str | None = None
) -> dict[str, Any]:
    """List all views in a specific schema."""
    try:
        database = _get_database(database_id)
        views = database.get_all_view_names_in_schema(
            catalog=catalog, schema=schema_name
        )
        # views is a set of (view_name, schema, catalog) tuples
        view_names = sorted(v[0] for v in views)
        return {"views": view_names, "schema": schema_name}
    except Exception as ex:
        logger.error(
            "Error listing views for db %s, schema %s: %s",
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
    """Get column metadata for a table, enriched with Superset dataset info."""
    try:
        database = _get_database(database_id)
        table = Table(table=table_name, schema=schema_name, catalog=catalog)
        columns = database.get_columns(table)

        # Get table comment from the database engine
        table_comment = None
        try:
            table_comment = database.get_table_comment(table)
        except Exception as comment_ex:
            logger.debug(
                "Could not get table comment for %s.%s: %s",
                schema_name, table_name, comment_ex,
            )

        # Get Superset dataset metadata (descriptions, verbose_names, metrics)
        ds_meta = _get_superset_dataset_metadata(
            database_id, table_name, schema_name
        )
        column_meta = ds_meta["column_meta"]

        # Format columns with all available metadata
        col_info = []
        for col in columns:
            col_name = col.get("column_name") or col.get("name", "unknown")
            entry: dict[str, Any] = {
                "name": col_name,
                "type": str(col.get("type", "unknown")),
                "nullable": col.get("nullable", True),
            }
            # SQL column comment from the database engine
            if col.get("comment"):
                entry["comment"] = col["comment"]
            # Default value
            if col.get("default") is not None:
                entry["default"] = str(col["default"])
            # Superset dataset metadata (verbose_name, description)
            superset_meta = column_meta.get(col_name)
            if superset_meta:
                if superset_meta.get("verbose_name"):
                    entry["verbose_name"] = superset_meta["verbose_name"]
                if superset_meta.get("description"):
                    entry["description"] = superset_meta["description"]
            col_info.append(entry)

        result: dict[str, Any] = {
            "table": table_name,
            "schema": schema_name,
            "columns": col_info,
        }

        # Table-level metadata
        if table_comment:
            result["table_comment"] = table_comment
        if ds_meta["table_description"]:
            result["table_description"] = ds_meta["table_description"]
        if ds_meta["metrics"]:
            result["predefined_metrics"] = ds_meta["metrics"]

        return result
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

        from superset_core.queries.types import QueryOptions

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

        from superset_core.queries.types import QueryOptions

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


def _validate_sql_syntax(sql: str, dialect: str | None = None) -> str | None:
    """
    Validate SQL syntax using sqlglot. Returns error message if invalid,
    None if valid. This catches obvious syntax errors before hitting the DB.
    """
    try:
        import sqlglot

        sqlglot_dialect = None
        if dialect and "mssql" in dialect.lower():
            sqlglot_dialect = "tsql"
        elif dialect and "postgres" in dialect.lower():
            sqlglot_dialect = "postgres"
        elif dialect and "mysql" in dialect.lower():
            sqlglot_dialect = "mysql"

        sqlglot.transpile(sql, read=sqlglot_dialect)
        return None
    except sqlglot.errors.ParseError as e:
        return f"SQL syntax error: {str(e)}"
    except Exception:
        # If sqlglot itself fails, don't block — let the DB handle it
        return None


def tool_set_editor_sql(
    database_id: int,
    sql: str,
    schema_name: str | None = None,
    catalog: str | None = None,
) -> dict[str, Any]:
    """
    Validate the SQL by executing it (LIMIT 1), then return the frontend
    action so it gets placed in the editor.  If the SQL fails, return the
    error to the LLM so it can fix the query before trying again.
    """
    sql_stripped = sql.strip().upper()
    is_select = sql_stripped.startswith("SELECT") or sql_stripped.startswith("WITH")

    if is_select:
        # Wrap in a validation query that returns at most 1 row
        database = _get_database(database_id)
        db_backend = database.backend.lower() if database.backend else ""
        if "mssql" in db_backend:
            validation_sql = f"SELECT TOP 1 * FROM ({sql}) AS _validation_check"
        else:
            validation_sql = f"SELECT * FROM ({sql}) AS _validation_check LIMIT 1"

        try:
            from superset_core.queries.types import QueryOptions
            options = QueryOptions(
                catalog=catalog,
                schema=schema_name,
                limit=1,
            )
            database.execute(validation_sql, options)
            logger.info("set_editor_sql validation passed for SQL (%d chars)", len(sql))
        except Exception as ex:
            logger.warning(
                "set_editor_sql validation FAILED: %s\nSQL: %s", ex, sql[:500]
            )
            return {
                "error": (
                    f"SQL validation failed — this query has errors and was NOT "
                    f"sent to the editor. Fix the query and try set_editor_sql again. "
                    f"DB error: {str(ex)}"
                ),
                "sql": sql,
            }

    # Validation passed (or non-SELECT) — send to frontend
    return {"action": "set_editor_sql", "sql": sql}


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

        # Validate SQL syntax before executing
        database = _get_database(database_id)
        dialect = database.backend if database else None
        syntax_error = _validate_sql_syntax(sql, dialect)
        if syntax_error:
            return {"error": syntax_error, "sql": sql}

        from superset_core.queries.types import QueryOptions

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
            "is_empty": len(rows) == 0,
        }
    except Exception as ex:
        logger.error("Error executing SQL in db %s: %s\nSQL: %s", database_id, ex, sql)
        return {"error": str(ex), "sql": sql}


# --------------------------------------------------------------------------
# Dataset management
# --------------------------------------------------------------------------


def tool_list_datasets(
    database_id: int,
    search: str | None = None,
) -> dict[str, Any]:
    """List Superset datasets, optionally filtered by search term."""
    try:
        query = db.session.query(SqlaTable).filter(
            SqlaTable.database_id == database_id,
        )
        if search:
            query = query.filter(
                SqlaTable.table_name.ilike(f"%{search}%")
            )
        query = query.order_by(SqlaTable.table_name)
        datasets = query.limit(100).all()

        results = []
        for ds in datasets:
            is_virtual = bool(ds.sql)
            results.append({
                "id": ds.id,
                "name": ds.table_name,
                "type": "virtual" if is_virtual else "physical",
                "schema": ds.schema or None,
                "description": ds.description or None,
            })

        return {"datasets": results, "count": len(results)}
    except Exception as ex:
        logger.error("Error listing datasets for db %s: %s", database_id, ex)
        return {"error": str(ex)}


def tool_get_dataset(dataset_id: int) -> dict[str, Any]:
    """Get full details of a Superset dataset by ID."""
    try:
        dataset = db.session.query(SqlaTable).filter_by(id=dataset_id).first()
        if not dataset:
            return {"error": f"Dataset with id={dataset_id} not found"}

        # Column metadata
        columns_info = []
        for col in dataset.columns:
            entry: dict[str, Any] = {
                "column_name": col.column_name,
                "type": col.type or "unknown",
                "is_active": col.is_active if hasattr(col, "is_active") else True,
            }
            if col.verbose_name:
                entry["verbose_name"] = col.verbose_name
            if col.description:
                entry["description"] = col.description
            if col.filterable is not None:
                entry["filterable"] = col.filterable
            if col.groupby is not None:
                entry["groupby"] = col.groupby
            columns_info.append(entry)

        # Metrics
        metrics_info = []
        for m in dataset.metrics:
            metric_entry: dict[str, Any] = {
                "metric_name": m.metric_name,
                "expression": m.expression,
            }
            if m.verbose_name:
                metric_entry["verbose_name"] = m.verbose_name
            if m.description:
                metric_entry["description"] = m.description
            if m.metric_type:
                metric_entry["metric_type"] = m.metric_type
            metrics_info.append(metric_entry)

        result: dict[str, Any] = {
            "id": dataset.id,
            "name": dataset.table_name,
            "type": "virtual" if dataset.sql else "physical",
            "schema": dataset.schema or None,
            "database_id": dataset.database_id,
            "description": dataset.description or None,
            "columns": columns_info,
            "metrics": metrics_info,
        }

        if dataset.sql:
            result["sql"] = dataset.sql

        return result
    except Exception as ex:
        logger.error("Error getting dataset %s: %s", dataset_id, ex)
        return {"error": str(ex)}


def tool_update_dataset(
    dataset_id: int,
    description: str | None = None,
    sql: str | None = None,
    columns: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Update an existing Superset dataset. Logs all changes."""
    try:
        dataset = db.session.query(SqlaTable).filter_by(id=dataset_id).first()
        if not dataset:
            return {"error": f"Dataset with id={dataset_id} not found"}

        changes: list[str] = []

        # Update description
        if description is not None:
            old_desc = dataset.description
            dataset.description = description
            changes.append(f"description: '{old_desc}' -> '{description}'")

        # Update SQL (virtual datasets only)
        if sql is not None:
            if not dataset.sql:
                return {"error": "Cannot set SQL on a physical dataset — only virtual datasets have SQL"}
            old_sql = dataset.sql
            dataset.sql = sql
            changes.append(f"sql updated (was {len(old_sql or '')} chars, now {len(sql)} chars)")

        # Update column metadata
        if columns:
            col_map = {c.column_name: c for c in dataset.columns}
            for col_update in columns:
                col_name = col_update.get("column_name")
                if not col_name or col_name not in col_map:
                    changes.append(f"column '{col_name}' not found, skipped")
                    continue
                col_obj = col_map[col_name]
                if "verbose_name" in col_update:
                    col_obj.verbose_name = col_update["verbose_name"]
                    changes.append(f"column '{col_name}' verbose_name set to '{col_update['verbose_name']}'")
                if "description" in col_update:
                    col_obj.description = col_update["description"]
                    changes.append(f"column '{col_name}' description updated")

        if not changes:
            return {"message": "No changes specified", "dataset_id": dataset_id}

        db.session.commit()
        logger.info(
            "Updated dataset %s (%s): %s",
            dataset_id, dataset.table_name, "; ".join(changes),
        )

        return {
            "message": "Dataset updated successfully",
            "dataset_id": dataset_id,
            "dataset_name": dataset.table_name,
            "changes": changes,
        }
    except Exception as ex:
        db.session.rollback()
        logger.error("Error updating dataset %s: %s", dataset_id, ex, exc_info=True)
        return {"error": f"Failed to update dataset: {str(ex)}"}


# --------------------------------------------------------------------------
# Chart management (read / update existing charts)
# --------------------------------------------------------------------------


def tool_list_charts(
    search: str | None = None,
    dataset_id: int | None = None,
) -> dict[str, Any]:
    """List existing Superset charts, optionally filtered."""
    try:
        from superset.models.slice import Slice

        query = db.session.query(Slice)

        if search:
            query = query.filter(Slice.slice_name.ilike(f"%{search}%"))
        if dataset_id is not None:
            query = query.filter(
                Slice.datasource_id == dataset_id,
                Slice.datasource_type == "table",
            )

        query = query.order_by(Slice.changed_on.desc())
        charts = query.limit(50).all()

        results = []
        for chart in charts:
            results.append({
                "id": chart.id,
                "name": chart.slice_name,
                "viz_type": chart.viz_type,
                "datasource_id": chart.datasource_id,
                "datasource_type": chart.datasource_type,
                "description": chart.description or None,
                "changed_on": str(chart.changed_on) if chart.changed_on else None,
                "url": f"/explore/?slice_id={chart.id}",
            })

        return {"charts": results, "count": len(results)}
    except Exception as ex:
        logger.error("Error listing charts: %s", ex)
        return {"error": str(ex)}


def tool_get_chart(chart_id: int) -> dict[str, Any]:
    """Get full details of a Superset chart by ID."""
    try:
        import json as stdlib_json
        from superset.models.slice import Slice

        chart = db.session.query(Slice).filter_by(id=chart_id).first()
        if not chart:
            return {"error": f"Chart with id={chart_id} not found"}

        # Parse params JSON
        params = {}
        if chart.params:
            try:
                params = stdlib_json.loads(chart.params)
            except stdlib_json.JSONDecodeError:
                params = {"_raw": chart.params}

        result: dict[str, Any] = {
            "id": chart.id,
            "name": chart.slice_name,
            "viz_type": chart.viz_type,
            "datasource_id": chart.datasource_id,
            "datasource_type": chart.datasource_type,
            "description": chart.description or None,
            "params": params,
            "url": f"/explore/?slice_id={chart.id}",
            "changed_on": str(chart.changed_on) if chart.changed_on else None,
        }

        # Add datasource name if available
        if chart.datasource_name:
            result["datasource_name"] = chart.datasource_name

        return result
    except Exception as ex:
        logger.error("Error getting chart %s: %s", chart_id, ex)
        return {"error": str(ex)}


def tool_update_chart(
    chart_id: int,
    chart_name: str | None = None,
    description: str | None = None,
    viz_type: str | None = None,
    params: dict[str, Any] | None = None,
    datasource_id: int | None = None,
) -> dict[str, Any]:
    """Update an existing Superset chart. Logs all changes."""
    try:
        import json as stdlib_json
        from superset.models.slice import Slice

        chart = db.session.query(Slice).filter_by(id=chart_id).first()
        if not chart:
            return {"error": f"Chart with id={chart_id} not found"}

        changes: list[str] = []

        if chart_name is not None:
            old_name = chart.slice_name
            chart.slice_name = chart_name
            changes.append(f"name: '{old_name}' -> '{chart_name}'")

        if description is not None:
            chart.description = description
            changes.append("description updated")

        if viz_type is not None:
            superset_viz = VIZ_TYPE_MAP.get(viz_type, viz_type)
            old_viz = chart.viz_type
            chart.viz_type = superset_viz
            changes.append(f"viz_type: '{old_viz}' -> '{superset_viz}'")

        if params is not None:
            # Merge new params into existing params
            existing_params = {}
            if chart.params:
                try:
                    existing_params = stdlib_json.loads(chart.params)
                except stdlib_json.JSONDecodeError:
                    existing_params = {}
            existing_params.update(params)
            chart.params = stdlib_json.dumps(existing_params)
            changes.append(f"params updated ({len(params)} keys changed)")

        if datasource_id is not None:
            old_ds = chart.datasource_id
            chart.datasource_id = datasource_id
            chart.datasource_type = "table"
            changes.append(f"datasource_id: {old_ds} -> {datasource_id}")

        if not changes:
            return {"message": "No changes specified", "chart_id": chart_id}

        db.session.commit()
        logger.info(
            "Updated chart %s (%s): %s",
            chart_id, chart.slice_name, "; ".join(changes),
        )

        return {
            "message": "Chart updated successfully",
            "chart_id": chart_id,
            "chart_name": chart.slice_name,
            "changes": changes,
            "url": f"/explore/?slice_id={chart.id}",
        }
    except Exception as ex:
        db.session.rollback()
        logger.error("Error updating chart %s: %s", chart_id, ex, exc_info=True)
        return {"error": f"Failed to update chart: {str(ex)}"}


# --------------------------------------------------------------------------
# Chart creation
# --------------------------------------------------------------------------

# Map simplified viz_type names to Superset viz_type identifiers
VIZ_TYPE_MAP = {
    "bar": "echarts_timeseries_bar",
    "line": "echarts_timeseries_line",
    "pie": "pie",
    "table": "table",
}


def _strip_trailing_order_by(sql: str) -> str:
    """
    Strip trailing ORDER BY clause from SQL. MSSQL does not allow ORDER BY
    in subqueries/derived tables/views unless TOP or OFFSET is specified.
    Since Superset wraps virtual dataset SQL in a subquery, ORDER BY causes
    errors on MSSQL.
    """
    import re

    # Match ORDER BY ... at the end of the SQL, possibly followed by a semicolon
    # Handles multi-line and case-insensitive
    cleaned = re.sub(
        r'\bORDER\s+BY\s+[^;]*?(?:;?\s*)$',
        '',
        sql.strip(),
        flags=re.IGNORECASE | re.DOTALL,
    ).strip()
    return cleaned or sql


def _is_mssql(database_id: int) -> bool:
    """Check if the database is MSSQL."""
    try:
        database = _get_database(database_id)
        return "mssql" in database.backend.lower()
    except Exception:
        return False


def _find_existing_dataset(
    database_id: int,
    table_name: str,
    schema_name: str | None = None,
) -> Any:
    """Try to find an existing dataset by table name and schema."""
    from superset.connectors.sqla.models import SqlaTable

    query = db.session.query(SqlaTable).filter(
        SqlaTable.database_id == database_id,
        SqlaTable.table_name == table_name,
    )
    if schema_name:
        query = query.filter(SqlaTable.schema == schema_name)
    return query.first()


def _create_virtual_dataset(
    database_id: int,
    sql: str,
    dataset_name: str,
    schema_name: str | None = None,
) -> Any:
    """Create a virtual (SQL-based) dataset."""
    from superset.commands.dataset.create import CreateDatasetCommand

    payload = {
        "database": database_id,
        "table_name": dataset_name,
        "sql": sql,
    }
    if schema_name:
        payload["schema"] = schema_name

    dataset = CreateDatasetCommand(payload).run()
    logger.info(
        "Created virtual dataset: id=%s, name=%s", dataset.id, dataset_name
    )
    return dataset


def _build_form_data(
    dataset_id: int,
    viz_type: str,
    x_column: str,
    y_column: str,
    y_aggregate: str = "SUM",
    group_by: list[str] | None = None,
) -> dict[str, Any]:
    """Build Superset form_data for a given chart configuration."""
    superset_viz_type = VIZ_TYPE_MAP.get(viz_type, viz_type)

    metric = {
        "expressionType": "SIMPLE",
        "aggregate": y_aggregate,
        "column": {"column_name": y_column},
        "label": f"{y_aggregate}({y_column})",
    }

    form_data: dict[str, Any] = {
        "viz_type": superset_viz_type,
        "datasource": f"{dataset_id}__table",
        "time_range": "No filter",
        "row_limit": 10000,
    }

    if viz_type == "table":
        form_data["all_columns"] = [x_column, y_column]
        if group_by:
            form_data["all_columns"].extend(group_by)
    elif viz_type == "pie":
        form_data["groupby"] = [x_column]
        form_data["metric"] = metric
    elif viz_type in ("bar", "line"):
        form_data["x_axis"] = x_column
        form_data["metrics"] = [metric]
        if group_by:
            form_data["groupby"] = group_by
    else:
        form_data["groupby"] = [x_column]
        form_data["metrics"] = [metric]

    return form_data


def _generate_explore_url(
    dataset_id: int,
    form_data: dict[str, Any],
) -> str:
    """Generate an explore URL by caching form_data and returning a keyed URL."""
    from superset.commands.explore.form_data.parameters import CommandParameters
    from superset.mcp_service.commands.create_form_data import (
        MCPCreateFormDataCommand,
    )
    from superset.utils import json as superset_json
    from superset.utils.core import DatasourceType

    cmd_params = CommandParameters(
        datasource_type=DatasourceType.TABLE,
        datasource_id=dataset_id,
        chart_id=0,
        tab_id=None,
        form_data=superset_json.dumps(form_data),
    )
    form_data_key = MCPCreateFormDataCommand(cmd_params).run()
    return f"/explore/?form_data_key={form_data_key}"


def _validate_chart_sql(
    database_id: int,
    sql: str,
    schema_name: str | None = None,
    catalog: str | None = None,
) -> dict[str, Any] | None:
    """Validate chart SQL by executing it with TOP 1 / LIMIT 1.

    Returns None on success.  On failure returns an error dict that includes
    the DB error AND the column list of any tables referenced, so the LLM
    can self-correct without extra tool calls.
    """
    try:
        database = _get_database(database_id)
        db_backend = database.backend.lower() if database.backend else ""
        if "mssql" in db_backend:
            validation_sql = f"SELECT TOP 1 * FROM ({sql}) AS _val"
        else:
            validation_sql = f"SELECT * FROM ({sql}) AS _val LIMIT 1"

        from superset_core.queries.types import QueryOptions
        options = QueryOptions(catalog=catalog, schema=schema_name, limit=1)
        database.execute(validation_sql, options)
        return None  # success
    except Exception as ex:
        error_msg = str(ex)
        logger.warning("create_chart SQL validation FAILED: %s", error_msg[:300])

        # Try to extract referenced table names and return their columns
        hint_lines: list[str] = []
        table_refs = _extract_table_refs(sql)
        if table_refs:
            for tbl in table_refs[:4]:  # max 4 tables
                try:
                    cols = tool_get_table_columns(
                        database_id, tbl, schema_name or "dbo", catalog
                    )
                    if "columns" in cols:
                        col_names = [c["name"] for c in cols["columns"]]
                        hint_lines.append(f"  {tbl}: {', '.join(col_names)}")
                except Exception:
                    pass

        hint = ""
        if hint_lines:
            hint = (
                "\n\nAvailable columns in referenced tables:\n"
                + "\n".join(hint_lines)
                + "\n\nFix the column names and call create_chart again."
            )

        return {
            "error": (
                f"SQL validation failed — chart NOT created. "
                f"DB error: {error_msg}{hint}"
            )
        }


def _extract_table_refs(sql: str) -> list[str]:
    """Best-effort extraction of table/view names from SQL (FROM / JOIN)."""
    pattern = r'(?:FROM|JOIN)\s+(?:\[?dbo\]?\.)?\[?(\w+)\]?'
    matches = re.findall(pattern, sql, re.IGNORECASE)
    # Deduplicate preserving order
    seen: set[str] = set()
    result: list[str] = []
    for m in matches:
        low = m.lower()
        if low not in seen and low not in ("select", "as", "on", "where"):
            seen.add(low)
            result.append(m)
    return result


def tool_create_chart(
    database_id: int,
    sql: str,
    chart_name: str,
    viz_type: str,
    x_column: str,
    y_column: str,
    y_aggregate: str = "SUM",
    group_by: list[str] | None = None,
    schema_name: str | None = None,
    catalog: str | None = None,
    save_chart: bool = False,
) -> dict[str, Any]:
    """Create a chart from a SQL query and return an explore URL."""
    try:
        # --- Pre-validate SQL BEFORE doing anything expensive ---
        validation_error = _validate_chart_sql(
            database_id, sql, schema_name, catalog
        )
        if validation_error:
            return validation_error

        # Standardised AI naming: ai_YYYYMMDD_HHMM_Topic
        safe_name = _ai_resource_name(chart_name)

        # MSSQL: strip ORDER BY from virtual dataset SQL — MSSQL disallows
        # ORDER BY in subqueries/derived tables unless TOP/OFFSET is present,
        # and Superset wraps virtual dataset SQL in a subquery for charting.
        dataset_sql = sql
        if _is_mssql(database_id):
            dataset_sql = _strip_trailing_order_by(sql)
            if dataset_sql != sql:
                logger.info(
                    "Stripped ORDER BY from chart SQL for MSSQL compatibility"
                )

        # Step 1: Try to find existing dataset, else create virtual one
        dataset = _find_existing_dataset(database_id, safe_name, schema_name)
        if not dataset:
            dataset = _create_virtual_dataset(
                database_id, dataset_sql, safe_name, schema_name
            )
        dataset_id_val: int = dataset.id

        # Step 2: Build form_data
        form_data = _build_form_data(
            dataset_id=dataset_id_val,
            viz_type=viz_type,
            x_column=x_column,
            y_column=y_column,
            y_aggregate=y_aggregate,
            group_by=group_by,
        )

        # Step 3: Save chart or generate preview URL
        if save_chart:
            from superset.commands.chart.create import CreateChartCommand
            from superset.utils import json as superset_json

            # Enforce naming convention on saved charts
            saved_chart_name = (
                chart_name if chart_name.startswith("ai_")
                else _ai_resource_name(chart_name)
            )
            chart = CreateChartCommand(
                {
                    "slice_name": saved_chart_name,
                    "viz_type": form_data["viz_type"],
                    "datasource_id": dataset_id_val,
                    "datasource_type": "table",
                    "params": superset_json.dumps(form_data),
                }
            ).run()
            explore_url = f"/explore/?slice_id={chart.id}"
            logger.info(
                "Saved chart: id=%s, name=%s, url=%s",
                chart.id, saved_chart_name, explore_url,
            )
        else:
            explore_url = _generate_explore_url(dataset_id_val, form_data)
            logger.info(
                "Generated chart preview: name=%s, url=%s",
                chart_name, explore_url,
            )

        result_data: dict[str, Any] = {
            "action": "open_chart",
            "url": explore_url,
            "chart_name": saved_chart_name if save_chart else chart_name,
            "dataset_name": safe_name,
            "viz_type": viz_type,
            "saved": save_chart,
        }
        if save_chart:
            result_data["chart_id"] = chart.id
        return result_data

    except Exception as ex:
        logger.error("Error creating chart '%s': %s", chart_name, ex, exc_info=True)
        return {"error": f"Failed to create chart: {str(ex)}"}


def tool_create_dashboard(
    chart_ids: list[int],
    dashboard_title: str,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a Superset dashboard from saved chart IDs."""
    try:
        from superset.commands.dashboard.create import CreateDashboardCommand
        from superset.utils import json as superset_json

        # Enforce naming convention
        final_title = (
            dashboard_title if dashboard_title.startswith("ai_")
            else _ai_resource_name(dashboard_title)
        )

        # Build v2 grid layout — 2 charts per row, 6 units wide each
        position_json: dict[str, Any] = {
            "DASHBOARD_VERSION_KEY": "v2",
            "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
            "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": []},
            "HEADER_ID": {"type": "HEADER", "id": "HEADER_ID", "meta": {"text": final_title}},
        }

        # Resolve chart slice names for better labels
        chart_names: dict[int, str] = {}
        try:
            from superset.models.slice import Slice
            for cid in chart_ids:
                s = db.session.query(Slice).filter_by(id=cid).first()
                if s:
                    chart_names[cid] = s.slice_name
        except Exception:
            pass

        for idx, chart_id in enumerate(chart_ids):
            row_idx = idx // 2
            row_key = f"ROW-ai-{row_idx}"
            chart_key = f"CHART-ai-{idx}"

            # Create ROW only for the first chart in each pair
            if row_key not in position_json:
                position_json[row_key] = {
                    "type": "ROW",
                    "id": row_key,
                    "children": [],
                    "meta": {"background": "BACKGROUND_TRANSPARENT"},
                }
                position_json["GRID_ID"]["children"].append(row_key)

            position_json[chart_key] = {
                "type": "CHART",
                "id": chart_key,
                "children": [],
                "meta": {
                    "chartId": chart_id,
                    "width": 6,
                    "height": 50,
                    "sliceName": chart_names.get(chart_id, f"Chart {idx + 1}"),
                },
            }
            position_json[row_key]["children"].append(chart_key)

        payload: dict[str, Any] = {
            "dashboard_title": final_title,
            "position_json": superset_json.dumps(position_json),
            "json_metadata": superset_json.dumps({
                "default_filters": "{}",
                "expanded_slices": {},
                "refresh_frequency": 0,
                "timed_refresh_immune_slices": [],
                "color_scheme": "",
            }),
        }
        if description:
            payload["description"] = description

        dashboard = CreateDashboardCommand(payload).run()
        db.session.commit()

        dashboard_url = f"/superset/dashboard/{dashboard.id}/"
        logger.info(
            "Created dashboard: id=%s, title=%s, charts=%s, url=%s",
            dashboard.id, final_title, chart_ids, dashboard_url,
        )

        return {
            "action": "open_dashboard",
            "dashboard_id": dashboard.id,
            "dashboard_title": final_title,
            "dashboard_url": dashboard_url,
            "chart_count": len(chart_ids),
        }

    except Exception as ex:
        logger.error("Error creating dashboard '%s': %s", dashboard_title, ex, exc_info=True)
        return {"error": f"Failed to create dashboard: {str(ex)}"}


# --------------------------------------------------------------------------
# Tool dispatcher
# --------------------------------------------------------------------------

# Actions that are passed to the frontend without backend execution
FRONTEND_ACTIONS: set[str] = {"ask_user", "update_todo"}

# Tools whose results contain actions to relay to the frontend
TOOLS_WITH_ACTIONS = {"set_editor_sql", "create_chart", "create_dashboard", "ask_user", "update_todo"}


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

    if tool_name == "list_views":
        return tool_list_views(
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

    if tool_name == "set_editor_sql":
        return tool_set_editor_sql(
            database_id=database_id,
            sql=arguments["sql"],
            schema_name=schema_name,
            catalog=catalog,
        )

    if tool_name == "execute_sql":
        return tool_execute_sql(
            database_id,
            sql=arguments["sql"],
            schema_name=schema_name,
            catalog=catalog,
        )

    if tool_name == "create_chart":
        return tool_create_chart(
            database_id=database_id,
            sql=arguments["sql"],
            chart_name=arguments["chart_name"],
            viz_type=arguments["viz_type"],
            x_column=arguments["x_column"],
            y_column=arguments["y_column"],
            y_aggregate=arguments.get("y_aggregate", "SUM"),
            group_by=arguments.get("group_by"),
            schema_name=schema_name,
            catalog=catalog,
            save_chart=arguments.get("save_chart", False),
        )

    # Dataset management tools
    if tool_name == "list_datasets":
        return tool_list_datasets(
            database_id=database_id,
            search=arguments.get("search"),
        )

    if tool_name == "get_dataset":
        return tool_get_dataset(
            dataset_id=arguments["dataset_id"],
        )

    if tool_name == "update_dataset":
        return tool_update_dataset(
            dataset_id=arguments["dataset_id"],
            description=arguments.get("description"),
            sql=arguments.get("sql"),
            columns=arguments.get("columns"),
        )

    # Chart management tools
    if tool_name == "list_charts":
        return tool_list_charts(
            search=arguments.get("search"),
            dataset_id=arguments.get("dataset_id"),
        )

    if tool_name == "get_chart":
        return tool_get_chart(
            chart_id=arguments["chart_id"],
        )

    if tool_name == "update_chart":
        return tool_update_chart(
            chart_id=arguments["chart_id"],
            chart_name=arguments.get("chart_name"),
            description=arguments.get("description"),
            viz_type=arguments.get("viz_type"),
            params=arguments.get("params"),
            datasource_id=arguments.get("datasource_id"),
        )

    if tool_name == "create_dashboard":
        return tool_create_dashboard(
            chart_ids=arguments["chart_ids"],
            dashboard_title=arguments["dashboard_title"],
            description=arguments.get("description"),
        )

    return {"error": f"Unknown tool: {tool_name}"}
