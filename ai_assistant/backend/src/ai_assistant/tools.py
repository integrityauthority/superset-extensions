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

from superset.connectors.sqla.models import SqlaTable
from superset.extensions import db
from superset.models.core import Database
from superset.sql.parse import Table

logger = logging.getLogger(__name__)


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
                "Get column names, data types, nullable info, and metadata for a table. "
                "Returns column comments/descriptions, verbose names, table comment, "
                "and any predefined Superset metrics. "
                "Use this to understand the structure AND business meaning of a table."
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
# Chart creation
# --------------------------------------------------------------------------

# Map simplified viz_type names to Superset viz_type identifiers
VIZ_TYPE_MAP = {
    "bar": "echarts_timeseries_bar",
    "line": "echarts_timeseries_line",
    "pie": "pie",
    "table": "table",
}


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
        # Sanitize dataset name from chart name
        safe_name = f"ai_{chart_name.replace(' ', '_')[:80]}"

        # Step 1: Try to find existing dataset, else create virtual one
        dataset = _find_existing_dataset(database_id, safe_name, schema_name)
        if not dataset:
            dataset = _create_virtual_dataset(
                database_id, sql, safe_name, schema_name
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

            chart = CreateChartCommand(
                {
                    "slice_name": chart_name,
                    "viz_type": form_data["viz_type"],
                    "datasource_id": dataset_id_val,
                    "datasource_type": "table",
                    "params": superset_json.dumps(form_data),
                }
            ).run()
            explore_url = f"/explore/?slice_id={chart.id}"
            logger.info(
                "Saved chart: id=%s, name=%s, url=%s",
                chart.id, chart_name, explore_url,
            )
        else:
            explore_url = _generate_explore_url(dataset_id_val, form_data)
            logger.info(
                "Generated chart preview: name=%s, url=%s",
                chart_name, explore_url,
            )

        return {
            "action": "open_chart",
            "url": explore_url,
            "chart_name": chart_name,
            "viz_type": viz_type,
            "saved": save_chart,
        }

    except Exception as ex:
        logger.error("Error creating chart '%s': %s", chart_name, ex, exc_info=True)
        return {"error": f"Failed to create chart: {str(ex)}"}


# --------------------------------------------------------------------------
# Tool dispatcher
# --------------------------------------------------------------------------

# Actions that are passed to the frontend without backend execution
FRONTEND_ACTIONS = {"set_editor_sql"}

# Tools whose results contain actions to relay to the frontend
TOOLS_WITH_ACTIONS = {"set_editor_sql", "create_chart"}


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

    return {"error": f"Unknown tool: {tool_name}"}
