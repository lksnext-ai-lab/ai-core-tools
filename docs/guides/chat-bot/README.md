# Platform Chatbot — Knowledge Base & Prompt Template

> Part of [Platform Chatbot Guide](../platform-chatbot.md) · [Mattin AI Documentation](../../index.md)

## What Is This?

This folder contains ready-to-use materials for setting up a **platform guide agent** — an AI assistant that helps users navigate and get the most out of Mattin AI.

You can use these files as the knowledge base for the platform chatbot by indexing them into a Silo (via a Repository). Any user who wants to deploy a guide bot can copy these files manually and upload them to their setup.

---

## Contents

| File | Description |
|------|-------------|
| [`agent-prompt.md`](agent-prompt.md) | System prompt template for the guide agent |
| [`kb-overview.md`](kb-overview.md) | What Mattin AI is and how it is organized |
| [`kb-apps.md`](kb-apps.md) | Apps (workspaces), roles, and collaboration |
| [`kb-ai-services.md`](kb-ai-services.md) | Configuring LLM providers (AI Services) |
| [`kb-agents.md`](kb-agents.md) | Creating and configuring agents |
| [`kb-silos-and-rag.md`](kb-silos-and-rag.md) | Silos, Repositories, Domains, and RAG |
| [`kb-conversations.md`](kb-conversations.md) | Playground, conversations, and file attachments |
| [`kb-skills.md`](kb-skills.md) | Skills — reusable prompt blocks |
| [`kb-output-parsers.md`](kb-output-parsers.md) | Output parsers for structured responses |
| [`kb-marketplace.md`](kb-marketplace.md) | Agent Marketplace — discovering and sharing agents |
| [`kb-mcp.md`](kb-mcp.md) | MCP integration — connecting external tools |

---

## How to Use

### Option A — Repository (recommended)

1. Create a **Silo** in your app (e.g. "Platform Guide KB").
2. Create a **Repository** inside that Silo.
3. Upload all `kb-*.md` files to the Repository. The platform will vectorize them automatically.
4. Create an agent, link it to the Silo, and paste the contents of `agent-prompt.md` as the system prompt.
5. Enable the agent as the platform chatbot in **System Settings → Platform**.

### Option B — System prompt only (no RAG)

If you prefer a self-contained agent without a knowledge base, paste the contents of all `kb-*.md` files directly into the system prompt (after the role instructions in `agent-prompt.md`). Note that this approach is limited by the LLM's context window and works best with concise models.

---

## Customizing

- Edit `agent-prompt.md` to reflect your organization's name, tone, and any platform-specific notes.
- Add your own `kb-*.md` files to cover internal processes, team conventions, or custom platform extensions.
- Remove files that are not relevant to your users (e.g. `kb-mcp.md` if your users don't use MCP).
