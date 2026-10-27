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
Agent evaluation: real questions through the whole agent (planner, tools,
LLM), checked against known answers.

Prompt rules are not enforcement; this set is. Run it before and after any
prompt or planner change, on the same model, and compare the pass counts.

Prerequisites, on a test instance only:
- the examples database (PostgreSQL), with ``synthetic_postgres.sql`` loaded
  and SELECT on schema ``vambery_eval`` granted to the connection's user;
- an LLM provider configured for Vambery.

Usage, inside the Superset app container:

    EVAL_DB=1 EVAL_OUT=/tmp/eval.json python run_eval.py [case ...]

Each case is judged on the final answer text and on which tools ran. LLM
output varies between runs, so a single failure is a signal to look, and the
pass count over several runs is the measure.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from superset.app import create_app

USER = os.environ.get("EVAL_USER", "admin")
DB_ID = int(os.environ.get("EVAL_DB", "1"))
OUT = os.environ.get("EVAL_OUT", "/tmp/eval.json")


def _number(text: str, value: float) -> bool:
    """Whether `value` appears in `text`, in any common thousands format."""
    digits = re.sub(r"(?<=\d)[\s,.  ](?=\d{3}\b)", "", text)
    return re.search(rf"(?<![\d.]){int(value)}(?:[.,]0+)?(?!\d)", digits) is not None


@dataclass
class Case:
    name: str
    question: str
    schema: str
    checks: list[tuple[str, Callable[[str, list[str]], bool]]]
    setup: Callable[[], dict[str, Any]] | None = None
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def _setup_dashboard() -> dict[str, Any]:
    """A dashboard with one chart, for the edit-in-place case."""
    from ai_assistant.tools import execute_tool

    chart = execute_tool("create_chart", {
        "chart_name": "EvalBirths", "viz_type": "bar",
        "sql": "SELECT gender, SUM(num) AS total FROM birth_names GROUP BY gender",
        "x_column": "gender", "y_column": "total", "save_chart": True,
    }, DB_ID, "public", None)
    dash = execute_tool("create_dashboard", {
        "dashboard_title": "EvalBirths board", "chart_ids": [chart["chart_id"]],
    }, DB_ID, "public", None)
    return {"dashboard_id": dash["dashboard_id"], "title": dash["dashboard_title"]}


CASES = [
    Case(
        name="births_by_gender",
        schema="public",
        question="How many births are recorded for each gender in birth_names?",
        checks=[
            ("boys total 48133355", lambda a, t: _number(a, 48133355)),
            ("girls total 32546308", lambda a, t: _number(a, 32546308)),
            ("query placed in the editor", lambda a, t: "set_editor_sql" in t),
        ],
    ),
    Case(
        name="late_revision",
        schema="vambery_eval",
        question="What is the total amount of all invoices in the invoices table?",
        checks=[
            ("total is 20000 (latest revision per invoice)", lambda a, t: _number(a, 20000)),
            ("not the replay-skewed 18000", lambda a, t: not _number(a, 18000)),
        ],
        notes="Latest row by loaded_at picks a replayed old revision for invoice 3.",
    ),
    Case(
        name="join_fanout",
        schema="vambery_eval",
        question="What is the total value of all orders that have items?",
        checks=[
            ("total is 600", lambda a, t: _number(a, 600)),
            ("not the fanned-out 1100", lambda a, t: not _number(a, 1100)),
        ],
        notes="SUM(order_total) across the order_items join counts orders once per item.",
    ),
    Case(
        name="conflicting_duplicates",
        schema="vambery_eval",
        question="What is the total of the latest revision of every invoice in invoice_conflicts?",
        checks=[
            (
                "reports the conflict for invoice 2",
                lambda a, t: re.search(
                    r"conflict|duplicate|ambiguous|two (different )?amounts|ellentmond|duplik",
                    a, re.I,
                ) is not None,
            ),
        ],
        notes="Invoice 2 revision 2 has two amounts; a single total hides that.",
    ),
    Case(
        name="edit_existing_dashboard",
        schema="public",
        question="Add a gender filter to the dashboard called '{title}'.",
        setup=_setup_dashboard,
        checks=[
            ("used update_dashboard", lambda a, t: "update_dashboard" in t),
            ("did not create a new dashboard", lambda a, t: "create_dashboard" not in t),
        ],
    ),
]


def _tool_names(result: dict[str, Any]) -> list[str]:
    names = []
    for step in result.get("steps", []):
        name = step.get("tool") or step.get("name") or step.get("tool_name")
        if name:
            names.append(name)
    return names


def main() -> int:
    wanted = set(sys.argv[1:])
    app = create_app()
    report: dict[str, Any] = {"cases": {}}
    with app.app_context(), app.test_request_context():
        from flask import g
        from flask_login import login_user

        from superset.extensions import db, security_manager

        user = db.session.query(security_manager.user_model).filter_by(username=USER).one()
        g.user = user
        login_user(user)

        from ai_assistant import __version__
        from ai_assistant.agent import run_agent
        from ai_assistant.config import get_ai_config

        config = get_ai_config()
        provider = config["provider"]
        report["version"] = __version__
        report["model"] = f"{provider}/{config.get(provider, {}).get('deployment_name') or config.get(provider, {}).get('model')}"

        passed = 0
        for case in CASES:
            if wanted and case.name not in wanted:
                continue
            extra = case.setup() if case.setup else {}
            question = case.question.format(**extra)
            started = time.time()
            try:
                result = run_agent(
                    messages=[{"role": "user", "content": question}],
                    database_id=DB_ID,
                    schema_name=case.schema,
                )
            except Exception as ex:  # noqa: BLE001
                result = {"response": f"EXCEPTION {type(ex).__name__}: {ex}", "steps": []}
            answer = result.get("response", "")
            tools = _tool_names(result)
            outcomes = {label: bool(check(answer, tools)) for label, check in case.checks}
            ok = all(outcomes.values())
            passed += ok
            report["cases"][case.name] = {
                "pass": ok,
                "checks": outcomes,
                "seconds": round(time.time() - started, 1),
                "tools": tools,
                "answer": answer,
                "notes": case.notes,
            }
            print(f"{'PASS' if ok else 'FAIL'} {case.name} ({report['cases'][case.name]['seconds']}s) "
                  + ", ".join(f"{k}: {v}" for k, v in outcomes.items()))
        report["passed"] = passed
        report["total"] = len(report["cases"])

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, ensure_ascii=False)
    print(f"{passed}/{report['total']} passed ({report['version']}, {report['model']}) -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
