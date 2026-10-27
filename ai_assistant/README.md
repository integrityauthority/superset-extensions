# Vambery AI Agent

An AI agent for Apache Superset **7.0+**. It explores databases, writes and runs
SQL, builds charts and dashboards, and edits the ones you already have, through a
chat panel available on every page — and, for other programs, through Superset's
MCP server.

| Superset | Vambery | Surface | Conversation storage |
|----------|---------|---------|----------------------|
| **7.0+** | 0.8 and newer | Official chat surface (`core.chat`): floating bubble or docked panel on every page, plus buttons in the SQL Lab editor | Extensions Storage API, per user (not encrypted yet — see below) |
| 6.1 / 6.2 | [0.7.x](https://github.com/integrityauthority/superset-extensions/releases/tag/v0.7.0) only | SQL Lab sidebar (6.1), chat surface (6.2) | in memory |

> **0.7.x is the last line that supports Superset 6.x.** It gets no new features.
> Upgrade Superset to 7.0 before moving to 0.8 or newer.

> The agent works on the database of a SQL Lab tab. On other pages the panel
> shows a notice instead of failing on every message.

> **Named after [Ármin Vámbéry](https://en.wikipedia.org/wiki/%C3%81rmin_V%C3%A1mb%C3%A9ry)** — the Hungarian orientalist, traveler, and polyglot who explored unknown territories. Like its namesake, Vambery navigates your data landscape so you don't have to.

## Features

**Acts as you, with your permissions.** Every tool runs as the signed-in user: only
databases exposed in SQL Lab, only tables you may read (the same check SQL Lab
applies), only charts, datasets and dashboards you are an editor of. SQL runs
through Superset, so row-level security applies, and every tool call is logged with
the user. Queries must be a single read-only statement.

**Answers you can check.**
- Explores schemas, tables and **views**, and reads column comments, descriptions and
  predefined metrics before writing SQL.
- A planner–checker loop plans the steps, runs them, and re-plans when a result is
  wrong. It is told to fix the grain before any total: the latest revision per key,
  never the latest arrival; no sums across one-to-many joins.
- Every reported number comes with the assumptions behind it.
- Queries are validated against the database before they reach the editor; database
  errors are reported, not hidden as empty results.

**Works in SQL Lab.**
- Puts the final query into the editor and runs it, or opens it in a new tab.
- **Ask Vambery** button in the editor toolbar: asks about the selected SQL (or the
  whole query).
- When a query fails, the offending line is marked in the editor and the chat offers
  **Explain and fix**.

**Edits what already exists.**
- Charts: name, type, parameters, data source.
- Datasets: descriptions, column metadata, virtual-dataset SQL, **metrics and
  calculated columns**.
- Dashboards: title, description, published state, add / remove / reorder charts,
  **native filters**.
- Superset 7.0 keeps a version history of all three, so every change can be reverted.
- `query_dataset` answers with a dataset's own metric definitions.

**Creates new things when asked:** bar, line, pie and table charts (previews or saved),
and dashboards from saved charts.

**For other agents (MCP).** Superset's MCP server publishes Vambery as one tool,
`extensions.integrityauthority.vambery-ai-assistant.ask`. Hermes, Claude Code or any
MCP client asks a question and gets the answer, the SQL and the assumptions back.
Read-only unless the call sets `allow_changes`. See [docs/mcp.md](docs/mcp.md).

**Chat.**
- Streaming steps, a live task checklist, clickable clarification questions.
- Edit and resend earlier prompts.
- Conversations saved per SQL Lab tab.
- **Settings:** the model to start with, favourite models, answer language, deleting
  your saved conversations.

Conversations are stored **unencrypted** for now: Superset 7.0.0rc2 cannot read back
values written with `encrypt: true`. The fix is submitted upstream
([apache/superset#45788](https://github.com/apache/superset/pull/45788));
`ENCRYPT_AT_REST` in `conversationStorage.ts` goes back on once it is released.

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

The extension discovers models from ALL configured providers at once, every time
the panel loads:

- **Ollama** models come from `/api/tags`.
- **Azure OpenAI** deployments come from the resource itself (cached for ten
  minutes). Embedding, speech and image deployments are left out. Set
  `AZURE_OPENAI_DEPLOYMENTS` (comma-separated) to offer a fixed list instead.
- **OpenAI** returns the configured model.

Users pick a model per question from one dropdown, without restarting Superset.
Favourites set in the panel's settings are listed first.

Newer reasoning models on Azure (for example `gpt-6-luna`) refuse tool calls on
Chat Completions while reasoning is on. Vambery notices the refusal, retries with
`reasoning_effort: "none"` for that deployment, and remembers it. To force a value
for every call, set `AZURE_OPENAI_REASONING_EFFORT`.

## Configuration

### Option 1: superset_config.py (full control)

```python
AI_ASSISTANT = {
    "provider": "azure_openai",  # or "openai" or "ollama"
    # Replace the entire built-in system prompt (use with caution):
    # "system_prompt_override": "You are a custom SQL assistant for ...",
    "system_prompt_extra": "",   # additional instructions appended to the system prompt
    "max_tool_rounds": 50,       # max tool-use rounds per conversation turn
    "max_sample_rows": 20,       # max rows for sample queries
    "enable_planner": True,      # plan→execute→check→replan loop (set False for simple tool-calling)
    "planner_max_steps": 15,     # upper bound on plan steps (configurable, no hard limit)
    "planner_max_retries_per_step": 3,  # retries before marking a step as error

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
| `AZURE_OPENAI_DEPLOYMENTS` | `azure_openai.deployments` | — (discover from the resource) |
| `AZURE_OPENAI_REASONING_EFFORT` | `azure_openai.reasoning_effort` | — (adapt per model) |
| `OLLAMA_BASE_URL` | `ollama.base_url` | — |
| `OLLAMA_MODEL` | `ollama.model` | — |
| `AI_SYSTEM_PROMPT_OVERRIDE` | `system_prompt_override` | `""` (uses built-in prompt) |
| `AI_SYSTEM_PROMPT_EXTRA` | `system_prompt_extra` | `""` |
| `AI_MAX_TOOL_ROUNDS` | `max_tool_rounds` | `50` |
| `AI_MAX_SAMPLE_ROWS` | `max_sample_rows` | `20` |
| `AI_ENABLE_PLANNER` | `enable_planner` | `True` |
| `AI_PLANNER_MAX_STEPS` | `planner_max_steps` | `15` |
| `AI_PLANNER_MAX_RETRIES_PER_STEP` | `planner_max_retries_per_step` | `3` |

## Agent Tools

The agent has 23 tools. Every one runs with the signed-in user's permissions.

### Schema Exploration

| Tool | Description |
|------|-------------|
| `list_schemas` | Schemas of the connected database you may access |
| `list_tables` | Tables in a schema you may access |
| `list_views` | Views in a schema — often pre-built joins and aggregations |
| `get_table_columns` | Columns with types, comments, descriptions, verbose names and predefined metrics |
| `sample_table_data` | Sample rows from a table or view |
| `get_distinct_values` | Distinct values of a column (up to 50) |

### SQL

| Tool | Description |
|------|-------------|
| `execute_sql` | Runs one read-only statement (max 50 rows) behind SQL Lab's access check |
| `set_editor_sql` | Validates the query against the database, then puts it in the editor and runs it |
| `open_sql_tab` | Same validation, but opens a new SQL Lab tab and leaves the current editor alone |
| `query_dataset` | Queries a dataset by its metric and column names (Superset's tabular query layer: RLS, cache, limits) |

### Charts

| Tool | Description |
|------|-------------|
| `create_chart` | Bar, line, pie or table chart, as a preview or saved |
| `list_charts` / `get_chart` | Find charts and read their configuration |
| `update_chart` | Edit name, description, type, params or data source (editors only) |

### Datasets

| Tool | Description |
|------|-------------|
| `list_datasets` / `get_dataset` | Find datasets and read columns, metrics, SQL |
| `update_dataset` | Edit descriptions, column metadata, virtual SQL, **metrics and calculated columns** (editors only) |

### Dashboards

| Tool | Description |
|------|-------------|
| `create_dashboard` | New dashboard from saved charts |
| `list_dashboards` / `get_dashboard` | Find dashboards; read charts in layout order and native filters |
| `update_dashboard` | Edit in place: title, description, published, add / remove / reorder charts, add / remove native value filters (editors only) |

### Interactive

| Tool | Description |
|------|-------------|
| `ask_user` | A clarification question with clickable options |
| `update_todo` | The live task checklist |

## Architecture

```
┌──────────────────────────────────────────────────┐
│  SQL Lab                                         │
│  ┌──────────────────┐  ┌──────────────────────┐  │
│  │  SQL Editor       │  │  Vambery AI Agent    │  │
│  │  Results Table    │  │  Chat Panel + Todo   │  │
│  └──────────────────┘  └──────────────────────┘  │
└──────────────────────────────────────────────────┘
         │                         │
         ▼                         ▼
┌──────────────┐       ┌────────────────────────┐
│  Superset    │◄─────►│  AI Agent              │
│  Internal    │       │  ┌──────────────────┐  │
│  APIs        │       │  │ Planner (LLM)    │  │
│              │       │  │ plan→exec→check  │  │
│  Database    │       │  └───────┬──────────┘  │
│  SqlaTable   │       │          │             │
│              │       │  17 tools:             │
│  Slice       │       │  - Schema exploration  │
└──────────────┘       │  - SQL execution       │
                       │  - Chart management    │
                       │  - Dataset management  │
                       │  - Interactive (UX)    │
                       └───────────┬────────────┘
                                   │
                                   ▼
                         ┌──────────────────┐
                         │  LLM Provider    │
                         │  - Azure OpenAI  │
                         │  - OpenAI        │
                         │  - Ollama        │
                         └──────────────────┘
```

**Flow (with planner enabled — default):**
1. User types a question in the Chat Panel
2. `POST /api/v1/ai_assistant/chat/stream` sends the message (SSE)
3. `run_agent_stream()` dispatches to `_run_planner_stream()`
4. **Plan**: LLM generates a structured execution plan (JSON array of steps)
5. **Execute**: Each step runs in its own agent sub-loop with full tool access
6. **Check**: After each step, an LLM checker validates the result against the expected outcome
7. **Replan**: If results are empty/wrong/unexpected, the checker rewrites remaining steps with discovered identifiers
8. **Summary**: After all steps, LLM generates a final summary
9. SSE events stream each step, action, `update_todo` progress, and final response to the frontend
10. Frontend applies actions (set SQL in editor, open chart preview, show todo progress)

**Flow (simple mode, `enable_planner=False`):**
1–7. Same as before v0.4.0: direct LLM→tools loop without planning

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
  "version": "0.3.1",
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
  "version": "0.3.1",
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

EXTENSIONS_PATH = "/app/extensions"
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
│       ├── index.tsx              # Extension entry — dual registration (core.chat → sidebar fallback)
│       ├── ChatPanel.tsx          # Chat UI component
│       ├── VamberyTrigger.tsx     # Collapsed bubble trigger (core.chat hosts)
│       ├── hostCapabilities.ts    # Runtime feature detection (chat / navigation / SQL Lab context)
│       ├── conversationStorage.ts # Extensions Storage API access (persistent)
│       ├── useConversationStorage.ts # React hook — debounced auto-save, per-tab scope
│       └── superset-core.d.ts     # Type declarations for @apache-superset/core
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
- `integrityauthority.vambery-ai-assistant-<version>.supx` — the extension package
- `integrityauthority.vambery-ai-assistant-<version>-requirements.txt` — Python deps to copy into `docker/requirements-local.txt`

### Frontend dev server (hot reload)

```bash
cd extensions/ai_assistant/frontend
npm run start
# Runs webpack-dev-server on http://localhost:3000
```

## Database Support

- **MSSQL** — full support with `TOP`, `[schema].[table]` syntax, ORDER BY stripping for charts
- **PostgreSQL** — full support
- **Any SQL database** — works with any database Superset can connect to
