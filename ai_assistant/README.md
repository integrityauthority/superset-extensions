# Vambery AI Agent

An AI-powered SQL assistant for Apache Superset's SQL Lab (6.1.x+). It lives in the
right sidebar and helps users explore databases, write SQL queries, manage datasets
and charts, and create visualizations through a conversational interface.

> **Named after [Ármin Vámbéry](https://en.wikipedia.org/wiki/%C3%81rmin_V%C3%A1mb%C3%A9ry)** — the Hungarian orientalist, traveler, and polyglot who explored unknown territories. Like its namesake, Vambery navigates your data landscape so you don't have to.

## Features

- **Natural language to SQL** — describe what you need, the AI writes the query
- **Schema-aware** — inspects databases, schemas, **tables and views** before writing queries
- **Views support** — automatically discovers and uses database views alongside tables
- **Rich metadata** — uses table comments, column descriptions, verbose names, and predefined Superset metrics
- **Dialect-aware** — detects the connected database engine (MSSQL, PostgreSQL, etc.) and adapts SQL syntax
- **SQL validation** — uses `sqlglot` for dialect-aware syntax validation before executing queries
- **Chart creation** — creates bar, line, pie, and table charts from query results
- **Dataset management** — list, inspect, and edit existing Superset datasets (descriptions, column metadata, SQL)
- **Chart management** — list, inspect, and edit existing Superset charts (name, viz type, params)
- **Internal task planning** — breaks complex requests into steps, verifies each result, never stops halfway
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
| **Ollama** | `ollama` | No | Self-hosted / local AI. Use models with tool-calling support (llama3.1, qwen2.5, mistral, etc.) |

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

The AI agent has access to 15 tools organized by category:

### Schema Exploration

| Tool | Description |
|------|-------------|
| `list_schemas` | Lists all schemas in the connected database |
| `list_tables` | Lists tables in a schema (tables only) |
| `list_views` | Lists database views in a schema — views often contain pre-built joins and aggregations |
| `get_table_columns` | Returns columns with types, comments, descriptions, verbose names, and predefined metrics (works on tables and views) |
| `sample_table_data` | Returns sample rows from a table or view (configurable limit) |
| `get_distinct_values` | Returns distinct values for a column (up to 50) |

### SQL Execution

| Tool | Description |
|------|-------------|
| `execute_sql` | Executes SELECT/WITH queries safely (max 50 rows, validated with sqlglot) |
| `set_editor_sql` | Sets SQL in the user's editor and auto-executes |

### Chart Management

| Tool | Description |
|------|-------------|
| `create_chart` | Creates bar, line, pie, or table charts with preview or save |
| `list_charts` | Lists existing Superset charts (search by name or dataset) |
| `get_chart` | Gets full chart details: viz_type, params, datasource, explore URL |
| `update_chart` | Edits chart name, description, viz_type, or params (requires explicit user request) |

### Dataset Management

| Tool | Description |
|------|-------------|
| `list_datasets` | Lists Superset datasets for the current database (search by name) |
| `get_dataset` | Gets full dataset details: columns, metrics, SQL (virtual), description |
| `update_dataset` | Edits dataset description, column metadata, or SQL (requires explicit user request) |

## Architecture

```
┌──────────────────────────────────────────────────┐
│  SQL Lab                                         │
│  ┌──────────────────┐  ┌──────────────────────┐  │
│  │  SQL Editor       │  │  Vambery AI Agent    │  │
│  │  Results Table    │  │  Chat Panel          │  │
│  └──────────────────┘  └──────────────────────┘  │
└──────────────────────────────────────────────────┘
         │                         │
         ▼                         ▼
┌──────────────┐       ┌────────────────────────┐
│  Superset    │◄─────►│  AI Agent              │
│  Internal    │       │  15 tools:             │
│  APIs        │       │  - Schema exploration  │
│              │       │  - SQL execution       │
│  Database    │       │  - Chart management    │
│  SqlaTable   │       │  - Dataset management  │
│  Slice       │       └───────────┬────────────┘
└──────────────┘                   │
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
5. Tools use Superset's internal Python APIs directly (Database, SqlaTable, Slice models)
6. SSE events stream each step, action, and final response to the frontend
7. Frontend applies actions (set SQL in editor, open chart preview)

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
  "version": "0.3.0",
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
  "version": "0.3.0",
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

---

## Docker Deployment (Step-by-Step)

This is the full walkthrough for deploying Superset with the Vambery AI Agent extension on a server using Docker Compose.

### Prerequisites

- Docker and Docker Compose installed
- Apache Superset 6.1.x+ (or `integrityauthority/superset` fork)
- LLM provider credentials (Azure OpenAI API key, or Ollama server running)

### Step 1: Get the extension

**Option A — .supx package (recommended):**

Download the `.supx` and `requirements.txt` from [GitHub Releases](https://github.com/integrityauthority/superset-extensions/releases), or build from source:

```bash
bash extensions/build-extensions.sh
```

Place the `.supx` file in your extensions directory (e.g. `/app/extensions/`).

**Option B — Git submodule (development):**

```bash
git clone --recurse-submodules https://github.com/integrityauthority/superset.git
cd superset
```

If you already have the repo but the `extensions/` folder is empty:

```bash
git submodule update --init --remote extensions
```

### Step 2: Configure environment variables

Create or edit `docker/.env-local`:

```bash
# === AI Assistant Configuration ===

# Provider: azure_openai | openai | ollama
AI_PROVIDER=azure_openai

# --- Azure OpenAI ---
AZURE_OPENAI_API_KEY=your-api-key-here
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_VERSION=2024-12-01-preview

# --- OR: Ollama (self-hosted, no API key) ---
# AI_PROVIDER=ollama
# OLLAMA_BASE_URL=http://your-ollama-host:11434
# OLLAMA_MODEL=qwen3.5:122b

# --- OR: OpenAI ---
# AI_PROVIDER=openai
# OPENAI_API_KEY=sk-...
# OPENAI_MODEL=gpt-4o
```

### Step 3: Install Python dependencies

The build script auto-generates a `*-requirements.txt` file next to
the `.supx` — copy its contents into `docker/requirements-local.txt`:

```bash
# If you built locally, the file is already in extensions/:
cat extensions/integrityauthority.vambery-ai-assistant-*-requirements.txt \
    >> docker/requirements-local.txt

# Or just add manually:
echo "openai>=1.0.0" >> docker/requirements-local.txt
```

This file is automatically installed by Superset's `docker-bootstrap.sh` during
container startup — before extensions are loaded.

> **Why not auto-install?** The `.supx` format runs backend code in-memory and
> does not support automatic dependency installation. The extension attempts a
> runtime `pip install` fallback, but it may fail if the container has no internet
> or write access. Pre-installing via `requirements-local.txt` is reliable.

> **Tip:** If you're using MSSQL databases, also add `pyodbc>=5.2.0` to the same file.

### Step 4: Configure superset_config.py

```python
FEATURE_FLAGS = {
    "ENABLE_EXTENSIONS": True,
}

# For .supx files:
EXTENSIONS_PATH = "/app/extensions"

# OR for LOCAL_EXTENSIONS (development):
# LOCAL_EXTENSIONS = ["/app/extensions/ai_assistant"]
```

### Step 5: Verify docker-compose build args

Your `docker-compose-non-dev.yml` must include `DEV_MODE: "false"` for extensions to work:

```yaml
x-common-build: &common-build
  context: .
  target: dev
  args:
    DEV_MODE: "false"          # REQUIRED for Module Federation / extensions
    INSTALL_MSSQL_ODBC: "true" # If using MSSQL databases
```

**Without `DEV_MODE: "false"`, extensions will NOT load** — the frontend build is skipped entirely, so the Module Federation remote entry is never generated.

### Step 6: Build and start

```bash
docker compose -f docker-compose-non-dev.yml up -d --build
```

### Step 7: Verify

1. Check containers are running:
   ```bash
   docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
   ```

2. Check extension loaded (look for "Vambery AI Agent extension registered"):
   ```bash
   docker logs superset_app --tail 50 2>&1 | grep -i "vambery\|extension"
   ```

3. Open SQL Lab in the browser, expand the right sidebar — the **Vambery AI Agent** panel should be visible.

4. Health check:
   ```bash
   curl http://localhost:8088/api/v1/ai_assistant/health
   ```

---

## Python Dependencies

The extension requires the `openai` Python package. The Superset `.supx` format
does not support automatic dependency installation — you must pre-install them.

**Recommended:** The build script generates a `*-requirements.txt` file alongside
the `.supx` package. Copy its contents into `docker/requirements-local.txt`:

```bash
# Auto-generated file from build-extensions.sh:
cat integrityauthority.vambery-ai-assistant-*-requirements.txt >> docker/requirements-local.txt

# Or add manually:
echo "openai>=1.0.0" >> docker/requirements-local.txt
```

This file is automatically installed by Superset's `docker-bootstrap.sh` during
container startup — before extensions are loaded.

**Runtime fallback:** The extension also attempts to install `openai` at
load time using `uv` (preferred) or `pip` (fallback). This works on some setups
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
│       └── tools.py               # Tool definitions & execution (15 tools)
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
- `integrityauthority.vambery-ai-assistant-<version>-requirements.txt` — Python deps to copy into `docker/requirements-local.txt`

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

## Database Support

- **MSSQL** — full support with `TOP`, `[schema].[table]` syntax, ORDER BY stripping for charts
- **PostgreSQL** — full support
- **Any SQL database** — works with any database Superset can connect to
