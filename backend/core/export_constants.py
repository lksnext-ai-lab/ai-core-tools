"""Export/Import version constants and utilities."""

# Version constants
CURRENT_EXPORT_VERSION = "1.0.0"
SUPPORTED_EXPORT_VERSIONS = ["1.0.0"]

# Component type identifiers
COMPONENT_AI_SERVICE = "ai_service"
COMPONENT_EMBEDDING_SERVICE = "embedding_service"
COMPONENT_OUTPUT_PARSER = "output_parser"
COMPONENT_MCP_CONFIG = "mcp_config"
COMPONENT_SILO = "silo"
COMPONENT_REPOSITORY = "repository"
COMPONENT_DOMAIN = "domain"
COMPONENT_AGENT = "agent"
COMPONENT_APP = "app"


def is_version_supported(version: str) -> bool:
    """Check if export version is supported.

    Args:
        version: Export version string

    Returns:
        bool: True if version is supported
    """
    return version in SUPPORTED_EXPORT_VERSIONS


def validate_export_version(version: str) -> None:
    """Validate export version, raise ValueError if unsupported.

    Args:
        version: Export version string

    Raises:
        ValueError: If version is not supported
    """
    if not is_version_supported(version):
        raise ValueError(
            f"Unsupported export version '{version}'. "
            f"Supported versions: {', '.join(SUPPORTED_EXPORT_VERSIONS)}"
        )


def get_component_type_from_file(file_data: dict) -> str:
    """Detect component type from export file structure.

    Args:
        file_data: Parsed export file data

    Returns:
        str: Component type identifier

    Raises:
        ValueError: If component type cannot be determined
    """
    if "ai_service" in file_data:
        return COMPONENT_AI_SERVICE
    elif "embedding_service" in file_data:
        return COMPONENT_EMBEDDING_SERVICE
    elif "output_parser" in file_data:
        return COMPONENT_OUTPUT_PARSER
    elif "mcp_config" in file_data:
        return COMPONENT_MCP_CONFIG
    elif "silo" in file_data:
        return COMPONENT_SILO
    elif "repository" in file_data:
        return COMPONENT_REPOSITORY
    elif "domain" in file_data:
        return COMPONENT_DOMAIN
    elif "agent" in file_data:
        return COMPONENT_AGENT
    elif "app" in file_data:
        return COMPONENT_APP
    else:
        raise ValueError("Unknown export file format")
