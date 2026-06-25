# Claude Code Agent System — Mattin AI

A native **Claude Code** multi-agent development system for this repo: spec-driven development, issue resolution, full-stack implementation experts, and a **self-correcting review board** that audits every change and drives auto-correction before it's committed.

> This is **separate from and parallel to** `.github/` (the GitHub Copilot ecosystem). The two never modify each other. This system lives entirely under `.claude/` and is version-controlled with the repo.

## How it works (the orchestration model)

In Claude Code, **subagents cannot spawn other subagents.** So the **main conversation is the orchestrator (tech lead)**: you run a **command** (`/spec`, `/implement`, …) and the command spawns specialist subagents, feeds each one's output to the next, runs auditors in parallel, and loops experts ⇄ auditors until the change converges — then commits behind confirmation gates.

```
You → /command  ──►  expert subagent (implements, isolated context, returns a summary)
                ──►  auditor subagents in parallel (review the diff)
                ──►  findings? → re-invoke the SAME expert with the findings → re-audit   ⟲ (max 3 rounds)
                ──►  confirmation gate → git commit / push / PR  (via the git-workflow skill)
```

"Interaction between agents" = this delegation graph, conducted by the command. Agents never talk to each other directly.

## Commands (`/…`) — the workflows

| Command | Use it for |
|---|---|
| `/spec <request \| #issue>` | Spec-driven development: explore → `product-analyst` writes `spec.md` → `solution-architect` writes `plan.md`. |
| `/plan <slug>` | (Re)generate the technical step plan for an existing spec. |
| `/implement <slug>` | **Core.** Execute the plan step-by-step with the self-correction loop and confirmation-gated commits. |
| `/solve-issue <#>` | End-to-end: triage a GitHub issue → route to spec or direct impl → execute → gated PR. |
| `/fix <bug>` | Reproduce-first bug fix: root cause → failing test → fix → verify → audit. |
| `/review [--fix]` | Run the review board on the current diff → prioritized report; `--fix` applies + re-audits. |
| `/production-audit [area]` | Full production-readiness sweep (incl. concurrency, fault tolerance, isolation) → prioritized roadmap (what's missing to ship). |
| `/ship [patch\|minor\|major]` | Release-readiness checklist → GO/NO-GO (leaves the git release to you). |
| `/new-agent <type> <name>` | Extend this system (scaffold an agent/command/skill via `claude-system-architect`). |

## Agents (21) — `.claude/agents/`

**Research (1):** `codebase-explorer` (haiku, read-only).

**Discovery / Spec / Plan (4):** `issue-triager`, `root-cause-analyst`, `product-analyst`, `solution-architect`.

**Implementation experts (7):** `backend-engineer`, `frontend-engineer`, `database-engineer`, `ai-engineer`, `test-engineer`, `devops-engineer`, `docs-engineer`. *(File ops only — they never run git; the command commits.)*

**Review board — auditors (8):** `code-reviewer`, `security-auditor`, `performance-auditor`, `architecture-reviewer`, `accessibility-auditor`, `production-readiness-analyst`, **`reliability-auditor` (SRE — concurrency, fault tolerance, isolation)**, `dependency-auditor`. *(Read-only; most keep `memory: project` to accumulate codebase patterns.)*

**System maintenance (1):** `claude-system-architect`.

Model tiers: **haiku** = fast research · **sonnet** = implementation & most audits · **opus** = spec, architecture, and the deep/critical audits (security, architecture, production-readiness, root-cause).

## Skills (4) — `.claude/skills/`

| Skill | Role |
|---|---|
| `git-workflow` | Confirmation-gated commit/push/PR procedure (user-invoked). |
| `spec-driven` | Templates & conventions for `spec.md` / `plan.md` / `status.yaml` (background knowledge). |
| `review-board` | Auditor selection, severity rubric, finding format, and the self-correction convergence protocol. |
| `production-standards` | Best-practice rubric per dimension — **concurrency, fault tolerance/resilience, isolation**, observability, ops — that reliability/readiness auditors hold findings against. |

## Delegation graph

```
/solve-issue → issue-triager ─┬─ large → /spec → product-analyst → solution-architect → /implement
                              └─ small ────────────────────────────────────────────────→ /implement
/fix → root-cause-analyst → test-engineer (repro) → {backend|frontend|ai|database}-engineer (fix) → review board → verify
/implement (per step): {expert} ─impl─► review board ─findings─► {expert} ─fix─► review board … ─► git-workflow (gated)
/review:           review board (parallel) → dedupe/synthesize → [--fix] {expert}
/production-audit: production-readiness ∥ reliability(concurrency/faults/isolation) ∥ security ∥ performance ∥ architecture ∥ accessibility ∥ dependency → roadmap
codebase-explorer: feeds context to planners and implementers
claude-system-architect: maintains .claude/ (via /new-agent)
```

## Specs — `.claude/specs/`

Specs, plans, and status manifests live under `.claude/specs/<slug>/` and are **not committed** (internal working docs; the guard hook and `git-workflow` block staging them). See [`specs/README.md`](specs/README.md) and the `spec-driven` skill.

## Hooks — `.claude/settings.json` + `.claude/hooks/*.ps1` (PowerShell)

- **PreToolUse / Edit|Write** → `guard-secrets.ps1`: deny editing `.env`/`*.pem`/credentials/`settings.local.json` (templates allowed).
- **PreToolUse / Bash `git add`** → `guard-git-add.ps1`: block `git add -A/./--all` and staging of secrets/`.claude/specs`.
- **PostToolUse / Edit|Write** → `lint-frontend.ps1`: run `eslint` on edited `frontend/**/*.{ts,tsx}` (non-blocking).
- **SessionStart** → `session-context.ps1`: inject branch, working tree, and active specs.

`settings.json` also allowlists common read-only commands (git status/log/diff, pytest, eslint) and sets `includeCoAuthoredBy: false` (project policy: no Co-Authored-By lines).

## Getting started

- New feature from a GitHub issue → `/solve-issue 166`
- New feature from a description → `/spec "add per-app usage quotas to the public API"` then `/implement <slug>`
- A bug → `/fix "playground freezes uploading a PDF over 10MB"`
- Review your current branch → `/review` (or `/review --fix`)
- "Is it production-ready?" → `/production-audit`

> **Note:** agents/commands/skills added directly on disk load on the **next session start**. Components created via the `/agents` UI load immediately.

## Conventions

- Stack truth: LangChain ≥1.2 / LangGraph ≥1.0 (1.x), Pydantic v2, SQLAlchemy 2.x, FastAPI, React 19. Experts verify library APIs via Context7 / LangChain Docs before writing.
- Backend layering: router → service → repository → model; RBAC `@require_min_role`; tenant isolation by `app_id`.
- Frontend: all HTTP via `services/api.ts`; Tailwind + dark mode + WCAG 2.1; client customization via `clientConfig.ts`.
- Git: GPG-signed, Conventional Commits, GitFlow off `develop`; publishing actions always pause for confirmation.
- `.github/` is off-limits to this system.
