from typing import Optional, List
from sqlalchemy.orm import Session
from models.mcp_config import MCPConfig


class MCPConfigRepository:
    
    @staticmethod
    def get_all_by_app_id(db: Session, app_id: int) -> List[MCPConfig]:
        """Get all MCP configs for a specific app"""
        return db.query(MCPConfig).filter(MCPConfig.app_id == app_id).all()

    @staticmethod
    def get_by_id_and_app_id(db: Session, config_id: int, app_id: int) -> Optional[MCPConfig]:
        """Get a specific MCP config by ID and app ID"""
        return db.query(MCPConfig).filter(
            MCPConfig.config_id == config_id,
            MCPConfig.app_id == app_id
        ).first()

    @staticmethod
    def create(db: Session, config: MCPConfig) -> MCPConfig:
        """Create a new MCP config"""
        db.add(config)
        db.commit()
        db.refresh(config)
        return config

    @staticmethod
    def update(db: Session, config: MCPConfig) -> MCPConfig:
        """Update an existing MCP config"""
        db.add(config)
        db.commit()
        db.refresh(config)
        return config

    @staticmethod
    def delete(db: Session, config: MCPConfig) -> None:
        """Delete an MCP config"""
        db.delete(config)
        db.commit()

    @staticmethod
    def delete_by_id_and_app_id(db: Session, config_id: int, app_id: int) -> bool:
        """Delete an MCP config by ID and app ID"""
        config = MCPConfigRepository.get_by_id_and_app_id(db, config_id, app_id)
        if config:
            MCPConfigRepository.delete(db, config)
            return True
        return False
