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

SYSTEM_PROMPT = """\
You are an AI SQL assistant integrated into Apache Superset's SQL Lab.
You help users write, debug, and optimize SQL queries, and create visualizations.

## Your Capabilities
- You can inspect database schemas (list schemas, tables, columns)
- You can sample data from tables to understand their content
- You can check distinct/unique values in columns
- You can execute SQL queries to test and validate them
- You can set the final SQL query in the user's editor AND auto-execute it
- You can **create charts** (bar, line, pie, table) from query results

## Your Workflow
When a user asks you to create or modify a query:
1. First, explore the database schema using your tools (list_schemas, list_tables, get_table_columns)
2. **Pay attention to column metadata**: get_table_columns returns column comments, \
descriptions, verbose names, and predefined metrics when available. Use these to understand \
the business meaning of columns — they often contain critical context like what values mean, \
naming conventions, or relationships to other tables.
3. Sample data from relevant tables to understand the data (sample_table_data, get_distinct_values)
4. Write and test the query using execute_sql to make sure it works
5. **MANDATORY**: Once the query is correct, call set_editor_sql to place it in the user's \
editor. This auto-runs it and is the primary way users get your output.
6. If the data is suitable for visualization, use create_chart to generate a chart
7. Explain what the query does and any assumptions you made

## CRITICAL: ALWAYS call set_editor_sql — this is NON-NEGOTIABLE
- You MUST call `set_editor_sql` with your final query as the LAST tool call before \
writing your text response. This is the most important action — without it, the user \
gets nothing actionable. DO NOT just show SQL in your text response without also calling \
set_editor_sql.
- Every conversation that involves SQL MUST end with a set_editor_sql call. No exceptions.
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

## Chart Creation
- Use the `create_chart` tool to create interactive visualizations from query results.
- **When to create a chart**: After presenting query results that have clear visual \
patterns — aggregations, comparisons, distributions, trends over time.
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
- If the user asks for a visualization, chart, or graph — always use create_chart.
- The SQL you pass to create_chart should be a clean, tested query (test with execute_sql first).

## Rules
- Always explore the schema before writing queries - don't guess column names
- Test your queries with execute_sql before presenting them as final
- **ALWAYS call set_editor_sql** to put the final query in the editor — never skip this step
- Be concise but informative in your explanations
- If you encounter errors, debug them and try alternative approaches
- Respect the database dialect (MSSQL uses TOP, brackets; PostgreSQL uses LIMIT, double quotes)
- When the user asks an open-ended question about data, provide the most useful analytical \
query first, then offer 2-3 alternative queries that explore the data from different angles
- Use markdown formatting in your responses: headers, bold, code blocks, lists
"""


def build_system_prompt(
    database_name: str | None = None,
    schema_name: str | None = None,
    current_sql: str | None = None,
    extra_prompt: str = "",
) -> str:
    """Build the system prompt with context about the current environment."""
    parts = [SYSTEM_PROMPT]

    if database_name or schema_name:
        context = "\n## Current Context\n"
        if database_name:
            context += f"- Connected database: {database_name}\n"
        if schema_name:
            context += f"- Selected schema: {schema_name}\n"
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

    Returns:
        {
            "response": "assistant's final text response",
            "actions": [{"type": "set_sql", "sql": "..."}],
            "steps": [{"type": "tool_call", ...}, ...],
            "usage": {"prompt_tokens": ..., "completion_tokens": ..., "total_tokens": ...}
        }
    """
    config = get_ai_config()
    provider = config["provider"]
    provider_config = get_provider_config(provider)
    max_rounds = config.get("max_tool_rounds", 10)
    max_sample_rows = config.get("max_sample_rows", 20)

    # Build system prompt with context
    system_prompt = build_system_prompt(
        database_name=database_name,
        schema_name=schema_name,
        current_sql=current_sql,
        extra_prompt=config.get("system_prompt_extra", ""),
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

                # Track actions to relay to the frontend
                if tool_name in TOOLS_WITH_ACTIONS:
                    # create_chart returns the full action object; set_editor_sql uses args
                    if "action" in tool_result:
                        actions.append(tool_result)
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

    # Max rounds exceeded
    logger.warning("Agent exceeded max rounds (%d)", max_rounds)
    return {
        "response": (
            "I've been working on this for a while but haven't finished. "
            "Here's what I've done so far. You can continue the conversation "
            "for me to refine the results."
        ),
        "actions": actions,
        "steps": steps,
        "usage": total_usage,
        "warning": "max_rounds_exceeded",
    }


def run_agent_stream(
    messages: list[dict[str, Any]],
    database_id: int,
    database_name: str | None = None,
    schema_name: str | None = None,
    catalog: str | None = None,
    current_sql: str | None = None,
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
    provider = config["provider"]
    provider_config = get_provider_config(provider)
    max_rounds = config.get("max_tool_rounds", 10)
    max_sample_rows = config.get("max_sample_rows", 20)

    system_prompt = build_system_prompt(
        database_name=database_name,
        schema_name=schema_name,
        current_sql=current_sql,
        extra_prompt=config.get("system_prompt_extra", ""),
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

                # Yield actions to the frontend immediately
                if tool_name in TOOLS_WITH_ACTIONS:
                    if "action" in tool_result:
                        yield {"event": "action", "data": tool_result}
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

    # Max rounds exceeded
    logger.warning("Agent stream exceeded max rounds (%d)", max_rounds)
    yield {
        "event": "response",
        "data": {
            "response": (
                "I've been working on this for a while but haven't finished. "
                "Here's what I've done so far. You can continue the conversation "
                "for me to refine the results."
            ),
            "usage": total_usage,
            "warning": "max_rounds_exceeded",
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

    if "columns" in result:
        cols = result["columns"]
        return f"Table {result.get('table', '?')}: {len(cols)} columns"

    if "data" in result:
        return f"{result.get('row_count', '?')} rows returned"

    if "values" in result:
        vals = result["values"]
        return f"{len(vals)} distinct values in {result.get('column', '?')}"

    if "action" in result:
        if result["action"] == "open_chart":
            saved = "saved" if result.get("saved") else "preview"
            return f"Chart created ({saved}): {result.get('chart_name', '?')}"
        return f"Frontend action: {result['action']}"

    return json.dumps(result, default=str)[:100]
