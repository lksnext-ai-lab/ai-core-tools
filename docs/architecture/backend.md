# Backend Architecture

> Part of [Mattin AI Documentation](../README.md)

## Overview

<!-- TODO: FastAPI application structure, entry point (main.py) -->

## Router Layer

<!-- TODO: Internal routers (session/OIDC auth), Public routers (API key auth), MCP router -->

### Internal API Routers

<!-- TODO: List all internal routers: admin, agents, ai_services, api_keys, apps, apps_usage, auth, collaboration, conversations, domains, embedding_services, folders, mcp_configs, mcp_servers, ocr, output_parsers, repositories, silos, skills, user, version -->

### Public API Routers

<!-- TODO: List all public routers: agents, auth, chat, files, ocr, repositories, resources, silos -->

### Controls

<!-- TODO: rate_limit, role_authorization, file_size_limit, origins -->

## Service Layer

<!-- TODO: Business logic services — 28 services covering agent execution, memory management, file handling, etc. -->

## Repository Layer

<!-- TODO: Data access layer — 19 repositories using SQLAlchemy ORM -->

## Models

<!-- TODO: SQLAlchemy ORM models — 22 models: Agent, App, User, Silo, Repository, Domain, etc. -->

## Schemas

<!-- TODO: Pydantic request/response schemas — 20 schema files -->

## Utilities

<!-- TODO: Auth config, logging, error handlers, decorators, security -->
