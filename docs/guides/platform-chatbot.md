# Platform Chatbot Guide

> Part of [Mattin AI Documentation](../index.md)

## Overview

The **Platform Chatbot** is a global AI assistant widget that appears as a floating button in the bottom-right corner of the Mattin AI interface. When enabled, it is available to all logged-in users on every page of the platform.

An OMNIADMIN configures any existing agent as the backend for the chatbot. That agent can have a knowledge base (Silo), skills, memory, and any other capabilities — making it suitable for use cases such as platform onboarding guides, internal FAQ bots, IT support assistants, or general-purpose helpers.

---

## How It Works

1. The OMNIADMIN sets `platform_chatbot_agent_id` in **System Settings → Platform** to the ID of the desired agent.
2. On login, the platform checks whether a valid chatbot agent is configured.
3. If configured, a floating chat button appears in the bottom-right corner for all users.
4. Clicking the button opens a chat panel backed by the configured agent.
5. Conversations persist per user across page navigations and browser reloads.

The chatbot calls do **not** count toward any usage quotas (SaaS tier LLM call limits or marketplace quotas).

---

## Configuration

### Step 1 — Prepare the agent

Before enabling the chatbot, create and configure the agent you want to use:

1. Go to any App you manage.
2. Create a new agent (or use an existing one).
3. Configure the agent's system prompt, LLM service, and optionally a Silo for knowledge retrieval.
4. Test the agent in the Playground to make sure it behaves as expected.
5. Note the agent's **ID** — you will need it in the next step.

> **Finding the agent ID**: Open the agent in the UI. The ID appears in the browser URL:
> `…/apps/{app_id}/agents/{agent_id}`

### Step 2 — Enable the chatbot in System Settings

Requires **OMNIADMIN** role.

1. Go to **System Settings** (top-level admin menu).
2. Select the **Platform** category.
3. Set `platform_chatbot_agent_id` to the agent's integer ID.
4. Save. The chatbot becomes active immediately for all users on their next page load (no restart required).

### Step 3 — Disable the chatbot

Set `platform_chatbot_agent_id` back to `-1` (the default). The widget will no longer appear.

---

## System Setting Reference

| Setting key | Type | Default | Description |
|-------------|------|---------|-------------|
| `platform_chatbot_agent_id` | integer | `-1` | ID of the agent to use as the platform chatbot. `-1` = disabled. |

This setting is stored in `backend/system_defaults.yaml` under the `platform` category and can be overridden via the environment variable `AICT_SYSTEM_PLATFORM_CHATBOT_AGENT_ID`.

---

## Agent Capabilities

The platform chatbot agent supports all standard agent features:

| Feature | Notes |
|---------|-------|
| **System prompt** | Full control over the agent's personality and instructions |
| **LLM service** | Any configured AIService (OpenAI, Anthropic, Azure, etc.) |
| **Silo (RAG)** | Attach a knowledge base for retrieval-augmented answers |
| **Skills** | Attach reusable prompt blocks |
| **Memory** | Per-user persistent conversation sessions |
| **MCP tools** | Connect to external MCP servers |
| **Agent-as-tool** | Compose with other agents |
| **Streaming** | Responses stream token by token in the widget |

---

## Session and Memory Behaviour

- Each user has their own persistent conversation thread (`platform_chatbot_{user_id}`).
- Conversations survive page reloads and navigation.
- The user can click **New conversation** in the widget header to start a fresh session.
- Conversation history for the current session is stored in browser `localStorage`.
- The agent's memory settings (`memory_max_messages`, `memory_max_tokens`, `memory_summarize_threshold`) apply as configured on the agent.

---

## Recommendations

For a platform onboarding / guide use case, consider:

- Linking a **Silo** with a **Repository** containing your platform documentation or knowledge base files.
- Writing a focused **system prompt** that scopes the agent to platform-related questions.
- Enabling **streaming** on the agent's LLM service for a better user experience.
- Using a **low temperature** (0.2–0.4) for factual, consistent answers.

See the [Platform Chatbot Knowledge Base](chat-bot/README.md) for ready-to-use documentation files and a system prompt template designed for a platform guide agent.

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| Widget does not appear | `platform_chatbot_agent_id` is `-1` or the agent was deleted | Check System Settings → Platform and verify the agent exists |
| Widget appears but chat fails | Agent's LLM service is misconfigured or the API key is invalid | Test the agent directly in the Playground |
| Answers are irrelevant | System prompt is too broad or no knowledge base attached | Refine the system prompt; add a Silo with relevant documents |
| Old conversation context bleeds in | User's session has accumulated history | User can click "New conversation" to start fresh |

---

## See Also

- [Agent System](../ai/agent-system.md) — Agent configuration, memory, and tools
- [RAG & Vector Stores](../ai/rag-vector-stores.md) — Setting up a Silo for knowledge retrieval
- [SaaS Mode](saas-mode.md) — System settings and `system_defaults.yaml`
- [Platform Chatbot Knowledge Base](chat-bot/README.md) — Ready-to-use documentation and prompt template for a guide agent
