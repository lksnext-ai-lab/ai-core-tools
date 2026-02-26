---
name: Commit and Push
description: Standardized workflow for staging, committing, and pushing changes after an implementation agent finishes its work. Designed for handoff from implementation agents to @git-github.
---

# Commit and Push

This skill provides the standard procedure for committing and pushing code changes after an implementation agent (`@backend-expert`, `@react-expert`, `@alembic-expert`, `@docs-manager`) has finished its work. It is typically invoked via the `@git-github` agent.

## Parameters

| Parameter | Required | Description | Example |
|-----------|----------|-------------|---------|
| `type` | Yes | Conventional Commits type (`feat`, `fix`, `refactor`, `docs`, `test`, `chore`, etc.) | `feat` |
| `scope` | No | Area of change (`backend`, `frontend`, `alembic`, `docs`, `docker`, etc.) | `backend` |
| `description` | Yes | Short description of the change | `add memory management fields to Agent model` |
| `files` | No | Specific files to stage (defaults to reviewing all changed files) | `backend/models/agent.py` |
| `push` | No | Whether to push after committing (default: `true`) | `true` |
| `branch` | No | Target branch to push to (default: current branch) | `feature/memory-management` |

## Steps

### Step 1: Review Changes
Check what files have been modified and ensure everything looks correct.

```bash
git status
git diff --stat
```

### Step 2: Stage Files
Stage the relevant files. Prefer explicit file paths over `git add .`.

```bash
# Stage specific files (preferred)
git add <file1> <file2> ...

# Or stage all changes after careful review
git add -A
```

### Step 3: Craft Commit Message
Write a commit message following Conventional Commits format.

```bash
git commit -S -m "type(scope): description"
```

### Step 4: Pull Before Push
Always pull from the remote branch before pushing to avoid conflicts.

```bash
git pull origin <current-branch>
```

### Step 5: Push
Push the committed changes to the remote.

```bash
git push origin <current-branch>
```

### Step 6: Verify
Confirm the push was successful.

```bash
git log --oneline -3
```

## Output
- Committed and pushed changes to the remote branch
- Clean `git status` with no unstaged changes

## Example Usage

After `@backend-expert` finishes implementing a feature:

> User: `@git-github commit and push the changes — added memory management fields to the Agent model`

The `@git-github` agent follows this skill to:
1. Review the changed files
2. Stage `backend/models/agent.py` and the migration file
3. Commit with `feat(backend): add memory management fields to Agent model`
4. Pull and push to the current branch

