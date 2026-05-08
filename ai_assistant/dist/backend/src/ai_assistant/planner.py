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

Implements a persistent, phased plan→execute→check→replan loop.

Key concepts:
- **PlanContext**: Rich context object that accumulates discovered data
  (tables, columns, entity IDs) and flows to every step — eliminates
  redundant exploration and column name guessing.
- **Phases**: DISCOVER (code-driven schema exploration) → PLAN (LLM creates
  steps using discovered context) → EXECUTE (steps run with full context) →
  DELIVER (dashboard creation safety net).
- **Persistence**: Plan state is serializable to JSON so the frontend can
  send it back on follow-up messages (e.g. after ask_user).
"""

from __future__ import annotations

import hashlib
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
class PlanContext:
    """Rich context accumulated during plan execution.

    Flows to every step's system prompt, so the LLM never has to guess
    column names or re-discover schema information.
    """
    # Discovery results (populated in DISCOVER phase)
    tables: dict[str, list[str]] = field(default_factory=dict)   # table -> [columns]
    views: dict[str, list[str]] = field(default_factory=dict)    # view -> [columns]
    entity_filter: str | None = None   # rich filter with table/column/value info
    entity_name: str | None = None     # e.g. "HUNIKA Kft"
    db_backend: str = ""               # "mssql" or "postgresql"
    schema_name: str | None = None
    # Sampled distinct values from key categorical columns
    sample_values: dict[str, dict[str, list[str]]] = field(default_factory=dict)

    # Entity candidates offered via ask_user when lookup is ambiguous
    entity_candidates: list[dict[str, str]] = field(default_factory=list)

    # Accumulated during execution
    step_results: dict[str, str] = field(default_factory=dict)  # step_id -> summary
    chart_ids: list[int] = field(default_factory=list)
    dataset_ids: list[int] = field(default_factory=list)
    dashboard_created: bool = False

    # User answers from ask_user
    user_answers: dict[str, str] = field(default_factory=dict)  # question -> answer

    def to_prompt_block(self) -> str:
        """Render context as a text block for the LLM's system prompt."""
        parts: list[str] = []
        if self.db_backend:
            parts.append(f"SQL dialect: {self.db_backend}")
        if self.schema_name:
            parts.append(f"Schema: {self.schema_name}")
        if self.entity_name:
            parts.append(f"Target entity: {self.entity_name}")
        if self.entity_filter:
            parts.append(
                f"*** MANDATORY entity filter — use in EVERY SQL WHERE clause: "
                f"{self.entity_filter} ***"
            )
        if self.tables:
            parts.append("\nDiscovered tables and their columns (ONLY use these):")
            for tbl, cols in self.tables.items():
                parts.append(f"  {tbl}: {', '.join(cols)}")
        if self.views:
            parts.append("\nDiscovered views and their columns (ONLY use these):")
            for vw, cols in self.views.items():
                parts.append(f"  {vw}: {', '.join(cols)}")
        if self.sample_values:
            parts.append(
                "\nSampled distinct values for key columns (use EXACT "
                "values in WHERE/GROUP BY):"
            )
            for tbl, col_vals in self.sample_values.items():
                for col, vals in col_vals.items():
                    parts.append(f"  {tbl}.{col}: {vals}")
        if self.chart_ids:
            parts.append(f"\nCharts created so far (IDs): {self.chart_ids}")
        if self.step_results:
            parts.append("\nPrevious step results:")
            for sid, summary in self.step_results.items():
                parts.append(f"  Step {sid}: {summary}")
        if self.user_answers:
            parts.append("\nUser's answers to clarification questions:")
            for q, a in self.user_answers.items():
                parts.append(f"  Q: {q}")
                parts.append(f"  A: {a}")
        return "\n".join(parts)


@dataclass
class ExecutionPlan:
    question: str
    steps: list[PlanStep] = field(default_factory=list)
    context: PlanContext = field(default_factory=PlanContext)
    # Phase tracking: "discover", "plan", "ask_user", "execute", "deliver", "done"
    phase: str = "discover"
    # The current step index to resume from
    current_step_idx: int = 0
    summary: str | None = None


def _plan_question_hash(question: str) -> str:
    """Stable hash of the original question for plan matching."""
    return hashlib.sha256(question.strip().lower().encode()).hexdigest()[:16]


def serialize_plan(plan: ExecutionPlan) -> dict[str, Any]:
    """Serialize an ExecutionPlan to a JSON-safe dict for frontend storage."""
    return {
        "question": plan.question,
        "question_hash": _plan_question_hash(plan.question),
        "phase": plan.phase,
        "current_step_idx": plan.current_step_idx,
        "context": asdict(plan.context),
        "steps": [
            {
                "step_id": s.step_id,
                "description": s.description,
                "request": s.request,
                "expected_outcome": s.expected_outcome,
                "status": s.status,
                "result_summary": s.result_summary,
                "error": s.error,
                "retry_count": s.retry_count,
                "context_snippet": s.context_snippet,
            }
            for s in plan.steps
        ],
    }


def deserialize_plan(data: dict[str, Any]) -> ExecutionPlan:
    """Reconstruct an ExecutionPlan from a serialized dict."""
    ctx_data = data.get("context", {})
    context = PlanContext(
        tables=ctx_data.get("tables", {}),
        views=ctx_data.get("views", {}),
        entity_filter=ctx_data.get("entity_filter"),
        entity_name=ctx_data.get("entity_name"),
        db_backend=ctx_data.get("db_backend", ""),
        schema_name=ctx_data.get("schema_name"),
        sample_values=ctx_data.get("sample_values", {}),
        entity_candidates=ctx_data.get("entity_candidates", []),
        step_results=ctx_data.get("step_results", {}),
        chart_ids=ctx_data.get("chart_ids", []),
        dataset_ids=ctx_data.get("dataset_ids", []),
        dashboard_created=ctx_data.get("dashboard_created", False),
        user_answers=ctx_data.get("user_answers", {}),
    )
    steps = [
        PlanStep(
            step_id=s.get("step_id", i + 1),
            description=s.get("description", ""),
            request=s.get("request", ""),
            expected_outcome=s.get("expected_outcome", ""),
            status=s.get("status", "pending"),
            result_summary=s.get("result_summary"),
            error=s.get("error"),
            retry_count=s.get("retry_count", 0),
            context_snippet=s.get("context_snippet"),
        )
        for i, s in enumerate(data.get("steps", []))
    ]
    return ExecutionPlan(
        question=data.get("question", ""),
        steps=steps,
        context=context,
        phase=data.get("phase", "discover"),
        current_step_idx=data.get("current_step_idx", 0),
    )


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

PLAN_SYSTEM_PROMPT = """\
You are a query planner for Apache Superset SQL Lab.

Given a user question and DISCOVERED SCHEMA CONTEXT (with actual table names, \
column names, and entity filters), create an execution plan that DELIVERS \
what the user asked for.

The executor has tools: execute_sql, set_editor_sql, create_chart, \
create_dashboard, list_charts, get_chart, update_chart, list_datasets, \
get_dataset, update_dataset, get_table_columns, sample_table_data, \
get_distinct_values.

CRITICAL — you ALREADY have the schema info. Do NOT plan exploration steps \
(list_tables, get_table_columns) — the context below already contains all \
discovered tables and columns. Jump straight to SQL development and delivery.

RULES:
1. **Use EXACT column names from the context.** Never guess or invent \
   columns. Never invent table names. ONLY use tables/views listed in the \
   DISCOVERED CONTEXT section below.
2. **Entity filter is MANDATORY.** If the context has an entity_filter, \
   use the appropriate identifier column(s) listed there in your WHERE \
   clauses. The filter shows which table the entity was found in and all \
   its identifier values (id, adoszam, d_b_belso_azonosito, etc.). \
   When joining to other tables, use the matching column from that table \
   (e.g. if entity has adoszam=X, use WHERE t.adoszam = 'X' when \
   querying a table that has an adoszam column).
3. **NO DDL. ONLY SELECT.** You MUST NOT use CREATE, ALTER, DROP, INSERT, \
   UPDATE, or DELETE statements. All SQL must be SELECT queries only. \
   Do NOT create views, temp tables, or stored procedures.
4. **Verify column values BEFORE building charts.** For any categorical \
   column used in WHERE or GROUP BY, first call get_distinct_values or \
   execute_sql with SELECT DISTINCT to see the REAL values. NEVER assume \
   values like "BEVETEL", "KOLTSEG" — always check first.
5. **Budget**: ~30% SQL development + testing, ~70% delivery (create_chart, \
   create_dashboard).
6. **Charts MUST be saved**: always set save_chart=true.
7. **Dashboard is MANDATORY** if the user asks for one. The LAST step MUST \
   be create_dashboard referencing all chart_ids from earlier steps.
8. **Naming convention**: the backend auto-prefixes ai_YYYYMMDD_HHMM_Topic. \
   Don't add this prefix yourself.
9. **Write the FULL SQL in each step's request.** Don't just describe it — \
   write the actual query. The executor will validate and execute it.
10. **One chart per step.** Each create_chart step should create exactly one \
   chart with a focused purpose (e.g. revenue trend, cost breakdown).
11. **3+ charts minimum** for a dashboard request. Include at least: a trend \
   chart (line), a breakdown chart (bar or pie), and a summary/table chart.
12. Return ONLY a JSON array — no markdown fences, no explanation.

Output format:
[
  {
    "step_id": 1,
    "description": "Short human-readable label",
    "request": "Detailed instruction WITH the actual SQL query to use",
    "expected_outcome": "What a successful result looks like"
  }
]
"""

CHECK_SYSTEM_PROMPT = """\
You are a step-result checker for an Apache Superset SQL Lab AI agent.

You receive: the original user question, the full plan (with statuses), and \
the latest step's result.

Your job is MINIMAL and CONSERVATIVE:

1. **If the step got ANY useful result (even partial)** → return []
   A step that returns 1 row when you expected 5 is still a SUCCESS. \
   Do NOT re-plan just because the result is smaller than expected.

2. **If the step COMPLETELY FAILED (error or truly zero useful data AND \
   the step is critical):**
   - Return modified/new steps ONLY for the failed step and its immediate \
     dependencies. Do NOT rewrite the entire remaining plan.
   - Limit new steps to at most 2.

3. **If the step succeeded AND you found concrete identifiers (IDs, names):**
   - Update the `request` field of remaining pending steps to include that \
     data (e.g. "use company_id=42 found in step 2").
   - Do NOT change anything else about those steps.

4. **NEVER re-plan a step that already succeeded.** Once done is done.

5. **NEVER add more than 2 new steps** in a single check. The plan has a \
   budget — respect it.

6. **Bias toward []** (no changes). When in doubt, return []. Moving forward \
   is almost always better than re-planning.

7. step_id values MUST be integers. Use existing step_id for updates, or the \
   next sequential integer for new steps.

8. **Dashboard safety net.** If the user originally asked for a dashboard, \
   and you see that chart_ids have been created (check result summaries for \
   chart_id values), but there is NO remaining create_dashboard step in the \
   plan — you MUST add one. This is the most common failure mode.

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
    plan_context: PlanContext,
    provider_config: dict[str, Any],
    provider: str,
    max_steps: int = 15,
) -> ExecutionPlan:
    """Ask the LLM to generate a structured execution plan.

    Uses the rich PlanContext (with discovered tables, columns, entity filters)
    so the LLM can create steps with actual SQL instead of exploration.
    """
    context_block = plan_context.to_prompt_block()
    user_prompt = (
        f"DISCOVERED CONTEXT (tables, columns, entity filter):\n{context_block}\n\n"
        f"Max steps allowed: {max_steps}\n\n"
        f"Create a query plan for:\n{question}"
    )

    raw = _llm_plan_call(PLAN_SYSTEM_PROMPT, user_prompt, provider_config, provider)
    logger.info("Planner raw output (%d chars): %s", len(raw), raw[:500])

    parsed = _parse_json_array(raw)
    if not parsed:
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

    plan = ExecutionPlan(question=question, steps=steps, context=plan_context)
    plan.phase = "execute"
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

    Updates matching step_ids get refreshed; new steps are inserted.
    Crucially, unmentioned future steps are PRESERVED (not dropped).
    """
    if not updates:
        return

    # Keep steps up to (and including) the current step
    kept = plan.steps[: current_step_index + 1]

    # Build lookup for existing steps (by step_id) that are after current
    future_steps = list(plan.steps[current_step_index + 1:])
    existing_map = {s.step_id: s for s in future_steps}
    updated_ids: set[int] = set()

    for u in updates:
        raw_sid = u.get("step_id")
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
            s.status = "pending"
            s.result_summary = None
            s.error = None
            s.context_snippet = None
            s.retry_count = 0
            updated_ids.add(sid)
        else:
            # New step from checker — assign next sequential int ID
            new_id = (max(s.step_id for s in plan.steps) + 1) if plan.steps else 1
            # Avoid ID collisions
            while any(s.step_id == new_id for s in plan.steps) or new_id in updated_ids:
                new_id += 1
            future_steps.append(PlanStep(
                step_id=new_id,
                description=u.get("description", f"Step {new_id}"),
                request=u.get("request", ""),
                expected_outcome=u.get("expected_outcome", ""),
            ))
            updated_ids.add(new_id)

    # Preserve all future steps (updated or not) in their original order,
    # with new steps appended at the end
    kept.extend(future_steps)
    plan.steps = kept[:max_steps]
    logger.info(
        "Plan updated: now %d steps", len(plan.steps),
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
