# Git Workflow & Release Process

> Part of [Mattin AI Documentation](../index.md)

## Overview

This guide documents the Git branching model, commit conventions, and release process used in the Mattin AI project. The project follows **GitFlow** for releases: features are integrated into `develop`, and releases are cut as dedicated `release/<version>` branches before merging into `main`.

---

## Branch Naming Conventions

All branches follow a `type/description` naming pattern:

```
feature/<description>       # New features (e.g., feature/mcp-servers)
feat/<plan-slug>            # Feature branch from a plan execution
bug/<description>           # Bug fixes (e.g., bug/blocking)
fix/<description>           # Fixes (e.g., fix/mem-leak-2)
clean/<description>         # Cleanup / refactoring (e.g., clean/duplicity)
release/<version>           # GitFlow release branches (e.g., release/0.4.1)
hotfix/<description>        # Hotfixes branched from main (e.g., hotfix/critical-auth-bug)
```

**Key rules**:
- Feature branches are always created from `develop`
- Release branches are cut from `develop` and merged into `main`
- Hotfix branches are cut from `main` and merged into both `main` and `develop`
- Never push directly to `develop` or `main`

---

## Versioning Convention

The project uses semantic versioning with a development suffix:

| Context | Format | Example |
|---------|--------|---------|
| Active development on `develop` | `x.y.z.devN` | `0.4.2.dev0` |
| Release branch | `x.y.z` | `0.4.1` |
| After back-merge to `develop` | `x.y.(z+1).dev0` | `0.4.2.dev0` |

The version is stored in `pyproject.toml` under `[tool.poetry].version`. Version bumps are handled by the `@version-bumper` agent.

---

## Commit Convention

All commits follow [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): description

[optional body]
```

**Types**: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `build`, `ci`, `perf`, `style`

**Scopes**: `backend`, `frontend`, `alembic`, `docker`, `docs`, `agents`

**All commits must be GPG-signed**:

```bash
git commit -S -m "type(scope): description"

# Verify signature
git log --show-signature -1
```

Examples:

```bash
git commit -S -m "feat(backend): add visibility field to Agent model"
git commit -S -m "fix(frontend): resolve playground input focus issue"
git commit -S -m "chore(release): bump version to 0.4.1"
git commit -S -m "docs: update authentication migration guide"
```

---

## Remote Configuration

| Remote | URL | Purpose |
|--------|-----|---------|
| `origin` | `git@github.com:lksnext-ai-lab/ai-core-tools.git` | **Primary** — all day-to-day work |
| `lks` | `ssh://git@gitlab.devops.lksnext.com:2222/lks/genai/ai-core-tools.git` | **Mirror** — push only when explicitly requested |

Always push to `origin`. Push to `lks` only when explicitly asked.

**Pull before push** — always:

```bash
git pull origin <branch>
# resolve conflicts if any, then:
git push origin <branch>
```

---

## GitFlow Release Workflow

This is the standard process for cutting a release from `develop` into `main`.

### Step-by-Step

**1. Sync develop**

```bash
git checkout develop && git pull origin develop
```

**2. Create the release branch**

```bash
git checkout -b release/<version>
# e.g., git checkout -b release/0.4.1
```

**3. Bump version in `pyproject.toml`**

Drop the `.devN` suffix from the current version:

```toml
# Before (on develop):
version = "0.4.1.dev0"

# After (on release branch):
version = "0.4.1"
```

> Use `@version-bumper` to apply the bump, or edit `pyproject.toml` directly.

Close the changelog in the same commit: rename `## [Unreleased]` in `CHANGELOG.md` to `## [<version>] - YYYY-MM-DD`, fill it from `git log v<previous>..HEAD --oneline` (list breaking changes first), and add an empty `## [Unreleased]` section above it.

**4. Commit the version bump (signed)**

```bash
git add pyproject.toml CHANGELOG.md
git commit -S -m "chore(release): bump version to <version>"
git log --show-signature -1
```

**5. Push the release branch**

```bash
git pull origin release/<version> 2>/dev/null || true
git push -u origin release/<version>
```

**6. Open a PR targeting `main`**

```bash
cat > /tmp/release-pr.md << 'BODY'
## Release <version>

This PR merges the release branch into main.

### Changes
- Version bumped to <version>
- [List notable changes]
BODY

gh pr create --base main --title "chore(release): release <version>" --body-file /tmp/release-pr.md
rm /tmp/release-pr.md
```

Merge the PR with a **merge commit** (`gh pr merge <number> --merge`), never squash. A squash merge leaves `main` and `develop` without a shared history, so the back-merge in step 8 conflicts and `git log v<previous>..develop` lists commits that were already released.

**7. After the PR is merged — tag `main` and publish the GitHub Release**

```bash
git checkout main && git pull origin main
git tag -s v<version> -m "Release v<version>"
git push origin v<version>

# Release notes = the version's section of CHANGELOG.md
awk '/^## \[<version>\]/{f=1;next} /^## \[/{f=0} f' CHANGELOG.md > /tmp/release-notes.md
gh release create v<version> --title "v<version>" --notes-file /tmp/release-notes.md --verify-tag
rm /tmp/release-notes.md
```

> Publishing the GitHub Release is what builds the stable Docker images. The backend, frontend and OpenSandbox CI workflows run on `release: published` and push the `X.Y.Z`, `X.Y` and `latest` tags to GHCR (pre-releases are excluded from `latest`). Pushing only the git tag, or pushing to `main`, builds no image. Check the runs with `gh run list --event release`.

**8. Back-merge `main` into `develop`**

```bash
git checkout develop && git pull origin develop
git merge --no-ff main
git commit -S  # if a merge commit is needed
git push origin develop
```

**9. Prepare the next development version**

Bump `pyproject.toml` to the next patch dev version (e.g. `0.5.0` → `0.5.1.dev0`; use a minor bump such as `0.4.3.dev0` → `0.5.0` at release time when the cycle contains breaking changes):

```toml
# e.g., after releasing 0.4.1, next dev version is:
version = "0.4.2.dev0"
```

```bash
git add pyproject.toml
git commit -S -m "chore: start 0.4.2.dev0 development cycle"
git push origin develop
```

**10. Delete the release branch**

```bash
git push origin --delete release/<version>
git branch -d release/<version>
```

### Summary Diagram

```
develop ──────────────────────────────────────────────► develop
    │                                           ▲
    │  cut release/0.4.1                        │
    └──► release/0.4.1                          │
             │  bump version to 0.4.1           │
             │                                  │
             └──► PR ──► main ──── back-merge ──┘
                              │
                              └──► tag v0.4.1
```

---

## GitFlow Hotfix Workflow

Hotfixes address urgent issues that must go directly to `main` without waiting for the normal release cycle.

### Step-by-Step

**1. Branch from `main`**

```bash
git checkout main && git pull origin main
git checkout -b hotfix/<description>
# e.g., git checkout -b hotfix/critical-auth-bug
```

**2. Apply the fix**

Implement the fix (delegate to `@backend-expert` or `@react-expert` as needed).

**3. Bump patch version in `pyproject.toml`** (signed commit)

```bash
# e.g., 0.4.1 → 0.4.2
git add pyproject.toml
git commit -S -m "chore(release): bump version to 0.4.2"
```

**4. Create PR to `main`, tag, and back-merge**

Follow steps 6–10 of the [Release Workflow](#gitflow-release-workflow) above.

---

## GitHub CLI Usage

### Authentication Check

```bash
gh auth status
gh repo set-default lksnext-ai-lab/ai-core-tools
```

### Creating Issues and PRs

Always use `--body-file` — never `--body` inline or heredoc syntax:

```bash
# Correct
cat > /tmp/content.md << 'BODY'
Content here
BODY
gh issue create --title "Title" --body-file /tmp/content.md
rm /tmp/content.md

# Wrong — do not use
gh issue create --body "Content here"           # ❌
gh issue create --body-file <(echo "Content")   # ❌
```

This rule applies to both `gh issue create` and `gh pr create`.

### Available Issue Labels

`enhancement`, `bug`, `documentation`, `technical-debt`, `good-first-issue`, `help-wanted`, `question`, `discussion`, `invalid`, `wontfix`, `duplicate`

---

## Safety Rules

- ❌ Never force-push to shared branches without explicit user approval
- ❌ Never delete remote branches without confirmation
- ❌ Never commit secrets, credentials, or `.env` files
- ❌ Never use `git add .` without first reviewing `git status` and `git diff --stat`
- ❌ Never reset, rebase, or amend published commits without explicit instruction

---

## See Also

- [Copilot Agents, Skills & Instructions](copilot-agents.md) — The `@git-github` agent automates this workflow
- [Developer Guide](../dev-guide.md) — General development setup and conventions
