"""Service for exporting MCP Configurations."""

import json
from typing import Optional
from sqlalchemy.orm import Session
from models.mcp_config import MCPConfig
from schemas.export_schemas import (
    ExportMCPConfigSchema,
    MCPConfigExportFileSchema,
)
from services.base_export_service import BaseExportService
from repositories.mcp_config_repository import MCPConfigRepository
import logging

logger = logging.getLogger(__name__)


class MCPConfigExportService(BaseExportService):
    """Service for exporting MCP Configurations."""

    # Sensitive keys to remove during export (case-insensitive)
    SENSITIVE_KEYS = [
        'api_key', 'apikey', 'api-key',
        'token', 'access_token', 'accesstoken', 'bearer', 'bearer_token',
        'password', 'pass', 'pwd',
        'secret', 'client_secret', 'clientsecret',
        'auth', 'authorization', 'auth_token',
        'credential', 'credentials', 'creds',
        'private_key', 'privatekey'
    ]

    def __init__(self, session: Session):
        """Initialize MCP Config export service.

        Args:
            session: SQLAlchemy database session
        """
        super().__init__(session)
        self.mcp_config_repo = MCPConfigRepository()

    def _sanitize_config_json(self, config_data: dict) -> dict:
        """Remove sensitive data from MCP config JSON recursively.

        Args:
            config_data: Configuration dictionary

        Returns:
            dict: Sanitized configuration (copy)
        """
        if not isinstance(config_data, dict):
            return config_data

        # Create a copy to avoid modifying original
        sanitized = {}
        sensitive_lower = [key.lower() for key in self.SENSITIVE_KEYS]

        for key, value in config_data.items():
            # Check if key is sensitive (case-insensitive)
            if key.lower() in sensitive_lower:
                # Skip sensitive keys entirely
                continue
            elif isinstance(value, dict):
                # Recursively sanitize nested dicts
                sanitized[key] = self._sanitize_config_json(value)
            elif isinstance(value, list):
                # Sanitize list items
                sanitized[key] = [
                    self._sanitize_config_json(item) if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                # Keep non-sensitive values
                sanitized[key] = value

        return sanitized

    def export_mcp_config(
        self, config_id: int, app_id: int, user_id: Optional[int] = None
    ) -> MCPConfigExportFileSchema:
        """Export MCP Configuration to JSON structure.

        Args:
            config_id: ID of MCP config to export
            app_id: App ID (for permission check)
            user_id: User ID (for permission check, optional)

        Returns:
            MCPConfigExportFileSchema: Export file structure

        Raises:
            ValueError: If config not found or permission denied
        """
        # Load MCP config
        mcp_config = self.mcp_config_repo.get_by_id_and_app_id(
            self.session, config_id, app_id
        )
        if not mcp_config:
            raise ValueError(
                f"MCP Config with ID {config_id} not found in app {app_id}"
            )

        # Sanitize config JSON
        config_str = None
        if mcp_config.config:
            try:
                # Parse JSON from database
                if isinstance(mcp_config.config, str):
                    config_dict = json.loads(mcp_config.config)
                else:
                    config_dict = mcp_config.config

                # Sanitize sensitive keys
                sanitized_config = self._sanitize_config_json(config_dict)

                # Convert back to JSON string
                config_str = json.dumps(sanitized_config)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(
                    f"Failed to parse config JSON for MCP Config {config_id}: {e}"
                )
                # For safety, don't export unparseable config
                config_str = None

        # Create export schema
        export_config = ExportMCPConfigSchema(
            name=mcp_config.name,
            description=mcp_config.description,
            config=config_str,
        )

        # Create export file with metadata
        export_file = MCPConfigExportFileSchema(
            metadata=self.create_metadata(user_id, app_id),
            mcp_config=export_config,
        )

        logger.info(
            f"Exported MCP Config '{mcp_config.name}' (ID: {config_id}) "
            f"from app {app_id}"
        )

        return export_file
