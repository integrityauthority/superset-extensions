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

### Build and release automation — **Done** (2026-10-27)

- `scripts/build_supx.py` replaces `build-extensions.sh` and runs on any platform.
  It stops before touching `dist/` if the version strings disagree
  (`extension.json`, `package.json`, `pyproject.toml`, `__init__.py`) or the bundle is
  missing. It assembles in a temporary directory and writes the full `extension.json`
  plus the generated fields as `manifest.json`. Requirements files get LF line endings.
- `.github/workflows/release-supx.yml` builds the `.supx` on a `v*` tag and attaches it
  to the release. Superset accepts only plain `X.Y.Z` versions, so a release candidate
  is the final number published as a GitHub prerelease: it does not become the
  "latest" that deployments fetch until it is promoted.
- The v0.6.0 asset still reports `0.5.2` on `/health`; it stays as it was published.

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

Current version **1.0.0**, published as a prerelease until the browser check below (Superset 7.0+). **0.7.0** is the last release for
Superset 6.x. Design detail:
[core.chat + Storage API migration plan](ai_assistant/docs/core-chat-migration.md),
[MCP](ai_assistant/docs/mcp.md).

### Road to 1.0 — **Release candidate** (2026-10-27)

1.0 means:
- Superset 7.0+ only;
- permission-checked;
- able to edit what already exists;
- usable from SQL Lab directly and from external agents.

Once 1.0 is final, announce it in the
[beta discussion](https://github.com/apache/superset/discussions/38356) and elsewhere.

**How it was checked.** Every step ran on a 7.0.0rc2 test instance:
- **Tool parity harness** (`backend/tests/parity`): every tool with fixed inputs, as
  admin and as two restricted users. Against 0.7.0 there are 0 unexpected
  differences. Each intended change is listed with its reason in
  `expected_changes.json`.
- **Agent evaluation** (`backend/tests/agent_eval`): real questions through the whole
  agent on synthetic data, checked against known answers. 5/5 with
  `gpt-6-luna` (Azure).

**0.8 — 7.0-only foundation, permissions, no lost functionality** — done
- [x] 6.x code paths removed: `views` registration, the `window.superset` shim,
      capability detection.
- [x] Metadata tools on `superset_core` DAOs, with Superset's access filters.
      `find_one_or_none(id=…)` is avoided: after a filter that joins, `filter_by`
      targets the joined table (an upstream DAO bug worth reporting).
- [x] `query_dataset`: datasets queried by metric and column names through Superset's
      tabular query layer (RLS, cache, limits).
- [x] Authorisation gaps closed (see below).
- [x] Parity check: 0 unexpected differences. Two bugs found in 0.7 on 7.0 are fixed:
  - a failed query came back as an empty result;
  - a result served from Superset's cache (a list, not a DataFrame) was read as empty.

**0.9 — act in the app, and edit what exists** — done
- [x] SQL Lab:
  - query into the editor and run it, or into a new tab (`open_sql_tab`);
  - the editor selection travels with the question.
- [x] Failed queries: the offending line is marked in the editor, and the chat offers
      **Explain and fix**. The line is found by the identifier the error names, because
      Superset reformats the SQL it runs, so the database's own line numbers do not
      match the editor.
- [x] Commands and menus: **Ask Vambery** and **Explain and fix** in the SQL editor
      toolbar.
- [x] Editing in place:
  - `list_dashboards`, `get_dashboard`, `update_dashboard`: title, description,
    published, add / remove / reorder charts, native value filters, with filter scopes
    kept in sync;
  - metrics and calculated columns through `update_dataset`.

  Editorship and `is_managed_externally` are checked; the prompt prefers editing to
  duplicating and mentions version history.
- [x] Teaching the agent 7.0 (see below).

**0.10 — platform** — done except where marked
- [x] MCP: `ask` registered through `superset_core.mcp.decorators.tool`, read-only
      unless `allow_changes`. Verified over HTTP with a restricted user's API key.
- [x] Settings view:
  - the model to start with and favourite models;
  - answer language;
  - deleting all saved conversations.
- [x] Azure deployments discovered for the model picker.
- [x] Reasoning models that refuse tools while reasoning (`gpt-6-luna`) are retried with
      `reasoning_effort: "none"`.
- [ ] **Task Framework** for long runs: moved to 1.x. It needs the
      `GLOBAL_TASK_FRAMEWORK` feature flag and changes how the panel receives results
      (polling instead of a stream). The stream already shows progress; what is missing
      is surviving a closed tab.
- [ ] `onDidResizePanel`: moved to 1.x (cosmetic).
- [ ] Encryption at rest: waits for the upstream fix.

**1.0 final — what is left**
- [ ] Browser check on the test instance:
  - the toolbar buttons;
  - the failure banner;
  - the settings view;
  - an edited dashboard and its new native filter opening cleanly.
- [ ] Then promote the `v1.0.0` prerelease, so it becomes "latest". Production stays on 0.7.0 until it runs
      Superset 7.0. The deploy kit pins it, and its fetch script refuses a 7.0-only
      release on a 6.x image.

### Teach the agent about 7.0 — **Done** except where marked

- [x] New aggregates `MEDIAN`, `STDDEV_SAMP`, `VAR_SAMP` in `create_chart`, with which
      engines support them.
- [x] Version history mentioned on edits; edit-in-place preferred over copies.
- [x] `information_schema` and system catalogs avoided; SQL Lab blocks them by default.
- [x] **Query context:** checked, and not a problem. 7.0's own MCP `generate_chart`
      saves none either, and Superset rebuilds a missing one when the chart opens.
      `update_chart` now clears a stale one when params change.
- [ ] **Owners → Subjects:** new objects get the creator as editor through Superset's
      own create commands. Nothing reads owners. Only the test instance's admin was
      exercised; recheck with groups once production uses them.
- [ ] Tag objects the agent creates (tagging is on by default in 7.0).

### Configuration and preferences — **Done**

- Admin defaults stay in `superset_config.py` / env: provider, default model,
  `AZURE_OPENAI_DEPLOYMENTS` (optional allow-list), `AZURE_OPENAI_REASONING_EFFORT`
  (optional).
- Discovery: Ollama models from `/api/tags`; Azure deployments from the resource,
  cached for ten minutes, with embeddings, speech and images left out.
- Per user, in Superset (persistent tier): favourite models, picker filter, answer
  language. The model to start with stays in the local tier.
- [ ] Open: whether conversations stay per SQL Lab tab now that the panel is global.

### Tool duplication vs. Superset internals — **Done in 0.8**

Raised by Erik O'Leary in
[issue #2](https://github.com/integrityauthority/superset-extensions/issues/2).
- The metadata tools use `superset_core.common.daos`, whose access filters Superset
  applies (verified: a user without database access sees nothing).
- Aggregates over datasets can go through `query_dataset`.
- Free-form SQL and schema exploration stay ours. They now sit behind SQL Lab's own
  access check, and `Database.execute` applies RLS and the SQL mutator.
- [ ] Reply to issue #2 with the outcome.

### Answer correctness — aggregate semantics — **Done**, kept as a regression set

The checker now sees the schema and the SQL that ran. The final summary now gets
every step's SQL and result (before, it often said it had none).

`backend/tests/agent_eval` holds the cases on synthetic data:
- late-arriving old revision: 20 000, not 18 000;
- join fan-out: 600, not 1 100;
- conflicting duplicates: the conflict is reported.

It also checks that the agent edits an existing dashboard rather than creating a new
one. Run it before and after any prompt or planner change.

- [ ] A step that already saved a chart with a wrong aggregate cannot be corrected in
      place. Consider deferring `save_chart` until the checker has passed the producing
      SQL step.

### Authorisation and database access — **Done in 0.8**

The agent does what the user could do in SQL Lab and Superset's UI, nothing more:
- databases through `DatabaseDAO`, and only when exposed in SQL Lab;
- SQL behind `raise_for_access(..., force_dataset_match=True)`, as SQL Lab;
- table access for metadata and samples;
- editorship for writes;
- auth fails closed;
- every tool call is logged as `ai_assistant.audit` with the user and the SQL;
- the read-only guard parses the SQL: one statement, no mutation.

A user without database access was refused everywhere. A user without editorship
could not change another user's chart; 0.7 allowed both.

- [ ] Recommended regardless: a read-only database account for Superset's connections.
      This is the one control that no code bug can bypass.

### Storage API — **Done in 0.7.0**, encryption **Blocked**

- [ ] Re-enable `ENCRYPT_AT_REST` once a Superset release contains
      [#45788](https://github.com/apache/superset/pull/45788). Values written by the
      broken builds will still read back.
- [ ] `persistent.shared` for playbooks.
