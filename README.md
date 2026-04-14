# Superset Extensions by Integrity Authority

Community extensions for [Apache Superset](https://github.com/apache/superset) (6.1.x+), built using Superset's native [Extension System](https://superset.apache.org/developer-docs/extensions/overview/) and the `.supx` package format.

---

## Extensions

### [Vambery AI Agent](ai_assistant/) `(beta)`

An AI-powered data assistant that lives inside SQL Lab. Ask questions in natural language, and the AI inspects your database schema, writes SQL, executes queries, and creates charts — all without leaving Superset.

**Highlights:**
- Natural language to SQL with schema introspection and metadata awareness
- Explores both **tables and views** automatically
- Interactive chart creation (bar, line, pie, table)
- **Dataset and chart management** — browse, inspect, and edit existing Superset objects
- Send to Editor buttons on all SQL code blocks
- Streaming responses with real-time tool-use visibility
- Multiple LLM providers: Azure OpenAI, OpenAI, Ollama (local/self-hosted)
- Ollama model auto-discovery with per-question model selector
- 15 agent tools for comprehensive data exploration and management

See the **[full documentation](ai_assistant/README.md)** for configuration, architecture, and API reference.

---

## Installation

### Method 1: .supx Package (recommended)

The `.supx` format is the official Superset extension package — a self-contained zip archive that Superset auto-discovers and loads. This is the recommended way to deploy extensions.

**Option A — Download a pre-built release:**

Download the `.supx` file **and** the matching `requirements.txt` from [GitHub Releases](https://github.com/integrityauthority/superset-extensions/releases).

**Option B — Build it yourself:**

```bash
bash extensions/build-extensions.sh
# Output:
#   integrityauthority.vambery-ai-assistant-<version>.supx            (extension package)
#   integrityauthority.vambery-ai-assistant-<version>-requirements.txt (Python deps)
```

**Deploy the .supx file:**

1. Place the `.supx` file in your extensions directory (e.g. `/app/extensions/`)
2. Install Python dependencies (see [ai_assistant/README.md](ai_assistant/README.md#python-dependencies))
3. Configure `superset_config.py`:

```python
FEATURE_FLAGS = {
    "ENABLE_EXTENSIONS": True,
}

EXTENSIONS_PATH = "/app/extensions"
```

> See the **[full Docker deployment guide](ai_assistant/README.md#docker-deployment-step-by-step)** for the complete walkthrough.

### Method 2: Git Submodule + LOCAL_EXTENSIONS (development)

> **Note:** `LOCAL_EXTENSIONS` is supported for development workflows and git-based deployments. For production, we recommend `.supx` (Method 1).

```bash
# Inside your Superset repo
git submodule add https://github.com/integrityauthority/superset-extensions.git extensions
git submodule update --init
```

Or when cloning a fork that already has this submodule:

```bash
git clone --recurse-submodules https://github.com/integrityauthority/superset.git
```

**Build the extension:**

```bash
bash extensions/build-extensions.sh
```

**Configure Superset** — add to `superset_config.py`:

```python
FEATURE_FLAGS = {
    "ENABLE_EXTENSIONS": True,
}

LOCAL_EXTENSIONS = ["/app/extensions/ai_assistant"]
```

---

## Troubleshooting

### Extension panel not visible in SQL Lab

| Symptom | Cause | Fix |
|---------|-------|-----|
| Panel missing from sidebar | `DEV_MODE` not set to `"false"` | Set `DEV_MODE: "false"` in docker-compose build args, rebuild |
| Panel missing from sidebar | `ENABLE_EXTENSIONS` not enabled | Add `FEATURE_FLAGS = {"ENABLE_EXTENSIONS": True}` to superset_config.py |
| Panel missing from sidebar | Extension path wrong | For .supx: verify `EXTENSIONS_PATH` points to the directory containing the .supx file. For LOCAL_EXTENSIONS: verify the path exists inside the container |
| Panel missing from sidebar | Frontend not built | Run `bash extensions/build-extensions.sh` before building Docker image |

### Backend API works but chat returns errors

| Symptom | Cause | Fix |
|---------|-------|-----|
| "openai package is required" | `openai` not installed | Add `openai>=1.0.0` to `docker/requirements-local.txt`, restart container |
| "Authentication required" | Not logged in or CSRF issue | Ensure you're logged into Superset |
| "provider not configured" | Missing env vars | Check `docker/.env-local` has the correct `AI_PROVIDER` and credentials |
| Connection timeout to LLM | Network issue | For Ollama: ensure the host is reachable from Docker (use IP, not hostname) |
| "model does not support tools" | Wrong model | Use a model with function calling support (GPT-4o+, llama3.1+, qwen2.5+) |
| Health shows `dependency_openai: false` | Auto-install failed | Add `openai>=1.0.0` to `docker/requirements-local.txt` and restart |

### Submodule issues (LOCAL_EXTENSIONS method only)

```bash
# Submodule folder exists but is empty
git submodule update --init --remote extensions

# Submodule is stuck on old version
cd extensions && git pull origin main && cd ..
git add extensions && git commit -m "chore: update extensions submodule"

# Remove and re-add submodule
git submodule deinit -f extensions
git rm -f extensions
rm -rf .git/modules/extensions
git submodule add https://github.com/integrityauthority/superset-extensions.git extensions
```

---

## Contributing

We welcome contributions! Here's how:

1. **Feature requests** — [Open an issue](https://github.com/integrityauthority/superset-extensions/issues/new?labels=enhancement&template=feature_request.md) with the `enhancement` label
2. **Bug reports** — [Open an issue](https://github.com/integrityauthority/superset-extensions/issues/new?labels=bug&template=bug_report.md) with the `bug` label
3. **Pull requests** — Fork, branch, and submit a PR

## Roadmap

- [x] `.supx` packaging as primary deployment format
- [x] Database views support (list, query, chart from views)
- [x] Dataset management (list, inspect, edit)
- [x] Chart management (list, inspect, edit existing charts)
- [x] Internal task planning and self-verification for reliable task completion
- [ ] Dashboard-level AI assistant (create dashboards, add charts to dashboards)
- [ ] Context-aware mode across all Superset tabs (Dashboard, Explore, SQL Lab)
- [ ] Multi-turn memory with conversation history persistence
- [ ] Playbooks / knowledge base per database, schema, and table (e.g. [agentplaybooks.ai](https://agentplaybooks.ai))
- [ ] Chart data retrieval tool (fetch raw data behind existing charts)
- [ ] Support for more chart types (scatter, heatmap, geospatial)
- [ ] Natural language filters and drill-downs
- [ ] Dataset recommendations based on user queries
- [ ] MCP tool registration for external AI agent integration
- [ ] OpenAI Responses API migration for server-side state and built-in tools

## Extension Format

This repo targets **Apache Superset 6.1.x+** and the `.supx` extension format:

| Convention | Status |
|------------|--------|
| `.supx` zip packaging (primary deployment format) | **Done** |
| `EXTENSIONS_PATH` auto-discovery | **Done** |
| `extension.json` manifest with publisher namespace | Done |
| Module Federation frontend (`views.registerView()`) | Done |
| Backend entrypoint auto-loaded by Superset | Done |
| `@integrityauthority/` scoped npm package | Done |
| `LOCAL_EXTENSIONS` support (legacy/development) | Done |
| `superset-extensions` CLI support | Pending (CLI not yet released) |

## Status

**Public Beta** — This extension is functional and actively developed. We use it in production, but expect rough edges. Breaking changes may occur between versions.

Built with the [Apache Superset Extension System](https://github.com/apache/superset) — the first community AI extension for Superset.

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).

## About

Built by [Integrity Authority](https://github.com/integrityauthority) — we build data tools that respect your intelligence.
