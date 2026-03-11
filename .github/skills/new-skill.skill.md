---
name: New Skill
description: Bootstraps a new GitHub Copilot custom skill definition with proper structure, parameters, and step-by-step workflow.
---

# New Skill Skill (Meta-Skill)

Creates a new Copilot custom skill definition file in `.github/skills/` following the project's established conventions and template structure.

## Parameters

| Parameter | Required | Description | Example |
|-----------|----------|-------------|---------|
| `name` | Yes | Human-readable skill name (2-4 words) | `Scaffold API Endpoint` |
| `slug` | No | Kebab-case filename (derived from name if omitted) | `scaffold-api-endpoint` |
| `description` | Yes | One-line description of what the skill automates | `Creates the full backend stack for a new REST resource` |
| `parameters` | Yes | List of input parameters the skill accepts | `resource_name, include_tests` |

## Steps

### Step 1: Create the Skill File

Create `.github/skills/<slug>.skill.md` with the following structure:

````markdown
---
name: <name>
description: <description>
---

# <name>

<1-2 sentence description of what this skill does and when to use it.>

## Parameters

| Parameter | Required | Description | Example |
|-----------|----------|-------------|---------|
| `<param>` | Yes/No | <What this parameter controls> | `<example value>` |

## Steps

### Step 1: <Action Name>
<What to do and why>

```<language>
<code or command to execute>
```

### Step 2: <Action Name>
<What to do and why>

### Step N: Verify
<How to confirm the skill executed correctly>
- [ ] <Verification checklist item>

## Output
<What files/artifacts are created or modified>

## Example Usage
<Show how to invoke this skill>
````

### Step 2: Define Parameters

For each input the skill needs:
- Choose a clear, descriptive parameter name
- Mark whether it's required or optional
- Provide a sensible default for optional parameters
- Include a realistic example value
- Keep parameters to 5 or fewer — if you need more, the skill is too complex (split it)

### Step 3: Map the Steps

Document each step with:
1. **What** action to take (create file, run command, modify existing file)
2. **Where** the action happens (file paths, directories)
3. **How** to perform it (templates, commands, patterns to follow)
4. **Why** this step is needed (context for the AI)

Guidelines:
- Steps should be sequential and deterministic
- Each step should produce a verifiable artifact
- Include the actual file templates/code patterns from this project
- Reference real project paths (`backend/models/`, `frontend/src/components/`, etc.)

### Step 4: Add Verification

End the skill with a verification checklist:
- Files created exist and are syntactically valid
- Commands ran without errors
- Generated code follows project conventions
- No lint/type errors introduced

### Step 5: Link to Agents (Optional)

If an agent commonly triggers this skill, add a reference in the agent's documentation:

```markdown
## Related Skills

### <Skill Name> (`<slug>`)
- **Invoke when**: <condition>
- **Parameters needed**: <list>
```

### Step 6: Verify

- [ ] Skill file exists at `.github/skills/<slug>.skill.md`
- [ ] Frontmatter has valid `name` and `description`
- [ ] Parameters are clearly defined with examples
- [ ] Steps are specific, sequential, and actionable
- [ ] Verification section confirms correct execution
- [ ] No overlap with existing skills

## Output

- `.github/skills/<slug>.skill.md` — The new skill definition
- Optionally: Updates to agent files that reference this skill

## Example Usage

> "@ai-dev-architect Create a new skill called 'Add API Endpoint' that scaffolds a full REST resource with model, schema, repository, service, and router for the Mattin AI backend"

