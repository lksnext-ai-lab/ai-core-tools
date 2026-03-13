---
description: Standard protocol for agent-to-agent handoffs using VS Code native handoff buttons. All agents must follow this pattern when delegating to another agent.
applyTo: ".github/agents/*.agent.md"
---

# Handoff Protocol

VS Code Copilot supports **native handoff buttons** defined in the agent's frontmatter. After each response, the configured handoff buttons appear automatically — the user clicks one to switch to the target agent with a pre-filled prompt and the full conversation context.

## How to Define Handoffs (frontmatter)

```yaml
handoffs:
  - label: "Commit with @git-github"
    agent: git-github
    prompt: "Please commit the files that @<this-agent> just created or modified. Review the conversation above for the exact file list and suggested commit message."
    send: false
```

| Field | Description |
|-------|-------------|
| `label` | Button text shown to the user |
| `agent` | Target agent `name` (from its frontmatter) |
| `prompt` | Pre-filled prompt sent to the target agent when clicked |
| `send` | `false` = user can review/edit before submitting (recommended); `true` = auto-submits |

## Work Summary Block

When your work is complete and you want the user to proceed with the handoff, end your response with this block so the target agent has clear context:

```
---
## Ready to commit

**Files changed**: `<file1>`, `<file2>`
**Suggested commit**: `<conventional-commit-message>`
**Branch**: <current branch>
---
```

The handoff button will appear below this block. The user clicks it to continue.

## Rules

- ✅ Define handoffs in frontmatter — not in the response body
- ✅ End your response with the Work Summary block so the target agent has context
- ✅ Use `send: false` so the user can review before the target agent acts
- ❌ Never run write-side shell commands that belong to the target agent (e.g., `git add`, `git commit`, `git push`)
- ❌ Never try to programmatically invoke another agent from the response body
