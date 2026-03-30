# Agents

## What is an Agent?

An **Agent** is an AI assistant you configure inside an App. You control its personality and instructions (via a system prompt), the LLM it uses, whether it has access to a knowledge base, and what tools it can call.

## Creating an Agent

1. Open your App and go to **Agents**.
2. Click **New Agent**.
3. Fill in the required fields:
   - **Name** — a label for this agent
   - **AI Service** — the LLM to use
4. Optionally configure:
   - **System Prompt** — instructions that define the agent's role and behavior
   - **Description** — a short summary (shown in the UI and Marketplace)
   - **Silo** — link a knowledge base for retrieval-augmented generation (RAG)
   - **Temperature** — controls response randomness (0 = deterministic, 1 = creative)
5. Save.

## System Prompt

The system prompt is the most important configuration field. It tells the agent:
- What its role is ("You are a customer support agent for Acme Corp.")
- How it should behave ("Be concise. Answer only questions related to our products.")
- Any constraints ("Do not discuss competitors.")

A good system prompt is specific, clear, and tested interactively in the Playground.

## Linking a Knowledge Base (RAG)

If your agent needs to answer questions based on specific documents:
1. Create a **Silo** and populate it with your documents (see [Silos and RAG](kb-silos-and-rag.md)).
2. In the agent configuration, set the **Silo** field to that Silo.
3. When users send messages, the agent automatically searches the Silo for relevant content and uses it to inform its answers.

## Memory

Agents can remember previous messages in a conversation. By default:
- **Memory** is enabled — the agent remembers the conversation history.
- **Max messages**: configurable limit on how many messages are kept.
- **Max tokens**: configurable token budget for the memory window.
- **Summarize threshold**: when reached, old messages are automatically summarized to save space.

Memory is per conversation session — different conversations with the same agent do not share memory.

## Temperature

| Value | Effect |
|-------|--------|
| 0.0 – 0.3 | Consistent, factual, deterministic |
| 0.4 – 0.7 | Balanced (default: 0.7) |
| 0.8 – 1.0 | Creative, varied, less predictable |

Use low temperature for support bots, data extraction, or factual Q&A. Use higher temperature for creative writing or brainstorming.

## Agent as Tool

Agents with **"Use as Tool"** enabled can be used by other agents as a callable sub-agent. This allows you to build multi-agent workflows where a coordinator agent delegates to specialist agents.

## OCR Agent

**OCR Agents** are a special subtype designed to process scanned documents. They use two LLMs: a vision model for reading the scanned pages, and a text model for structuring the output. OCR Agents appear as a separate type when creating an agent.

## Deleting an Agent

Deleting an agent removes it and all its conversations permanently. If the agent is configured as the platform chatbot, the widget will automatically disappear until a new agent is configured.
