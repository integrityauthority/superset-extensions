# Superset Extensions by Integrity Authority

Community extensions for [Apache Superset](https://github.com/apache/superset), built using Superset's native [Extension System](https://github.com/apache/superset/blob/master/docs/docs/contributing/extensions.mdx).

---

## Vambery AI Agent `(beta)`

An AI-powered data assistant that lives inside SQL Lab. Ask questions in natural language, and the AI inspects your database schema, writes SQL, executes queries, and creates charts — all without leaving Superset.

> **Named after [Ármin Vámbéry](https://en.wikipedia.org/wiki/%C3%81rmin_V%C3%A1mb%C3%A9ry)** — the Hungarian orientalist, traveler, and polyglot who explored unknown territories. Like its namesake, Vambery navigates your data landscape so you don't have to.

### Features

#### AI-Powered SQL Assistant
- **Natural language to SQL** — describe what you need, and the AI writes the query
- **Schema-aware** — automatically inspects databases, schemas, tables, and columns before writing queries
- **Rich metadata support** — uses table comments, column descriptions, verbose names, and predefined Superset metrics to write accurate queries
- **Query execution** — tests queries and shows results before presenting them
- **Auto-fill editor** — sets the final query in SQL Lab's editor and auto-executes it

#### Interactive Chart Creation
- **One-click visualizations** — AI creates bar, line, pie, and table charts from query results
- **Preview by default** — charts open in Superset's Explore view for customization
- **Save on demand** — permanently save charts when explicitly requested
- **Smart dataset handling** — reuses existing datasets or creates virtual datasets from SQL

#### Modern Chat Interface
- **Markdown rendering** — formatted responses with syntax-highlighted code blocks, tables, and lists
- **Send to Editor** — click any SQL block in the chat to send it to the editor
- **Streaming responses** — real-time SSE streaming with visible tool-use steps
- **Light/dark theme** — adapts to Superset's theme automatically
- **BETA badge** — because we're honest about where we are

#### Database Support
- **MSSQL** — full support with `TOP`, `[schema].[table]` syntax
- **PostgreSQL** — full support
- **Any SQL database** — works with any database Superset can connect to

### Architecture

```
┌─────────────────────────────────────────────────┐
│  SQL Lab                                        │
│  ┌──────────────────────┐ ┌───────────────────┐ │
│  │                      │ │  Vambery AI Agent  │ │
│  │   SQL Editor         │ │  ┌─────────────┐  │ │
│  │                      │ │  │ Chat Panel   │  │ │
│  │                      │ │  │             │  │ │
│  │   Results Table      │ │  │ "Show me top │  │ │
│  │                      │ │  │  customers"  │  │ │
│  │                      │ │  │             │  │ │
│  └──────────────────────┘ │  └─────────────┘  │ │
│                           └───────────────────┘ │
└─────────────────────────────────────────────────┘
        │                           │
        ▼                           ▼
┌──────────────┐          ┌──────────────────┐
│  Superset    │◄────────►│  AI Agent        │
│  Backend     │          │  (tool calling)  │
│              │          │                  │
│  - Databases │          │  - list_schemas  │
│  - Datasets  │          │  - list_tables   │
│  - Charts    │          │  - get_columns   │
│  - Explore   │          │  - execute_sql   │
│              │          │  - create_chart  │
└──────────────┘          └───────┬──────────┘
                                  │
                                  ▼
                          ┌──────────────────┐
                          │  LLM Provider    │
                          │  - Azure OpenAI  │
                          │  - OpenAI        │
                          │  - OpenRouter    │
                          └──────────────────┘
```

### AI Tools

| Tool | Description |
|------|-------------|
| `list_schemas` | Lists all schemas in the connected database |
| `list_tables` | Lists tables in a schema |
| `get_table_columns` | Returns columns with types, comments, descriptions, verbose names, and predefined metrics |
| `sample_table_data` | Returns sample rows from a table (configurable limit) |
| `get_distinct_values` | Returns distinct values for a column (up to 50) |
| `execute_sql` | Executes SELECT/WITH queries safely (max 50 rows) |
| `set_editor_sql` | Sets SQL in the editor and auto-executes |
| `create_chart` | Creates bar, line, pie, or table charts with preview or save |

### Installation

#### As a Git Submodule (recommended)

```bash
# Inside your Superset repo
git submodule add https://github.com/integrityauthority/superset-extensions.git extensions
git submodule update --init
```

Or when cloning a fork that already has this submodule:

```bash
git clone --recurse-submodules https://github.com/integrityauthority/superset.git
```

#### Build the Extension

```bash
# Build from the extensions directory
bash extensions/build-extensions.sh

# Or manually
cd extensions/ai_assistant/frontend
npm install --legacy-peer-deps
npm run build
```

#### Configure Superset

Add to your `superset_config.py`:

```python
FEATURE_FLAGS = {
    "ENABLE_EXTENSIONS": True,
}

LOCAL_EXTENSIONS = ["/app/extensions/ai_assistant"]
```

### Configuration

Configure the AI provider in `superset_config.py`:

```python
AI_ASSISTANT = {
    "provider": "azure_openai",  # or "openai"
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

    # OR OpenAI / OpenRouter
    "openai": {
        "api_key": "your-api-key",
        "model": "gpt-4o",
        "base_url": "",  # optional, set for OpenRouter
    },
}
```

Or use environment variables:

| Variable | Description |
|----------|-------------|
| `AI_PROVIDER` | `azure_openai` or `openai` |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_DEPLOYMENT` | Deployment/model name |
| `AZURE_OPENAI_API_VERSION` | API version (default: `2025-03-01-preview`) |
| `AI_SYSTEM_PROMPT_EXTRA` | Extra system prompt instructions |
| `AI_MAX_TOOL_ROUNDS` | Max tool rounds (default: 10) |
| `AI_MAX_SAMPLE_ROWS` | Max sample rows (default: 20) |

### Docker Setup

The extension works out of the box with Superset's Docker Compose setup. Add to `docker/.env-local`:

```bash
AZURE_OPENAI_API_KEY=your-key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4o
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/ai_assistant/chat` | POST | Synchronous chat |
| `/api/v1/ai_assistant/chat/stream` | POST | Streaming chat (SSE) |
| `/api/v1/ai_assistant/health` | GET | Health check |

### Project Structure

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

### Contributing

We welcome contributions! Here's how:

1. **Feature requests** — [Open an issue](https://github.com/integrityauthority/superset-extensions/issues/new?labels=enhancement&template=feature_request.md) with the `enhancement` label
2. **Bug reports** — [Open an issue](https://github.com/integrityauthority/superset-extensions/issues/new?labels=bug&template=bug_report.md) with the `bug` label
3. **Pull requests** — Fork, branch, and submit a PR

### Roadmap

- [ ] Dashboard-level AI assistant
- [ ] Multi-turn memory with conversation history persistence
- [ ] Support for more chart types (scatter, heatmap, geospatial)
- [ ] Natural language filters and drill-downs
- [ ] Dataset recommendations based on user queries
- [ ] Support for more LLM providers (Anthropic Claude, Google Gemini, local models)

### Status

**Public Beta** — This extension is functional and actively developed. We use it in production, but expect rough edges. Breaking changes may occur between versions.

Built with the [Apache Superset Extension System](https://github.com/apache/superset) — the first community AI extension for Superset.

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).

## About

Built by [Integrity Authority](https://github.com/integrityauthority) — we build data tools that respect your intelligence.
