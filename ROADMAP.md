# Roadmap

Open questions and planned work for this repository.

**How this is organised.** [Cross-cutting](#cross-cutting) covers anything that applies
to the repo as a whole — Superset version targets, build and release, upstream
contributions. Everything below [Extensions](#extensions) is scoped to one extension;
a new extension gets its own `## <name>` section there, and keeps detailed design docs
under `<extension>/docs/`.

Items are marked **Open** (decision still needed), **Planned** (decided, not started)
or **Blocked** (waiting on something external).

---

## Cross-cutting

### Superset version targets — **Planned**

Only 6.1.0 has ever been released (2026-05-13); `6.2` and `7.0` exist as branches with
no tags yet. Capabilities we care about are split across them:

| Base | `core.chat` + `navigation` | Extensions Storage API |
|------|---------------------------|------------------------|
| 6.1 (production) | ❌ | ❌ |
| 6.2 (branch) | ✅ | ❌ |
| 7.0 (branch) | ✅ | ✅ |

Agreed approach: **capability detection with graceful fallback is the default**, so one
build runs everywhere; a **pinned, versioned base image is an opt-in fast track**, never
a requirement. Production stays on 6.1.x — a regulated system does not run an untagged
branch.

- [ ] Dev/test image pinned to the `6.2` branch (tag form: `6.2.0-dev-<date>-<sha>`), so
      the chat surface can actually be exercised.
- [ ] Re-check for 6.2/7.0 release tags periodically; revisit when either ships.

### Build and release automation — **Open**

`build-extensions.sh` fails on Windows: it passes POSIX paths to a native Python, so the
`.supx` packaging step aborts *after* clearing `dist/`. This already caused one broken
commit (a dropped `dist/manifest.json`, fixed in `8c0e646`). There is no CI in the repo,
so every release artifact is built by hand.

The script's manifest generation has also drifted from what actually ships: it emits a
subset (no `contributions`, no `moduleFederation.exposes`, no backend `dependencies`),
while the shipped `manifest.json` is the full `extension.json` plus generated fields.

- **Question:** add a GitHub Actions workflow that builds and attaches the `.supx` on
  tag, or keep it manual?
- Recommendation: add the workflow. It removes the platform dependency entirely, and the
  build must not be able to half-destroy `dist/` again.
- [ ] Reconcile the script's manifest generation with the shipped format.
- [ ] Make the script fail before touching `dist/` if its prerequisites are missing.

### Upstream contributions to Apache Superset — **Open**

Only contribute what is generally useful, via SIP + PR with tests.

- [ ] **Client Actions / agentic UI manipulation** *(primary candidate)*. SIP-214
      explicitly deferred this. We have a working reference (`set_editor_sql`,
      `ask_user`, `update_todo`). Check for an existing SIP first and join it if there
      is one; otherwise propose the abstraction, not our specific tools.
- [ ] **Page context in the navigation namespace** *(secondary)*. `navigation.getPage()`
      returns only the page *type*; the concrete identifier (dashboard id, explore
      datasource, SQL Lab tab) is not exposed.
- **Not upstream:** LLM provider abstraction, planner-checker loop, concrete tool
  implementations. These are extension-level by nature.

---

## Extensions

## ai_assistant — Vambery AI Agent

Current version **0.6.0**. Design detail: [core.chat + Storage API migration plan](ai_assistant/docs/core-chat-migration.md).

### Tool duplication vs. Superset internals — **Open**

Raised by Erik O'Leary in
[issue #2](https://github.com/integrityauthority/superset-extensions/issues/2): are we
duplicating tooling that Superset's MCP service already provides?

The overlap is real. Of our 18 tools, about nine have direct equivalents among the 24 in
`superset/mcp_service` (present since 6.1): `execute_sql`, `list_charts`,
`get_chart_info`, `update_chart`, `generate_chart`, `generate_dashboard`,
`list_datasets`, `get_dataset_info`.

What the code shows: the MCP tools are thin wrappers. `mcp_core.py` — where the logic
lives — imports no `fastmcp` at all, only `pydantic` and `superset.daos.base.BaseDAO`.
**So the real de-duplication target is `superset.daos.*`, not MCP.** Both the MCP service
and the REST API sit on it; we currently bypass it with raw
`db.session.query(SqlaTable)` / `Slice`.

- **Question:** move the metadata tools onto the DAO layer now, or leave them?
- Recommendation: yes, but scoped to `list_datasets`, `get_dataset`, `list_charts`,
  `get_chart` — the place where duplication and our authorisation gap are the same code.
- **Do not** import the MCP tool functions (they need the optional `fastmcp` extra and a
  FastMCP `Context`), and do not couple to `superset.mcp_service.*` internals of a
  service we don't run.
- **Keep ours regardless:** SQL execution and schema exploration (our sqlglot validation,
  dialect handling, `list_views` — which MCP has no equivalent for), and the UI-action
  tools, which cannot be MCP tools at all.
- [ ] Verify whether Superset DAOs apply permission filtering on this version. Expect
      **not** — filtering lives in the API layer's `base_filters`, and MCP adds it via
      `@tool(class_permission_name=...)`. Moving to DAOs removes duplication; it does not
      by itself fix authorisation.

### Authorisation and database access — **Open**

Found while reviewing the agent's SQL path. Ordered by severity.

- [ ] **No authorisation checks anywhere.** `security_manager` appears only in
      `_check_auth` (authentication). Any authenticated user can pass an arbitrary
      `database_id` and query any database Superset is connected to, regardless of their
      Superset permissions.
- [ ] **Least-privilege database account.** The agent runs SQL with the credentials
      stored on the Superset connection, not the end user's. A dedicated read-only
      account (or read-only replica) is the one control that neither prompt injection nor
      a string-check bug can bypass — cheap, and needs no code change.
- [ ] **Prefix-based SELECT guard is bypassable.** `sql.startswith("SELECT")` lets a
      stacked statement through (`SELECT 1; DELETE …`) on drivers that allow it. Parse
      with sqlglot and assert exactly one statement, checking type from the AST.
- [ ] **Metadata writes from prompts.** `update_dataset`, `update_chart`,
      `create_chart(save=true)`, `create_dashboard` write Superset objects with no
      per-object permission check.
- [ ] **Auth fails open**, and SQL is logged without the acting user — weak audit trail.

### Publish our tools to MCP — **Open**

The complement to the question above: `@tool` from `superset_core.mcp.decorators`
(available since 6.1) lets an extension register tools *into* the MCP service.

Direction: factor tool logic into one shared layer, have the in-app agent call it
directly in-process, and expose the data-oriented tools via `@tool` so external agents
reach them. One implementation, two surfaces, no protocol hop locally.

Deliberately **not** doing the reverse — having our in-process agent call MCP. The MCP
service runs as a separate process with its own Flask app and connection pool over the
same database; routing through it would add latency and a second auth surface for no new
capability.

- [ ] Reply to [issue #2](https://github.com/integrityauthority/superset-extensions/issues/2)
      with this position (draft prepared).
- [ ] Decide which tools are worth publishing.

### Storage API — **Blocked** on a 7.0 build

Implemented in 0.6.0 and dormant: detection makes it a no-op on 6.1/6.2, and it activates
by itself on 7.0. It has never run against a live Storage API.

- [ ] Exercise on a 7.0 build: persistence, `encrypt: true`, per-tab scoping,
      `persistent.shared` for playbooks.

### Chat surface follow-ups — **Planned**

Dual registration landed in 0.6.0 (`core.chat` with SQL Lab sidebar fallback).

- [ ] Exercise on a 6.2 build — all 18 tools and the planner through the chat mount;
      confirm the panel degrades correctly on the nine non-SQL-Lab pages.
- [ ] Handle `onDidResizePanel` instead of fixed sizing (note: the docs warn not all
      hosts provide a resizer).
- [ ] Check theme and syntax highlighting in the narrower floating bubble.
- [ ] Decide whether conversations should stay per-SQL-Lab-tab now that the panel is
      global.
- [ ] Retire the `views` fallback once a `core.chat` host is the supported minimum.
