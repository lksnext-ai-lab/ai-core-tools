"""
MCP Authentication Module

Handles authentication for MCP endpoints supporting:
- API Key authentication (X-API-KEY header)
- JWT Bearer token authentication (Authorization header)
"""

from typing import Optional, Tuple
from datetime import datetime
from fastapi import HTTPException, status, Request

from models.api_key import APIKey
from models.app import App
from models.mcp_server import MCPServer
from db.database import SessionLocal
from repositories.mcp_server_repository import MCPServerRepository, AppSlugRepository
from utils.logger import get_logger

logger = get_logger(__name__)


class MCPAuthResult:
    """Result of MCP authentication"""
    def __init__(
        self,
        app: App,
        mcp_server: MCPServer,
        api_key_id: Optional[int] = None,
        user_id: Optional[int] = None
    ):
        # Store primitive values to avoid DetachedInstanceError after session closes
        self.app_id = app.app_id
        self.app_slug = app.slug
        self.server_id = mcp_server.server_id
        self.server_slug = mcp_server.slug
        self.server_name = mcp_server.name

        # Also store the objects for use within the same session context
        self.app = app
        self.mcp_server = mcp_server
        self.api_key_id = api_key_id
        self.user_id = user_id


def authenticate_mcp_request(
    request: Request,
    app_identifier: str,
    server_identifier: str,
    by_id: bool = False
) -> MCPAuthResult:
    """
    Authenticate an MCP request.

    Args:
        request: FastAPI request object
        app_identifier: App slug or ID
        server_identifier: MCP server slug or ID
        by_id: If True, identifiers are IDs; otherwise, they are slugs

    Returns:
        MCPAuthResult with authenticated app and server

    Raises:
        HTTPException: If authentication fails
    """
    # Extract authentication credentials
    api_key = request.headers.get("X-API-KEY")
    auth_header = request.headers.get("Authorization")

    if not api_key and not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide X-API-KEY header or Authorization: Bearer <token>"
        )

    session = SessionLocal()
    try:
        # Find the MCP server
        if by_id:
            try:
                app_id = int(app_identifier)
                server_id = int(server_identifier)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid app_id or server_id format"
                )

            app = session.query(App).filter(App.app_id == app_id).first()
            if not app:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="App not found"
                )

            mcp_server = MCPServerRepository.get_by_id_and_app_id(session, server_id, app_id)
        else:
            # Lookup by slugs
            app = AppSlugRepository.get_by_slug(session, app_identifier)
            if not app:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"App with slug '{app_identifier}' not found"
                )

            mcp_server = MCPServerRepository.get_by_slug(session, app_identifier, server_identifier)

        if not mcp_server:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="MCP server not found"
            )

        if not mcp_server.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="MCP server is not active"
            )

        # Authenticate using API key
        if api_key:
            return _authenticate_with_api_key(session, app, mcp_server, api_key)

        # Authenticate using JWT Bearer token
        if auth_header:
            return _authenticate_with_bearer_token(session, app, mcp_server, auth_header)

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No valid authentication method provided"
        )

    finally:
        session.close()


def _authenticate_with_api_key(
    session,
    app: App,
    mcp_server: MCPServer,
    api_key: str
) -> MCPAuthResult:
    """Authenticate using API key"""
    # Validate API key belongs to this app
    api_key_obj = session.query(APIKey).filter(
        APIKey.app_id == app.app_id,
        APIKey.key == api_key,
        APIKey.is_active == True
    ).first()

    if not api_key_obj:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key"
        )

    # Check if the app owner is active
    if app.owner and hasattr(app.owner, 'is_active') and not app.owner.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This API key belongs to a deactivated account"
        )

    # Update last used timestamp
    api_key_obj.last_used_at = datetime.now()
    session.commit()

    logger.info(f"MCP request authenticated via API key for server {mcp_server.server_id}")

    return MCPAuthResult(
        app=app,
        mcp_server=mcp_server,
        api_key_id=api_key_obj.key_id
    )


def _authenticate_with_bearer_token(
    session,
    app: App,
    mcp_server: MCPServer,
    auth_header: str
) -> MCPAuthResult:
    """Authenticate using Bearer token (JWT)"""
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Use: Bearer <token>"
        )

    token = auth_header[7:]  # Remove "Bearer " prefix

    # For now, we'll support API keys passed as bearer tokens for simplicity
    # In a full implementation, this would validate JWT tokens
    api_key_obj = session.query(APIKey).filter(
        APIKey.app_id == app.app_id,
        APIKey.key == token,
        APIKey.is_active == True
    ).first()

    if api_key_obj:
        # API key used as bearer token
        if app.owner and hasattr(app.owner, 'is_active') and not app.owner.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This token belongs to a deactivated account"
            )

        api_key_obj.last_used_at = datetime.now()
        session.commit()

        logger.info(f"MCP request authenticated via Bearer token (API key) for server {mcp_server.server_id}")

        return MCPAuthResult(
            app=app,
            mcp_server=mcp_server,
            api_key_id=api_key_obj.key_id
        )

    # If not an API key, could implement JWT validation here
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid bearer token"
    )
