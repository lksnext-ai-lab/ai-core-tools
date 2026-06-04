---
name: git-workflow
description: Confirmation-gated git/GitHub procedure (branch, stage, commit, push, PR) used by orchestrating commands. Pauses for explicit user approval before every commit, push, and PR.
disable-model-invocation: true
allowed-tools: Bash, Read
---

# git-workflow — Confirmation-gated git/GitHub procedure

This skill defines **how** any orchestrating command (`/implement`, `/solve-issue`, `/fix`) performs version control. The golden rule: **publishing actions pause for explicit user approval; local actions run freely.**

## Operation classes

**Non-publishing (run freely, no pause):**
`git status`, `git log`, `git diff`, `git branch`, `git checkout`, `git add`, `git commit -S`. Staging is the review point — the commit itself follows once staging is approved.

**Publishing (ALWAYS pause for an explicit `yes` before running):**
`git push`, `gh pr create`, `gh issue create`, `gh release create`. Pushing to a remote, opening PRs, creating issues/releases.

**Exception:** if the user's prior message already contains the action verb ("commit it", "push it", "open the PR"), that message *is* the confirmation — do not pause again.

## 1. Branch

Before any implementation work, ensure a feature branch exists off the base branch (`develop`):

```bash
git rev-parse --abbrev-ref HEAD          # current branch
git status --porcelain                   # must be clean before branching
git checkout develop && git pull origin develop
git checkout -b <type>/<slug>            # e.g. feat/issue-166-s3-storage
```

Branch naming: `feat/`, `fix/<issue-NN>-<slug>`, `refactor/`, `chore/`, `release/`, `hotfix/`. If the working tree already sits on an appropriate feature branch, reuse it.

## 2. Stage (review point)

After an implementation subagent finishes:

```bash
git status --porcelain                   # see what changed
git add <explicit application paths>     # NEVER `git add -A` / `git add .`
git diff --staged --name-status          # show the user EXACTLY what is staged
```

**Never stage:** `.claude/specs/**` (internal working docs), `.env*`, `*.pem`, `*credentials*`, build artifacts, `node_modules/`, `__pycache__/`. The `PreToolUse` guard hook also blocks these, but staging selectively is the first line of defense.

## 3. Commit confirmation gate

Present, then wait for `yes` / `skip` / `abort`:

```
Ready to commit:
  Files:   <output of git diff --staged --name-status>
  Message: <type>(<scope>): <description>

           <optional body: Spec/Step/FR metadata for plan-driven work>
```

Commit message = [Conventional Commits](https://www.conventionalcommits.org/): `type(scope): description`.
Types: `feat fix refactor docs test chore build ci perf style`. Scopes: `backend frontend alembic docker docs deploy`.

On `yes`:
```bash
git commit -S -m "<message>"             # signed (project signs all commits)
```
If signing fails in this environment, report it and ask the user how to proceed — do not silently drop `-S`.

## 4. Push confirmation gate

After all commits for the branch, present and wait for `yes` / `no`:

```
Ready to push:
  Branch:  <branch> → origin
  Commits: <output of git log --oneline origin/<branch>..HEAD>
```

On `yes`:
```bash
git pull origin <branch> --rebase 2>/dev/null || true
git push -u origin <branch>
```

## 5. PR confirmation gate

Write the PR body to a temp file (never inline `--body`), present a preview, wait for `yes` / `no` / `edit`:

```
Ready to open PR:
  Base:  develop   Head: <branch>
  Title: <type>(<scope>): <description>
  Body:  <first ~15 lines of the body file>
```

On `yes`:
```bash
gh pr create --base develop --head <branch> --title "<title>" --body-file <tempfile>
```

## Hard rules

- Never push, open a PR, or create an issue/release without an explicit gate.
- Never use `git add -A`, `git add .`, `git commit -a`, `git reset --hard`, `git push --force` unless the user explicitly asks.
- Never skip hooks (`--no-verify`) or signing (`--no-gpg-sign`) unless explicitly told.
- Never add `Co-Authored-By` or "Generated with Claude Code" lines (project policy).
- `.github/` belongs to the GitHub Copilot ecosystem — never modify it as part of a git-workflow step.
