"""Service for importing MCP Configurations."""

import json
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session
from models.mcp_config import MCPConfig
from schemas.export_schemas import MCPConfigExportFileSchema
from schemas.import_schemas import (
    ConflictMode,
    ValidateImportResponseSchema,
    ImportSummarySchema,
    ComponentType,
)
from core.export_constants import validate_export_version
from repositories.mcp_config_repository import MCPConfigRepository
import logging

logger = logging.getLogger(__name__)


class MCPConfigImportService:
    """Service for importing MCP Configurations."""

    def __init__(self, session: Session):
        """Initialize MCP Config import service.

        Args:
            session: SQLAlchemy database session
        """
        self.session = session
        self.mcp_config_repo = MCPConfigRepository()

    def get_by_name_and_app(self, name: str, app_id: int) -> Optional[MCPConfig]:
        """Get MCP Config by name and app ID.

        Args:
            name: Config name
            app_id: App ID

        Returns:
            Optional[MCPConfig]: Config if found, None otherwise
        """
        return (
            self.session.query(MCPConfig)
            .filter(MCPConfig.name == name, MCPConfig.app_id == app_id)
            .first()
        )

    def validate_import(
        self, export_data: MCPConfigExportFileSchema, app_id: int
    ) -> ValidateImportResponseSchema:
        """Validate MCP Config import without importing.

        Args:
            export_data: Parsed export file
            app_id: Target app ID

        Returns:
            ValidateImportResponseSchema: Validation result
        """
        # Validate version
        validate_export_version(export_data.metadata.export_version)

        # Validate config JSON structure if present
        warnings = []
        if export_data.mcp_config.config:
            try:
                json.loads(export_data.mcp_config.config)
            except json.JSONDecodeError as e:
                warnings.append(f"Invalid JSON in config field: {e}")

        # Check for name conflict
        existing_config = self.get_by_name_and_app(
            export_data.mcp_config.name, app_id
        )

        return ValidateImportResponseSchema(
            component_type=ComponentType.MCP_CONFIG,
            component_name=export_data.mcp_config.name,
            has_conflict=existing_config is not None,
            warnings=warnings,
            missing_dependencies=[],
        )

    def _merge_configs(
        self, existing_config: dict, imported_config: dict
    ) -> dict:
        """Merge imported config with existing, preserving sensitive keys.

        Args:
            existing_config: Current config from database
            imported_config: New config from import file

        Returns:
            dict: Merged configuration
        """
        # Sensitive keys to preserve from existing config
        sensitive_keys = [
            'api_key', 'apiKey', 'api-key',
            'token', 'access_token', 'accessToken', 'bearer',
            'password', 'pass', 'pwd',
            'secret', 'client_secret', 'clientSecret',
            'auth', 'authorization', 'auth_token',
            'credential', 'credentials', 'creds',
            'private_key', 'privateKey'
        ]

        # Start with imported config
        merged = imported_config.copy()

        # Preserve existing sensitive keys (case-insensitive matching)
        existing_lower = {k.lower(): k for k in existing_config.keys()}
        for sensitive in sensitive_keys:
            sensitive_lower = sensitive.lower()
            if sensitive_lower in existing_lower:
                original_key = existing_lower[sensitive_lower]
                # Keep the existing sensitive value
                merged[original_key] = existing_config[original_key]

        return merged

    def import_mcp_config(
        self,
        export_data: MCPConfigExportFileSchema,
        app_id: int,
        conflict_mode: ConflictMode = ConflictMode.FAIL,
        new_name: Optional[str] = None,
    ) -> ImportSummarySchema:
        """Import MCP Configuration.

        Args:
            export_data: Parsed export file
            app_id: Target app ID
            conflict_mode: How to handle name conflicts
            new_name: Optional custom name (for rename mode)

        Returns:
            ImportSummarySchema: Import operation summary

        Raises:
            ValueError: On conflict with FAIL mode
        """
        # Validate
        validation = self.validate_import(export_data, app_id)

        # Handle conflict
        final_name = export_data.mcp_config.name
        existing_config = self.get_by_name_and_app(final_name, app_id)
        warnings = validation.warnings.copy()
        next_steps = []

        if existing_config:
            if conflict_mode == ConflictMode.FAIL:
                raise ValueError(
                    f"MCP Config '{final_name}' already exists in app {app_id}"
                )
            elif conflict_mode == ConflictMode.RENAME:
                if new_name:
                    final_name = new_name
                else:
                    date_str = datetime.now().strftime("%Y-%m-%d")
                    final_name = f"{final_name} (imported {date_str})"
                    
                    # Ensure uniqueness
                    counter = 1
                    while self.get_by_name_and_app(final_name, app_id):
                        final_name = f"{export_data.mcp_config.name} (imported {date_str} {counter})"
                        counter += 1
            # ConflictMode.OVERRIDE: will update existing

        # Parse and prepare config JSON
        config_json = None
        if export_data.mcp_config.config:
            try:
                imported_config_dict = json.loads(export_data.mcp_config.config)

                # If overriding, merge with existing to preserve sensitive keys
                if conflict_mode == ConflictMode.OVERRIDE and existing_config:
                    try:
                        existing_config_dict = (
                            json.loads(existing_config.config)
                            if isinstance(existing_config.config, str)
                            else existing_config.config
                        )
                        config_dict = self._merge_configs(
                            existing_config_dict, imported_config_dict
                        )
                        warnings.append(
                            "Existing authentication credentials preserved"
                        )
                    except (json.JSONDecodeError, TypeError):
                        # If existing config is invalid, use imported only
                        config_dict = imported_config_dict
                else:
                    config_dict = imported_config_dict

                config_json = config_dict  # Store as dict for SQLAlchemy JSON field
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in config field: {e}")

        # Create or update MCP Config
        if conflict_mode == ConflictMode.OVERRIDE and existing_config:
            # Update existing
            existing_config.name = final_name
            existing_config.description = export_data.mcp_config.description
            existing_config.config = config_json
            existing_config.update_date = datetime.now()

            self.mcp_config_repo.update(self.session, existing_config)

            result_config_id = existing_config.config_id
            created = False

            next_steps.extend([
                "Test MCP connection after import",
                "Update URLs if needed for your environment"
            ])
        else:
            # Create new
            new_config = MCPConfig(
                app_id=app_id,
                name=final_name,
                description=export_data.mcp_config.description,
                config=config_json,
            )

            created_config = self.mcp_config_repo.create(self.session, new_config)
            result_config_id = created_config.config_id
            created = True

            warnings.append("Authentication tokens must be reconfigured")
            next_steps.extend([
                "Configure authentication tokens for the MCP server",
                "Test MCP connection after configuration",
                "Update URLs if needed for your environment"
            ])

        logger.info(
            f"{'Created' if created else 'Updated'} MCP Config "
            f"'{final_name}' (ID: {result_config_id}) in app {app_id}"
        )

        return ImportSummarySchema(
            component_type=ComponentType.MCP_CONFIG,
            component_id=result_config_id,
            component_name=final_name,
            mode=conflict_mode,
            created=created,
            warnings=warnings,
            next_steps=next_steps,
        )
