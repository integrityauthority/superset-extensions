# Superset Extensions by Integrity Authority

Community extensions for [Apache Superset](https://github.com/apache/superset), built using Superset's native [Extension System](https://github.com/apache/superset/blob/master/docs/docs/contributing/extensions.mdx).

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

### As a Git Submodule (recommended)

```bash
# Inside your Superset repo
git submodule add https://github.com/integrityauthority/superset-extensions.git extensions
git submodule update --init
```

Or when cloning a fork that already has this submodule:

```bash
git clone --recurse-submodules https://github.com/integrityauthority/superset.git
```

### Build the Extension

```bash
# Build from the extensions directory
bash extensions/build-extensions.sh

# Or manually
cd extensions/ai_assistant/frontend
npm install --legacy-peer-deps
npm run build
```

### Configure Superset

Add to your `superset_config.py`:

```python
FEATURE_FLAGS = {
    "ENABLE_EXTENSIONS": True,
}

LOCAL_EXTENSIONS = ["/app/extensions/ai_assistant"]
```

Then configure the AI provider — see the [Vambery AI Agent docs](ai_assistant/README.md#configuration) for details.

### Docker Setup

The extensions work out of the box with Superset's Docker Compose setup. Set your provider via environment variables in `docker/.env-local`:

```bash
# Azure OpenAI
AI_PROVIDER=azure_openai
AZURE_OPENAI_API_KEY=your-key
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_VERSION=2024-12-01-preview

# OR Ollama (self-hosted, no API key needed)
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://your-ollama-host:11434
OLLAMA_MODEL=qwen3.5:122b
```

### Deployment Checklist

1. **Clone with submodules**:
   ```bash
   git clone --recurse-submodules https://github.com/integrityauthority/superset.git
   cd superset
   ```

2. **Update submodule to latest**:
   ```bash
   git submodule update --init --remote extensions
   ```

3. **Configure** `docker/.env-local` — set `AI_PROVIDER` and the corresponding provider settings (see above).

4. **Build and start** (production / non-dev mode):
   ```bash
   docker compose -f docker-compose-non-dev.yml up -d --build
   ```

5. **Verify**: Open SQL Lab, expand the right sidebar — the Vambery AI Agent panel should be visible with the model selector.

### Important: Frontend Build Requirement

The Superset frontend must be compiled with `DEV_MODE=false` for the extension
system (Module Federation) to work. If your `docker-compose-non-dev.yml` uses
`target: dev`, ensure the build args include:

```yaml
x-common-build: &common-build
  context: .
  target: dev
  args:
    DEV_MODE: "false"          # Required for Module Federation
    INSTALL_MSSQL_ODBC: "true" # If using MSSQL
```

Without `DEV_MODE: "false"`, the frontend build is skipped and extensions won't
load in the browser (the backend API will work but the UI panel won't appear).

> **Note on Ollama**: The Ollama server must be network-reachable from the Docker
> container. If using internal hostnames, ensure DNS resolution works inside
> Docker or use the IP address directly.

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
- [ ] OpenAI Responses API migration for server-side state and built-in tools

## Status

**Public Beta** — This extension is functional and actively developed. We use it in production, but expect rough edges. Breaking changes may occur between versions.

Built with the [Apache Superset Extension System](https://github.com/apache/superset) — the first community AI extension for Superset.

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).

## About

Built by [Integrity Authority](https://github.com/integrityauthority) — we build data tools that respect your intelligence.
