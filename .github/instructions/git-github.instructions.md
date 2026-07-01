---
description: Project-wide rules for git and GitHub CLI usage in the Mattin AI repository. Applied globally to all agents and contexts.
applyTo: "**"
---

# Git & GitHub — Project Rules

These rules apply to **all git and GitHub CLI operations** in this repository, regardless of which agent is executing them.

## Commit Signing (disabled)

Commits are **not** GPG-signed — no signing key is configured in this environment. Use a plain `git commit` (no `-S`).

```bash
git commit -m "type(scope): description"
```

Verify after committing:

```bash
git log -1
```

## Pull Before Push

Always pull from the remote branch before pushing. This avoids rejected pushes and keeps history clean.

```bash
git pull origin <branch>
# Resolve any conflicts, then:
git push origin <branch>
```

Never push without pulling first.

## Remote Conventions

| Remote | URL | Purpose |
|--------|-----|---------|
| `origin` | `https://github.com/lksnext-ai-lab/ai-core-tools.git` | **Primary** — all day-to-day work happens here |
| `gitlab` | `https://gitlab.devops.lksnext.com/lks/genai/ai-core-tools.git` | LKS DevOps GitLab mirror — push only when explicitly requested |
| `mattinai` | `https://github.com/MattinAI-Ingenia/ai-core-tools.git` | MattinAI organization GitHub mirror — push only when explicitly requested |

Default: always push to `origin`. Push to `gitlab` or `mattinai` **only** when the user explicitly asks.

Verify with `git remote -v` before pushing — the URLs above must match exactly.

## Branch Naming

```
feat/<plan-slug>           # Feature branch from plan execution
feature/<description>      # General features
bug/<description>          # Bug fixes
fix/<description>          # Fixes
clean/<description>        # Refactoring / cleanup
release/<version>          # GitFlow release branches (e.g., release/0.4.1)
hotfix/<description>       # Hotfixes branched from main
```

- Always branch features from `develop`
- Release branches are cut from `develop` and merged into `main`
- Hotfix branches are cut from `main` and merged into both `main` and `develop`
- Never push directly to `develop` or `main`

## GitFlow Release Workflow

This project follows GitFlow for releases. The process to integrate `develop` into `main`:

1. Cut a `release/<version>` branch from `develop`
2. Bump `pyproject.toml` version: drop `.devN` suffix (e.g., `0.4.1.dev0` → `0.4.1`)
3. Commit: `git commit -m "chore(release): bump version to <version>"`
4. Push release branch and open a PR targeting `main`
5. After PR merge: tag `main` with `git tag -a v<version> -m "Release v<version>"` and push the tag
6. Back-merge `main` into `develop` (merge commit)
7. On `develop`, bump to next dev version (e.g., `0.4.2.dev0`) and commit
8. Delete the release branch

**Version convention**: Dev versions use `x.y.z.devN` suffix. Release branches drop it. After back-merge, patch increments and `.dev0` is added.

## Commit Message Format

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): description

[optional body]
```

**Types**: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `build`, `ci`, `perf`, `style`

**Scopes**: `backend`, `frontend`, `alembic`, `docker`, `docs`, `agents` (use what fits)

Examples:

```
feat(backend): add visibility field to Agent model
fix(frontend): resolve playground input focus issue
docs: update authentication migration guide
chore(docker): update base image to Python 3.12
```

## GitHub CLI — Body Content Rule

When creating issues or PRs with `gh`, **always** use `--body-file`. Never use `--body` inline or heredoc syntax.

```bash
# CORRECT
cat > /tmp/content.md << 'BODY'
Content here
BODY
gh issue create --title "Title" --body-file /tmp/content.md
rm /tmp/content.md

# WRONG — do not use these
gh issue create --body "Content here"           # ❌ --body
gh issue create --body-file <(echo "Content")   # ❌ process substitution
```

The same rule applies to `gh pr create`.

Always clean up temp files after use.

## GitHub CLI — Default Repository

Set the default repo before running `gh` commands:

```bash
gh repo set-default lksnext-ai-lab/ai-core-tools
```

Check authentication status before any `gh` operation:

```bash
gh auth status
```

## Available Issue Labels

`enhancement`, `bug`, `documentation`, `technical-debt`, `good-first-issue`, `help-wanted`, `question`, `discussion`, `invalid`, `wontfix`, `duplicate`

## Publication Confirmation Gates

Publishing a branch or opening a PR is irreversible from the user's perspective (everyone can see it once it's on a public remote). Agents that run git operations on behalf of the user (`@git-github`, `@plan-executor`, `@release-manager`) MUST confirm before each publication step:

- **Before `git push`**: show the branch, the remote, and the new commits (`git log --oneline <remote>/<branch>..HEAD`) and ask for explicit `yes`.
- **Before `gh pr create`**: show the proposed title, body preview, base branch, and head branch and ask for explicit `yes`.

Exception: when the user's immediate prior message already names the publication ("push it", "open the PR with title X"), that message counts as the confirmation and the agent can proceed.

Non-publishing operations (status, add, commit, branch creation, log, diff, issue/PR view/list) do NOT require a gate and should run directly.

## Safety Rules

- ❌ Never force-push to shared branches without explicit user approval
- ❌ Never delete remote branches without confirmation
- ❌ Never commit secrets, credentials, or `.env` files
- ❌ Never use `git add .` without first reviewing `git status` and `git diff --stat`
- ❌ Never reset, rebase, or amend published (already pushed) commits without explicit user instruction
- ❌ Never `git push` without showing the commits that would be pushed and getting explicit user confirmation (see Confirmation Gates above)
- ❌ Never `gh pr create` without showing the proposed title/body/base/head and getting explicit user confirmation (see Confirmation Gates above)
