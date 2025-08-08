from typing import Optional, List
from models.mcp_config import MCPConfig, TransportType
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
                transport_type=config.transport_type.value if hasattr(config.transport_type, 'value') else config.transport_type,
                created_at=config.create_date
            ))
        
        return result

    @staticmethod
    def get_mcp_config_detail(db: Session, app_id: int, config_id: int) -> Optional[MCPConfigDetailSchema]:
        """Get detailed information about a specific MCP config"""
        if config_id == 0:
            # New MCP config
            transport_types = [{"value": t.value, "name": t.value} for t in TransportType]
            
            return MCPConfigDetailSchema(
                config_id=0,
                name="",
                server_name="",
                description="",
                transport_type=None,
                command="",
                args="",
                env="",
                created_at=None,
                available_transport_types=transport_types
            )        # Existing MCP config
        config = MCPConfigRepository.get_by_id_and_app_id(db, config_id, app_id)
        
        if not config:
            return None
        
        # Get available transport types
        transport_types = [{"value": t.value, "name": t.value} for t in TransportType]
        
        return MCPConfigDetailSchema(
            config_id=config.config_id,
            name=config.name,
            server_name=config.server_name or "",
            description=config.description or "",
            transport_type=config.transport_type.value if hasattr(config.transport_type, 'value') else config.transport_type,
            command=config.command or "",
            args=json.dumps(config.args) if config.args else "",
            env=json.dumps(config.env) if config.env else "",
            created_at=config.create_date,
            available_transport_types=transport_types
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
        config.server_name = config_data.server_name
        config.description = config_data.description
        config.transport_type = TransportType(config_data.transport_type)
        config.command = config_data.command
        
        # Parse JSON fields
        try:
            config.args = json.loads(config_data.args) if config_data.args else []
        except json.JSONDecodeError:
            config.args = []
        try:
            config.env = json.loads(config_data.env) if config_data.env else {}
        except json.JSONDecodeError:
            config.env = {}
        
        # Use repository to save
        if config_id == 0:
            return MCPConfigRepository.create(db, config)
        else:
            return MCPConfigRepository.update(db, config)

    @staticmethod
    def delete_mcp_config(db: Session, app_id: int, config_id: int) -> bool:
        """Delete an MCP config"""
        return MCPConfigRepository.delete_by_id_and_app_id(db, config_id, app_id) 