from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session

# Import schemas and auth
from schemas.mcp_server_schemas import (
    MCPServerListSchema,
    MCPServerDetailSchema,
    CreateMCPServerSchema,
    UpdateMCPServerSchema,
    AppSlugResponseSchema,
    UpdateAppSlugSchema,
)
from .auth_utils import get_current_user_oauth
from routers.controls.role_authorization import require_min_role, AppRole

# Import database and service
from db.database import get_db
from services.mcp_server_service import MCPServerService, AppSlugService

# Import logger
from utils.logger import get_logger

MCP_SERVER_NOT_FOUND_ERROR = "MCP server not found"

logger = get_logger(__name__)

mcp_servers_router = APIRouter()

# ==================== MCP SERVER MANAGEMENT ====================


@mcp_servers_router.get("/",
                        summary="List MCP servers",
                        tags=["MCP Servers"],
                        response_model=List[MCPServerListSchema])
async def list_mcp_servers(
    app_id: int,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("viewer")),
    db: Session = Depends(get_db)
):
    """
    List all MCP servers for a specific app.
    """
    try:
        return MCPServerService.list_mcp_servers(db, app_id)
    except Exception as e:
        logger.error(f"Error listing MCP servers for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving MCP servers: {str(e)}"
        )


@mcp_servers_router.get("/tool-agents",
                        summary="List available tool agents",
                        tags=["MCP Servers"])
async def list_tool_agents(
    app_id: int,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("viewer")),
    db: Session = Depends(get_db)
):
    """
    List all agents marked as tools that can be exposed via MCP servers.
    """
    try:
        return MCPServerService.get_tool_agents(db, app_id)
    except Exception as e:
        logger.error(f"Error listing tool agents for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving tool agents: {str(e)}"
        )


# ==================== APP SLUG MANAGEMENT ====================
# NOTE: These routes MUST be before /{server_id} to avoid routing conflicts


@mcp_servers_router.get("/slug/info",
                        summary="Get app slug info",
                        tags=["App Slug"])
async def get_app_slug_info(
    app_id: int,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("viewer")),
    db: Session = Depends(get_db)
):
    """
    Get the current slug configuration for the app.
    """
    try:
        slug_info = AppSlugService.get_app_slug_info(db, app_id)

        if slug_info is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="App not found"
            )

        return slug_info

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting slug info for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving app slug: {str(e)}"
        )


@mcp_servers_router.put("/slug",
                        summary="Update app slug",
                        tags=["App Slug"],
                        response_model=AppSlugResponseSchema)
async def update_app_slug(
    app_id: int,
    slug_data: UpdateAppSlugSchema,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("administrator")),
    db: Session = Depends(get_db)
):
    """
    Update the app's URL slug.
    """
    try:
        slug_info = AppSlugService.update_app_slug(db, app_id, slug_data.slug)

        if slug_info is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="App not found"
            )

        return slug_info

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating slug for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating app slug: {str(e)}"
        )


# ==================== MCP SERVER CRUD ====================


@mcp_servers_router.get("/{server_id}",
                        summary="Get MCP server details",
                        tags=["MCP Servers"],
                        response_model=MCPServerDetailSchema)
async def get_mcp_server(
    app_id: int,
    server_id: int,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("viewer")),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific MCP server.
    """
    try:
        server_detail = MCPServerService.get_mcp_server_detail(db, app_id, server_id)

        if server_detail is None and server_id != 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=MCP_SERVER_NOT_FOUND_ERROR
            )

        return server_detail

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving MCP server {server_id} for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving MCP server: {str(e)}"
        )


@mcp_servers_router.post("/",
                         summary="Create MCP server",
                         tags=["MCP Servers"],
                         response_model=MCPServerDetailSchema,
                         status_code=status.HTTP_201_CREATED)
async def create_mcp_server(
    app_id: int,
    server_data: CreateMCPServerSchema,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("administrator")),
    db: Session = Depends(get_db)
):
    """
    Create a new MCP server.
    """
    try:
        server = MCPServerService.create_mcp_server(db, app_id, server_data)

        if server is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create MCP server"
            )

        return server

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating MCP server for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating MCP server: {str(e)}"
        )


@mcp_servers_router.put("/{server_id}",
                        summary="Update MCP server",
                        tags=["MCP Servers"],
                        response_model=MCPServerDetailSchema)
async def update_mcp_server(
    app_id: int,
    server_id: int,
    server_data: UpdateMCPServerSchema,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("administrator")),
    db: Session = Depends(get_db)
):
    """
    Update an existing MCP server.
    """
    try:
        server = MCPServerService.update_mcp_server(db, app_id, server_id, server_data)

        if server is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=MCP_SERVER_NOT_FOUND_ERROR
            )

        return server

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating MCP server {server_id} for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating MCP server: {str(e)}"
        )


@mcp_servers_router.delete("/{server_id}",
                           summary="Delete MCP server",
                           tags=["MCP Servers"])
async def delete_mcp_server(
    app_id: int,
    server_id: int,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("administrator")),
    db: Session = Depends(get_db)
):
    """
    Delete an MCP server.
    """
    try:
        success = MCPServerService.delete_mcp_server(db, app_id, server_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=MCP_SERVER_NOT_FOUND_ERROR
            )

        return {"message": "MCP server deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting MCP server {server_id} for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting MCP server: {str(e)}"
        )
