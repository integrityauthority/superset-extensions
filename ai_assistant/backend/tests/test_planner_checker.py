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

"""The checker must see enough to judge whether a total is right.

A step that returns rows can still report the wrong number — e.g. picking the
"latest" invoice revision by arrival order instead of by revision. The checker
can only catch that if it receives the discovered columns and the SQL that ran.
"""

from __future__ import annotations

import pytest

from ai_assistant import planner
from ai_assistant.planner import (
    CHECK_SYSTEM_PROMPT,
    PLAN_SYSTEM_PROMPT,
    ExecutionPlan,
    PlanContext,
    PlanStep,
    check_step_result,
)

INVOICE_SQL = (
    "WITH ranked AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY invoice_id "
    "ORDER BY seq DESC) AS rn FROM invoice_changes) "
    "SELECT COUNT(*), SUM(amount_cents) FROM ranked WHERE rn = 1"
)


def _plan_with_executed_step() -> tuple[ExecutionPlan, PlanStep]:
    context = PlanContext(
        db_backend="postgresql",
        tables={"invoice_changes": ["seq", "invoice_id", "revision", "amount_cents"]},
        views={"v_invoices": ["invoice_id", "amount_cents"]},
        step_results={"1": "should not be resent to the checker"},
    )
    step = PlanStep(
        step_id=1,
        description="Total of latest invoice revisions",
        request=INVOICE_SQL,
        expected_outcome="One row with invoice count and total",
        status="done",
        result_summary="1 row",
        context_snippet=f"Executed SQL: {INVOICE_SQL}\nResult: {{\"row_count\": 1}}",
    )
    chart = PlanStep(
        step_id=2,
        description="Chart the total",
        request="create_chart using the step 1 query",
        expected_outcome="Saved chart",
    )
    plan = ExecutionPlan(question="What is the invoice total?", steps=[step, chart], context=context)
    return plan, step


def test_schema_block_lists_dialect_tables_and_views_only():
    plan, _ = _plan_with_executed_step()
    block = plan.context.schema_block()

    assert "SQL dialect: postgresql" in block
    assert "invoice_changes: seq, invoice_id, revision, amount_cents" in block
    assert "v_invoices: invoice_id, amount_cents" in block
    assert "should not be resent" not in block


def test_schema_block_empty_context():
    assert PlanContext().schema_block() == ""


def test_checker_prompt_carries_schema_and_executed_sql(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, str] = {}

    def fake_llm(system_prompt: str, user_prompt: str, provider_config, provider) -> str:
        captured["system"] = system_prompt
        captured["user"] = user_prompt
        return "[]"

    monkeypatch.setattr(planner, "_llm_plan_call", fake_llm)
    plan, step = _plan_with_executed_step()

    assert check_step_result(plan, step, provider_config={}, provider="test") == []
    assert captured["system"] is CHECK_SYSTEM_PROMPT
    # The version column must be visible, or rule 2a can never fire.
    assert "invoice_changes: seq, invoice_id, revision, amount_cents" in captured["user"]
    assert "Executed SQL:" in captured["user"]
    assert "ORDER BY seq DESC" in captured["user"]


def test_checker_prompt_without_discovered_schema(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, str] = {}

    def fake_llm(system_prompt: str, user_prompt: str, provider_config, provider) -> str:
        captured["user"] = user_prompt
        return "[]"

    monkeypatch.setattr(planner, "_llm_plan_call", fake_llm)
    step = PlanStep(step_id=1, description="d", request="r", expected_outcome="e", status="done")
    check_step_result(ExecutionPlan(question="q", steps=[step]), step, {}, "test")

    assert "SCHEMA:\n(no schema discovered)" in captured["user"]


def test_checker_keeps_partial_results_but_checks_aggregate_semantics():
    # Partial results stay a success for exploration…
    assert "unless rule 2 applies" in CHECK_SYSTEM_PROMPT
    # …but evident aggregate defects are corrected downstream, never on speculation.
    for needle in ("arrival or insert order", "one-to-many", "Never flag on speculation"):
        assert needle in CHECK_SYSTEM_PROMPT
    # Correction must not rewrite the step that already ran.
    assert "leave the executed step as it is" in CHECK_SYSTEM_PROMPT


def test_planner_requires_authoritative_row_by_version_column():
    assert "Aggregate correctness" in PLAN_SYSTEM_PROMPT
    assert "NEVER by arrival or" in PLAN_SYSTEM_PROMPT
