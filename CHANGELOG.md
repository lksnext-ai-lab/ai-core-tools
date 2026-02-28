# Changelog

All notable changes to the Mattin AI project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

### Changed

### Fixed

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
  - Client setup guide
  - Plugin development guide
  - Copilot agents, skills & instructions documentation
  - Dual-licensing documentation (AGPL-3.0 / Commercial)

#### API & Features
- **User Management**: Current user information endpoints
- **File Management**: Conversation-specific file handling in chat API
- **Conversation Management**: Enhanced conversation tracking and deletion
- **Agent Form UX**: Tabbed interface for improved agent configuration experience
- **Runtime Configuration**: Frontend runtime configuration using environment variables

### Changed

#### Major Upgrades
- **LangChain/LangGraph 1.x Migration**: Complete migration to LangChain and LangGraph 1.x
  - Updated memory management for new APIs
  - Dependency updates across the project
  - Breaking changes from 0.x to 1.x addressed

#### Authentication
- **OIDC Authentication**: Migration to `lks-idprovider` for Entra ID authentication
  - Centralized OIDC configuration management
  - Updated environment variable naming conventions
  - OIDC-enabled build configuration
  - Runtime configuration for OIDC settings

#### Dependencies
- **Dependency Updates**: Major dependency upgrades and cleanups
  - Removed legacy Flask decorators
  - Removed Celery dependency (replaced with background tasks)
  - Updated YouTube downloader dependencies
  - Removed openai-whisper dependency (whisper not loaded on local)
  - Poetry lock file updates

#### Refactoring
- **Code Quality Improvements**: Extensive refactoring for maintainability
  - Eliminated code duplication in UI components
  - Sequential video task processing with improved comments
  - Silo service refactoring for media support
  - Repository-level M2M relationship management
  - Removed console.log() statements and commented code
  - Deleted unused imports across the codebase
  - Enhanced error handling for file system operations

#### Database
- **Alembic Migrations**: Database schema improvements
  - Media management migration versions
  - Conversation model updates
  - Role-based access control migrations
  - Viewer role addition

#### Configuration
- **Environment Variables**: Updated configuration management
  - OIDC configuration environment variables
  - Vector database type configuration
  - Kubernetes ingress configuration updates
  - Secret key references for deployments

### Fixed

#### Agent Issues
- **Agent as Tool**: Fixed system prompts for agent-as-tool composition
- **Temperature Field**: Temperature field now correctly displays 0 when editing agents

#### API Issues
- **Playground API**: Updated API examples in playground
- **API Key Logging**: Removed API keys from log outputs
- **Empty Documents**: Handle empty document extraction in silo operations

#### Media & File Issues
- **Media References**: Corrected media.media_id references
- **File Uploads**: Fixed duplicate file uploads in repositories
- **YouTube URLs**: Fixed duplicate handling in YouTube URL processing
- **Folder Association**: Fixed no duplicates on API folder_id append

#### Database Issues
- **Alembic Conflicts**: Resolved conflicts in Alembic revision files
- **Model Definitions**: Fixed comma usage in `__init__` models
- **Qdrant Corruption**: Addressed Qdrant corruption issues

#### Authentication & Security
- **Authorization Token**: API correctly receives authorization token
- **Pydantic v2**: Fixed Pydantic v2 compatibility in backend agent examples
- **Security Vulnerabilities**: Cleaned up security vulnerabilities and bugs
- **Resource Cleanup**: Enhanced resource cleanup in MCP config service

#### Connection & Errors
- **Connection Testing**: Improved connection testing with timeout and validation
- **Error Logging**: Enhanced error logging for MCP services
- **Windows Compatibility**: Fixed psycopg issues on Windows

### Removed

- **Deprecated Code**: Removed deprecated tests and notebooks with hardcoded API keys
- **Unused Code**: Removed unused imports, functions, and commented code throughout
- **Legacy Components**: Removed pgVectorTools class (replaced by abstraction)
- **Redundant Routes**: Removed redundant /auth route from ingress configuration
- **Duplicate Code**: Eliminated code duplication in warning banners

### Security

- **Vulnerability Fixes**: Addressed multiple security vulnerabilities identified by SonarQube
- **API Key Protection**: Ensured API keys are not logged or exposed in responses
- **Authentication Hardening**: Enhanced authentication flow and token handling
- **MCP Authorization**: Implemented authorization for MCP server access

## [0.3.0]

Initial release with v0.3.0 baseline.

