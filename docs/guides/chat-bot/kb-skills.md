# Skills

## What is a Skill?

A **Skill** is a reusable block of instructions (Markdown text) that can be attached to one or more agents. When a skill is attached to an agent, its content is automatically injected into the agent's system prompt at execution time.

Skills are useful for:
- Shared instructions that apply to multiple agents (e.g. "Always respond in the user's language.")
- Domain knowledge that doesn't belong in the main system prompt (e.g. a glossary, a list of products, a formatting guide).
- Modular prompt building — combine a base agent with different skill sets for different contexts.

## Creating a Skill

1. Open your App and go to **Skills**.
2. Click **New Skill**.
3. Enter a **Name** and a **Description** (used to help the agent understand when to apply the skill).
4. Write the **content** — plain text or Markdown instructions.
5. Save.

## Attaching a Skill to an Agent

1. Open the agent configuration.
2. Go to the **Skills** section.
3. Select one or more skills from your App's skill library.
4. Save.

The skill content is injected into the system prompt automatically every time the agent runs.

## Example Use Cases

| Skill | Content |
|-------|---------|
| Language rule | "Always respond in the same language the user writes in." |
| Tone guide | "Use a formal, professional tone. Avoid jargon." |
| Product glossary | A list of product names, abbreviations, and definitions. |
| Formatting rules | "Format all lists with bullet points. Use headers for sections." |
| Escalation instructions | "If you cannot answer, tell the user to contact support@company.com." |

## Notes

- Skills are scoped to an App — they cannot be shared directly across Apps (but you can copy the content).
- The order in which skills are injected follows the order they were attached to the agent.
- Keep skills focused and concise. Very long skills can consume a large portion of the LLM's context window.
