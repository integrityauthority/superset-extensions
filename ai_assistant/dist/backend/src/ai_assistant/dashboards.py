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
Dashboard tools: find, inspect and edit existing dashboards.

Edits go to the dashboard the user named, never a copy. Superset 7.0 keeps a
version history of dashboards, so every change can be reviewed and reverted.

Layout edits work on the v2 ``position_json`` tree. Charts are added in new
rows at the end of the grid, removed wherever they sit, and reordered only in
plain layouts (rows directly under the grid), where the order is unambiguous.
"""

from __future__ import annotations

import json
import logging
import secrets
from typing import Any

from superset_core.common import daos

from superset.connectors.sqla.models import SqlaTable
from superset.extensions import db
from superset.models.dashboard import Dashboard
from superset.models.slice import Slice

from ai_assistant.access import audit, check_editor, find_visible

logger = logging.getLogger(__name__)

CHARTS_PER_ROW = 2
CHART_WIDTH = 6
CHART_HEIGHT = 50

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_dashboards",
            "description": (
                "List existing dashboards the user can see, newest first. "
                "Use this to find a dashboard the user refers to before editing it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "search": {
                        "type": "string",
                        "description": "Optional case-insensitive filter on the title",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dashboard",
            "description": (
                "Get a dashboard's title, description, published state, its charts "
                "in layout order and its native filters."
            ),
            "parameters": {
                "type": "object",
                "properties": {"dashboard_id": {"type": "integer"}},
                "required": ["dashboard_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_dashboard",
            "description": (
                "Edit an EXISTING dashboard in place: title, description, published "
                "state, add or remove charts, reorder charts, add or remove native "
                "value filters. Prefer this over creating a new dashboard whenever "
                "the user talks about a dashboard that already exists. ONLY use it "
                "when the user asks for the change. Changes are kept in the "
                "dashboard's version history and can be reverted."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {"type": "integer"},
                    "dashboard_title": {"type": "string"},
                    "description": {"type": "string"},
                    "published": {"type": "boolean"},
                    "add_chart_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Saved charts to add, in new rows at the end",
                    },
                    "remove_chart_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                    "chart_order": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": (
                            "Chart ids in the desired order; charts not listed keep "
                            "their relative order after them. Plain layouts only."
                        ),
                    },
                    "add_filters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "dataset_id": {"type": "integer"},
                                "column": {"type": "string"},
                                "multi_select": {"type": "boolean"},
                            },
                            "required": ["name", "dataset_id", "column"],
                        },
                        "description": "Native value (select) filters to add",
                    },
                    "remove_filters": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Names (or ids) of native filters to remove",
                    },
                },
                "required": ["dashboard_id"],
            },
        },
    },
]


def _new_id(prefix: str) -> str:
    return f"{prefix}-vambery-{secrets.token_hex(4)}"


def _load_json(text: str | None) -> dict[str, Any]:
    try:
        value = json.loads(text or "{}")
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _chart_components(position: dict[str, Any]) -> list[dict[str, Any]]:
    """CHART components in visual order (depth-first from the root)."""
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()

    def walk(node_id: str) -> None:
        if node_id in seen or node_id not in position:
            return
        seen.add(node_id)
        node = position[node_id]
        if isinstance(node, dict) and node.get("type") == "CHART":
            ordered.append(node)
        for child in node.get("children", []) if isinstance(node, dict) else []:
            walk(child)

    walk("ROOT_ID")
    return ordered


def _parent_of(position: dict[str, Any], node_id: str) -> str | None:
    for key, node in position.items():
        if isinstance(node, dict) and node_id in node.get("children", []):
            return key
    return None


def _empty_position(title: str) -> dict[str, Any]:
    return {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": [], "parents": ["ROOT_ID"]},
        "HEADER_ID": {"type": "HEADER", "id": "HEADER_ID", "meta": {"text": title}},
    }


def _chart_node(chart: Any, row_id: str) -> dict[str, Any]:
    return {
        "type": "CHART",
        "id": _new_id("CHART"),
        "children": [],
        "parents": ["ROOT_ID", "GRID_ID", row_id],
        "meta": {
            "chartId": chart.id,
            "uuid": str(chart.uuid),
            "sliceName": chart.slice_name,
            "width": CHART_WIDTH,
            "height": CHART_HEIGHT,
        },
    }


def _append_rows(position: dict[str, Any], charts: list[Any]) -> None:
    grid = position.setdefault(
        "GRID_ID", {"type": "GRID", "id": "GRID_ID", "children": []}
    )
    for start in range(0, len(charts), CHARTS_PER_ROW):
        row_id = _new_id("ROW")
        row = {
            "type": "ROW",
            "id": row_id,
            "children": [],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        }
        for chart in charts[start : start + CHARTS_PER_ROW]:
            node = _chart_node(chart, row_id)
            position[node["id"]] = node
            row["children"].append(node["id"])
        position[row_id] = row
        grid["children"].append(row_id)


def _remove_charts(position: dict[str, Any], chart_ids: set[int]) -> int:
    removed = 0
    for node in _chart_components(position):
        if node.get("meta", {}).get("chartId") not in chart_ids:
            continue
        parent = _parent_of(position, node["id"])
        if parent:
            position[parent]["children"].remove(node["id"])
            if position[parent].get("type") == "ROW" and not position[parent]["children"]:
                grand = _parent_of(position, parent)
                if grand:
                    position[grand]["children"].remove(parent)
                del position[parent]
        del position[node["id"]]
        removed += 1
    return removed


def _is_plain(position: dict[str, Any]) -> bool:
    """Rows of charts directly under the grid, nothing else."""
    for row_id in position.get("GRID_ID", {}).get("children", []):
        row = position.get(row_id, {})
        if row.get("type") != "ROW":
            return False
        if any(position.get(c, {}).get("type") != "CHART" for c in row.get("children", [])):
            return False
    return True


def _reorder(position: dict[str, Any], order: list[int]) -> None:
    charts = _chart_components(position)
    rank = {chart_id: i for i, chart_id in enumerate(order)}
    charts.sort(key=lambda n: rank.get(n["meta"].get("chartId"), len(order)))
    for row_id in list(position["GRID_ID"]["children"]):
        del position[row_id]
    position["GRID_ID"]["children"] = []
    for start in range(0, len(charts), CHARTS_PER_ROW):
        row_id = _new_id("ROW")
        position[row_id] = {
            "type": "ROW",
            "id": row_id,
            "children": [n["id"] for n in charts[start : start + CHARTS_PER_ROW]],
            "parents": ["ROOT_ID", "GRID_ID"],
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
        }
        for node in charts[start : start + CHARTS_PER_ROW]:
            node["parents"] = ["ROOT_ID", "GRID_ID", row_id]
        position["GRID_ID"]["children"].append(row_id)


def _select_filter(name: str, dataset_id: int, column: str, multi: bool) -> dict[str, Any]:
    return {
        "id": f"NATIVE_FILTER-{secrets.token_urlsafe(15)}",
        "name": name,
        "type": "NATIVE_FILTER",
        "filterType": "filter_select",
        "description": "",
        "targets": [{"datasetId": dataset_id, "column": {"name": column}}],
        "controlValues": {
            "multiSelect": multi,
            "enableEmptyFilter": False,
            "defaultToFirstItem": False,
            "inverseSelection": False,
            "searchAllOptions": False,
        },
        "defaultDataMask": {"extraFormData": {}, "filterState": {}, "ownState": {}},
        "cascadeParentIds": [],
        "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
        "chartsInScope": [],
        "tabsInScope": [],
    }


def _refresh_filter_scopes(position: dict[str, Any], filters: list[dict[str, Any]]) -> None:
    """Keep ``chartsInScope`` right for filters scoped to the whole dashboard.

    Superset stores the charts a filter applies to next to its scope. Filters
    that cover everything (root scope, nothing excluded) must list every chart
    after charts are added or removed; narrower scopes are left as the user
    set them.
    """
    chart_ids = [n["meta"].get("chartId") for n in _chart_components(position)]
    for spec in filters:
        scope = spec.get("scope") or {}
        if scope.get("rootPath") == ["ROOT_ID"] and not scope.get("excluded"):
            spec["chartsInScope"] = list(chart_ids)


def _summary(dashboard: Any) -> dict[str, Any]:
    position = _load_json(dashboard.position_json)
    metadata = _load_json(dashboard.json_metadata)
    charts = [
        {"chart_id": n["meta"].get("chartId"), "name": n["meta"].get("sliceName")}
        for n in _chart_components(position)
    ]
    # Charts attached to the dashboard but missing from the layout still show up
    in_layout = {c["chart_id"] for c in charts}
    charts += [
        {"chart_id": s.id, "name": s.slice_name, "not_in_layout": True}
        for s in dashboard.slices
        if s.id not in in_layout
    ]
    filters = [
        {
            "id": f.get("id"),
            "name": f.get("name"),
            "type": f.get("filterType"),
            "targets": [
                {"dataset_id": t.get("datasetId"), "column": (t.get("column") or {}).get("name")}
                for t in f.get("targets", [])
            ],
        }
        for f in metadata.get("native_filter_configuration", [])
    ]
    return {
        "id": dashboard.id,
        "title": dashboard.dashboard_title,
        "description": dashboard.description,
        "published": bool(dashboard.published),
        "url": f"/superset/dashboard/{dashboard.id}/",
        "charts": charts,
        "native_filters": filters,
        "plain_layout": _is_plain(position),
    }


def tool_list_dashboards(search: str | None = None) -> dict[str, Any]:
    try:
        query = db.session.query(Dashboard)
        if search:
            query = query.filter(Dashboard.dashboard_title.ilike(f"%{search}%"))
        query = query.order_by(Dashboard.changed_on.desc())
        dashboards = daos.DashboardDAO.query(query)[:50]
        return {
            "dashboards": [
                {
                    "id": d.id,
                    "title": d.dashboard_title,
                    "published": bool(d.published),
                    "chart_count": len(d.slices),
                    "url": f"/superset/dashboard/{d.id}/",
                }
                for d in dashboards
            ],
            "count": len(dashboards),
        }
    except Exception as ex:
        logger.error("Error listing dashboards: %s", ex)
        return {"error": str(ex)}


def tool_get_dashboard(dashboard_id: int) -> dict[str, Any]:
    try:
        dashboard = find_visible(daos.DashboardDAO, Dashboard, dashboard_id)
        if dashboard is None:
            return {"error": f"Dashboard with id={dashboard_id} not found"}
        return _summary(dashboard)
    except Exception as ex:
        logger.error("Error getting dashboard %s: %s", dashboard_id, ex)
        return {"error": str(ex)}


def tool_update_dashboard(  # noqa: C901
    dashboard_id: int,
    dashboard_title: str | None = None,
    description: str | None = None,
    published: bool | None = None,
    add_chart_ids: list[int] | None = None,
    remove_chart_ids: list[int] | None = None,
    chart_order: list[int] | None = None,
    add_filters: list[dict[str, Any]] | None = None,
    remove_filters: list[str] | None = None,
) -> dict[str, Any]:
    try:
        dashboard = find_visible(daos.DashboardDAO, Dashboard, dashboard_id)
        if dashboard is None:
            return {"error": f"Dashboard with id={dashboard_id} not found"}
        check_editor(dashboard, f"dashboard '{dashboard.dashboard_title}'")
        audit("update_dashboard", dashboard_id=dashboard_id)

        position = _load_json(dashboard.position_json) or _empty_position(
            dashboard.dashboard_title or ""
        )
        metadata = _load_json(dashboard.json_metadata)
        changes: list[str] = []

        if dashboard_title is not None:
            changes.append(f"title: '{dashboard.dashboard_title}' -> '{dashboard_title}'")
            dashboard.dashboard_title = dashboard_title
            if isinstance(position.get("HEADER_ID"), dict):
                position["HEADER_ID"].setdefault("meta", {})["text"] = dashboard_title
        if description is not None:
            dashboard.description = description
            changes.append("description updated")
        if published is not None:
            dashboard.published = published
            changes.append(f"published: {published}")

        if remove_chart_ids:
            ids = set(remove_chart_ids)
            removed = _remove_charts(position, ids)
            dashboard.slices = [s for s in dashboard.slices if s.id not in ids]
            changes.append(f"removed {removed} chart(s) from the layout")

        if add_chart_ids:
            present = {n["meta"].get("chartId") for n in _chart_components(position)}
            charts, missing = [], []
            for chart_id in add_chart_ids:
                if chart_id in present:
                    continue
                chart = find_visible(daos.ChartDAO, Slice, chart_id)
                (charts if chart is not None else missing).append(chart or chart_id)
            if missing:
                return {"error": f"Charts not found: {missing}. Nothing was changed."}
            _append_rows(position, charts)
            dashboard.slices = list(dashboard.slices) + [
                c for c in charts if c not in dashboard.slices
            ]
            changes.append(f"added {len(charts)} chart(s)")

        if chart_order:
            if not _is_plain(position):
                return {
                    "error": (
                        "This dashboard uses tabs, columns or other components; "
                        "reordering is only supported for plain rows of charts. "
                        "Nothing was changed."
                    )
                }
            _reorder(position, chart_order)
            changes.append("charts reordered")

        filters = metadata.setdefault("native_filter_configuration", [])
        if remove_filters:
            names = set(remove_filters)
            kept = [f for f in filters if f.get("name") not in names and f.get("id") not in names]
            changes.append(f"removed {len(filters) - len(kept)} filter(s)")
            metadata["native_filter_configuration"] = filters = kept
        for spec in add_filters or []:
            dataset = find_visible(daos.DatasetDAO, SqlaTable, int(spec["dataset_id"]))
            if dataset is None:
                return {"error": f"Dataset with id={spec['dataset_id']} not found. Nothing was changed."}
            if spec["column"] not in {c.column_name for c in dataset.columns}:
                return {
                    "error": (
                        f"Column '{spec['column']}' is not in dataset "
                        f"'{dataset.table_name}'. Nothing was changed."
                    )
                }
            filters.append(
                _select_filter(
                    spec["name"], dataset.id, spec["column"], spec.get("multi_select", True)
                )
            )
            changes.append(f"filter '{spec['name']}' added on {dataset.table_name}.{spec['column']}")

        if not changes:
            return {"message": "No changes specified", "dashboard_id": dashboard_id}

        _refresh_filter_scopes(position, filters)
        dashboard.position_json = json.dumps(position)
        dashboard.json_metadata = json.dumps(metadata)
        db.session.commit()
        logger.info("Updated dashboard %s: %s", dashboard_id, "; ".join(changes))
        return {
            "action": "open_dashboard",
            "message": "Dashboard updated. The previous version is in its version history.",
            "dashboard_id": dashboard_id,
            "dashboard_url": f"/superset/dashboard/{dashboard_id}/",
            "changes": changes,
        }
    except Exception as ex:
        db.session.rollback()
        logger.error("Error updating dashboard %s: %s", dashboard_id, ex, exc_info=True)
        return {"error": f"Failed to update dashboard: {ex}"}
