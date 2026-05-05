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
Vambery AI Agent — Planner & Checker.

Implements a code-enforced plan→execute→check→replan loop inspired by
app-vanna's Executor pattern.  The planner creates a structured JSON
execution plan from a natural-language question, and the checker validates
each step's result — updating the plan when results are empty, wrong, or
reveal new identifiers that later steps should use.

The planner is invoked from ``agent.py`` and operates *inside* the existing
SSE streaming pipeline so the frontend sees live ``update_todo`` progress.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Any

from ai_assistant.llm import create_chat_completion

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PlanStep:
    step_id: int
    description: str
    request: str
    expected_outcome: str
    # Runtime state — filled during execution
    status: str = "pending"          # pending | in_progress | done | error
    result_summary: str | None = None
    error: str | None = None
    retry_count: int = 0
    # Collected context from tool results (kept compact for the checker)
    context_snippet: str | None = None


@dataclass
class ExecutionPlan:
    question: str
    steps: list[PlanStep] = field(default_factory=list)
    summary: str | None = None


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

PLAN_SYSTEM_PROMPT = """\
You are a query planner for Apache Superset SQL Lab.

Given a user question and database/schema context, create a step-by-step \
execution plan.  Each step will be executed by an AI agent that has access \
to tools: list_schemas, list_tables, list_views, get_table_columns, \
sample_table_data, get_distinct_values, execute_sql, set_editor_sql, \
create_chart, list_datasets, get_dataset, update_dataset, list_charts, \
get_chart, update_chart.

Rules:
- First steps should explore the schema (list tables/views, inspect columns).
- Middle steps should write, test, and refine SQL queries.
- Later steps should deliver results: set_editor_sql, create_chart, etc.
- Each step should have a clear, measurable expected_outcome so the checker \
  can decide whether the step succeeded.
- If the task involves multiple independent queries or charts, plan separate \
  steps for each.
- Steps may reference results from earlier steps (e.g. "use the company IDs \
  found in step 1").
- Return ONLY a JSON array — no markdown fences, no explanation.

Output format:
[
  {
    "step_id": 1,
    "description": "Short human-readable label",
    "request": "Detailed instruction for the agent executing this step",
    "expected_outcome": "What a successful result looks like"
  }
]
"""

CHECK_SYSTEM_PROMPT = """\
You are a step-result checker for an Apache Superset SQL Lab AI agent.

After each step in the execution plan you will receive:
- The original user question
- The full plan (with statuses)
- The latest step's result (summary + optional data snippet)

Your job:
1. Decide whether the step succeeded relative to its expected_outcome.
2. If the result is empty, erroneous, or clearly wrong:
   - Return a JSON array of MODIFIED or NEW steps (from the current position \
     onward) so the executor can re-plan.
   - You may add, remove, or rewrite future steps.
3. If the step succeeded AND you discovered useful identifiers, names, IDs, \
   or other concrete data:
   - Update the `request` field of remaining steps to include that data \
     (e.g. "use company_id=42 found in step 2").
4. If everything is fine and no changes are needed, return an empty JSON \
   array: []

SUPER IMPORTANT: propagate discovered identifiers / concrete data to \
remaining steps so the SQL generator can use them.

IMPORTANT: step_id values MUST be integers (not strings like "5b").
Use the existing step_id for updates, or the next sequential integer for \
new steps.

Return ONLY the JSON array — no markdown, no explanation.
"""

# ---------------------------------------------------------------------------
# Helper: call LLM for planning (no tools, just text)
# ---------------------------------------------------------------------------

def _llm_plan_call(
    system_prompt: str,
    user_prompt: str,
    provider_config: dict[str, Any],
    provider: str,
) -> str:
    """Fire a simple system+user chat completion (no tools) and return text."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    result = create_chat_completion(
        provider_config=provider_config,
        provider=provider,
        messages=messages,
        tools=None,
    )
    return (result.get("message") or {}).get("content") or ""


def _parse_json_array(text: str) -> list[dict[str, Any]]:
    """Extract a JSON array from LLM output (handles markdown fences)."""
    # Strip markdown code fences if present
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if m:
        text = m.group(1).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        logger.warning("Planner: failed to parse JSON from LLM output: %s", text[:300])
    return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_plan(
    question: str,
    schema_context: str,
    provider_config: dict[str, Any],
    provider: str,
    max_steps: int = 15,
) -> ExecutionPlan:
    """Ask the LLM to generate a structured execution plan.

    Args:
        question: The user's natural-language question.
        schema_context: A short description of the current database/schema
            context (db name, schema, dialect, etc.) to ground the planner.
        provider_config: LLM provider configuration dict.
        provider: LLM provider name.
        max_steps: Upper bound on the number of plan steps.

    Returns:
        An ``ExecutionPlan`` with parsed steps, or a single fallback step
        if the LLM fails to produce a valid plan.
    """
    user_prompt = (
        f"Database context:\n{schema_context}\n\n"
        f"Max steps allowed: {max_steps}\n\n"
        f"Create a query plan for:\n{question}"
    )

    raw = _llm_plan_call(PLAN_SYSTEM_PROMPT, user_prompt, provider_config, provider)
    logger.info("Planner raw output (%d chars): %s", len(raw), raw[:500])

    parsed = _parse_json_array(raw)
    if not parsed:
        # Fallback: single generic step so execution still proceeds
        logger.warning("Planner produced no valid steps — using fallback plan")
        parsed = [{
            "step_id": 1,
            "description": "Execute the user's request",
            "request": question,
            "expected_outcome": "A useful result is returned",
        }]

    steps = [
        PlanStep(
            step_id=s.get("step_id", idx + 1),
            description=s.get("description", f"Step {idx + 1}"),
            request=s.get("request", ""),
            expected_outcome=s.get("expected_outcome", ""),
        )
        for idx, s in enumerate(parsed[:max_steps])
    ]

    plan = ExecutionPlan(question=question, steps=steps)
    logger.info("Planner created plan with %d steps", len(plan.steps))
    return plan


def check_step_result(
    plan: ExecutionPlan,
    current_step: PlanStep,
    provider_config: dict[str, Any],
    provider: str,
) -> list[dict[str, Any]]:
    """Validate the result of the just-executed step and optionally re-plan.

    Returns:
        A list of step dicts to replace/extend the remaining plan,
        or ``[]`` if no changes are needed.
    """
    # Build a compact view of the plan for the checker
    plan_snapshot = []
    for s in plan.steps:
        entry: dict[str, Any] = {
            "step_id": s.step_id,
            "description": s.description,
            "request": s.request,
            "expected_outcome": s.expected_outcome,
            "status": s.status,
        }
        if s.result_summary:
            entry["result_summary"] = s.result_summary
        if s.error:
            entry["error"] = s.error
        if s.context_snippet:
            entry["context_snippet"] = s.context_snippet
        plan_snapshot.append(entry)

    user_prompt = (
        f"Original question: {plan.question}\n\n"
        f"Full plan:\n{json.dumps(plan_snapshot, indent=2, default=str)}\n\n"
        f"Just executed step {current_step.step_id}: {current_step.description}\n"
        f"Result summary: {current_step.result_summary or '(no result)'}\n"
        f"Error: {current_step.error or '(none)'}\n"
        f"Context snippet: {current_step.context_snippet or '(none)'}\n\n"
        f"Return [] if the result is satisfactory, or a JSON array of "
        f"modified/new steps from this point onward."
    )

    raw = _llm_plan_call(CHECK_SYSTEM_PROMPT, user_prompt, provider_config, provider)
    logger.info("Checker raw output (%d chars): %s", len(raw), raw[:500])
    return _parse_json_array(raw)


def apply_plan_updates(
    plan: ExecutionPlan,
    current_step_index: int,
    updates: list[dict[str, Any]],
    max_steps: int = 15,
) -> None:
    """Merge checker updates into the plan (in place).

    Replaces steps *after* current_step_index with the updated steps.
    New steps get ``status="pending"``; existing step_ids that match
    an update get their request/description refreshed.
    """
    if not updates:
        return

    # Keep steps up to (and including) the current step
    kept = plan.steps[: current_step_index + 1]

    # Build lookup for existing steps (by step_id) that are after current
    existing_map = {s.step_id: s for s in plan.steps[current_step_index + 1 :]}

    for u in updates:
        raw_sid = u.get("step_id")
        # Normalize step_id to int (checker may return strings like "5b")
        sid = None
        if raw_sid is not None:
            try:
                sid = int(raw_sid)
            except (ValueError, TypeError):
                sid = None

        if sid is not None and sid in existing_map:
            # Update existing step
            s = existing_map[sid]
            s.description = u.get("description", s.description)
            s.request = u.get("request", s.request)
            s.expected_outcome = u.get("expected_outcome", s.expected_outcome)
            # Reset execution state so it re-runs
            s.status = "pending"
            s.result_summary = None
            s.error = None
            s.context_snippet = None
            s.retry_count = 0
            kept.append(s)
        else:
            # New step from checker — assign next sequential int ID
            new_id = kept[-1].step_id + 1 if kept else 1
            kept.append(PlanStep(
                step_id=new_id,
                description=u.get("description", f"Step {new_id}"),
                request=u.get("request", ""),
                expected_outcome=u.get("expected_outcome", ""),
            ))

    plan.steps = kept[:max_steps]
    logger.info(
        "Plan updated: now %d steps (was %d before merge)",
        len(plan.steps), current_step_index + 1 + len(existing_map),
    )


def plan_to_todo_items(plan: ExecutionPlan) -> list[dict[str, str]]:
    """Convert plan steps into the ``update_todo`` action payload."""
    return [
        {
            "id": str(s.step_id),
            "text": s.description,
            "status": _map_status(s.status),
        }
        for s in plan.steps
    ]


def _map_status(status: str) -> str:
    """Map planner status values to the frontend todo status values."""
    return {
        "pending": "pending",
        "in_progress": "in_progress",
        "done": "done",
        "error": "error",
    }.get(status, "pending")
