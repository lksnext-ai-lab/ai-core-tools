from typing import Optional, List
from models.mcp_server import MCPServer
from models.agent import Agent
from models.app import App
from repositories.mcp_server_repository import MCPServerRepository, AppSlugRepository
from sqlalchemy.orm import Session
from datetime import datetime
import re
import unicodedata
from config import MCP_BASE_URL
from schemas.mcp_server_schemas import (
    MCPServerListSchema,
    MCPServerDetailSchema,
    MCPServerAgentSchema,
    MCPConnectionHintsSchema,
    CreateMCPServerSchema,
    UpdateMCPServerSchema,
    AppSlugResponseSchema,
)
from utils.logger import get_logger

logger = get_logger(__name__)


class MCPServerService:

    @staticmethod
    def generate_slug(name: str) -> str:
        """Generate a URL-safe slug from a name"""
        # Normalize unicode characters
        slug = unicodedata.normalize('NFKD', name)
        # Convert to ASCII, ignore non-convertible characters
        slug = slug.encode('ascii', 'ignore').decode('ascii')
        # Convert to lowercase
        slug = slug.lower()
        # Replace spaces and underscores with hyphens
        slug = re.sub(r'[\s_]+', '-', slug)
        # Remove all non-alphanumeric characters except hyphens
        slug = re.sub(r'[^a-z0-9-]', '', slug)
        # Remove multiple consecutive hyphens
        slug = re.sub(r'-+', '-', slug)
        # Strip leading/trailing hyphens
        slug = slug.strip('-')
        # Limit length
        slug = slug[:100]
        return slug or 'server'

    @staticmethod
    def validate_slug(db: Session, app_id: int, slug: str, exclude_server_id: Optional[int] = None) -> bool:
        """Check if a slug is valid and unique within the app"""
        if not slug:
            return False
        if not re.match(r'^[a-z0-9-]+$', slug):
            return False
        if len(slug) > 100:
            return False
        return not MCPServerRepository.slug_exists(db, app_id, slug, exclude_server_id)

    @staticmethod
    def ensure_unique_slug(db: Session, app_id: int, base_slug: str, exclude_server_id: Optional[int] = None) -> str:
        """Ensure the slug is unique by appending a number if needed"""
        slug = base_slug
        counter = 1
        while MCPServerRepository.slug_exists(db, app_id, slug, exclude_server_id):
            slug = f"{base_slug}-{counter}"
            counter += 1
            if counter > 100:  # Safety limit
                slug = f"{base_slug}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                break
        return slug

    @staticmethod
    def get_endpoint_url(app: App, server: MCPServer) -> str:
        """Get the slug-based endpoint URL for an MCP server"""
        if app.slug and server.slug:
            return f"{MCP_BASE_URL}/mcp/v1/{app.slug}/{server.slug}"
        return f"{MCP_BASE_URL}/mcp/v1/id/{app.app_id}/{server.server_id}"

    @staticmethod
    def get_endpoint_url_by_id(app: App, server: MCPServer) -> str:
        """Get the ID-based (fallback) endpoint URL for an MCP server"""
        return f"{MCP_BASE_URL}/mcp/v1/id/{app.app_id}/{server.server_id}"

    @staticmethod
    def get_connection_hints(app: App, server: MCPServer) -> MCPConnectionHintsSchema:
        """Generate connection configuration hints for MCP clients"""
        endpoint_url = MCPServerService.get_endpoint_url(app, server)
        endpoint_url_by_id = MCPServerService.get_endpoint_url_by_id(app, server)

        # Claude Desktop configuration (Streamable HTTP)
        claude_desktop = {
            "mcpServers": {
                server.name.lower().replace(' ', '-'): {
                    "url": endpoint_url,
                    "headers": {
                        "X-API-KEY": "<your-api-key>"
                    }
                }
            }
        }

        # Cursor configuration
        cursor = {
            "mcpServers": {
                server.name.lower().replace(' ', '-'): {
                    "url": endpoint_url,
                    "headers": {
                        "X-API-KEY": "<your-api-key>"
                    }
                }
            }
        }

        # Curl example for testing
        curl_example = (
            f'curl -X POST "{endpoint_url}" \\\n'
            f'  -H "X-API-KEY: <your-api-key>" \\\n'
            f'  -H "Content-Type: application/json" \\\n'
            f'  -d \'{{"jsonrpc": "2.0", "method": "tools/list", "id": 1}}\''
        )

        return MCPConnectionHintsSchema(
            claude_desktop=claude_desktop,
            cursor=cursor,
            curl_example=curl_example,
            endpoint_url=endpoint_url,
            endpoint_url_by_id=endpoint_url_by_id
        )

    @staticmethod
    def list_mcp_servers(db: Session, app_id: int) -> List[MCPServerListSchema]:
        """Get all MCP servers for a specific app as list items"""
        app = db.query(App).filter(App.app_id == app_id).first()
        if not app:
            return []

        servers = MCPServerRepository.get_all_by_app_id(db, app_id)

        result = []
        for server in servers:
            agent_count = len(server.agent_associations) if server.agent_associations else 0
            result.append(MCPServerListSchema(
                server_id=server.server_id,
                name=server.name,
                slug=server.slug,
                description=server.description,
                is_active=server.is_active,
                agent_count=agent_count,
                endpoint_url=MCPServerService.get_endpoint_url(app, server),
                create_date=server.create_date
            ))

        return result

    @staticmethod
    def get_mcp_server_detail(db: Session, app_id: int, server_id: int) -> Optional[MCPServerDetailSchema]:
        """Get detailed information about a specific MCP server"""
        app = db.query(App).filter(App.app_id == app_id).first()
        if not app:
            return None

        if server_id == 0:
            # New MCP server - return empty form data
            return MCPServerDetailSchema(
                server_id=0,
                name="",
                slug="",
                description="",
                is_active=True,
                rate_limit=0,
                agents=[],
                endpoint_url="",
                endpoint_url_by_id="",
                connection_hints=MCPConnectionHintsSchema(
                    claude_desktop={},
                    cursor={},
                    curl_example="",
                    endpoint_url="",
                    endpoint_url_by_id=""
                ),
                create_date=None,
                update_date=None
            )

        server = MCPServerRepository.get_by_id_and_app_id(db, server_id, app_id)
        if not server:
            return None

        # Build agent list with details and availability status
        agents = []
        for assoc in server.agent_associations:
            agent = assoc.agent
            if agent:
                # Check if agent is still available (exists and is marked as tool)
                is_available = agent.is_tool
                unavailable_reason = None
                if not agent.is_tool:
                    unavailable_reason = "Agent is no longer marked as a tool"

                agents.append(MCPServerAgentSchema(
                    agent_id=agent.agent_id,
                    agent_name=agent.name,
                    agent_description=agent.description,
                    tool_name_override=assoc.tool_name_override,
                    tool_description_override=assoc.tool_description_override,
                    is_available=is_available,
                    unavailable_reason=unavailable_reason
                ))
            else:
                # Agent was deleted - include placeholder info
                agents.append(MCPServerAgentSchema(
                    agent_id=assoc.agent_id,
                    agent_name="[Deleted Agent]",
                    agent_description=None,
                    tool_name_override=assoc.tool_name_override,
                    tool_description_override=assoc.tool_description_override,
                    is_available=False,
                    unavailable_reason="Agent has been deleted"
                ))

        return MCPServerDetailSchema(
            server_id=server.server_id,
            name=server.name,
            slug=server.slug,
            description=server.description,
            is_active=server.is_active,
            rate_limit=server.rate_limit,
            agents=agents,
            endpoint_url=MCPServerService.get_endpoint_url(app, server),
            endpoint_url_by_id=MCPServerService.get_endpoint_url_by_id(app, server),
            connection_hints=MCPServerService.get_connection_hints(app, server),
            create_date=server.create_date,
            update_date=server.update_date
        )

    @staticmethod
    def create_mcp_server(
        db: Session,
        app_id: int,
        data: CreateMCPServerSchema
    ) -> Optional[MCPServerDetailSchema]:
        """Create a new MCP server"""
        app = db.query(App).filter(App.app_id == app_id).first()
        if not app:
            return None

        # Generate or validate slug
        if data.slug:
            slug = MCPServerService.generate_slug(data.slug)
        else:
            slug = MCPServerService.generate_slug(data.name)

        # Ensure unique slug within app
        slug = MCPServerService.ensure_unique_slug(db, app_id, slug)

        # Create server
        server = MCPServer(
            name=data.name,
            slug=slug,
            description=data.description or "",
            is_active=data.is_active,
            rate_limit=data.rate_limit,
            app_id=app_id,
            create_date=datetime.now(),
            update_date=datetime.now()
        )
        server = MCPServerRepository.create(db, server)

        # Add agent associations
        if data.agent_ids:
            for agent_id in data.agent_ids:
                # Verify agent exists and belongs to this app and is a tool
                agent = db.query(Agent).filter(
                    Agent.agent_id == agent_id,
                    Agent.app_id == app_id,
                    Agent.is_tool == True
                ).first()
                if agent:
                    MCPServerRepository.add_agent(db, server.server_id, agent_id)

        # Refresh to get associations
        db.refresh(server)

        return MCPServerService.get_mcp_server_detail(db, app_id, server.server_id)

    @staticmethod
    def update_mcp_server(
        db: Session,
        app_id: int,
        server_id: int,
        data: UpdateMCPServerSchema
    ) -> Optional[MCPServerDetailSchema]:
        """Update an existing MCP server"""
        server = MCPServerRepository.get_by_id_and_app_id(db, server_id, app_id)
        if not server:
            return None

        # Update fields if provided
        if data.name is not None:
            server.name = data.name

        if data.slug is not None:
            slug = MCPServerService.generate_slug(data.slug)
            if not MCPServerService.validate_slug(db, app_id, slug, server_id):
                slug = MCPServerService.ensure_unique_slug(db, app_id, slug, server_id)
            server.slug = slug

        if data.description is not None:
            server.description = data.description

        if data.is_active is not None:
            server.is_active = data.is_active

        if data.rate_limit is not None:
            server.rate_limit = data.rate_limit

        server.update_date = datetime.now()
        server = MCPServerRepository.update(db, server)

        # Update agents if provided
        if data.agent_ids is not None:
            # Clear existing associations
            MCPServerRepository.clear_agents(db, server_id)

            # Add new associations
            for agent_id in data.agent_ids:
                # Verify agent exists and belongs to this app and is a tool
                agent = db.query(Agent).filter(
                    Agent.agent_id == agent_id,
                    Agent.app_id == app_id,
                    Agent.is_tool == True
                ).first()
                if agent:
                    MCPServerRepository.add_agent(db, server.server_id, agent_id)

        return MCPServerService.get_mcp_server_detail(db, app_id, server.server_id)

    @staticmethod
    def delete_mcp_server(db: Session, app_id: int, server_id: int) -> bool:
        """Delete an MCP server"""
        return MCPServerRepository.delete_by_id_and_app_id(db, server_id, app_id)

    @staticmethod
    def get_tool_agents(db: Session, app_id: int) -> List[dict]:
        """Get all agents marked as tools for this app"""
        agents = db.query(Agent).filter(
            Agent.app_id == app_id,
            Agent.is_tool == True
        ).all()

        return [
            {
                "agent_id": agent.agent_id,
                "name": agent.name,
                "description": agent.description
            }
            for agent in agents
        ]

    @staticmethod
    def get_mcp_servers_using_agent(db: Session, agent_id: int) -> List[dict]:
        """
        Get all MCP servers that use a specific agent.
        Used to warn users when unmarking/deleting an agent.
        """
        from models.mcp_server import MCPServerAgent

        # Find all MCP server associations for this agent
        associations = db.query(MCPServerAgent).filter(
            MCPServerAgent.agent_id == agent_id
        ).all()

        servers = []
        for assoc in associations:
            server = assoc.mcp_server
            if server:
                servers.append({
                    "server_id": server.server_id,
                    "server_name": server.name,
                    "app_id": server.app_id
                })

        return servers


class AppSlugService:
    """Service for App slug management"""

    @staticmethod
    def generate_slug(name: str) -> str:
        """Generate a URL-safe slug from a name"""
        return MCPServerService.generate_slug(name)

    @staticmethod
    def validate_slug(db: Session, slug: str, exclude_app_id: Optional[int] = None) -> bool:
        """Check if a slug is valid and unique"""
        if not slug:
            return False
        if not re.match(r'^[a-z0-9-]+$', slug):
            return False
        if len(slug) > 100:
            return False
        return not AppSlugRepository.slug_exists(db, slug, exclude_app_id)

    @staticmethod
    def ensure_unique_slug(db: Session, base_slug: str, exclude_app_id: Optional[int] = None) -> str:
        """Ensure the slug is unique by appending a number if needed"""
        slug = base_slug
        counter = 1
        while AppSlugRepository.slug_exists(db, slug, exclude_app_id):
            slug = f"{base_slug}-{counter}"
            counter += 1
            if counter > 100:
                slug = f"{base_slug}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                break
        return slug

    @staticmethod
    def get_app_slug_info(db: Session, app_id: int) -> Optional[AppSlugResponseSchema]:
        """Get app slug information"""
        app = db.query(App).filter(App.app_id == app_id).first()
        if not app:
            return None

        mcp_base_url = f"{MCP_BASE_URL}/mcp/v1"
        if app.slug:
            mcp_base_url = f"{MCP_BASE_URL}/mcp/v1/{app.slug}"

        return AppSlugResponseSchema(
            app_id=app.app_id,
            slug=app.slug,
            mcp_base_url=mcp_base_url
        )

    @staticmethod
    def update_app_slug(db: Session, app_id: int, slug: str) -> Optional[AppSlugResponseSchema]:
        """Update an app's slug"""
        app = db.query(App).filter(App.app_id == app_id).first()
        if not app:
            return None

        # Generate and validate slug
        clean_slug = MCPServerService.generate_slug(slug)
        if not AppSlugService.validate_slug(db, clean_slug, app_id):
            clean_slug = AppSlugService.ensure_unique_slug(db, clean_slug, app_id)

        app = AppSlugRepository.update_slug(db, app_id, clean_slug)
        if not app:
            return None

        return AppSlugService.get_app_slug_info(db, app_id)

    @staticmethod
    def get_app_by_slug(db: Session, slug: str) -> Optional[App]:
        """Get an app by its slug"""
        return AppSlugRepository.get_by_slug(db, slug)
