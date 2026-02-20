```skill
---
name: New Agent
description: Bootstraps a new GitHub Copilot custom agent with proper structure, frontmatter, and conventions for this repository.
---

# New Agent Skill

Creates a new Copilot custom agent definition file in `.github/agents/` following the project's established conventions and template structure.

## Parameters

| Parameter | Required | Description | Example |
|-----------|----------|-------------|---------|
| `name` | Yes | Human-readable agent name (2-3 words) | `Database Migration Expert` |
| `slug` | No | Kebab-case filename (derived from name if omitted) | `db-migration-expert` |
| `description` | Yes | One-line description of the agent's specialization | `Expert in Alembic migrations, schema design, and database versioning` |
| `domains` | Yes | Key competency areas (comma-separated) | `Alembic, SQLAlchemy models, PostgreSQL` |

## Steps

### Step 1: Create the Agent File

Create `.github/agents/<slug>.agent.md` with the following structure:

````markdown
```chatagent
---
name: <name>
description: <description>
---

# <name> Agent

You are an expert <domain description>. <1-2 sentences establishing identity and scope.>

## Core Competencies

### <Domain Area 1>
- **<Skill>**: <Description>
- **<Skill>**: <Description>

### <Domain Area 2>
- **<Skill>**: <Description>

## Workflow

### When Given a Task
1. **Understand**: Clarify requirements and constraints
2. **Analyze**: Review existing code and patterns
3. **Plan**: Outline changes needed
4. **Implement**: Make changes following project conventions
5. **Verify**: Validate changes work correctly
6. **Document**: Update relevant documentation

## Specific Instructions

### Always Do
- ✅ Follow existing project conventions and patterns
- ✅ <Domain-specific instruction>

### Never Do
- ❌ <Domain-specific anti-pattern>

## Collaborating with Other Agents

### Version Bumper (`@version-bumper`)
- **Delegate to**: `@version-bumper` when version changes are needed
- **DO NOT** manually edit version numbers in `pyproject.toml`

### <Other relevant agents>
- **Delegate to**: `@<agent>` when <condition>

## What This Agent Does NOT Do
- ❌ <Out-of-scope task>
```
````

### Step 2: Populate Core Competencies

Fill in the competency sections with specific, actionable knowledge relevant to the agent's domain. Reference actual project files, patterns, and conventions. Include:
- At least 2-3 competency areas with 4-6 skills each
- Real code examples from the Mattin AI codebase
- Common anti-patterns specific to this domain

### Step 3: Add Delegation Rules

Check existing agents in `.github/agents/` and add bidirectional delegation:
- Add a "Collaborating with Other Agents" section to the new agent referencing relevant existing agents
- Update existing agents to reference the new agent where appropriate

### Step 4: Create Companion Instructions (Optional)

If the agent's domain benefits from auto-applied rules, create a matching instruction file:

```markdown
\```instructions
---
description: <Rules for the agent's domain>
applyTo: "<relevant glob pattern>"
---

# <Domain> Conventions

<Auto-applied rules for files in this domain>
\```
```

Save as `.github/instructions/.<domain>.instructions.md`

### Step 5: Verify

- [ ] Agent file exists at `.github/agents/<slug>.agent.md`
- [ ] Frontmatter has valid `name` and `description`
- [ ] Core competencies are specific and actionable
- [ ] Collaboration section references relevant existing agents
- [ ] "What This Agent Does NOT Do" section defines clear boundaries
- [ ] No conflicts with existing agents' scopes

## Output

- `.github/agents/<slug>.agent.md` — The new agent definition
- Optionally: `.github/instructions/.<domain>.instructions.md` — Companion instruction file
- Optionally: Updates to existing agent files (delegation references)

## Example Usage

> "@ai-dev-architect Create a new agent called 'Database Migration Expert' that specializes in Alembic migrations, schema design, and PostgreSQL database management for this project"

```
