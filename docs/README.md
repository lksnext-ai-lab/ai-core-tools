# Mattin AI — Documentation

> Last updated: 2026-02-20 (based on commit `593f5ba`)

## Description

Mattin AI is a comprehensive AI toolbox that provides a wide range of artificial intelligence capabilities and tools. This project offers various AI functionalities including:

- Large Language Models (LLMs) integration and management
- Retrieval-Augmented Generation (RAG) systems
- Semantic search capabilities
- Vector database management
- AI agents and automation
- And more...

The project aims to simplify the integration and use of AI technologies within LKS Next, providing a unified platform for various AI-powered solutions.

## Table of Contents

- [Overview](#description)
- [Getting Started](#getting-started)
- [Architecture](#architecture)
- [AI & LLM](#ai--llm)
- [API Reference](#api-reference)
- [Guides](#guides)
- [Copilot Agents & Tooling](#copilot-agents--tooling)
- [Reference](#reference)
- [Contributing](#contributing)
- [Legal](#legal)

---

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
- [Agent System](ai/agent-system.md) — Agent execution engine, memory management, skills, and tools
- [MCP Integration](ai/mcp-integration.md) — Model Context Protocol servers, handlers, and configuration

### API Reference
- [Internal API](api/internal-api.md) — Frontend-backend communication endpoints (session/OIDC auth)
- [Public API](api/public-api.md) — External programmatic API (API key auth, rate limiting)

### Guides
- [Client Project Setup](guides/client-setup.md) — Creating and customizing client frontends
- [Plugin Development](guides/plugin-development.md) — Building plugins for client projects
- [Deployment Guide](guides/deployment.md) — Docker, Docker Compose, and Kubernetes deployment
- [Authentication Guide](guides/authentication.md) — OIDC, Entra ID, FAKE mode, and session auth

### Copilot Agents & Tooling
- [Copilot Agents, Skills & Instructions](guides/copilot-agents.md) — Multi-agent Copilot architecture, agent directory, skills, auto-applied instructions, and delegation graph

### Reference
- [Role Authorization](reference/role-authorization.md) — Role hierarchy, decorators, and access control
- [File Processing](reference/file-processing.md) — PDF, OCR, transcription, and media handling

---

## Contributing

We welcome contributions from LKS Next community! To contribute to this project, please follow these guidelines:

1. Fork the repository and create a new branch for your changes.
2. Ensure your changes adhere to the project's coding standards and best practices.
3. Make sure to include appropriate tests for your changes.
4. Submit a pull request, explaining the purpose and details of your changes.
5. All contributions are subject to the GNU Affero General Public License v3.0 (AGPL 3.0).

By contributing to this project, you agree to the terms and conditions of the AGPL 3.0.

### Legal

This project is available under a dual licensing model:

- **Open Source**: GNU Affero General Public License v3.0 (AGPL 3.0)
- **Commercial**: Proprietary license with enhanced rights and features

For full license details, see [LICENSE](LICENSE.md) and the [LICENSE](../LICENSE) file in the repository root.
