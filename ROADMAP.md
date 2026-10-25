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

Last checked **2026-10-25**. 6.1.0 is the only final release (2026-05-13). **7.0 has
release candidates** — `7.0.0rc1` (2026-10-13) and `7.0.0rc2` (2026-10-16), with official
`apache/superset` images for both. `6.2` is still an untagged branch, so 7.0 may well ship
first. Capabilities we care about are split across them:

| Base | `core.chat` + `navigation` | Extensions Storage API | Backend stack |
|------|---------------------------|------------------------|---------------|
| 6.1 (production) | ❌ | ❌ | SQLAlchemy 1.4, Flask 2 |
| 6.2 (branch) | ✅ | ❌ | SQLAlchemy 1.4, Flask 2 |
| 7.0 (rc2 tagged) | ✅ | ✅ | **SQLAlchemy 2.0, Flask 3** |

Against `7.0.0rc2`, the extension API files we build on (`chat`, `navigation`,
`contributions`, `sqlLab`, `views`) are byte-identical to the 6.2 branch, and the Storage
API signatures match our declarations exactly. No code change is needed to target it.

The 7.0 stack change matters more for our backend than any extension API change. A
static check of `ai_assistant` found one legacy call (`Query.get()`, now `session.get()`)
and nothing else that SQLAlchemy 2.0 or Flask 3 removed — explicit commits, no raw string
`execute`, no `select([...])`, no `dict(row)`. That is a static check, not a run.

Agreed approach: **capability detection with graceful fallback is the default**, so one
build runs everywhere; a **pinned, versioned base image is an opt-in fast track**, never
a requirement. Production stays on 6.1.x — a regulated system does not run an untagged
branch.

- [ ] Test instance on the official `apache/superset:7.0.0rc2` image — a tag, not a branch,
      which fits the pinning rule better than the earlier `6.2` branch plan. Use its own
      metadata database (a copy at most, never the production one), and keep scheduled
      reports off so a copied schedule cannot send duplicates.
- [ ] Move production to 7.0.0 once it is final, after the test instance has passed.
- [ ] Re-check for the 7.0.0 final and any 6.2 tag periodically.
- [ ] Run the backend on a 7.0 build (SQLAlchemy 2.0 / Flask 3) — chat, streaming, JWT
      login and the four write tools (`update_dataset`, `update_chart`, `create_chart`,
      `create_dashboard`) in particular.
- 7.0 also adds pieces worth adopting later: a name-based, **RLS-respecting** query API
  for datasets (`POST /api/v1/datasource/<type>/<id>/query`,
  [#43527](https://github.com/apache/superset/pull/43527)), and the Global Task Framework
  in `superset_core` ([#43407](https://github.com/apache/superset/pull/43407)) for
  long-running work.

### Build and release automation — **Open**

`build-extensions.sh` fails on Windows: it passes POSIX paths to a native Python, so the
`.supx` packaging step aborts *after* clearing `dist/`. This already caused one broken
commit (a dropped `dist/manifest.json`, fixed in `6adbd7b`). There is no CI in the repo,
so every release artifact is built by hand.

The hand-built path has also shipped a wrong artifact: the **v0.6.0 `.supx` reports
`0.5.2` on `/health`**, because the backend was copied into `dist/` before the version
strings were synced. The code inside is the 0.6.0 code; only the label is wrong. `dist/`
on `main` is fixed; the published asset is not.

The script's manifest generation has also drifted from what actually ships: it emits a
subset (no `contributions`, no `moduleFederation.exposes`, no backend `dependencies`),
while the shipped `manifest.json` is the full `extension.json` plus generated fields.

- **Question:** add a GitHub Actions workflow that builds and attaches the `.supx` on
  tag, or keep it manual?
- Recommendation: add the workflow. It removes the platform dependency entirely, and the
  build must not be able to half-destroy `dist/` again.
- [ ] Reconcile the script's manifest generation with the shipped format.
- [ ] Release check: fail if `extension.json`, `package.json`, `pyproject.toml`,
      `__init__.py` and `dist/backend/.../__init__.py` disagree on the version.
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
- [ ] **SQL Lab: tables not loading after database + schema selection.** Our Superset
      build carries a fix from March 2026 (`useDatabaseSelector` dispatching against an
      empty query editor). Upstream 7.0.0rc2 has no equivalent guard, but may have solved it
      differently. Reproduce on stock 7.0 first; upstream it only if the bug is still there.
- **Not upstream:** LLM provider abstraction, planner-checker loop, concrete tool
  implementations. These are extension-level by nature.

---

## Extensions

## ai_assistant — Vambery AI Agent

Current version **0.6.1**. Design detail: [core.chat + Storage API migration plan](ai_assistant/docs/core-chat-migration.md).

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
- On 7.0+, prefer the new dataset query API
  ([#43527](https://github.com/apache/superset/pull/43527)) for aggregates over
  *datasets*: it enters the pipeline at `QueryContextFactory`, so RLS, caching and
  row-limit clamping apply — which our raw `Database.execute()` path skips. Upstream
  refactored two MCP tools onto the same `superset/common/tabular_query.py` after they
  drifted apart; the same drift is our risk. Free-form SQL stays on our path.

### Answer correctness — aggregate semantics — **Planned**

Raised in the
[public beta discussion](https://github.com/apache/superset/discussions/38356#discussioncomment-18748250):
the checker treated any partial result as success, so a query can return plausible rows
and still report the wrong total — e.g. picking the "latest" invoice revision by arrival
order lets a late, replayed old revision win (verified on synthetic data: 18 000 vs.
20 000).

Done (unreleased):
- Planner, executor and simple-mode checklist require fixing the grain before any
  total: authoritative row by version column, never by insert order; no SUM/COUNT across
  a one-to-many join.
- The checker now receives the discovered schema and the SQL that actually ran — before,
  it saw neither, so it could not have caught this even when told to. It corrects
  downstream steps only for evident defects, keeping its bias toward no re-planning.
- The final summary states the assumptions behind every reported number.

Still open:
- [ ] Prompt rules are not enforcement. Build a small synthetic regression set (late
      revisions, join fan-out, duplicate keys) and run the agent against it before and
      after prompt changes — synthetic data only.
- [ ] Include a **conflicting-duplicates** case (suggested in the discussion): two
      different amounts for the same invoice *and* revision. The version-column rule then
      silently picks the later arrival. Expected: report the conflict and withhold the total
      and any saved chart. Since the executor does not ask questions mid-run, the conflict
      surfaces in the final answer.
- [ ] A step that already saved a chart with a wrong aggregate cannot be corrected in
      place; the checker can only add a corrective step. Consider deferring
      `save_chart` until the checker has passed the producing SQL step.

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
- Upstream MCP keeps moving and makes publishing more attractive for external agents
  (e.g. Hermes): typed tool outputs and request-wrapper validation errors on 7.0; an
  optional **per-role dataset scope** on master only
  ([#44146](https://github.com/apache/superset/pull/44146)). Published tools should
  follow the same conventions — arguments wrapped in a `request` model, typed outputs.

### Storage API — **Planned** (testable on `7.0.0rc2`)

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
- [ ] **Closing the chat loses the conversation on 6.2.** Per the 7.0 chat docs
      ([#44490](https://github.com/apache/superset/pull/44490)), switching display mode
      keeps the panel mounted, but closing it unmounts the panel. With no Storage API on
      6.2, the in-memory conversation is gone. **Open:** fall back to browser
      `sessionStorage` there? It would be unencrypted, which conflicts with the
      `encrypt: true` choice made for 7.0 — a policy call, not a technical one.
- [ ] Retire the `views` fallback once a `core.chat` host is the supported minimum.
