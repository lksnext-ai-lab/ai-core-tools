---
name: git-github
description: Comprehensive git and GitHub CLI procedures for the Mattin AI project. Covers branch management, commits, push/pull, PR creation, issue management, and releases. Used by @git-github and @plan-executor.
---

# Git & GitHub Skill

Shared procedures for all git and GitHub CLI operations in the Mattin AI project. Follow these step-by-step recipes for each operation type. Project-specific rules (signing, remotes, naming conventions) are enforced via `.github/instructions/.git-github.instructions.md`.

---

## Branch Operations

### Create a feature branch

```bash
git checkout develop
git pull origin develop
git checkout -b <branch-name>
git push -u origin <branch-name>
git branch --show-current   # verify
```

### Delete a branch (after merge)

```bash
git branch -d <branch-name>             # local
git push origin --delete <branch-name>  # remote
```

---

## Staging & Committing

### Stage and review

```bash
git status
git diff --stat

# Stage specific files (preferred)
git add <file1> <file2> ...

# Review what is staged before committing
git diff --staged
```

### Commit (GPG-signed, Conventional Commits)

```bash
git commit -S -m "type(scope): description"
git log --show-signature -1   # verify signature
```

For plan execution steps, include a body referencing the step:

```bash
git commit -S -m "feat(backend): add visibility field to Agent model

Plan: agent-marketplace
Step: 002
FR: FR-1"
```

### Amend last commit (unpublished only)

```bash
git add <files>
git commit -S --amend --no-edit
```

---

## Push & Pull

### Pull before push (always)

```bash
git pull origin <branch>   # resolve conflicts if any
git push origin <branch>
git log --oneline -3        # verify
```

### Push new branch

```bash
git push -u origin <branch-name>
```

---

## Pull Requests

### Create a PR

Always use `--body-file` — never `--body` or heredoc.

```bash
# 1. Write PR body to a temp file
cat > /tmp/pr-body.md << 'BODY'
## Summary
- <bullet: what was implemented>
- <bullet>

## Test Plan
- [ ] <manual verification step>
- [ ] <manual verification step>

## References
Plan: <slug>
Steps: 001 – NNN
BODY

# 2. Create PR
gh pr create --base develop \
  --title "feat(scope): description" \
  --body-file /tmp/pr-body.md

# 3. Clean up
rm /tmp/pr-body.md
```

### List / view PRs

```bash
gh pr list
gh pr list --state merged
gh pr view <number>
gh pr checks <number>
```

### Merge a PR

```bash
gh pr merge <number> --merge    # merge commit
gh pr merge <number> --squash   # squash and merge
gh pr merge <number> --rebase   # rebase and merge
```

---

## Issues

### Create an issue

Always use `--body-file` — never `--body` or heredoc.

```bash
# 1. Write issue body to a temp file
cat > /tmp/issue-body.md << 'BODY'
## Description
<what the issue is about>

## Steps to Reproduce (for bugs)
1. ...
2. ...

## Expected Behavior
<what should happen>

## Actual Behavior
<what happens instead>
BODY

# 2. Create issue
gh issue create --title "Issue title" --body-file /tmp/issue-body.md

# 3. Add labels
gh issue edit <number> --add-label "bug,enhancement"

# 4. Clean up
rm /tmp/issue-body.md
```

### List / manage issues

```bash
gh issue list
gh issue list --label "bug"
gh issue list --state closed
gh issue view <number>
gh issue close <number>
gh issue comment <number> --body-file /tmp/comment.md
```

---

## Releases & Tags

### Create a release

```bash
# Tag first
git tag -s v1.2.3 -m "Release v1.2.3"
git push origin v1.2.3

# Create release with notes
cat > /tmp/release-notes.md << 'BODY'
## What's Changed
- <change 1>
- <change 2>
BODY

gh release create v1.2.3 \
  --title "v1.2.3" \
  --notes-file /tmp/release-notes.md

rm /tmp/release-notes.md
```

### List releases

```bash
gh release list
gh release view v1.2.3
```

---

## Advanced Operations

### Stash

```bash
git stash
git stash pop
git stash list
```

### Cherry-pick

```bash
git cherry-pick <commit-sha>
```

### Rebase (interactive — avoid on shared branches)

```bash
git rebase -i HEAD~<n>
```

### Bisect (find a bug-introducing commit)

```bash
git bisect start
git bisect bad                  # current commit is bad
git bisect good <known-good>    # last known good commit
# git bisect good/bad after each test
git bisect reset                # when done
```

---

## Multi-Remote Operations

```bash
# Push to primary remote (default)
git push origin <branch>

# Push to internal GitLab mirror (only when explicitly requested)
git push lks <branch>

# Fetch from all remotes
git fetch --all
```

---

## Verification Checklist

After any git operation, confirm:

- [ ] `git status` shows a clean working tree (or expected state)
- [ ] `git log --show-signature -1` confirms GPG signature on last commit
- [ ] `git log --oneline -5` shows expected commit history
- [ ] Branch is on the correct base (`develop`, not `main`)
