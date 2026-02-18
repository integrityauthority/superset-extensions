# Superset Extensions

Community extensions for [Apache Superset](https://github.com/apache/superset).

## Extensions

### ai_assistant (Vambery AI Agent)

An AI-powered chat assistant for Superset that can query databases, explore datasets, and help with data analysis using Azure OpenAI.

- **Backend:** Python agent with tool-calling (execute SQL, list databases/datasets, get chart data)
- **Frontend:** React chat panel with SSE streaming, integrated into the Superset UI

See [ai_assistant/extension.json](ai_assistant/extension.json) for configuration.

## Usage with Superset

This repository is designed to be used as a [git submodule](https://git-scm.com/book/en/v2/Git-Tools-Submodules) inside a Superset installation:

```bash
# Inside your Superset repo:
git submodule add https://github.com/integrityauthority/superset-extensions.git extensions
git submodule update --init
```

Or when cloning a Superset fork that already has this submodule:

```bash
git clone --recurse-submodules https://github.com/integrityauthority/superset.git
```

## Development

```bash
# Backend
cd ai_assistant/backend
pip install -e .

# Frontend
cd ai_assistant/frontend
npm install
npm run build
```

## License

Apache License 2.0 - see [LICENSE](LICENSE).
