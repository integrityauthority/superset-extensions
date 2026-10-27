# Using Vambery from other agents (MCP)

Superset 7.0 runs an MCP server next to the web app. It loads extensions at
startup, and Vambery registers one tool there:

```
extensions.integrityauthority.vambery-ai-assistant.ask
```

Superset's own MCP tools already cover the building blocks: SQL, charts,
dashboards and datasets. `ask` adds the agent on top. It explores the schema,
plans and runs the queries, and checks the grain of every aggregate. Then it
returns the answer with the SQL and the assumptions behind each number. Use
`ask` for a question; use Superset's tools for a single, known operation.

## Arguments and result

| Argument | Type | Meaning |
|---|---|---|
| `question` | string | The question, in any language |
| `database_id` | integer | Superset database id (Superset's `list_databases` tool lists them) |
| `schema` | string, optional | Schema to work in |
| `allow_changes` | boolean, default `false` | Let the agent save charts and create or edit datasets and dashboards |

The result is an object with these fields:

| Field | Content |
|---|---|
| `answer` | Markdown text: the result and the assumptions behind each number |
| `sql` | The final query |
| `charts` | Charts the agent made: name, URL, whether saved |
| `dashboards` | Dashboards the agent made or changed: id, URL |
| `needs_clarification` | A question with options, when the agent needs a choice. Answer it in a follow-up call |
| `tools_used` | The agent's steps |

Without `allow_changes` the call only reads. Requests to create or change
anything are refused, and the agent answers with the data and the SQL instead.

## Permissions

Calls run as the user the MCP request authenticated as, with the same checks as
the chat panel:
- only databases exposed in SQL Lab;
- only tables the user may read;
- edits only on objects the user is an editor of.

The tool also requires SQL Lab's `can_execute_sql_query` permission.

Never run the MCP server without authentication. Without API keys or JWT, every
caller acts as `MCP_DEV_USERNAME`.

## Connecting Claude Code or Hermes

1. **On the Superset side:**
   - enable API keys (`FAB_API_KEY_ENABLED = True`);
   - start the MCP service (`superset mcp run`, or the `superset-mcp` compose service);
   - publish it over HTTPS.
2. **Create an API key.** Each user creates one on their Superset profile page. The
   key starts with `sst_`. It acts with that user's permissions.
3. **Register the server in the client:**

   ```bash
   claude mcp add --transport http superset https://<superset-host>:<mcp-port>/mcp --header "Authorization: Bearer sst_..."
   ```

Superset's MCP server uses tool search, so `tools/list` shows only a few tools.
Find `ask` with `search_tools` (for example, query "vambery") and call it through
`call_tool`. Most clients do this on their own.

A typical call takes 20–60 seconds: the agent runs several queries and checks
them. Give the client a generous timeout.
