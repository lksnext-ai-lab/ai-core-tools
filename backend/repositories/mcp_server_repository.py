from typing import Optional, List
from sqlalchemy.orm import Session, joinedload
from models.mcp_server import MCPServer, MCPServerAgent
from models.app import App


class MCPServerRepository:

    @staticmethod
    def get_all_by_app_id(db: Session, app_id: int) -> List[MCPServer]:
        """Get all MCP servers for a specific app"""
        return db.query(MCPServer).filter(
            MCPServer.app_id == app_id
        ).order_by(MCPServer.name).all()

    @staticmethod
    def get_by_id(db: Session, server_id: int) -> Optional[MCPServer]:
        """Get an MCP server by ID with eager loading of agents"""
        return db.query(MCPServer).options(
            joinedload(MCPServer.agent_associations)
        ).filter(
            MCPServer.server_id == server_id
        ).first()

    @staticmethod
    def get_by_id_and_app_id(db: Session, server_id: int, app_id: int) -> Optional[MCPServer]:
        """Get an MCP server by ID and app ID"""
        return db.query(MCPServer).options(
            joinedload(MCPServer.agent_associations)
        ).filter(
            MCPServer.server_id == server_id,
            MCPServer.app_id == app_id
        ).first()

    @staticmethod
    def get_by_slug(db: Session, app_slug: str, server_slug: str) -> Optional[MCPServer]:
        """Get an MCP server by app slug and server slug"""
        return db.query(MCPServer).join(App).options(
            joinedload(MCPServer.agent_associations)
        ).filter(
            App.slug == app_slug,
            MCPServer.slug == server_slug
        ).first()

    @staticmethod
    def get_by_app_slug_and_server_id(db: Session, app_slug: str, server_id: int) -> Optional[MCPServer]:
        """Get an MCP server by app slug and server ID (fallback)"""
        return db.query(MCPServer).join(App).options(
            joinedload(MCPServer.agent_associations)
        ).filter(
            App.slug == app_slug,
            MCPServer.server_id == server_id
        ).first()

    @staticmethod
    def slug_exists(db: Session, app_id: int, slug: str, exclude_server_id: Optional[int] = None) -> bool:
        """Check if a slug already exists for this app"""
        query = db.query(MCPServer).filter(
            MCPServer.app_id == app_id,
            MCPServer.slug == slug
        )
        if exclude_server_id:
            query = query.filter(MCPServer.server_id != exclude_server_id)
        return query.first() is not None

    @staticmethod
    def create(db: Session, server: MCPServer) -> MCPServer:
        """Create a new MCP server"""
        db.add(server)
        db.commit()
        db.refresh(server)
        return server

    @staticmethod
    def update(db: Session, server: MCPServer) -> MCPServer:
        """Update an existing MCP server"""
        db.add(server)
        db.commit()
        db.refresh(server)
        return server

    @staticmethod
    def delete(db: Session, server: MCPServer) -> None:
        """Delete an MCP server"""
        db.delete(server)
        db.commit()

    @staticmethod
    def delete_by_id_and_app_id(db: Session, server_id: int, app_id: int) -> bool:
        """Delete an MCP server by ID and app ID"""
        server = MCPServerRepository.get_by_id_and_app_id(db, server_id, app_id)
        if server:
            MCPServerRepository.delete(db, server)
            return True
        return False

    @staticmethod
    def add_agent(db: Session, server_id: int, agent_id: int,
                  tool_name_override: Optional[str] = None,
                  tool_description_override: Optional[str] = None) -> MCPServerAgent:
        """Add an agent to an MCP server"""
        association = MCPServerAgent(
            server_id=server_id,
            agent_id=agent_id,
            tool_name_override=tool_name_override,
            tool_description_override=tool_description_override
        )
        db.add(association)
        db.commit()
        db.refresh(association)
        return association

    @staticmethod
    def remove_agent(db: Session, server_id: int, agent_id: int) -> bool:
        """Remove an agent from an MCP server"""
        association = db.query(MCPServerAgent).filter(
            MCPServerAgent.server_id == server_id,
            MCPServerAgent.agent_id == agent_id
        ).first()
        if association:
            db.delete(association)
            db.commit()
            return True
        return False

    @staticmethod
    def clear_agents(db: Session, server_id: int) -> None:
        """Remove all agents from an MCP server"""
        db.query(MCPServerAgent).filter(
            MCPServerAgent.server_id == server_id
        ).delete()
        db.commit()

    @staticmethod
    def update_agent_association(db: Session, server_id: int, agent_id: int,
                                 tool_name_override: Optional[str] = None,
                                 tool_description_override: Optional[str] = None) -> Optional[MCPServerAgent]:
        """Update an agent association"""
        association = db.query(MCPServerAgent).filter(
            MCPServerAgent.server_id == server_id,
            MCPServerAgent.agent_id == agent_id
        ).first()
        if association:
            association.tool_name_override = tool_name_override
            association.tool_description_override = tool_description_override
            db.commit()
            db.refresh(association)
        return association


class AppSlugRepository:
    """Repository for App slug operations"""

    @staticmethod
    def get_by_slug(db: Session, slug: str) -> Optional[App]:
        """Get an app by its slug"""
        return db.query(App).filter(App.slug == slug).first()

    @staticmethod
    def slug_exists(db: Session, slug: str, exclude_app_id: Optional[int] = None) -> bool:
        """Check if a slug already exists"""
        query = db.query(App).filter(App.slug == slug)
        if exclude_app_id:
            query = query.filter(App.app_id != exclude_app_id)
        return query.first() is not None

    @staticmethod
    def update_slug(db: Session, app_id: int, slug: str) -> Optional[App]:
        """Update an app's slug"""
        app = db.query(App).filter(App.app_id == app_id).first()
        if app:
            app.slug = slug
            db.commit()
            db.refresh(app)
        return app
