# Vambery AI Agent

An AI-powered SQL assistant for Apache Superset's SQL Lab. It lives in the
right sidebar and helps users explore databases, write SQL queries, and create
chart visualizations through a conversational interface.

> **Named after [Ármin Vámbéry](https://en.wikipedia.org/wiki/%C3%81rmin_V%C3%A1mb%C3%A9ry)** — the Hungarian orientalist, traveler, and polyglot who explored unknown territories. Like its namesake, Vambery navigates your data landscape so you don't have to.

## Features

- **Natural language to SQL** — describe what you need, the AI writes the query
- **Schema-aware** — inspects databases, schemas, tables, and columns before writing queries
- **Rich metadata** — uses table comments, column descriptions, verbose names, and predefined Superset metrics
- **Dialect-aware** — detects the connected database engine (MSSQL, PostgreSQL, etc.) and adapts SQL syntax
- **SQL validation** — uses `sqlglot` for dialect-aware syntax validation before executing queries
- **Chart creation** — creates bar, line, pie, and table charts from query results
- **Send to Editor** — click any SQL code block in the chat to send it to the editor
- **Streaming** — tool call steps stream to the UI in real-time via SSE

## LLM Providers

The extension uses the **OpenAI Chat Completions API** format with function/tool
calling. Multiple providers are supported — configure one as the active provider.

| Provider | Config key | API key required | Notes |
|----------|------------|------------------|-------|
| **Azure OpenAI** | `azure_openai` | Yes | Default. GPT-4o, GPT-5, etc. |
| **OpenAI** | `openai` | Yes | Standard OpenAI. Also works for OpenRouter via `base_url`. |
| **Ollama** | `ollama` | No | Self-hosted. Use models with tool-calling support (llama3.1, qwen2.5, mistral, etc.) |

### Model requirements

The model must support **function calling / tool use**. Compatible models:

- **Azure/OpenAI**: GPT-4o, GPT-4o-mini, GPT-4.1, GPT-5 and newer
- **Ollama**: llama3.1 (8B/70B), qwen2.5, mistral, command-r — any model with tool-calling support

> **Note**: Smaller models (7-8B) work but may struggle with complex multi-step
> queries. For best results, use 70B+ parameter models or GPT-4o class models.

## Configuration

Add to `superset_config.py`:

```python
AI_ASSISTANT = {
    "provider": "azure_openai",  # or "openai" or "ollama"
    "system_prompt_extra": "",   # additional instructions for the AI
    "max_tool_rounds": 10,       # max tool-use rounds per conversation turn
    "max_sample_rows": 20,       # max rows for sample queries

    # Azure OpenAI
    "azure_openai": {
        "api_key": "your-api-key",
        "azure_endpoint": "https://your-resource.openai.azure.com/",
        "deployment_name": "gpt-4o",
        "api_version": "2025-03-01-preview",
    },

    # OpenAI / OpenRouter
    "openai": {
        "api_key": "your-api-key",
        "model": "gpt-4o",
        "base_url": "",  # optional, set for OpenRouter
    },

    # Ollama (self-hosted)
    "ollama": {
        "base_url": "http://aia08.inhat.hu:11434",
        "model": "llama3.1",
    },
}
```

### Environment variable fallback (Docker)

When `AI_ASSISTANT` is not set in `superset_config.py`, the extension reads
from environment variables:

| Variable | Maps to |
|----------|---------|
| `AI_PROVIDER` | `provider` (`azure_openai`, `openai`, or `ollama`) |
| `AZURE_OPENAI_API_KEY` | `azure_openai.api_key` |
| `AZURE_OPENAI_ENDPOINT` | `azure_openai.azure_endpoint` |
| `AZURE_OPENAI_DEPLOYMENT` | `azure_openai.deployment_name` |
| `AZURE_OPENAI_API_VERSION` | `azure_openai.api_version` |
| `OLLAMA_BASE_URL` | `ollama.base_url` |
| `OLLAMA_MODEL` | `ollama.model` |
| `AI_SYSTEM_PROMPT_EXTRA` | `system_prompt_extra` |
| `AI_MAX_TOOL_ROUNDS` | `max_tool_rounds` |
| `AI_MAX_SAMPLE_ROWS` | `max_sample_rows` |

## Agent Tools

| Tool | Description |
|------|-------------|
| `list_schemas` | Lists all schemas in the connected database |
| `list_tables` | Lists tables in a schema |
| `get_table_columns` | Returns columns with types, comments, descriptions, verbose names, and predefined metrics |
| `sample_table_data` | Returns sample rows from a table (configurable limit) |
| `get_distinct_values` | Returns distinct values for a column (up to 50) |
| `execute_sql` | Executes SELECT/WITH queries safely (max 50 rows, validated with sqlglot) |
| `set_editor_sql` | Sets SQL in the editor and auto-executes |
| `create_chart` | Creates bar, line, pie, or table charts with preview or save |

## Architecture

```
┌──────────────────────────────────────────────┐
│  SQL Lab                                     │
│  ┌──────────────────┐ ┌────────────────────┐ │
│  │  SQL Editor       │ │  Vambery AI Agent  │ │
│  │  Results Table    │ │  Chat Panel        │ │
│  └──────────────────┘ └────────────────────┘ │
└──────────────────────────────────────────────┘
        │                        │
        ▼                        ▼
┌──────────────┐       ┌──────────────────┐
│  Superset    │◄─────►│  AI Agent        │
│  Backend     │       │  (tool calling)  │
└──────────────┘       └───────┬──────────┘
                               │
                               ▼
                       ┌──────────────────┐
                       │  LLM Provider    │
                       │  - Azure OpenAI  │
                       │  - OpenAI        │
                       │  - Ollama        │
                       └──────────────────┘
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/ai_assistant/chat` | POST | Synchronous chat |
| `/api/v1/ai_assistant/chat/stream` | POST | Streaming chat (SSE) |
| `/api/v1/ai_assistant/health` | GET | Health check |

## Project Structure

```
ai_assistant/
├── extension.json              # Extension manifest
├── backend/src/ai_assistant/
│   ├── agent.py                # Agent loop & system prompt
│   ├── api.py                  # Flask REST endpoints
│   ├── config.py               # Configuration loading
│   ├── entrypoint.py           # Blueprint registration
│   ├── llm.py                  # LLM provider abstraction
│   └── tools.py                # Tool definitions & execution
└── frontend/src/
    ├── index.tsx               # Extension activation
    └── ChatPanel.tsx           # Chat UI component
```

## Development

### Frontend build

```bash
cd extensions/ai_assistant/frontend
npm install --legacy-peer-deps
npm run build
```

### Copy to dist

```bash
cp -r frontend/dist/* dist/frontend/dist/
cp backend/src/ai_assistant/*.py dist/backend/src/ai_assistant/
```

Update `dist/manifest.json` with the new `remoteEntry` hash after building.

## Database Support

- **MSSQL** — full support with `TOP`, `[schema].[table]` syntax, ORDER BY stripping for charts
- **PostgreSQL** — full support
- **Any SQL database** — works with any database Superset can connect to
