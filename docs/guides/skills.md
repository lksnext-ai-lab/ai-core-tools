# Skills

> Part of [Mattin AI Documentation](../README.md)

## Overview

A **Skill** is a reusable, Markdown-driven specialization that can be attached to one or more agents. Every skill is a small **package**: a `SKILL.md` file (frontmatter + instructions) plus zero or more bundled files (scripts, references, templates). At execution time, the skill's `SKILL.md` body is injected into the agent's context and the agent can use the `load_skill` / `read_skill_file` tools to pull in the full package on demand; if the skill declares a bootstrap script and a sandbox is available, its files are also materialised inside the sandbox so code can actually use them.

Skills are either:
- **App-scoped** — created/imported by an app admin, visible only within that app (`Skill.app_id` set).
- **System skills** — platform-wide, managed by omniadmins, `Skill.app_id IS NULL`. See [System skills](#system-skills) below.

---

## The skill package format

A package is a `SKILL.md` file at its root plus, optionally, any number of other files (scripts, reference docs, templates) under it. When imported as a `.zip`, `SKILL.md` must sit at the archive root (or under a single common top-level directory, which is stripped automatically).

### `SKILL.md` frontmatter contract

`SKILL.md` is a YAML frontmatter block (`---\n...\n---`) followed by a Markdown body. Parsing/rendering is a pure module, `backend/utils/skill_frontmatter.py` — no DB, no FastAPI — reused by import, export, the Claude Code plugin importer and the system-skill seeder, so the contract is identical everywhere a `SKILL.md` is read or written.

| Frontmatter key | Maps to | Meaning |
|---|---|---|
| `name` | `Skill.name` | **Required.** Normalised (lowercase, whitespace collapsed to `-`), restricted to `[a-z0-9._-]`, max 100 chars — it doubles as the sandbox directory name, so it must not start with `.`/`-`, end with `.`, contain `..`, or be a reserved device name. |
| `display_name` | `Skill.display_name` | Human-readable label; falls back to `name` when absent. |
| `description` | `Skill.description` | Short summary. |
| `when_to_use` | stored inside `Skill.frontmatter` (JSON) under `when_to_use` | Guidance on when the agent (or the [skill router](#the-opt-in-skill-router)) should reach for this skill. |
| `allowed-tools` (list or comma-separated string) | `Skill.allowed_tools` (JSON list) | **Metadata only — see the warning below.** |
| `runtime` | `Skill.runtime` | e.g. `python3.11`. Informational/sandbox-hint only. |
| `bootstrap_script_path` | `Skill.bootstrap_script_path` | Package-root-relative path to a script that prepares the skill's sandbox runtime (e.g. `pip install`s dependencies). Validated against the actual package contents at import time. |
| `runtime_options` | `Skill.runtime_options` (JSON) | Free-form object, provider-specific. |
| `disable-model-invocation` | — | Reserved for a future "not directly invocable" flag; currently parsed and preserved but not enforced. |
| any other key | preserved under `Skill.frontmatter`'s `extra` | Round-trips losslessly through export → import. |

Everything else in `SKILL.md` after the closing `---` is the **body** — stored as `Skill.content` and shown to the agent as the skill's instructions.

> **`allowed_tools` is metadata only.** It is persisted, imported/exported, and rendered in the UI purely for documentation/display. **No code path reads it to filter, restrict or grant the agent's actual tool access at execution time** — an agent's real tool set is determined entirely by its own configuration (MCP configs, code interpreter flag, agent-as-tool links, etc.), independent of what any attached skill's frontmatter claims it needs. Treat an `allowed_tools` list in a skill you didn't author as a hint, never as a security boundary.

### Zip import / export

- **Import**: `POST /internal/apps/{app_id}/skills/import` (app-scoped, `administrator`+) or `POST /internal/admin/system-skills/import` (system, omniadmin-only). Both accept a `.zip` and are validated by a hardened, fully in-memory streaming reader (`backend/utils/safe_zip.py`) before anything is parsed — see [Import limits](#import-limits) below for the exact caps. A structurally invalid archive is rejected with 400; a duplicate skill name in the target scope (app or system) is rejected with 409.
  - **`is_enabled` on import differs by scope.** The app-scoped route lands the imported skill **enabled** — a single-file upload an admin has presumably just reviewed, with blast radius limited to their own app. The admin system-skill route lands it **disabled** — a system skill is platform-wide (`app_id IS NULL`) and becomes immediately selectable in every tenant's skill picker the moment the request returns 201, so it must go through the same explicit review-and-enable step (`PATCH .../enabled`) as a Claude Code plugin import (below) before it can be attached to an agent.
- **Export**: `GET /internal/apps/{app_id}/skills/{skill_id}/export` (works for the app's own skills and for enabled system skills) or `GET /internal/admin/system-skills/{skill_id}/export`. Returns a `.zip` containing a re-rendered `SKILL.md` (frontmatter + body, deterministic key order) plus every bundled file at its recorded path — export → import round-trips losslessly.

### Import limits

Configurable via environment variables (see [Environment Variables](../reference/environment-variables.md#skill-package-import) for the full list and defaults): maximum file count, maximum uncompressed size per file and in total, a compression-ratio cap (zip-bomb guard), a cap on the uploaded archive's own size, and a process-wide concurrency bulkhead shared between import and export. Absolute paths, `..` traversal, and symlink entries are always rejected regardless of configuration.

---

## System skills

System skills are platform-wide skills with `Skill.app_id IS NULL`. They:

- Are managed exclusively by **omniadmins** through the admin **System Skills** page (`/internal/admin/system-skills/*` — list including disabled, create, edit, delete, import, export, enable/disable). App-level admins cannot create, edit or delete them — any attempt through the app-scoped skill routes is rejected with **403**.
- Are visible to every app as **read-only, merged entries** in that app's skill listing: `SkillService.list_skills` merges the app's own skills with all currently **enabled** system skills. A **disabled** system skill disappears from every app's listing entirely (an app admin never sees it as an option to attach). If a system skill's normalised name collides with one of the app's own skills, the app's own skill wins and the collision is logged.
- Are never counted against an app's `skills` tier quota (only app-scoped skill creation is quota'd).
- Carry a `source` field: `'admin'` (created directly, via the admin UI or an import) or `'yaml'` (seeded from `backend/system_defaults.yaml` at startup — see [Curated system skill packages](#adding-a-curated-system-skill-package) below). A `source='yaml'` system skill **cannot be hard-deleted** — `DELETE .../system-skills/{id}` returns **409** for it, because the seeder would simply recreate it (create-if-missing only) on the next restart. The only way to remove it from use is to **disable** it (`is_enabled=False`), which the seeder always respects and never overrides.

---

## `is_enabled` vs `is_frozen`

These are two independent flags with different jobs — do not conflate them:

| Flag | Set by | Meaning |
|---|---|---|
| `is_enabled` | An admin (app admin for their own skills, omniadmin for system skills) via the enable/disable toggle | Whether the skill is currently *usable*. A disabled app skill stays visible/editable to its owner but is dropped when resolving which skills an agent can actually use this turn (`resolve_agent_skills`); a disabled system skill disappears from every app's listing entirely. |
| `is_frozen` | `FreezeService`, automatically, when a subscription tier changes (SaaS mode) | Whether the resource currently **exceeds** the owning app's tier limits. Frozen resources are a billing/quota concept unrelated to whether an admin wants the skill active. |

A skill can be enabled and frozen, disabled and not frozen, or any other combination — they gate different things and neither implies the other.

---

## Sandbox activation

When an agent calls the `load_skill` tool (or the skill is loaded implicitly) and a sandbox is available for the conversation, the skill's bundled files are materialised inside that sandbox so later `code_interpreter`/sandbox tool calls can actually use them:

1. The service layer builds a detached `SkillPackagePayload` (name, files, bootstrap script path, runtime) from the `Skill`/`SkillFile` rows — the sandbox provider never sees an ORM object or a DB session.
2. `SandboxProvider.ensure_skill(handle, payload)` materialises the package under `<skills_root>/<normalised skill name>/` (`/workspace/.skills/<name>/` by default — `SKILLS_ROOT` in `backend/tools/sandbox/provider.py`; some providers use a different filesystem root and override `skills_root`).
3. If the skill declares a `bootstrap_script_path`, it is run (timeout `SANDBOX_SKILL_BOOTSTRAP_TIMEOUT_S`, default 120s — deliberately more generous than a normal execution timeout, since bootstrap scripts are explicitly allowed network egress to install dependencies).
4. `ensure_skill` is **idempotent**: re-activating an already-active skill (same `skill_id`) is a fast no-op; a *different* skill trying to reuse the same normalised name is refused rather than overwriting the existing directory. Activation state is tracked per sandbox in `SandboxHandle.active_skills`, plus an on-disk marker so a backend restart or resumed sandbox doesn't blindly re-run a bootstrap.
5. A bootstrap failure or timeout never aborts the turn — it's recorded as a `degraded` activation (the skill's files are still usable, just without whatever the bootstrap would have installed). Only a genuinely dead sandbox propagates, so the caller can evict and recreate the handle.

Two tools read the *content* side of a skill without necessarily needing sandbox activation:
- `load_skill(skill_name)` — returns the skill's `SKILL.md` body as an activation message, and, when a sandbox is available, triggers the materialisation above.
- `read_skill_file(skill_name, path)` — reads one bundled file (text files inline, binary files reported by name/size only) directly from the `SkillFile` rows, without needing the sandbox at all. `path` is normalised through the same path-safety rules used at import time before any lookup.

---

## The opt-in skill router

By default, every skill attached to an agent is always resolved and injected into the prompt. For agents with many attached skills, `Agent.skill_router_enabled` (boolean, **default `false`**) turns on a lightweight pre-selection step: before assembling the prompt, a small, isolated LLM call (metadata only — skill `name`/`description`/`when_to_use`, never full skill content, system prompt or history) picks at most 2 relevant skills for that turn (`backend/services/skill_router_service.py`). It falls back to a deterministic keyword scorer if no LLM is available, the call fails, or it exceeds its own short timeout (3.5s) — the router is never allowed to block or fail a turn.

Enable it per agent (agent form toggle, or `PATCH`/`POST` with `skill_router_enabled: true`) when an agent has enough skills that always injecting all of them would bloat the prompt or dilute relevance. It is **off by default** everywhere — a 2-skill support bot pays nothing for it; a 20-skill document agent opts in.

---

## Adding a curated system skill package

Curated system skills ship as real directories under `backend/system_skills/<name>/` and are seeded (create-if-missing only, never updated/restored) on every backend startup, in every deployment mode, by `backend/services/system_skills_seeder.py`.

1. **Directory layout** — mirror the shipped examples (`word`, `pdf`, `pptx`, `data-analysis`, `charts`):
   ```
   backend/system_skills/<name>/
     SKILL.md                     # required — frontmatter + instructions
     scripts/
       bootstrap.sh                # optional — installs sandbox dependencies
       <name>.py                   # optional — a genuine, runnable template script
     references/
       <topic>-cheatsheet.md       # optional — extra reference material
   ```
2. **Register it** in `backend/system_defaults.yaml`'s `skills:` list:
   ```yaml
   skills:
     - name: word
       path: word          # relative to backend/system_skills/
   ```
   `name` must match the `name` in the package's own `SKILL.md` frontmatter — a mismatch is rejected as a seeding failure for that package (the rest of the list still seeds).
3. **Packaging requirement (do not re-break this)**: the backend Docker image is built with `context: ..` / `dockerfile: backend/Dockerfile`, so only the **root** `/.dockerignore` applies to the build — `backend/.dockerignore` is inert. The root file excludes `*.md` and `docs/`, which would otherwise strip every `SKILL.md` out of the image; a defensive negation (`!backend/system_skills/**`) keeps the packages in. That negation **must stay the last skill-related rule** in `/.dockerignore` — `.dockerignore` uses last-match-wins, so any new broad exclude pattern (e.g. a future `**/*.md`) added *after* it would silently re-exclude every `SKILL.md` again, with no error signal (the seeder is fail-soft: it logs and continues on a missing/corrupt package). If you ever add a new ignore rule near the bottom of that file, re-verify with `docker compose -f docker/docker-compose.yaml build backend` that `backend/system_skills/**/SKILL.md` still ships in the image before merging.
4. Verify end to end: restart the backend, confirm the skill was created (`source='yaml'`, `app_id IS NULL`), attach it to an agent, and — if it has a bootstrap script — activate it in a sandbox and run its script.

Editing a package's files on disk or in `system_defaults.yaml` **after** it has already been seeded has no effect on an existing installation — the seeder never updates, restores or re-enables an already-created system skill, so an admin's own edits/disables survive every restart untouched. To ship a genuine content update, an admin has to make it directly (via the admin UI/API) on the already-seeded row.

---

## Claude Code plugin import

A Claude Code plugin archive can bundle several skills under `skills/<name>/SKILL.md` (optionally wrapped in one common top-level directory, matching what `zip -r plugin.zip my-plugin/` or a GitHub "Download ZIP" of a plugin repo produces). `POST /internal/apps/{app_id}/import-claude-plugin` (`administrator`+) imports every candidate found, one at a time, as an **app-scoped** skill:

- Each candidate is validated and persisted independently (its own duplicate-name check, its own DB transaction/commit). One bad or duplicate candidate never aborts the rest of the archive.
- The response is a **per-skill report** — `imported` / `skipped` (e.g. duplicate name) / `failed` (with a reason) — for every candidate found, plus aggregate counts. Only the whole archive being unreadable or violating the shared zip-safety limits fails the request outright (400); a partial outcome across candidates is a normal 200.
- The archive-level candidate count is capped by `SKILL_IMPORT_MAX_PLUGIN_SKILLS` (default 25); lock contention on one candidate is bounded once per whole archive (`SKILL_IMPORT_LOCK_TIMEOUT_SECONDS`) rather than retried per remaining candidate, so a large contended import can't monopolise the shared import/export bulkhead.

**Imported skills land with `is_enabled=False`.** This is deliberate: unlike the single-skill `/import` path (where an admin has presumably reviewed the one `SKILL.md` they're uploading), a bulk plugin import can create many skills from an archive an admin has not read line-by-line. Landing them disabled forces an explicit, per-skill review-and-enable step (via the existing `PATCH .../enabled` route) before any of them actually take effect for an agent — an admin decides what to trust rather than a whole third-party plugin becoming live by default the instant it's uploaded.

---

## Access control summary

| Action | App-scoped skills | System skills |
|---|---|---|
| View (own app's listing) | viewer+ | any app sees enabled ones (read-only) |
| Create / edit / delete | administrator+ (owning app) | omniadmin only, via `/internal/admin/system-skills/*` |
| Import / export | administrator+ / viewer+ | omniadmin only |
| Enable / disable | administrator+ (owning app) | omniadmin only |
| Attach to an agent | editor+ (owning app) | any app, for enabled system skills |

---

## See Also

- [Agent System](../ai/agent-system.md) — agent execution flow, memory, and where skills fit into the prompt-assembly pipeline
- [Environment Variables](../reference/environment-variables.md#skill-package-import) — full list of skill import/sandbox-bootstrap environment variables
- [Role Authorization](../reference/role-authorization.md) — role hierarchy and `@require_min_role`
