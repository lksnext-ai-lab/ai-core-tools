# Mattin AI — Documentation

> Last updated: 2026-04-27 (based on commit `d40b51d` + silo playground revamp: enhanced search controls, result inspection, faceted filters, curator tools, API snippets, observability, A/B compare)

## Table of Contents

- [Overview](#overview)
- [Getting Started](#getting-started)
- [Architecture](#architecture)
- [AI & LLM](#ai--llm)
- [API Reference](#api-reference)
- [Guides](#guides)
- [Copilot Agents & Tooling](#copilot-agents--tooling)
- [Reference](#reference)
- [Legal](#legal)

---

### Overview
- [Project Overview](README.md) — What Mattin AI is, features, licensing, and contribution guidelines

### Getting Started
- [Developer Guide](dev-guide.md) — Setup, conventions, Alembic migrations, and role authorization
- [Environment Variables](reference/environment-variables.md) — Complete configuration reference for backend and frontend

### Architecture
- [Architecture Overview](architecture/overview.md) — High-level system design, data flow, and multi-tenancy model
- [Backend Architecture](architecture/backend.md) — FastAPI structure, services, repositories, and models
- [Frontend Architecture](architecture/frontend.md) — React library, pages, components, contexts, and theming
- [Database Schema](architecture/database.md) — SQLAlchemy models, migrations, and pgvector integration

### AI & LLM
- [LLM Integration](ai/llm-integration.md) — Supported LLM providers, configuration, and structured output
- [RAG & Vector Stores](ai/rag-vector-stores.md) — Silo system, vector database backends (PGVector, Qdrant), and retrieval
- [Multimodal Video RAG](architecture/multimodal-rag.md) — Video analysis pipeline, audio/visual chunk splitting, and retrieval
- [Agent System](ai/agent-system.md) — Agent execution engine, memory management, skills, and tools
- [A2A Integration](ai/a2a-integration.md) — High-level design for exposing Mattin AI agents as A2A-compatible agents
- [MCP Integration](ai/mcp-integration.md) — Model Context Protocol servers, handlers, and configuration

### API Reference
- [Internal API](api/internal-api.md) — Frontend-backend communication endpoints (session/OIDC auth)
- [Public API](api/public-api.md) — External programmatic API (API key auth, rate limiting)

### Guides
- [Client Project Setup](guides/client-setup.md) — Creating and customizing client frontends
- [Plugin Development](guides/plugin-development.md) — Building plugins for client projects
- [Deployment Guide](guides/deployment.md) — Docker, Docker Compose, and Kubernetes deployment
- [Authentication Guide](guides/authentication.md) — OIDC, Entra ID, FAKE mode, and session auth
- [App Export and Import](guides/app-export-import.md) — Export app configuration and import into a new workspace
- [Agent Marketplace](guides/marketplace.md) — Publish agents to the platform-wide marketplace, manage profiles, ratings, and quotas
- [SaaS Mode](guides/saas-mode.md) — SaaS deployment: Stripe billing, subscription tiers, quota enforcement, and `system_defaults.yaml` configuration
- [Platform Chatbot](guides/platform-chatbot.md) — Configure a global AI assistant widget backed by any agent; includes knowledge base files and prompt template for a platform guide agent

### Copilot Agents & Tooling
- [Copilot Agents, Skills & Instructions](guides/copilot-agents.md) — Multi-agent Copilot architecture, agent directory, skills, auto-applied instructions, and delegation graph

### Reference
- [Role Authorization](reference/role-authorization.md) — Role hierarchy, decorators, and access control
- [File Processing](reference/file-processing.md) — PDF, OCR, transcription, and media handling

### Legal
- [License](LICENSE.md) — LKS S. Coop. Inner Source License
