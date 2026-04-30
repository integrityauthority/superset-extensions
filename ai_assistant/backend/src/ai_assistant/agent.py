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
Vambery AI Agent Orchestrator.

Manages the conversation loop between the user, LLM, and tools.
Implements the agentic pattern: the LLM can call tools (database introspection,
SQL execution) during its reasoning and produce a final response with actions.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ai_assistant.config import get_ai_config, get_provider_config
from ai_assistant.llm import create_chat_completion
from ai_assistant.tools import execute_tool, TOOLS_WITH_ACTIONS, TOOL_DEFINITIONS

logger = logging.getLogger(__name__)


def _detect_db_engine_type(database_id: int) -> str | None:
    """Detect the SQL dialect/engine type from the Superset Database model."""
    try:
        from superset.extensions import db
        from superset.models.core import Database

        database = db.session.query(Database).filter_by(id=database_id).first()
        if database:
            return database.backend
    except Exception as ex:
        logger.debug("Could not detect DB engine type for db %s: %s", database_id, ex)
    return None

SYSTEM_PROMPT = """\
You are an AI SQL assistant integrated into Apache Superset's SQL Lab.
You help users write, debug, and optimize SQL queries, create visualizations, \
and manage Superset datasets and charts.

## Your Capabilities
- Inspect database schemas: list schemas, tables, **views**, columns
- Sample data from tables and views to understand their content
- Check distinct/unique values in columns
- Execute SQL queries to test and validate them
- Set the final SQL query in the user's editor AND auto-execute it
- **Create charts** (bar, line, pie, table) from query results
- **Browse and manage Superset datasets** (list, inspect, edit)
- **Browse and manage Superset charts** (list, inspect, edit)
- **Ask clarification questions** with clickable option buttons (`ask_user`)
- **Show task progress** with a visible todo checklist (`update_todo`)

## CRITICAL: Task Planning with update_todo
For ANY task with 2 or more steps, ALWAYS call `update_todo` FIRST to show your plan. \
This gives the user real-time visibility into your progress.

1. Break the task into concrete steps (explore schema, write SQL, create chart, etc.)
2. Call `update_todo` with all steps as "pending"
3. As you complete each step, call `update_todo` again with updated statuses
4. If a step fails, mark it "error" and add a retry/fix step

Example flow:
- User asks "show me monthly sales" →
- Call update_todo: [{id:"1", text:"Explore schema for sales data", status:"in_progress"}, \
{id:"2", text:"Write and test SQL query", status:"pending"}, \
{id:"3", text:"Set editor SQL", status:"pending"}, \
{id:"4", text:"Create chart", status:"pending"}]
- After finding tables → update item 1 to "done", item 2 to "in_progress"
- Continue until all items are "done"

After each major step, verify the result before moving on:
- After exploring schema → confirm you found the right tables/views and columns
- After writing SQL → test with execute_sql and check the results make sense
- After set_editor_sql → confirm it succeeded (no error returned)
- After create_chart → confirm the chart was created successfully
- If the user asked for BOTH a query AND a chart → deliver BOTH, not just one

**Do NOT skip steps. Do NOT stop after partially completing the task.**

## Your Workflow
When a user asks you to create or modify a query:
1. Explore the database schema using your tools (list_schemas, list_tables, **list_views**, \
get_table_columns)
2. **ALWAYS check views too** — call `list_views` alongside `list_tables`. Views often \
contain pre-built joins, aggregations, or filtered data that are more useful than raw tables. \
You can use get_table_columns, sample_table_data, and execute_sql on views the same way as tables.
3. **Pay attention to column metadata**: get_table_columns returns column comments, \
descriptions, verbose names, and predefined metrics when available. Use these to understand \
the business meaning of columns — they often contain critical context like what values mean, \
naming conventions, or relationships to other tables.
4. Sample data from relevant tables/views to understand the data (sample_table_data, get_distinct_values)
5. Write and test the query using execute_sql to make sure it works
6. **MANDATORY**: Once the query is correct, call set_editor_sql to place it in the user's \
editor. This auto-runs it and is the primary way users get your output.
7. If the data is suitable for visualization, **ALWAYS use create_chart** to generate a chart
8. Explain what the query does and any assumptions you made

## CRITICAL: ALWAYS call set_editor_sql — this is NON-NEGOTIABLE
- You MUST call `set_editor_sql` with your final query as the LAST tool call before \
writing your text response. This is the most important action — without it, the user \
gets nothing actionable. DO NOT just show SQL in your text response without also calling \
set_editor_sql.
- **set_editor_sql is SERVER-VALIDATED**: the system will execute your SQL before placing \
it in the editor. If the SQL has errors (wrong column names, bad syntax, etc.), the tool \
will return an error instead of placing the SQL. When this happens, you MUST fix the SQL \
and call set_editor_sql again. NEVER present an errored query to the user.
- Every conversation that involves SQL MUST end with a **successful** set_editor_sql call. No exceptions.
- If the user's request could be answered by multiple queries, call set_editor_sql with \
the most relevant one AND include alternatives as ```sql code blocks in your text response.
- Structure your response:
  - The PRIMARY query goes into set_editor_sql (auto-executes in the editor)
  - Additional ALTERNATIVE queries go in your text response as ```sql code blocks
  - For each alternative, add a one-line explanation of what it shows

## Using Column Metadata
- When get_table_columns returns `comment`, `description`, or `verbose_name` for columns, \
use these to understand what columns represent and write better queries.
- When `table_comment` or `table_description` is returned, use it to understand the table's \
purpose and any important notes about the data.
- When `predefined_metrics` are returned, consider reusing their SQL expressions — they \
represent validated business metrics the organization already uses.

## CRITICAL: Chart Creation — ALWAYS Create Charts When Appropriate
- Use the `create_chart` tool to create interactive visualizations from query results.
- **When to create a chart**: ALWAYS create a chart when the query results have:
  - Aggregations (GROUP BY, SUM, COUNT, AVG) → bar or pie chart
  - Time-based data (dates, months, years) → line chart
  - Comparisons across categories → bar chart
  - Proportional breakdowns → pie chart
  - The user mentions "show me", "visualize", "chart", "graph", "plot", or similar
- **If in doubt, CREATE the chart.** It's better to create a chart the user doesn't need \
than to skip one they wanted.
- **Chart types**:
  - `bar` — Comparisons across categories (e.g., revenue by product, count by region)
  - `line` — Trends over time or ordered sequences (e.g., monthly sales, yearly growth)
  - `pie` — Proportional breakdowns (e.g., market share, distribution of categories)
  - `table` — Detailed data display with many columns
- **Column mapping**:
  - `x_column` = the category/grouping/time column (what goes on the X axis or slice labels)
  - `y_column` = the numeric measure column (what gets aggregated for bar height, line value, etc.)
  - `y_aggregate` = how to aggregate: SUM, COUNT, AVG, MAX, MIN
- **By default, charts are previews** (user can customize and save in Explore). Only set \
`save_chart=true` if the user explicitly asks to save/persist the chart.
- The SQL you pass to create_chart should be a clean, tested query (test with execute_sql first).
- **Self-check after chart creation**: verify the tool returned a URL, not an error. If it \
failed, debug the issue (wrong column name, SQL error, etc.) and try again.

## Dataset Management
- Use `list_datasets` to see what datasets are already registered in Superset for the \
current database.
- Use `get_dataset` to inspect a dataset's full configuration: columns, metrics, SQL, description.
- Use `update_dataset` ONLY when the user **explicitly asks** to edit or update a dataset. \
This includes changing descriptions, column metadata, or SQL for virtual datasets.
- **Never modify datasets without the user's explicit request.** When the user asks you to \
edit a dataset, confirm what you will change before calling update_dataset.

## Chart Management (Existing Charts)
- Use `list_charts` to find existing charts — search by name or filter by dataset.
- Use `get_chart` to inspect a chart's full configuration: viz_type, params, datasource.
- Use `update_chart` ONLY when the user **explicitly asks** to edit or modify an existing chart. \
This includes changing the chart name, visualization type, parameters, or data source.
- **Never modify charts without the user's explicit request.** When the user asks you to \
edit a chart, confirm what you will change before calling update_chart.

## Asking Clarification Questions (ask_user)
- Use `ask_user` when the user's request is **ambiguous** and there are distinct approaches.
- Use it when you need **confirmation** before a destructive or expensive operation \
(e.g., overwriting a dataset, updating many charts).
- Provide 2-5 clear, distinct options. Each option should represent a meaningfully different path.
- Do NOT use ask_user for trivial decisions — just pick the best default and proceed.
- After calling ask_user, STOP and wait for the user's response before continuing. \
Do not call other tools in the same round after ask_user.

## Task Progress (update_todo)
- For ANY task with 2+ steps, call `update_todo` at the START with your plan.
- Update it after completing each step (mark "done") and starting the next ("in_progress").
- If a step fails, mark it "error" and optionally add new steps to fix the issue.
- Keep item descriptions short and clear (e.g., "Explore schema", "Write SQL", "Create chart").
- The user sees this as a live progress checklist — it builds trust and transparency.
- For simple single-step tasks (e.g., "what tables are in this schema?"), skip update_todo.

## Rules
- Always explore the schema before writing queries — don't guess column names
- **Always check both tables AND views** when exploring a schema
- Test your queries with execute_sql before presenting them as final
- **ALWAYS call set_editor_sql** to put the final query in the editor — never skip this step. \
If set_editor_sql returns an error, fix the SQL and retry — do NOT give up or show broken SQL.
- Be concise but informative in your explanations
- If you encounter errors, debug them and try alternative approaches
- Respect the database dialect (MSSQL uses TOP, brackets; PostgreSQL uses LIMIT, double quotes)
- When the user asks an open-ended question about data, provide the most useful analytical \
query first, then offer 2-3 alternative queries that explore the data from different angles
- Use markdown formatting in your responses: headers, bold, code blocks, lists

## CRITICAL: ALWAYS FINISH THE TASK — NEVER GIVE UP
- You MUST complete every task the user asks for. Do NOT stop halfway through.
- If a query fails, fix it and try again. If data is missing, try different approaches.
- You have up to 50 tool calls available — use as many as needed to get the job done.
- Do NOT say "I've been working on this for a while" or "I haven't finished" — \
these responses are UNACCEPTABLE. Always deliver a complete, working result.
- If you're exploring data and haven't found what you need, keep trying different \
tables, views, columns, or query strategies until you succeed.
- Plan efficiently: explore schema first (tables + views), then write and test the query in \
as few steps as possible. Avoid redundant tool calls.

## Self-Verification Checklist (run this mentally before your final response)
- [ ] Did I explore the schema thoroughly (tables AND views)?
- [ ] Did I test my SQL with execute_sql and confirm it returns correct data?
- [ ] Did I call set_editor_sql with the final query and it SUCCEEDED (no error returned)?
- [ ] If the results are visual (aggregations, trends, comparisons): did I call create_chart?
- [ ] If the user asked to edit a dataset/chart: did I make the requested changes?
- [ ] Is my response complete and actionable?
If any answer is NO — go back and do it before responding.
"""


def build_system_prompt(
    database_name: str | None = None,
    schema_name: str | None = None,
    current_sql: str | None = None,
    extra_prompt: str = "",
    db_engine_type: str | None = None,
    system_prompt_override: str = "",
) -> str:
    """Build the system prompt with context about the current environment.

    If system_prompt_override is set, it replaces the built-in SYSTEM_PROMPT
    entirely. The extra_prompt is always appended regardless.
    """
    base_prompt = system_prompt_override.strip() if system_prompt_override else SYSTEM_PROMPT
    parts = [base_prompt]

    if database_name or schema_name or db_engine_type:
        context = "\n## Current Context\n"
        if database_name:
            context += f"- Connected database: {database_name}\n"
        if schema_name:
            context += f"- Selected schema: {schema_name}\n"
        if db_engine_type:
            context += f"- SQL dialect: {db_engine_type}\n"
            if "mssql" in db_engine_type.lower():
                context += (
                    "- **MSSQL rules**: Use TOP instead of LIMIT, use square brackets "
                    "[column] for identifiers, ORDER BY is NOT allowed in subqueries "
                    "or derived tables unless TOP/OFFSET is specified, use "
                    "FORMAT(date, 'yyyy-MM') for date formatting, use STRING_AGG "
                    "instead of GROUP_CONCAT.\n"
                )
            elif "postgres" in db_engine_type.lower():
                context += (
                    "- **PostgreSQL rules**: Use LIMIT instead of TOP, use double "
                    "quotes for identifiers, use TO_CHAR for date formatting.\n"
                )
        parts.append(context)

    if current_sql and current_sql.strip():
        parts.append(
            f"\n## Current Editor Content\n"
            f"The user's SQL editor currently contains:\n```sql\n{current_sql}\n```\n"
        )

    if extra_prompt:
        parts.append(f"\n## Additional Instructions\n{extra_prompt}\n")

    return "\n".join(parts)


def run_agent(
    messages: list[dict[str, Any]],
    database_id: int,
    database_name: str | None = None,
    schema_name: str | None = None,
    catalog: str | None = None,
    current_sql: str | None = None,
    model_override: str | None = None,
    provider_override: str | None = None,
) -> dict[str, Any]:
    """
    Run the AI agent loop.

    Args:
        messages: Conversation history (user and assistant messages)
        database_id: The Superset database ID for tool execution
        database_name: Display name of the database (for context)
        schema_name: Selected schema name (for context)
        catalog: Selected catalog (for context)
        current_sql: Current SQL in the editor (for context)
        model_override: Override the configured model name at runtime
        provider_override: Override the configured provider at runtime

    Returns:
        {
            "response": "assistant's final text response",
            "actions": [{"type": "set_sql", "sql": "..."}],
            "steps": [{"type": "tool_call", ...}, ...],
            "usage": {"prompt_tokens": ..., "completion_tokens": ..., "total_tokens": ...}
        }
    """
    config = get_ai_config()
    provider = provider_override or config["provider"]
    provider_config = get_provider_config(provider)
    if model_override:
        provider_config = {**provider_config, "model": model_override}
    max_rounds = config.get("max_tool_rounds", 10)
    max_sample_rows = config.get("max_sample_rows", 20)

    # Detect database engine type for dialect-specific prompting
    db_engine_type = _detect_db_engine_type(database_id)

    # Build system prompt with context
    system_prompt = build_system_prompt(
        database_name=database_name,
        schema_name=schema_name,
        current_sql=current_sql,
        extra_prompt=config.get("system_prompt_extra", ""),
        db_engine_type=db_engine_type,
        system_prompt_override=config.get("system_prompt_override", ""),
    )

    # Prepare conversation with system prompt
    llm_messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
    ]
    # Add conversation history
    for msg in messages:
        llm_messages.append({"role": msg["role"], "content": msg["content"]})

    steps: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    for round_num in range(max_rounds):
        logger.info("Agent round %d/%d", round_num + 1, max_rounds)

        try:
            result = create_chat_completion(
                provider_config=provider_config,
                provider=provider,
                messages=llm_messages,
                tools=TOOL_DEFINITIONS,
            )
        except Exception as ex:
            logger.error("LLM API error in round %d: %s", round_num + 1, ex)
            return {
                "response": f"Error communicating with AI: {str(ex)}",
                "actions": actions,
                "steps": steps,
                "usage": total_usage,
                "error": True,
            }

        # Accumulate usage
        usage = result.get("usage", {})
        total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
        total_usage["completion_tokens"] += usage.get("completion_tokens", 0)
        total_usage["total_tokens"] += usage.get("total_tokens", 0)

        assistant_message = result["message"]
        finish_reason = result["finish_reason"]

        # Check for tool calls
        tool_calls = assistant_message.get("tool_calls")

        if tool_calls and finish_reason in ("tool_calls", "stop"):
            # Add assistant message with tool calls to conversation
            llm_messages.append(assistant_message)

            for tool_call in tool_calls:
                func = tool_call["function"]
                tool_name = func["name"]
                try:
                    tool_args = json.loads(func["arguments"])
                except json.JSONDecodeError:
                    tool_args = {}

                logger.info(
                    "Tool call: %s(%s)",
                    tool_name,
                    json.dumps(tool_args, default=str)[:200],
                )

                # Execute the tool
                tool_result = execute_tool(
                    tool_name=tool_name,
                    arguments=tool_args,
                    database_id=database_id,
                    schema_name=schema_name,
                    catalog=catalog,
                    max_sample_rows=max_sample_rows,
                )

                # Track actions to relay to the frontend (only if no error)
                if tool_name in TOOLS_WITH_ACTIONS and "error" not in tool_result:
                    if "action" in tool_result:
                        # Normalize: frontend expects "type" key, not "action"
                        action_data = {**tool_result}
                        action_data["type"] = action_data.pop("action")
                        actions.append(action_data)
                    else:
                        actions.append({"type": tool_name, **tool_args})

                # Record step for debugging/display
                steps.append(
                    {
                        "type": "tool_call",
                        "tool": tool_name,
                        "args": tool_args,
                        "result_summary": _summarize_result(tool_result),
                    }
                )

                # Add tool result to conversation
                tool_result_str = json.dumps(tool_result, default=str)
                llm_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": tool_result_str,
                    }
                )

            # Continue the loop for the next LLM call
            continue

        # No tool calls - this is the final response
        final_content = assistant_message.get("content", "")
        logger.info(
            "Agent completed in %d rounds. Actions: %d",
            round_num + 1,
            len(actions),
        )

        return {
            "response": final_content,
            "actions": actions,
            "steps": steps,
            "usage": total_usage,
        }

    # Max rounds exceeded — force a final answer without tools
    logger.warning("Agent exceeded max rounds (%d), forcing final answer", max_rounds)
    llm_messages.append({
        "role": "user",
        "content": (
            "You have used all available tool calls. You MUST now provide your "
            "final answer based on everything you've learned so far. Summarize "
            "your findings, present the best query you have, and call set_editor_sql "
            "if you haven't already. Do NOT say you haven't finished."
        ),
    })
    try:
        final_result = create_chat_completion(
            provider_config=provider_config,
            provider=provider,
            messages=llm_messages,
            tools=None,
        )
        forced_content = final_result.get("message", {}).get("content", "")
        usage = final_result.get("usage", {})
        total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
        total_usage["completion_tokens"] += usage.get("completion_tokens", 0)
        total_usage["total_tokens"] += usage.get("total_tokens", 0)
    except Exception:
        forced_content = ""

    return {
        "response": forced_content or (
            "I explored the database extensively but ran out of tool calls. "
            "Please try again with a more specific question."
        ),
        "actions": actions,
        "steps": steps,
        "usage": total_usage,
    }


def run_agent_stream(
    messages: list[dict[str, Any]],
    database_id: int,
    database_name: str | None = None,
    schema_name: str | None = None,
    catalog: str | None = None,
    current_sql: str | None = None,
    model_override: str | None = None,
    provider_override: str | None = None,
) -> Any:
    """
    Streaming version of run_agent.

    Yields SSE-style event dicts as the agent processes:
        {"event": "step",     "data": {"type": "tool_call", "tool": ..., ...}}
        {"event": "action",   "data": {"type": "set_editor_sql", "sql": ...}}
        {"event": "response", "data": {"response": ..., "usage": ...}}
        {"event": "error",    "data": {"error": ...}}
    """
    config = get_ai_config()
    provider = provider_override or config["provider"]
    provider_config = get_provider_config(provider)
    if model_override:
        provider_config = {**provider_config, "model": model_override}
    max_rounds = config.get("max_tool_rounds", 10)
    max_sample_rows = config.get("max_sample_rows", 20)

    # Detect database engine type for dialect-specific prompting
    db_engine_type = _detect_db_engine_type(database_id)

    system_prompt = build_system_prompt(
        database_name=database_name,
        schema_name=schema_name,
        current_sql=current_sql,
        extra_prompt=config.get("system_prompt_extra", ""),
        db_engine_type=db_engine_type,
        system_prompt_override=config.get("system_prompt_override", ""),
    )

    llm_messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
    ]
    for msg in messages:
        llm_messages.append({"role": msg["role"], "content": msg["content"]})

    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    for round_num in range(max_rounds):
        logger.info("Agent stream round %d/%d", round_num + 1, max_rounds)

        try:
            result = create_chat_completion(
                provider_config=provider_config,
                provider=provider,
                messages=llm_messages,
                tools=TOOL_DEFINITIONS,
            )
        except Exception as ex:
            logger.error("LLM API error in round %d: %s", round_num + 1, ex)
            yield {
                "event": "error",
                "data": {"error": f"Error communicating with AI: {str(ex)}"},
            }
            return

        # Accumulate usage
        usage = result.get("usage", {})
        total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
        total_usage["completion_tokens"] += usage.get("completion_tokens", 0)
        total_usage["total_tokens"] += usage.get("total_tokens", 0)

        assistant_message = result["message"]
        finish_reason = result["finish_reason"]
        tool_calls = assistant_message.get("tool_calls")

        if tool_calls and finish_reason in ("tool_calls", "stop"):
            llm_messages.append(assistant_message)

            for tool_call in tool_calls:
                func = tool_call["function"]
                tool_name = func["name"]
                try:
                    tool_args = json.loads(func["arguments"])
                except json.JSONDecodeError:
                    tool_args = {}

                logger.info(
                    "Tool call: %s(%s)",
                    tool_name,
                    json.dumps(tool_args, default=str)[:200],
                )

                tool_result = execute_tool(
                    tool_name=tool_name,
                    arguments=tool_args,
                    database_id=database_id,
                    schema_name=schema_name,
                    catalog=catalog,
                    max_sample_rows=max_sample_rows,
                )

                # Yield step event so frontend can show it immediately
                yield {
                    "event": "step",
                    "data": {
                        "type": "tool_call",
                        "tool": tool_name,
                        "args": tool_args,
                        "result_summary": _summarize_result(tool_result),
                    },
                }

                # Yield actions to the frontend immediately (only if no error)
                if tool_name in TOOLS_WITH_ACTIONS and "error" not in tool_result:
                    if "action" in tool_result:
                        # Normalize: frontend expects "type" key, not "action"
                        action_data = {**tool_result}
                        action_data["type"] = action_data.pop("action")
                        yield {"event": "action", "data": action_data}
                    else:
                        yield {
                            "event": "action",
                            "data": {"type": tool_name, **tool_args},
                        }

                tool_result_str = json.dumps(tool_result, default=str)
                llm_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": tool_result_str,
                    }
                )

            continue

        # No tool calls — final response
        final_content = assistant_message.get("content", "")
        logger.info(
            "Agent stream completed in %d rounds.",
            round_num + 1,
        )
        yield {
            "event": "response",
            "data": {
                "response": final_content,
                "usage": total_usage,
            },
        }
        return

    # Max rounds exceeded — force a final answer without tools
    logger.warning("Agent stream exceeded max rounds (%d), forcing final answer", max_rounds)
    llm_messages.append({
        "role": "user",
        "content": (
            "You have used all available tool calls. You MUST now provide your "
            "final answer based on everything you've learned so far. Summarize "
            "your findings, present the best query you have, and call set_editor_sql "
            "if you haven't already. Do NOT say you haven't finished."
        ),
    })
    try:
        final_result = create_chat_completion(
            provider_config=provider_config,
            provider=provider,
            messages=llm_messages,
            tools=None,
        )
        forced_content = final_result.get("message", {}).get("content", "")
        usage = final_result.get("usage", {})
        total_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
        total_usage["completion_tokens"] += usage.get("completion_tokens", 0)
        total_usage["total_tokens"] += usage.get("total_tokens", 0)
    except Exception:
        forced_content = ""

    yield {
        "event": "response",
        "data": {
            "response": forced_content or (
                "I explored the database extensively but ran out of tool calls. "
                "Please try again with a more specific question."
            ),
            "usage": total_usage,
        },
    }


def _summarize_result(result: dict[str, Any]) -> str:
    """Create a short summary of a tool result for display in the UI."""
    if "error" in result:
        return f"Error: {result['error'][:100]}"

    if "schemas" in result:
        schemas = result["schemas"]
        return f"Found {len(schemas)} schemas: {', '.join(schemas[:5])}{'...' if len(schemas) > 5 else ''}"

    if "tables" in result:
        tables = result["tables"]
        return f"Found {len(tables)} tables in {result.get('schema', '?')}"

    if "views" in result:
        views = result["views"]
        return f"Found {len(views)} views in {result.get('schema', '?')}"

    if "columns" in result and "table" in result:
        cols = result["columns"]
        return f"Table {result.get('table', '?')}: {len(cols)} columns"

    if "datasets" in result:
        return f"Found {result.get('count', '?')} datasets"

    if "charts" in result:
        return f"Found {result.get('count', '?')} charts"

    # Single dataset detail
    if "name" in result and "columns" in result and "metrics" in result:
        return f"Dataset '{result['name']}': {len(result['columns'])} columns, {len(result['metrics'])} metrics"

    # Single chart detail
    if "name" in result and "viz_type" in result and "params" in result:
        return f"Chart '{result['name']}' ({result['viz_type']})"

    # Update results (dataset or chart)
    if "changes" in result and "message" in result:
        return f"{result['message']}: {len(result['changes'])} change(s)"

    if "data" in result:
        return f"{result.get('row_count', '?')} rows returned"

    if "values" in result:
        vals = result["values"]
        return f"{len(vals)} distinct values in {result.get('column', '?')}"

    if "action" in result:
        if result["action"] == "open_chart":
            saved = "saved" if result.get("saved") else "preview"
            return f"Chart created ({saved}): {result.get('chart_name', '?')}"
        if result["action"] == "ask_user":
            return f"Question: {result.get('question', '?')[:80]}"
        if result["action"] == "update_todo":
            items = result.get("items", [])
            done = sum(1 for i in items if i.get("status") == "done")
            return f"Todo: {done}/{len(items)} items done"
        return f"Frontend action: {result['action']}"

    return json.dumps(result, default=str)[:100]
