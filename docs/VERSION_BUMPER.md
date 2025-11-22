# Version Bumper Agent

This module provides tools and services for managing semantic versioning in the Mattin AI Core Tools project.

## Overview

The version bumper functionality allows automated or manual version bumping following semantic versioning principles (MAJOR.MINOR.PATCH).

## Components

### 1. Utility Module (`backend/utils/version_bumper.py`)

Core utilities for version management:

- **Version Parsing**: Parse semantic version strings
- **Version Bumping**: Calculate new versions based on bump type
- **File Operations**: Read and write version from/to `pyproject.toml`
- **Error Handling**: Comprehensive error handling with custom exceptions

#### Example Usage:

```python
from utils.version_bumper import bump_project_version, BumpType, read_current_version

# Read current version
current = read_current_version()  # Returns: "0.3.7"

# Bump version
result = bump_project_version(BumpType.PATCH)
# Returns: {"old_version": "0.3.7", "new_version": "0.3.8"}
```

### 2. LangChain Tools (`backend/tools/versionTools.py`)

Four LangChain tools that can be used by AI agents:

#### `get_project_version`
Returns the current project version from pyproject.toml.

**Use case**: When an agent needs to check the current version before deciding whether to bump it.

#### `bump_version_patch`
Bumps the PATCH version (x.x.X).

**Use case**: Bug fixes and minor improvements (e.g., 0.3.7 → 0.3.8)

#### `bump_version_minor`
Bumps the MINOR version (x.X.0) and resets patch to 0.

**Use case**: New features that are backward-compatible (e.g., 0.3.7 → 0.4.0)

#### `bump_version_major`
Bumps the MAJOR version (X.0.0) and resets minor and patch to 0.

**Use case**: Breaking changes or major new versions (e.g., 0.3.7 → 1.0.0)

#### Example Usage in Agent:

```python
from tools.versionTools import VERSION_TOOLS

# Add version tools to an agent
tools.extend(VERSION_TOOLS)

# The agent can now use these tools:
# - "What is the current version?"
# - "Bump the patch version"
# - "Upgrade to version 1.0.0"
```

### 3. Service Layer (`backend/services/version_service.py`)

Business logic for version management:

```python
from services.version_service import VersionService

service = VersionService()

# Get current version
version_info = service.get_current_version()
# Returns: {"version": "0.3.7", "name": "ai-core-tools"}

# Bump version
result = service.bump_version("patch")
# Returns: {"old_version": "0.3.7", "new_version": "0.3.8"}
```

### 4. API Endpoints (`backend/routers/internal/version.py`)

RESTful API for version management:

#### GET `/version/`
Get the current application version.

**Response:**
```json
{
  "version": "0.3.7",
  "name": "ai-core-tools"
}
```

#### POST `/version/bump`
Bump the application version.

**Request:**
```json
{
  "bump_type": "patch"  // or "minor" or "major"
}
```

**Response:**
```json
{
  "old_version": "0.3.7",
  "new_version": "0.3.8",
  "message": "Version successfully bumped from 0.3.7 to 0.3.8"
}
```

**Example cURL:**
```bash
# Get current version
curl -X GET http://localhost:8000/internal/version/

# Bump patch version
curl -X POST http://localhost:8000/internal/version/bump \
  -H "Content-Type: application/json" \
  -d '{"bump_type": "patch"}'

# Bump minor version
curl -X POST http://localhost:8000/internal/version/bump \
  -H "Content-Type: application/json" \
  -d '{"bump_type": "minor"}'

# Bump major version
curl -X POST http://localhost:8000/internal/version/bump \
  -H "Content-Type: application/json" \
  -d '{"bump_type": "major"}'
```

## Semantic Versioning Guide

Version format: **MAJOR.MINOR.PATCH**

- **MAJOR**: Increment when making incompatible API changes
- **MINOR**: Increment when adding functionality in a backward-compatible manner
- **PATCH**: Increment when making backward-compatible bug fixes

### Examples:

| Current | Bump Type | New Version | Use Case |
|---------|-----------|-------------|----------|
| 0.3.7   | patch     | 0.3.8      | Bug fix |
| 0.3.7   | minor     | 0.4.0      | New feature |
| 0.3.7   | major     | 1.0.0      | Breaking change |
| 1.2.3   | patch     | 1.2.4      | Bug fix |
| 1.2.3   | minor     | 1.3.0      | New feature |
| 1.2.3   | major     | 2.0.0      | Breaking change |

## Error Handling

The module includes comprehensive error handling:

- **`InvalidVersionError`**: Raised when version format is invalid
- **`FileNotFoundError`**: Raised when pyproject.toml is not found
- **`VersionBumperError`**: Base exception for all version bumper errors

## Integration with Agents

To create an agent that can manage versions:

1. Create a new agent in the Mattin AI system
2. Add the version tools to the agent's available tools
3. Configure the agent's system prompt to understand version management:

```
You are a version management assistant. You can check the current version 
and bump it according to semantic versioning rules. 

When asked to bump a version:
1. First check the current version using get_project_version
2. Ask for confirmation if not explicitly stated
3. Use the appropriate bump tool (patch/minor/major)
4. Confirm the new version
```

## Security Considerations

- The version bump endpoint should be protected with proper authentication
- Consider adding audit logging for version changes
- Version changes should be tracked in git commits
- Consider requiring approval for major version bumps

## Testing

The implementation has been tested with:

- ✓ Version parsing and validation
- ✓ All bump types (major, minor, patch)
- ✓ Edge cases (0.0.1, 0.9.9, etc.)
- ✓ Read and write operations to pyproject.toml
- ✓ Error handling for invalid inputs

## Future Enhancements

Potential improvements:

1. **Git Integration**: Automatically create git tags for new versions
2. **Changelog Generation**: Auto-update CHANGELOG.md on version bump
3. **Pre-release Versions**: Support alpha/beta/rc versions (e.g., 1.0.0-beta.1)
4. **Version History**: Track version change history in database
5. **Approval Workflow**: Require approval for certain version bumps
6. **CI/CD Integration**: Trigger builds/deployments on version changes
7. **Multi-file Support**: Update version in multiple files (package.json, etc.)

## Contributing

When contributing to version management:

1. Follow semantic versioning principles
2. Add tests for new functionality
3. Update documentation
4. Ensure error handling is comprehensive
5. Consider backward compatibility

## License

Part of the Mattin AI Core Tools project - see main LICENSE file.
