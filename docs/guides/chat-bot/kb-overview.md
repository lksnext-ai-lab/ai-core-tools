# Mattin AI — Platform Overview

## What is Mattin AI?

Mattin AI is an AI toolbox platform that lets teams create, configure, and use AI-powered assistants and workflows. It brings together large language models (LLMs), knowledge bases, and automation tools in a single web interface — without requiring users to write code.

## Main Concepts

| Concept | What it is |
|---------|-----------|
| **App** | A workspace that groups all your AI resources together. Think of it as a project or team space. |
| **Agent** | An AI assistant you configure. You define its instructions, the LLM it uses, and optionally a knowledge base. |
| **AI Service** | A connection to an LLM provider (OpenAI, Anthropic, Azure, etc.). Agents use AI Services to power their responses. |
| **Silo** | A vector knowledge base. You fill it with documents or web content; agents search it to give informed answers. |
| **Repository** | A collection of uploaded files inside a Silo. |
| **Domain** | A web source whose pages are crawled and indexed into a Silo. |
| **Conversation** | A chat session with an agent (also called the Playground). |
| **Skill** | A reusable block of instructions that can be attached to agents. |
| **Output Parser** | A schema that makes an agent return structured data (JSON) instead of free text. |
| **MCP** | Model Context Protocol — a standard for connecting agents to external tools and services. |
| **Marketplace** | A catalog of shared agents that can be used across the platform. |

## How Everything Fits Together

```
App (workspace)
├── AI Services      ← LLM provider connections
├── Agents           ← AI assistants (use AI Services + optional Silo)
│   ├── Skills       ← Reusable instruction blocks
│   └── Output Parser ← Structured response schema
├── Silos            ← Knowledge bases
│   ├── Repositories ← Uploaded document collections
│   └── Domains      ← Crawled web sources
└── Conversations    ← Chat sessions with agents
```

## Getting Started

1. Create an **App** (your workspace).
2. Add an **AI Service** to connect an LLM provider.
3. Create an **Agent** and configure its instructions and LLM.
4. Optionally, create a **Silo** and upload documents for the agent to search.
5. Chat with the agent in the **Playground**.
