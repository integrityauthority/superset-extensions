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
Vambery's tools for Superset's MCP server (Superset 7.0+).

Superset's own MCP server already exposes the building blocks (SQL, charts,
dashboards, datasets). What it does not have is the agent: planning across
several queries, checking the result against the schema, and stating the
assumptions behind each number. That is what ``ask`` publishes.

Registered at extension load, so the host prefixes the name:
``extensions.integrityauthority.vambery-ai-assistant.ask``. Calls run as the
user the MCP request authenticated as (API key or JWT), with the same
permission checks as the chat panel, and need SQL Lab's
``can_execute_sql_query``.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _collect(result: dict[str, Any]) -> dict[str, Any]:
    """Reduce an agent run to what an external caller can use."""
    actions = result.get("actions") or []
    sql = [a.get("sql") for a in actions if a.get("type") in ("set_editor_sql", "open_sql_tab")]
    charts = [
        {"name": a.get("chart_name"), "url": a.get("url"), "saved": a.get("saved")}
        for a in actions
        if a.get("type") == "open_chart"
    ]
    dashboards = [
        {"id": a.get("dashboard_id"), "url": a.get("dashboard_url")}
        for a in actions
        if a.get("type") == "open_dashboard"
    ]
    questions = [
        {"question": a.get("question"), "options": [o.get("label") for o in a.get("options", [])]}
        for a in actions
        if a.get("type") == "ask_user"
    ]
    return {
        "answer": result.get("response", ""),
        "sql": sql[-1] if sql else None,
        "charts": charts,
        "dashboards": dashboards,
        "needs_clarification": questions[-1] if questions else None,
        "tools_used": [s.get("tool") for s in result.get("steps", []) if s.get("tool")],
    }


def register() -> None:
    from superset_core.mcp.decorators import tool

    @tool(
        name="ask",
        tags=["vambery", "agent"],
        class_permission_name="SQLLab",
        method_permission_name="execute_sql_query",
    )
    def ask(
        question: str,
        database_id: int,
        schema: str | None = None,
        allow_changes: bool = False,
    ) -> dict[str, Any]:
        """Answer a data question with Vambery, the Superset AI agent.

        Vambery explores the schema, plans and runs read-only SQL, checks that
        aggregates have the right grain (latest revision per key, no sums
        across one-to-many joins), and returns the answer with the SQL it
        used and the assumptions behind each number.

        Args:
            question: The question, in any language.
            database_id: Superset database id (see Superset's list_databases).
            schema: Schema to work in; defaults to the database default.
            allow_changes: Let the agent save charts and create or edit
                datasets and dashboards. Off by default: the call only reads.

        Returns answer (text), sql (the final query), charts, dashboards,
        needs_clarification (a question to answer in a follow-up call) and
        tools_used.
        """
        from ai_assistant.access import get_database
        from ai_assistant.agent import run_agent
        from ai_assistant.tools import read_only_session

        get_database(database_id)
        note = (
            "\n\n(Asked through Superset's MCP API by another program: there is no "
            "SQL editor or browser on the other end. Put the final SQL in your "
            "answer as a code block"
            + ("" if allow_changes else "; this session is read-only")
            + ".)"
        )
        with read_only_session(not allow_changes):
            result = run_agent(
                messages=[{"role": "user", "content": question + note}],
                database_id=database_id,
                schema_name=schema,
            )
        return _collect(result)
