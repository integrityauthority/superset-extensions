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
Tool parity harness: runs every agent tool with fixed inputs inside a live
Superset and writes the normalised results as JSON.

Run it against two Vambery versions and compare the files with
compare_parity.py. Nothing here calls an LLM, so the runs are deterministic.

Usage, inside the Superset app container (the examples database must exist):

    PARITY_USER=admin PARITY_DB=1 PARITY_OUT=/tmp/parity-0.8.json \
        python run_parity.py

PARITY_USER is the Superset user the tools run as. With a restricted user the
results show which calls the permission checks refuse.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

from superset.app import create_app

USER = os.environ.get("PARITY_USER", "admin")
DB_ID = int(os.environ.get("PARITY_DB", "1"))
SCHEMA = os.environ.get("PARITY_SCHEMA", "public")
OUT = os.environ.get("PARITY_OUT", "/tmp/parity.json")

TABLE = "birth_names"
# Unique per run, so lookups never pick up objects left by an earlier run.
RUN = f"Parity{os.getpid()}"
GOOD_SQL = (
    "SELECT gender, SUM(num) AS total FROM birth_names "
    "GROUP BY gender ORDER BY gender"
)

# Volatile values are masked so two runs compare equal when behaviour matches.
_MASKS = [
    (re.compile(r"ai_\d{8}_\d{4}_"), "ai_<ts>_"),
    (re.compile(r"Parity\d+"), "Parity"),
    (re.compile(r"slice_id=\d+"), "slice_id=<id>"),
    (re.compile(r"\d+__table"), "<id>__table"),
    (re.compile(r"form_data_key=[\w-]+"), "form_data_key=<key>"),
    (re.compile(r"/dashboard/\d+/"), "/dashboard/<id>/"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(\.\d+)?"), "<datetime>"),
]
_ID_KEYS = {"chart_id", "dashboard_id", "dataset_id", "id"}


def _normalise(value: Any, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {k: _normalise(v, k) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_normalise(v) for v in value]
    if key in _ID_KEYS and isinstance(value, int):
        return "<id>"
    if isinstance(value, str):
        for pattern, repl in _MASKS:
            value = pattern.sub(repl, value)
        return value
    return value


def _cleanup(db: Any) -> None:
    """Delete the charts, dashboards and datasets this run created."""
    from superset.connectors.sqla.models import SqlaTable
    from superset.models.dashboard import Dashboard
    from superset.models.slice import Slice

    for model, column in (
        (Dashboard, Dashboard.dashboard_title),
        (Slice, Slice.slice_name),
        (SqlaTable, SqlaTable.table_name),
    ):
        for obj in db.session.query(model).filter(column.like(f"%{RUN}%")).all():
            db.session.delete(obj)
    db.session.commit()


def main() -> int:  # noqa: C901
    app = create_app()
    with app.app_context(), app.test_request_context():
        from flask import g
        from flask_login import login_user

        from superset.extensions import db, security_manager

        user = (
            db.session.query(security_manager.user_model)
            .filter_by(username=USER)
            .one()
        )
        g.user = user
        login_user(user)

        from ai_assistant import __version__
        from ai_assistant.tools import discover_schema, execute_tool

        results: dict[str, Any] = {"version": __version__, "user": USER}
        state: dict[str, Any] = {}

        def run(name: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
            try:
                out = execute_tool(tool, args, DB_ID, SCHEMA, None)
            except Exception as ex:  # noqa: BLE001
                out = {"exception": type(ex).__name__, "message": str(ex)}
            results[name] = _normalise(out)
            return out

        run("list_schemas", "list_schemas", {})
        run("list_tables", "list_tables", {"schema_name": SCHEMA})
        run("list_views", "list_views", {"schema_name": SCHEMA})
        run("get_table_columns", "get_table_columns",
            {"table_name": TABLE, "schema_name": SCHEMA})
        run("sample_table_data", "sample_table_data",
            {"table_name": TABLE, "schema_name": SCHEMA})
        run("get_distinct_values", "get_distinct_values",
            {"table_name": TABLE, "schema_name": SCHEMA, "column_name": "gender"})
        run("execute_sql", "execute_sql", {"sql": GOOD_SQL})
        # The same statement again is answered from Superset's result cache,
        # which returns rows in a different shape than a fresh query.
        run("execute_sql_cached", "execute_sql", {"sql": GOOD_SQL})
        run("execute_sql_cte", "execute_sql",
            {"sql": f"WITH t AS ({GOOD_SQL}) SELECT * FROM t"})
        run("execute_sql_delete", "execute_sql", {"sql": "DELETE FROM birth_names"})
        run("execute_sql_stacked", "execute_sql",
            {"sql": "SELECT 1; DELETE FROM birth_names WHERE 1 = 0"})
        run("execute_sql_bad_column", "execute_sql",
            {"sql": "SELECT no_such_column FROM birth_names"})
        run("set_editor_sql", "set_editor_sql", {"sql": GOOD_SQL})
        run("set_editor_sql_bad", "set_editor_sql",
            {"sql": "SELECT no_such_column FROM birth_names"})
        run("set_editor_sql_ddl", "set_editor_sql", {"sql": "DROP TABLE birth_names"})

        run("create_chart_preview", "create_chart", {
            "chart_name": f"{RUN} births by gender", "viz_type": "bar",
            "sql": GOOD_SQL, "x_column": "gender", "y_column": "total",
        })
        saved = run("create_chart_saved", "create_chart", {
            "chart_name": f"{RUN} births by gender saved", "viz_type": "pie",
            "sql": GOOD_SQL, "x_column": "gender", "y_column": "total",
            "save_chart": True,
        })
        state["chart_id"] = saved.get("chart_id")

        datasets = run("list_datasets", "list_datasets", {"search": RUN})
        found = [d for d in datasets.get("datasets", []) if f"{RUN}_births_by_gender_saved" in d["name"]]
        state["dataset_id"] = found[-1]["id"] if found else None

        if state["dataset_id"]:
            run("get_dataset", "get_dataset", {"dataset_id": state["dataset_id"]})
            run("update_dataset", "update_dataset", {
                "dataset_id": state["dataset_id"],
                "description": "Parity run",
                "columns": [{"column_name": "total", "verbose_name": "Total births"}],
            })
            # New in 0.8: metrics, calculated columns and querying by name.
            run("update_dataset_metric", "update_dataset", {
                "dataset_id": state["dataset_id"],
                "metrics": [{"metric_name": "total_sum", "expression": "SUM(total)"}],
                "calculated_columns": [{
                    "column_name": "is_girl",
                    "expression": "CASE WHEN gender = 'girl' THEN 1 ELSE 0 END",
                    "type": "INTEGER",
                }],
            })
            run("query_dataset", "query_dataset", {
                "dataset_id": state["dataset_id"],
                "metrics": ["total_sum"], "dimensions": ["gender"],
                "order": [{"column": "gender", "descending": False}],
            })
            run("query_dataset_calc", "query_dataset", {
                "dataset_id": state["dataset_id"],
                "metrics": ["total_sum"], "dimensions": ["is_girl"],
                "order": [{"column": "is_girl", "descending": False}],
            })
            run("query_dataset_bad_metric", "query_dataset", {
                "dataset_id": state["dataset_id"], "metrics": ["no_such_metric"],
            })
        if state["chart_id"]:
            run("list_charts", "list_charts", {"search": f"{RUN}_births_by_gender_saved"})
            run("get_chart", "get_chart", {"chart_id": state["chart_id"]})
            run("update_chart", "update_chart", {
                "chart_id": state["chart_id"],
                "description": "Parity run",
                "params": {"show_legend": False},
            })
            dash = run("create_dashboard", "create_dashboard", {
                "dashboard_title": f"{RUN} dashboard",
                "chart_ids": [state["chart_id"]],
            })
            state["dashboard_id"] = dash.get("dashboard_id")

        # New in 0.9: find and edit existing dashboards.
        if state.get("dashboard_id") and state["chart_id"]:
            dash_id = state["dashboard_id"]
            second = execute_tool("create_chart", {
                "chart_name": f"{RUN} second chart", "viz_type": "bar",
                "sql": GOOD_SQL, "x_column": "gender", "y_column": "total",
                "save_chart": True,
            }, DB_ID, SCHEMA, None).get("chart_id")
            run("list_dashboards", "list_dashboards", {"search": RUN})
            run("update_dashboard_add", "update_dashboard", {
                "dashboard_id": dash_id, "dashboard_title": f"{RUN} renamed",
                "add_chart_ids": [second],
                "add_filters": [{"name": "Gender", "dataset_id": state["dataset_id"],
                                 "column": "gender"}],
            })
            run("update_dashboard_bad_column", "update_dashboard", {
                "dashboard_id": dash_id,
                "add_filters": [{"name": "X", "dataset_id": state["dataset_id"],
                                 "column": "no_such_column"}],
            })
            run("update_dashboard_reorder", "update_dashboard", {
                "dashboard_id": dash_id, "chart_order": [second, state["chart_id"]],
            })
            run("get_dashboard_after_add", "get_dashboard", {"dashboard_id": dash_id})
            run("update_dashboard_remove", "update_dashboard", {
                "dashboard_id": dash_id, "remove_chart_ids": [second],
                "remove_filters": ["Gender"],
            })
            run("get_dashboard_after_remove", "get_dashboard", {"dashboard_id": dash_id})

        # A chart someone else owns: reading may be allowed, editing is not.
        if os.environ.get("PARITY_FOREIGN_CHART"):
            foreign = int(os.environ["PARITY_FOREIGN_CHART"])
            run("get_foreign_chart", "get_chart", {"chart_id": foreign})
            run("update_foreign_chart", "update_chart", {
                "chart_id": foreign, "description": "Parity run",
            })

        run("ask_user", "ask_user", {
            "question": "Which?", "options": [{"id": "a", "label": "A"}],
        })
        run("update_todo", "update_todo", {
            "items": [{"id": "1", "text": "step", "status": "done"}],
        })
        run("unknown_tool", "no_such_tool", {})

        _cleanup(db)

        try:
            discovered = discover_schema(DB_ID, SCHEMA, None, "births by gender")
            results["discover_schema"] = _normalise({
                "tables": sorted(discovered.get("tables", {})),
                "views": sorted(discovered.get("views", {})),
                "db_backend": discovered.get("db_backend"),
            })
        except Exception as ex:  # noqa: BLE001
            results["discover_schema"] = {"exception": type(ex).__name__}

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=1, sort_keys=True, default=str)
    print(f"wrote {OUT}: {len(results) - 2} cases, version {results['version']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
