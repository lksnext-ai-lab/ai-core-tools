from typing import Optional, List
from model.mcp_config import MCPConfig, TransportType
from extensions import db
from datetime import datetime

class MCPConfigService:
    @staticmethod
    def get_mcp_configs(app_id: int) -> List[MCPConfig]:
        """Get all MCP configs for a specific app ordered by creation date"""
        return db.session.query(MCPConfig)\
            .filter(MCPConfig.app_id == app_id)\
            .order_by(MCPConfig.create_date.desc())\
            .all()

    @staticmethod
    def get_mcp_config(config_id: int) -> Optional[MCPConfig]:
        """Get a specific MCP config by ID"""
        return db.session.query(MCPConfig).filter(MCPConfig.config_id == config_id).first()

    @staticmethod
    def create_or_update_mcp_config(config_data: dict) -> MCPConfig:
        """Create a new MCP config or update an existing one"""
        config_id = config_data.get('config_id')
        config = MCPConfigService.get_mcp_config(config_id) if config_id else None
        
        if not config:
            config = MCPConfig()
            config.create_date = datetime.now()
        
        MCPConfigService._update_mcp_config(config, config_data)
        
        db.session.add(config)
        db.session.commit()
        db.session.refresh(config)
        return config

    @staticmethod
    def _update_mcp_config(config: MCPConfig, data: dict):
        """Update MCP config attributes"""
        config.name = data['name']
        config.description = data.get('description')
        config.transport_type = TransportType(data['transport_type'])
        config.server_name = data['server_name']
        config.app_id = data['app_id']

        # Update transport-specific fields
        if config.transport_type == TransportType.STDIO:
            config.command = data.get('command')
            config.args = data.get('args')
            config.env = data.get('env')
            config.inputs = data.get('inputs')
            config.encoding = data.get('encoding', 'utf-8')
            config.encoding_error_handler = data.get('encoding_error_handler', 'strict')
        elif config.transport_type == TransportType.SSE:
            config.url = data.get('url')
            config.headers = data.get('headers')
            config.timeout = data.get('timeout', 5)
            config.sse_read_timeout = data.get('sse_read_timeout', 300)

    @staticmethod
    def delete_mcp_config(config_id: int):
        """Delete an MCP config"""
        config = db.session.query(MCPConfig).filter(MCPConfig.config_id == config_id).first()
        if config:
            db.session.delete(config)
            db.session.commit()
    
    @staticmethod
    def delete_by_app_id(app_id: int):
        """Delete all MCP configs for an app"""
        db.session.query(MCPConfig).filter(MCPConfig.app_id == app_id).delete()
        db.session.commit()

    @staticmethod
    def validate_mcp_config(config_data: dict) -> bool:
        """Validate MCP config data before creation/update"""
        required_fields = ['name', 'transport_type', 'server_name', 'app_id']
        
        # Check required fields
        for field in required_fields:
            if field not in config_data:
                raise ValueError(f"Missing required field: {field}")

        # Validate transport type
        try:
            transport_type = TransportType(config_data['transport_type'])
        except ValueError:
            raise ValueError(f"Invalid transport type: {config_data['transport_type']}")

        # Validate transport-specific fields
        if transport_type == TransportType.STDIO:
            if not config_data.get('command') or not config_data.get('args'):
                raise ValueError("Command and args are required for STDIO transport")
        elif transport_type == TransportType.SSE:
            if not config_data.get('url'):
                raise ValueError("URL is required for SSE transport")

        return True