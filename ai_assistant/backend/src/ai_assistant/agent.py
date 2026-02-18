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
from ai_assistant.tools import execute_tool, FRONTEND_ACTIONS, TOOL_DEFINITIONS

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are an AI SQL assistant integrated into Apache Superset's SQL Lab.
You help users write, debug, and optimize SQL queries.

## Your Capabilities
- You can inspect database schemas (list schemas, tables, columns)
- You can sample data from tables to understand their content
- You can check distinct/unique values in columns
- You can execute SQL queries to test and validate them
- You can set the final SQL query in the user's editor AND auto-execute it

## Your Workflow
When a user asks you to create or modify a query:
1. First, explore the database schema using your tools (list_schemas, list_tables, get_table_columns)
2. Sample data from relevant tables to understand the data (sample_table_data, get_distinct_values)
3. Write and test the query using execute_sql to make sure it works
4. Once the query is correct, use set_editor_sql to place it in the user's editor (this will auto-run it)
5. Explain what the query does and any assumptions you made

## CRITICAL: Always Provide Runnable SQL if there is any usable outcome from the query
- **ALWAYS call set_editor_sql** with your best query. Every conversation should end with \
a runnable SQL query placed in the editor. Even if the question is exploratory, provide a \
useful query the user can start from.
- If the user's request could be answered by multiple queries (different angles, aggregations, \
or perspectives), call set_editor_sql with the most relevant one AND include the other queries \
as formatted SQL code blocks in your text response so the user can copy-paste them.
- Structure your response to give the user **actionable SQL they can run immediately**:
  - The PRIMARY query goes into set_editor_sql (auto-executes)
  - Additional ALTERNATIVE queries go in your text response as ```sql code blocks
  - For each alternative, add a one-line explanation of what it shows
- Think about what would make a good **chart or dashboard** from this data. If a query result \
would be good for visualization, mention it (e.g., "This result works well as a bar chart \
grouped by X" or "You could create a time-series chart from this").

## Rules
- Always explore the schema before writing queries - don't guess column names
- Test your queries with execute_sql before presenting them as final
- Use set_editor_sql to put the final query in the editor
- Be concise but informative in your explanations
- If you encounter errors, debug them and try alternative approaches
- Respect the database dialect (MSSQL uses TOP, brackets; PostgreSQL uses LIMIT, double quotes)
- When the user asks an open-ended question about data, provide the most useful analytical \
query first, then offer 2-3 alternative queries that explore the data from different angles
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

                # Track frontend actions
                if tool_name in FRONTEND_ACTIONS:
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

                # Yield frontend actions (like set_editor_sql) immediately
                if tool_name in FRONTEND_ACTIONS:
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
        return f"Frontend action: {result['action']}"

    return json.dumps(result, default=str)[:100]
