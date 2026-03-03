# Vambery AI Agent — Superset Extension

An AI-powered SQL assistant for Apache Superset's SQL Lab. It lives in the
right sidebar and helps users explore databases, write SQL queries, and create
chart visualizations through a conversational interface.

## Features

- **Schema exploration** — list schemas, tables, columns with metadata
  (descriptions, verbose names, column comments, predefined Superset metrics).
- **SQL generation** — writes, tests, and places SQL queries directly into the
  SQL Lab editor with auto-execution.
- **Chart creation** — creates bar, line, pie, and table charts from query
  results. Charts open as Superset Explore previews (can be saved permanently).
- **Dialect-aware** — detects the connected database engine (MSSQL, PostgreSQL,
  etc.) and adapts SQL syntax accordingly. MSSQL-specific rules (TOP vs LIMIT,
  bracket quoting, ORDER BY restrictions) are injected into the agent's context.
- **SQL validation** — uses `sqlglot` for dialect-aware syntax validation before
  executing queries, catching errors early.
- **Streaming** — tool call steps stream to the UI in real-time via SSE so the
  user can follow the agent's reasoning.

## LLM API Compatibility

The extension uses the **OpenAI Chat Completions API**
(`client.chat.completions.create`) with function/tool calling. This is the
standard API — not the newer Responses API.

### Supported providers

| Provider | Config key | Notes |
|----------|------------|-------|
| **Azure OpenAI** | `azure_openai` | Default. Requires `api_key`, `azure_endpoint`, `deployment_name`. |
| **OpenAI** | `openai` | Standard OpenAI. Also works for OpenRouter via `base_url`. |

### Model requirements

The model must support **function calling / tool use** via the Chat Completions
API. Compatible models include:

- **GPT-4o** and newer (GPT-4o-mini, GPT-4.1, GPT-5, etc.)
- **GPT-4 Turbo** (function calling support)
- Any model exposed through the Chat Completions API that supports `tools`

> **Note**: GPT-3.5 Turbo has limited tool-calling reliability and is not
> recommended. For best results, use GPT-4o or newer.

## Configuration

Add to `superset_config.py`:

```python
AI_ASSISTANT = {
    "provider": "azure_openai",
    "azure_openai": {
        "api_key": "your-api-key",
        "api_version": "2025-03-01-preview",
        "azure_endpoint": "https://your-resource.openai.azure.com/",
        "deployment_name": "gpt-4o",
    },
    "system_prompt_extra": "",   # Additional instructions appended to the system prompt
    "max_tool_rounds": 10,       # Max tool-use round trips per conversation turn
    "max_sample_rows": 20,       # Max rows returned by sample/preview queries
}
```

### Environment variable fallback (Docker)

When `AI_ASSISTANT` is not set in `superset_config.py`, the extension reads
from environment variables:

| Variable | Maps to |
|----------|---------|
| `AI_PROVIDER` | `provider` |
| `AZURE_OPENAI_API_KEY` | `azure_openai.api_key` |
| `AZURE_OPENAI_API_VERSION` | `azure_openai.api_version` |
| `AZURE_OPENAI_ENDPOINT` | `azure_openai.azure_endpoint` |
| `AZURE_OPENAI_DEPLOYMENT` | `azure_openai.deployment_name` |
| `AI_SYSTEM_PROMPT_EXTRA` | `system_prompt_extra` |
| `AI_MAX_TOOL_ROUNDS` | `max_tool_rounds` |
| `AI_MAX_SAMPLE_ROWS` | `max_sample_rows` |

## Agent Tools

| Tool | Description |
|------|-------------|
| `list_schemas` | List all schemas in the connected database |
| `list_tables` | List all tables in a schema |
| `get_table_columns` | Column metadata with descriptions, comments, verbose names, and predefined metrics |
| `sample_table_data` | Sample rows from a table (up to 20) |
| `get_distinct_values` | Distinct values for a column |
| `execute_sql` | Run SELECT/WITH queries (max 50 rows, validated with sqlglot) |
| `set_editor_sql` | Place SQL in the editor and auto-execute |
| `create_chart` | Create bar/line/pie/table chart from a SQL query |

## Architecture

```
ChatPanel (React, SQL Lab sidebar)
  → POST /api/v1/ai_assistant/chat/stream (SSE)
  → run_agent_stream() — agent loop
  → LLM (Azure OpenAI / OpenAI Chat Completions API)
  → Tool calls → execute_tool() → Superset Database model
  → SSE events: step, action, response
  → Frontend applies actions (set SQL, open chart)
```

## Development

### Frontend build

```bash
cd extensions/ai_assistant/frontend
npm install
npm run build
```

### Copy to dist

```bash
cp -r frontend/dist/* dist/frontend/dist/
cp backend/src/ai_assistant/*.py dist/backend/src/ai_assistant/
```

Update `dist/manifest.json` with the new `remoteEntry` hash after building.
