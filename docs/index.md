# Mattin AI — Documentation

> Last updated: 2026-02-20 (based on commit `8f357ae`)

## Table of Contents

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

### Reference
- [Role Authorization](reference/role-authorization.md) — Role hierarchy, decorators, and access control
- [File Processing](reference/file-processing.md) — PDF, OCR, transcription, and media handling

### Legal
- [License](LICENSE.md) — LKS S. Coop. Inner Source License
