```skill
---
name: New Instruction
description: Bootstraps a new GitHub Copilot instruction file with proper frontmatter, scoping, and conventions for this repository.
---

# New Instruction

Creates a new Copilot instruction file in `.github/instructions/` that auto-applies rules to files matching a specific glob pattern.

## Parameters

| Parameter | Required | Description | Example |
|-----------|----------|-------------|---------|
| `name` | Yes | Descriptive name for the instruction set | `Python Testing` |
| `slug` | No | Kebab-case filename prefix (derived from name if omitted) | `.py-testing` |
| `description` | Yes | What these instructions cover | `Conventions for writing pytest tests in this project` |
| `applyTo` | No | Glob pattern to auto-apply (omit for workflow/manual instructions) | `tests/**/*.py` |

## Steps

### Step 1: Determine Scope

Choose the right scoping strategy:

| Scope | `applyTo` Pattern | Example |
|-------|-------------------|---------|
| All Python files | `**/*.py` | Coding style rules |
| Backend only | `backend/**` | Architecture patterns |
| Frontend only | `frontend/**/*.{ts,tsx}` | React conventions |
| Tests only | `tests/**` | Testing conventions |
| Specific dir | `backend/routers/**` | Router-specific rules |
| Workflow (no scope) | *(omit applyTo)* | Git workflow, issue management |

### Step 2: Create the Instruction File

Create `.github/instructions/<slug>.instructions.md`:

```markdown
\```instructions
---
description: <description>
applyTo: "<glob pattern>"
---

# <Instruction Title>

## Rules

### <Rule Category 1>
- <Specific, actionable rule>
- <Specific, actionable rule>

### <Rule Category 2>
- <Specific, actionable rule>

## Examples

### ✅ Correct
\```<language>
<correct pattern>
\```

### ❌ Incorrect
\```<language>
<incorrect pattern>
\```
\```
```

### Step 3: Verify No Conflicts

Check existing instructions in `.github/instructions/` for:
- Overlapping `applyTo` patterns with contradictory rules
- Redundancy with rules already in `.github/copilot-instructions.md`
- Conflicts with agent-specific guidance

### Step 4: Verify

- [ ] File exists at `.github/instructions/<slug>.instructions.md`
- [ ] Frontmatter has valid `description`
- [ ] `applyTo` pattern matches intended files (if scoped)
- [ ] Rules are specific and actionable
- [ ] No conflicts with existing instructions
- [ ] Includes correct/incorrect examples where useful

## Output

- `.github/instructions/<slug>.instructions.md` — The new instruction file

## Example Usage

> "@ai-dev-architect Create a new instruction file for Python testing conventions that applies to all files under tests/"

```
