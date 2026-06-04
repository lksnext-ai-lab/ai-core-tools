---
description: Scaffold a new .claude/ component (agent, command, or skill) following the system's conventions.
argument-hint: "<agent|command|skill> <name> — <purpose>"
allowed-tools: [Agent, Read, Glob, Grep]
---

# /new-agent — Extend the Claude Code system

Request: **$ARGUMENTS**

You are extending the `.claude/` agent system itself. Delegate to the `claude-system-architect` agent.

## Steps

1. Parse the request into: component **type** (`agent` / `command` / `skill`), **name** (kebab-case), and **purpose**.
2. Invoke the `claude-system-architect` agent with that, instructing it to:
   - read existing peers in the target directory and match their structure exactly,
   - check whether an existing agent/skill should be extended instead of adding a near-duplicate,
   - create the file with correct frontmatter and a focused body,
   - update `.claude/README.md` (roster table / workflow list / delegation graph) accordingly.
3. Review the result for convention compliance (minimal tool allowlist, right model tier, clear delegation `description`).

## Finish

Report what was created and which docs were updated. Remind the user that **disk-added agents require a session restart to load** (components created via the `/agents` UI load immediately). Never touch `.github/`. Never commit automatically.
