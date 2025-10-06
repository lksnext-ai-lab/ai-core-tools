from typing import Optional, List
from models.mcp_config import MCPConfig
from repositories.mcp_config_repository import MCPConfigRepository
from sqlalchemy.orm import Session
from datetime import datetime
import json
from schemas.mcp_config_schemas import MCPConfigListItemSchema, MCPConfigDetailSchema, CreateUpdateMCPConfigSchema

class MCPConfigService:
    @staticmethod
    def list_mcp_configs(db: Session, app_id: int) -> List[MCPConfigListItemSchema]:
        """Get all MCP configs for a specific app as list items"""
        configs = MCPConfigRepository.get_all_by_app_id(db, app_id)
        
        result = []
        for config in configs:
            result.append(MCPConfigListItemSchema(
                config_id=config.config_id,
                name=config.name,
                description=config.description or "",
                created_at=config.create_date
            ))
        
        return result

    @staticmethod
    def get_mcp_config_detail(db: Session, app_id: int, config_id: int) -> Optional[MCPConfigDetailSchema]:
        """Get detailed information about a specific MCP config"""
        if config_id == 0:
            # New MCP config
            return MCPConfigDetailSchema(
                config_id=0,
                name="",
                description="",
                config="{}",
                created_at=None
            )
        
        # Existing MCP config
        config = MCPConfigRepository.get_by_id_and_app_id(db, config_id, app_id)
        
        if not config:
            return None
        
        # Serialize config to JSON string if it's a dict
        config_str = json.dumps(config.config) if isinstance(config.config, dict) else config.config
        
        return MCPConfigDetailSchema(
            config_id=config.config_id,
            name=config.name,
            description=config.description or "",
            config=config_str,
            created_at=config.create_date
        )

    @staticmethod
    def create_or_update_mcp_config(
        db: Session, 
        app_id: int, 
        config_id: int, 
        config_data: CreateUpdateMCPConfigSchema
    ) -> MCPConfig:
        """Create a new MCP config or update an existing one"""
        if config_id == 0:
            # Create new MCP config
            config = MCPConfig()
            config.app_id = app_id
            config.create_date = datetime.now()
        else:
            # Update existing MCP config
            config = MCPConfigRepository.get_by_id_and_app_id(db, config_id, app_id)
            
            if not config:
                return None
        
        # Update config data
        config.name = config_data.name
        config.description = config_data.description
        
        # Parse config JSON field
        try:
            config.config = json.loads(config_data.config) if isinstance(config_data.config, str) else config_data.config
        except json.JSONDecodeError:
            config.config = {}
        
        # Use repository to save
        if config_id == 0:
            return MCPConfigRepository.create(db, config)
        else:
            return MCPConfigRepository.update(db, config)

    @staticmethod
    def delete_mcp_config(db: Session, app_id: int, config_id: int) -> bool:
        """Delete an MCP config"""
        return MCPConfigRepository.delete_by_id_and_app_id(db, config_id, app_id) 