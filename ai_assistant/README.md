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
- **Multi-provider model selector** — combined dropdown shows models from all configured providers (e.g. `azure_openai/gpt-5.2-chat`, `ollama/qwen3.5:122b`), placed near the Send button
- **Edit former prompts** — click the pencil icon on any previous user message to edit and resend it; subsequent messages are automatically flushed
- **Persistent task completion** — the agent uses up to 50 tool rounds and is forced to deliver a final answer

## LLM Providers

The extension uses the **OpenAI Chat Completions API** format with function/tool
calling. Multiple providers are supported — configure one or more.

| Provider | Config key | API key required | Notes |
|----------|------------|------------------|-------|
| **Azure OpenAI** | `azure_openai` | Yes | Default. GPT-4o, GPT-5, etc. |
| **OpenAI** | `openai` | Yes | Standard OpenAI. Also works for OpenRouter via `base_url`. |
| **Ollama** | `ollama` | No | Self-hosted. Use models with tool-calling support (llama3.1, qwen2.5, mistral, etc.) |

### Model requirements

The model must support **function calling / tool use**. Compatible models:

- **Azure/OpenAI**: GPT-4o, GPT-4o-mini, GPT-4.1, GPT-5 and newer
- **Ollama**: llama3.1 (8B/70B), qwen2.5, qwen3.5 (122B), mistral, command-r — any model with tool-calling support

> **Note**: Smaller models (7-8B) work but may struggle with complex multi-step
> queries. For best results, use 70B+ parameter models or GPT-4o class models.

### Multi-provider model selector

The extension discovers models from ALL configured providers simultaneously.
Ollama models are auto-discovered via `/api/tags`; Azure/OpenAI returns the
configured deployment. A combined dropdown near the Send button lets users
pick any model from any provider per question (e.g. `azure_openai/gpt-5.2-chat`
or `ollama/qwen3.5:122b`) without restarting Superset.

## Configuration

### Option 1: superset_config.py (full control)

```python
AI_ASSISTANT = {
    "provider": "azure_openai",  # or "openai" or "ollama"
    "system_prompt_extra": "",   # additional instructions for the AI
    "max_tool_rounds": 50,       # max tool-use rounds per conversation turn
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
        "base_url": "http://your-ollama-host:11434",
        "model": "llama3.1",
    },
}
```

### Option 2: Environment variables (Docker)

When `AI_ASSISTANT` is not set in `superset_config.py`, the extension reads
from environment variables. Set these in `docker/.env-local`:

```bash
# Provider: azure_openai | openai | ollama
AI_PROVIDER=azure_openai

# Azure OpenAI
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_VERSION=2025-03-01-preview

# OR: Ollama
# AI_PROVIDER=ollama
# OLLAMA_BASE_URL=http://your-ollama-host:11434
# OLLAMA_MODEL=llama3.1
```

**Full environment variable mapping:**

| Variable | Maps to | Default |
|----------|---------|---------|
| `AI_PROVIDER` | `provider` | `azure_openai` |
| `AZURE_OPENAI_API_KEY` | `azure_openai.api_key` | — |
| `AZURE_OPENAI_ENDPOINT` | `azure_openai.azure_endpoint` | — |
| `AZURE_OPENAI_DEPLOYMENT` | `azure_openai.deployment_name` | — |
| `AZURE_OPENAI_API_VERSION` | `azure_openai.api_version` | `2025-03-01-preview` |
| `OLLAMA_BASE_URL` | `ollama.base_url` | — |
| `OLLAMA_MODEL` | `ollama.model` | — |
| `AI_SYSTEM_PROMPT_EXTRA` | `system_prompt_extra` | `""` |
| `AI_MAX_TOOL_ROUNDS` | `max_tool_rounds` | `50` |
| `AI_MAX_SAMPLE_ROWS` | `max_sample_rows` | `20` |

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

**Flow:**
1. User types a question in the Chat Panel
2. `POST /api/v1/ai_assistant/chat/stream` sends the message (SSE)
3. `run_agent_stream()` starts the agent loop
4. Agent calls LLM → LLM returns tool calls → agent executes tools → repeats
5. SSE events stream each step, action, and final response to the frontend
6. Frontend applies actions (set SQL in editor, open chart preview)

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/ai_assistant/chat` | POST | Synchronous chat |
| `/api/v1/ai_assistant/chat/stream` | POST | Streaming chat (SSE) |
| `/api/v1/ai_assistant/models` | GET | List available LLM models (auto-discovery for Ollama) |
| `/api/v1/ai_assistant/health` | GET | Detailed health check (deps, config, connectivity) |
| `/api/v1/ai_assistant/health?quick=1` | GET | Quick health check (config only, no connectivity test) |

### Health Endpoint Details

The health endpoint checks three things:

1. **Dependencies** — is the `openai` Python package installed?
2. **Configuration** — are the provider credentials properly set?
3. **Connectivity** — can the extension actually reach the LLM provider?

Example response (all ok):

```json
{
  "status": "ok",
  "version": "0.2.1",
  "provider": "azure_openai",
  "dependency_openai": true,
  "config_ok": true,
  "connectivity": true
}
```

Example response (problems detected — HTTP 503):

```json
{
  "status": "degraded",
  "version": "0.2.1",
  "provider": "ollama",
  "dependency_openai": false,
  "config_ok": true,
  "connectivity": false,
  "errors": [
    "Python package 'openai' is not installed (pip install openai)",
    "Cannot reach ollama: <urlopen error [Errno 111] Connection refused>"
  ]
}
```

## Python Dependencies

The extension requires the `openai` Python package. The **recommended** way to
install it is via `docker/requirements-local.txt` in your Superset repo:

```
# docker/requirements-local.txt
openai>=1.0.0
```

This file is automatically installed by Superset's `docker-bootstrap.sh` during
container startup — before extensions are loaded.

**Auto-install fallback:** The extension also attempts to install `openai` at
load time using `uv` (preferred) or `pip` (fallback). This works on most setups
but may fail if the container has no write access to the venv or no internet.
If auto-install fails, a clear error is logged and the health endpoint reports
`dependency_openai: false`.

**Manual install** (inside a running container):

```bash
# Using uv (faster, available in Superset Docker images)
uv pip install openai>=1.0.0

# Or using pip
pip install openai>=1.0.0
```

## Project Structure

```
ai_assistant/
├── extension.json                 # Extension manifest (publisher, name, contributions)
├── backend/
│   ├── pyproject.toml             # Python package metadata and dependencies
│   └── src/ai_assistant/
│       ├── __init__.py
│       ├── entrypoint.py          # Blueprint registration (loaded by Superset)
│       ├── api.py                 # Flask REST endpoints (chat, stream, health, models)
│       ├── agent.py               # Agent loop, system prompt, tool orchestration
│       ├── config.py              # Configuration loading (superset_config.py + env vars)
│       ├── llm.py                 # LLM provider abstraction (Azure, OpenAI, Ollama)
│       └── tools.py               # Tool definitions & execution
├── frontend/
│   ├── package.json               # npm dependencies (scoped @integrityauthority/)
│   ├── webpack.config.js          # Module Federation config
│   ├── tsconfig.json
│   └── src/
│       ├── index.tsx              # Extension entry — registers view at module load
│       ├── ChatPanel.tsx          # Chat UI component
│       └── superset-core.d.ts    # Type declarations for @apache-superset/core
└── dist/                          # Built bundle (generated by build-extensions.sh)
    ├── manifest.json
    ├── frontend/dist/             # Webpack output (remoteEntry.*.js + chunks)
    └── backend/src/ai_assistant/  # Python source copy
```

## Development

### Building the frontend

```bash
cd extensions/ai_assistant/frontend
npm install --legacy-peer-deps
npm run build
```

### Building everything (recommended)

```bash
# From the extensions repo root — builds frontend, copies backend, generates manifest, packages .supx
bash build-extensions.sh
```

Output:
- `ai_assistant/dist/` — the full extension bundle (used by `LOCAL_EXTENSIONS`)
- `integrityauthority.vambery-ai-assistant-<version>.supx` — portable package (used by `EXTENSIONS_PATH`)

### Frontend dev server (hot reload)

```bash
cd extensions/ai_assistant/frontend
npm run start
# Runs webpack-dev-server on http://localhost:3000
```

### Manually updating dist after code changes

If you edit files without running the full build script:

```bash
# Frontend changes
cd extensions/ai_assistant/frontend && npm run build
cp -r frontend/dist/* ../dist/frontend/dist/

# Backend changes
cp backend/src/ai_assistant/*.py dist/backend/src/ai_assistant/

# Update manifest with new remoteEntry hash
# (or just re-run: bash build-extensions.sh)
```

## Extension Format

This extension follows the [Apache Superset Extension System](https://superset.apache.org/developer-docs/extensions/overview/) conventions and is forward-compatible with the upcoming `.supx` packaging standard:

- **Frontend**: Uses `views.registerView()` at module load time (no activate/deactivate lifecycle)
- **Backend**: Flask Blueprint registered via entrypoint (will migrate to `@api` decorator when `superset_core` is available)
- **Packaging**: `build-extensions.sh` produces both a `dist/` folder (LOCAL_EXTENSIONS) and a `.supx` zip (EXTENSIONS_PATH)

## Database Support

- **MSSQL** — full support with `TOP`, `[schema].[table]` syntax, ORDER BY stripping for charts
- **PostgreSQL** — full support
- **Any SQL database** — works with any database Superset can connect to
