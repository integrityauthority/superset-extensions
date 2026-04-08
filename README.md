# Superset Extensions by Integrity Authority

Community extensions for [Apache Superset](https://github.com/apache/superset), built using Superset's native [Extension System](https://superset.apache.org/developer-docs/extensions/overview/).

---

## Extensions

### [Vambery AI Agent](ai_assistant/) `(beta)`

An AI-powered data assistant that lives inside SQL Lab. Ask questions in natural language, and the AI inspects your database schema, writes SQL, executes queries, and creates charts — all without leaving Superset.

**Highlights:**
- Natural language to SQL with schema introspection and metadata awareness
- Interactive chart creation (bar, line, pie, table)
- Send to Editor buttons on all SQL code blocks
- Streaming responses with real-time tool-use visibility
- Multiple LLM providers: Azure OpenAI, OpenAI, Ollama (self-hosted)
- Ollama model auto-discovery with per-question model selector

See the **[full documentation](ai_assistant/README.md)** for configuration, architecture, and API reference.

---

## Installation

There are two ways to install extensions: **LOCAL_EXTENSIONS** (recommended for development and git-based deployments) and **.supx package** (recommended for simple deployments and sharing with colleagues).

### Method 1: Git Submodule + LOCAL_EXTENSIONS (recommended)

Best for teams that deploy Superset from a git fork.

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
# Build all extensions (frontend + backend + manifest + .supx)
bash extensions/build-extensions.sh

# Or manually for a single extension
cd extensions/ai_assistant/frontend
npm install --legacy-peer-deps
npm run build
```

**Configure Superset** — add to `superset_config.py`:

```python
FEATURE_FLAGS = {
    "ENABLE_EXTENSIONS": True,
}

LOCAL_EXTENSIONS = ["/app/extensions/ai_assistant"]
```

### Method 2: .supx Package (simple deployment)

Best for sharing extensions with colleagues or deploying without git submodules.

The build script produces a `.supx` file (a zip archive with the extension bundle). This is a self-contained, portable package following the [official Superset extension format](https://superset.apache.org/developer-docs/extensions/deployment/).

**Option A — Build it yourself:**

```bash
bash extensions/build-extensions.sh
# Output: integrityauthority.vambery-ai-assistant-0.1.0.supx
```

**Option B — Download a pre-built release:**

Download the `.supx` file from [GitHub Releases](https://github.com/integrityauthority/superset-extensions/releases).

**Deploy the .supx file:**

```python
# superset_config.py
FEATURE_FLAGS = {
    "ENABLE_EXTENSIONS": True,
}

# For .supx files (when Superset supports EXTENSIONS_PATH):
EXTENSIONS_PATH = "/app/extensions"

# For LOCAL_EXTENSIONS fallback (extract .supx and point to folder):
# unzip integrityauthority.vambery-ai-assistant-0.1.0.supx -d /app/extensions/ai_assistant/dist/
# LOCAL_EXTENSIONS = ["/app/extensions/ai_assistant"]
```

> **Note:** `EXTENSIONS_PATH` (auto-discovery of .supx files) is available in Superset's upcoming release. Until then, extract the .supx and use `LOCAL_EXTENSIONS` as shown above.

---

## Docker Deployment (Step-by-Step)

This is the full walkthrough for deploying Superset with extensions on a server using Docker Compose.

### Prerequisites

- Docker and Docker Compose installed
- Git access to `integrityauthority/superset` (or the upstream Apache Superset repo)
- LLM provider credentials (Azure OpenAI API key, or Ollama server running)

### Step 1: Clone the repo with submodules

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

### Step 3: Verify docker-compose build args

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

### Step 4: Build and start

```bash
docker compose -f docker-compose-non-dev.yml up -d --build
```

### Step 5: Verify

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

## Troubleshooting

### Extension panel not visible in SQL Lab

| Symptom | Cause | Fix |
|---------|-------|-----|
| Panel missing from sidebar | `DEV_MODE` not set to `"false"` | Set `DEV_MODE: "false"` in docker-compose build args, rebuild |
| Panel missing from sidebar | `ENABLE_EXTENSIONS` not enabled | Add `FEATURE_FLAGS = {"ENABLE_EXTENSIONS": True}` to superset_config.py |
| Panel missing from sidebar | `LOCAL_EXTENSIONS` path wrong | Verify the path exists inside the container: `docker exec superset_app ls /app/extensions/ai_assistant/dist/` |
| Panel missing from sidebar | Frontend not built | Run `bash extensions/build-extensions.sh` before building Docker image |

### Backend API works but chat returns errors

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Authentication required" | Not logged in or CSRF issue | Ensure you're logged into Superset |
| "provider not configured" | Missing env vars | Check `docker/.env-local` has the correct `AI_PROVIDER` and credentials |
| Connection timeout to LLM | Network issue | For Ollama: ensure the host is reachable from Docker (use IP, not hostname) |
| "model does not support tools" | Wrong model | Use a model with function calling support (GPT-4o+, llama3.1+, qwen2.5+) |

### Submodule issues

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

- [ ] Dashboard-level AI assistant
- [ ] Multi-turn memory with conversation history persistence
- [ ] Support for more chart types (scatter, heatmap, geospatial)
- [ ] Natural language filters and drill-downs
- [ ] Dataset recommendations based on user queries
- [ ] Playbooks / knowledge base per database, schema, and table
- [ ] Migrate to `.supx` packaging with `superset-extensions` CLI when available
- [ ] OpenAI Responses API migration for server-side state and built-in tools

## Extension Format Compatibility

This repo follows the [Apache Superset Extension System](https://superset.apache.org/developer-docs/extensions/overview/) conventions:

| Convention | Status |
|------------|--------|
| `extension.json` manifest with publisher namespace | Done |
| Module Federation frontend (`views.registerView()` at module load) | Done |
| Backend entrypoint auto-loaded by Superset | Done |
| `.supx` zip packaging (build script output) | Done |
| `@integrityauthority/` scoped npm package | Done |
| `superset-extensions` CLI support | Pending (CLI not yet released) |
| `EXTENSIONS_PATH` auto-discovery | Pending (Superset Next) |

When Superset's `superset-extensions` CLI and `EXTENSIONS_PATH` become available, the migration will be minimal — the `.supx` files are already produced by the build script.

## Status

**Public Beta** — This extension is functional and actively developed. We use it in production, but expect rough edges. Breaking changes may occur between versions.

Built with the [Apache Superset Extension System](https://github.com/apache/superset) — the first community AI extension for Superset.

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).

## About

Built by [Integrity Authority](https://github.com/integrityauthority) — we build data tools that respect your intelligence.
