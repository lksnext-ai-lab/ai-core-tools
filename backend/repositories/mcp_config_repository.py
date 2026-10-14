from typing import Optional, List
from sqlalchemy.orm import Session
from models.mcp_config import MCPConfig
from models.agent import AgentMCP


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
    def get_valid_config_ids_for_app(db: Session, config_ids: List[int], app_id: int) -> List[int]:
        """Filter ``config_ids`` down to those that exist and belong to ``app_id``.

        Used to scope agent-to-MCPConfig associations: without this filter, a caller
        could attach another tenant's MCP config to their own agent (IDOR).
        """
        if not config_ids:
            return []
        query = db.query(MCPConfig.config_id).filter(
            MCPConfig.config_id.in_(config_ids),
            MCPConfig.app_id == app_id
        )
        return [id for (id,) in query]

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
        db.query(AgentMCP).filter(AgentMCP.config_id == config.config_id).delete(synchronize_session=False)
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
