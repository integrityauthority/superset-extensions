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

### Superset version targets — **Decided: 7.0+ only from 0.8**

Last checked **2026-10-27**. 6.1.0 is the only final release; 7.0 has two release
candidates (`7.0.0rc1`, `7.0.0rc2`); 6.2 is still an untagged branch.

**Decision (2026-10-27): extensions in this repo target Superset 7.0 and newer.**
- **Vambery 0.7.x is the last line that runs on 6.x.** It stays available as a release
  for anyone who has not upgraded, but gets no new features.
- From 0.8 on, the capability detection and the 6.x fallbacks are removed: the `views`
  sidebar registration and the `window.superset` shim for `@apache-superset/core`.
- New work may use anything 7.0 provides without a fallback: `core.chat`, the SQL Lab
  and editor APIs, commands and menus, the Storage API, `superset_core` DAOs, MCP tool
  registration and the Task Framework.

The earlier rule, capability detection with graceful fallback so that one build runs
everywhere, applied while 6.x was the only stable base. It made the code carry two
surfaces and two storage modes. Its last result is 0.7.0.

Done:
- Test instance on the official `apache/superset:7.0.0rc2` image with production
  content. Vambery 0.7.0 verified there: `core.chat` and the Storage API work; the
  backend runs on SQLAlchemy 2.0 / Flask 3.

Open:
- [ ] Move production to 7.0.0 once it is final, after the test instance has passed.
- [ ] Re-check for the 7.0.0 final periodically. Pin the minimum host version in
      `extension.json` once 7.0.0 is tagged.

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

- [ ] **Encrypted extension storage** *(submitted)*. Values written with
      `encrypt: true` could never be read back. Issue
      [#45787](https://github.com/apache/superset/issues/45787), fix and real-cipher tests in
      [#45788](https://github.com/apache/superset/pull/45788). Once it is merged and released,
      Vambery turns `ENCRYPT_AT_REST` back on. Follow-up named in the issue:
      `re-encrypt-secrets` cannot handle user-scoped rows.

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

Current version **0.7.0**, the last one for Superset 6.x. Design detail:
[core.chat + Storage API migration plan](ai_assistant/docs/core-chat-migration.md).

### Road to 1.0 — **Planned** (decided 2026-10-27)

1.0 means: Superset 7.0+ only, permission-checked, able to edit what already exists, usable
from SQL Lab directly and from external agents. Once it ships, announce it in the
[beta discussion](https://github.com/apache/superset/discussions/38356) and elsewhere.

**0.8 — 7.0-only foundation, permissions, no lost functionality**
- [ ] Remove the 6.x code paths: `views` registration, the `window.superset` shim,
      the `isChatApiAvailable` / `isNavigationApiAvailable` detection, and the "no
      Storage API" branches. Bump the build to the 7.0 `@apache-superset/core` types.
- [ ] Move the metadata tools onto `superset_core` DAOs. Their `base_filter` applies
      Superset's own visibility rules.
- [ ] Route aggregates over datasets through the dataset query API
      ([#43527](https://github.com/apache/superset/pull/43527)), so that RLS, caching and row
      limits apply. Free-form SQL stays on our path.
- [ ] Close the authorisation gaps listed under
      [Authorisation and database access](#authorisation-and-database-access--open).
- [ ] **Parity check before and after.** List what each of the 18 tools does today and
      prove the new implementation does the same. Use a scripted run against the test
      instance with fixed inputs and compared outputs. Nothing ships if a capability is lost.

**0.9 — act in the app, and edit what exists**
- [ ] SQL Lab control through `sqlLab` and the editor handle:
  - insert or replace SQL in the editor, run it, or open it in a new tab;
  - use the selected text as context;
  - mark the faulty line with annotations.
- [ ] React to `onDidQueryFail`: offer to explain and fix the failing query.
- [ ] Commands and menus. Example: an "Ask Vambery" entry in the editor that opens the
      chat with the selection.
- [ ] **Edit existing objects, not just create new ones:**
  - `update_dashboard`: title, add, remove or reorder charts, layout, native filters;
  - edit a chart that already sits on a dashboard;
  - dataset metrics and calculated columns.
  - Say that 7.0 version history makes every change revertible. Check
    `is_managed_externally` before editing, because 7.0 refuses such updates server-side.
- [ ] **Teach the agent what 7.0 changed** (see [below](#teach-the-agent-about-70--planned)).

**0.10 — platform**
- [ ] Publish tools to MCP through `superset_core.mcp.decorators.tool`. The 7.0 MCP
      process loads extensions; this was checked on the test instance. Start with
      `vambery_ask`, the whole planner and checker behind one tool, plus a few read-only
      tools with `class_permission_name`.
- [ ] Long multi-step runs on the Task Framework (`superset_core.tasks`): they survive a
      closed tab, can be cancelled and report progress.
- [ ] Settings, see [Configuration and preferences](#configuration-and-preferences--planned).
- [ ] Chat polish: follow `onDidResizePanel`. Re-enable encryption when the upstream fix
      ([#45788](https://github.com/apache/superset/pull/45788)) is released.

**1.0** — the above, plus the answer-correctness regression set and a CI-built `.supx`.

### Teach the agent about 7.0 — **Planned**

From the 7.0 `UPDATING.md`, the changes the agent's tools and prompts must know about:
- [ ] **Owners → Subjects.** Owners, dashboard roles and RLS roles are replaced by
      Subjects. Check every place that reads or sets ownership.
- [ ] **`explore_json` is removed** and charts are drawn from their saved query context.
      `create_chart` does not save one today. Such charts work in Explore, which
      regenerates it on open, but reports, thumbnails and chart-data-by-id may fail
      until then. Save the query context at creation.
- [ ] **New aggregates:** `MEDIAN`, sample standard deviation and sample variance.
- [ ] **Version history and soft delete are on by default,** and tagging is on. Tag
      what the agent creates, and mention version history when it edits.
- [ ] **SQL Lab denies `information_schema` and large-object access by default.**
      Schema exploration must keep using the inspector, never `information_schema`
      queries.
- [ ] **Native value filters:** "Select all" always targets the whole column. This
      matters once the agent edits filters.

### Configuration and preferences — **Planned**

Today:
- **Configuration is server-side only:** the `AI_ASSISTANT` dict in
  `superset_config.py`, or environment variables. There is no settings screen.
- **Azure OpenAI** offers exactly one deployment (`AZURE_OPENAI_DEPLOYMENT`).
- **Ollama models are discovered live** from `/api/tags` each time the panel loads.
- **Per user,** the chosen model is remembered (Storage API, local tier). History is kept
  per SQL Lab tab (persistent tier).

Plan:
- [ ] Admin defaults keep coming from `superset_config.py` / env. The rest layers on
      top of them; nothing new is required to start.
- [ ] Azure discovery like Ollama's: list the resource's deployments and offer the
      chat-capable ones. An optional allow-list keeps embeddings and routers out.
- [ ] A small settings view in the chat:
  - favourite models and the default model;
  - history retention and "clear my history";
  - answer language.

  Stored per user in the persistent tier.
- [ ] Decide whether conversations stay per SQL Lab tab now that the panel is global.

### Tool duplication vs. Superset internals — **Planned for 0.8**

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

- **Decided (2026-10-27):** move onto the DAO layer in 0.8. Start with `list_datasets`,
  `get_dataset`, `list_charts` and `get_chart`, where the duplication and our
  authorisation gap are the same code. It must not lose any capability; see the parity
  check under [Road to 1.0](#road-to-10--planned-decided-2026-10-27). 7.0 exposes
  these DAOs to extensions as `superset_core.common.daos`.
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

### Publish our tools to MCP — **Planned for 0.10**

The complement to the question above: `@tool` from `superset_core.mcp.decorators` lets an
extension register tools *into* the MCP service. On 7.0 the MCP process loads extensions
at startup (checked on the test instance), so this needs no extra deployment step.

Direction: factor tool logic into one shared layer, have the in-app agent call it
directly in-process, and expose the data-oriented tools via `@tool` so external agents
reach them. One implementation, two surfaces, no protocol hop locally.

Deliberately **not** doing the reverse — having our in-process agent call MCP. The MCP
service runs as a separate process with its own Flask app and connection pool over the
same database; routing through it would add latency and a second auth surface for no new
capability.

- [ ] Reply to [issue #2](https://github.com/integrityauthority/superset-extensions/issues/2)
      with this position (draft prepared).
- [ ] Decide which tools are worth publishing. Starting point: `vambery_ask` (the
      planner and checker as one tool — what plain MCP tools do not offer) plus read-only
      tools. Publish nothing before the 0.8 permission work.
- Upstream MCP keeps moving and makes publishing more attractive for external agents
  (e.g. Hermes): typed tool outputs and request-wrapper validation errors on 7.0; an
  optional **per-role dataset scope** on master only
  ([#44146](https://github.com/apache/superset/pull/44146)). Published tools should
  follow the same conventions — arguments wrapped in a `request` model, typed outputs.

### Storage API — **Done in 0.7.0**, encryption **Blocked**

Verified on `7.0.0rc2`: conversations persist per SQL Lab tab and survive a reload. They
are stored **unencrypted**, because `encrypt: true` values cannot be read back on that
build. The fix is submitted upstream
([#45788](https://github.com/apache/superset/pull/45788)).

- [ ] Re-enable `ENCRYPT_AT_REST` once a release contains the fix. Values written by
      the broken builds will still read back.
- [ ] `persistent.shared` for playbooks.

### Chat surface follow-ups — **Planned**

`core.chat` registration landed in 0.6.0 and was verified on 7.0.0rc2 in 0.7.0.

- [ ] Handle `onDidResizePanel` instead of fixed sizing (the docs warn that not all
      hosts provide a resizer).
- [ ] Check theme and syntax highlighting in the narrower floating bubble.
- The 6.x-only items (sidebar fallback, losing conversations on 6.2) are closed by the
  7.0-only decision.
