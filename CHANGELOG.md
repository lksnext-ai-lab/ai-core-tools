# Changelog

All notable changes to the Mattin AI project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

### Changed

### Fixed

## [0.3.14] - 2026-02-28

### Added

#### Agent Development Tools
- **Python Code Interpreter**: Execute Python code within agent conversations
  - Subprocess-based Python REPL tool with sandboxed execution
  - Automatic file system synchronization for generated outputs
  - Support for file uploads available to agent scripts
  - Dependencies: pandas, openpyxl for data processing

#### Provider-Side Tools
- **Provider-Aware Tool Injection**: Map generic tool names to provider-specific implementations
  - Support for OpenAI, Anthropic, Google, and Azure providers
  - Generic tool names: `web_search`, `image_generation`, `code_interpreter`, `file_search`
  - Provider-specific tool routing in `create_agent()` execution flow
  - `server_tools` JSON field added to Agent model (with migration)

#### File Download Support
- **Workspace Download Tool**: Download files from agent working directories
  - `download_url_to_workspace` tool for programmatic file retrieval
  - Working directory now computed for all agent executions (not just code interpreter)
  - File type detection with proper categorization for images and documents
  - Signed URL endpoint pattern for secure file downloads in agents and marketplace

#### Image Generation
- **Multimodal Image Output**: Handle AI-generated images within conversations
  - Image generation call blocks decoded from base64 and saved to working directory
  - Auto-registration of generated files for download and display
  - UI support for image renders in conversation history

#### Community Governance
- **Code of Conduct**: Adopted community conduct standards for contributors and users

### Changed

- **Agent File Management**: Attached files panel now refreshes automatically after agent responses without requiring page reload (#30c3331)
- **Agent Form UI**: Added Capabilities section with clickable tool cards showing provider compatibility

### Fixed

- **Marketplace**: Refresh attachments panel after agent generates files (#30c3331)

## [0.3.13] - 2026-02-28

### Added

#### Agent Marketplace
- **Agent Marketplace Platform**: Full marketplace system for publishing and discovering agents
  - Marketplace catalog page with search, filtering, and agent cards
  - Agent detail page with conversation history viewing
  - Chat page with simplified consumer experience
  - Profile management section for agent publishing
  - USER role for marketplace consumers
  - Marketplace visibility, profile, and conversation source models
  - MarketplaceService for catalog, profiles, and conversations management
  - Marketplace API router with dedicated endpoints

#### Media & Transcription
- **Audio/Video Processing**: Complete media management system
  - Media upload, storage, and management in repositories
  - Audio and video transcription with configurable services
  - Background task processing for media with polling
  - Transcription service selection in frontend
  - YouTube URL support for media import
  - Media deletion with automatic embedding cleanup
  - Chunking support for audio/video with min/max duration and overlap

#### MCP Integration
- **MCP Server Support**: Expose agents as MCP tools for external consumption
  - MCP server configuration and management
  - Agent-to-MCP-tool mapping system
  - MCP server handler with JSON-RPC 2.0 support
  - Authentication support for MCP servers
  - Connection testing endpoints for MCP configs
  - Documentation for implementing authentication in MCP servers

#### Testing Infrastructure
- **Testing Framework**: Comprehensive testing infrastructure
  - Integration tests for agents, apps, and repositories
  - Unit test suite with pytest fixtures
  - `@test` Copilot agent for test development assistance
  - Testing strategy documentation
  - Test coverage for core services

#### Access Control
- **Role-Based Access Control (RBAC)**: Enhanced permission management
  - VIEWER role implementation with read-only access
  - Role hierarchy system in frontend
  - Role-based access dependencies for all resources
  - Access validation for AI services and embedding services
  - Collaboration page UI improvements for all roles

#### Vector Database
- **Vector Database Abstraction**: Multi-backend vector store support
  - Per-silo vector database type selection (PGVector or Qdrant)
  - Qdrant backend support with metadata filtering
  - VectorStoreInterface abstraction layer
  - Frontend UI for vector database type selection
  - Enhanced error handling for empty documents

#### AI Service Features
- **Connection Testing**: AI service and MCP config validation
  - Connection test endpoints with timeout and validation
  - Resource cleanup after connection tests
  - Error logging improvements for MCP configs
  - Frontend connection test UI

#### Copilot Agents
- **Specialized Agents**: Enhanced development workflow
  - `@test` agent for testing assistance
  - `@oss-manager` agent for open-source governance
  - `@plan-executor` agent for structured plan execution
  - `@alembic-expert` agent for database migrations
  - `@git-github` agent with git handoff convention
  - `commit-and-push` skill for standardized git workflows

#### Documentation
- **Complete Documentation Overhaul**: Comprehensive project documentation
  - Architecture documentation (data flow, technology stack, design decisions)
  - AI & LLM integration guides
  - RAG system documentation
  - API reference documentation (internal and public APIs)
  - Authentication guide
  - Deployment guide
  - File processing reference
  - Environment variables reference
  - Role authorization reference
