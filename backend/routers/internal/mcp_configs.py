from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session

# Import schemas and auth
from schemas.mcp_config_schemas import MCPConfigListItemSchema, MCPConfigDetailSchema, CreateUpdateMCPConfigSchema
from .auth_utils import get_current_user_oauth
from routers.controls.role_authorization import require_min_role, AppRole

# Import database and service
from db.database import get_db
from services.mcp_config_service import MCPConfigService

# Import logger
from utils.logger import get_logger


MCP_CONFIG_NOT_FOUND_ERROR = "MCP config not found"

logger = get_logger(__name__)

mcp_configs_router = APIRouter()

# ==================== MCP CONFIG MANAGEMENT ====================

@mcp_configs_router.get("/", 
                        summary="List MCP configs",
                        tags=["MCP Configs"],
                        response_model=List[MCPConfigListItemSchema])
async def list_mcp_configs(
    app_id: int, 
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("viewer")),
    db: Session = Depends(get_db)
):
    """
    List all MCP configs for a specific app.
    """
    
    try:
        return MCPConfigService.list_mcp_configs(db, app_id)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving MCP configs: {str(e)}"
        )


@mcp_configs_router.get("/{config_id}",
                        summary="Get MCP config details",
                        tags=["MCP Configs"],
                        response_model=MCPConfigDetailSchema)
async def get_mcp_config(
    app_id: int, 
    config_id: int, 
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("viewer")),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific MCP config.
    """
    
    try:
        config_detail = MCPConfigService.get_mcp_config_detail(db, app_id, config_id)
        
        if config_detail is None and config_id != 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=MCP_CONFIG_NOT_FOUND_ERROR
            )
        
        return config_detail
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving MCP config: {str(e)}"
        )


@mcp_configs_router.post("/{config_id}",
                         summary="Create or update MCP config",
                         tags=["MCP Configs"],
                         response_model=MCPConfigDetailSchema)
async def create_or_update_mcp_config(
    app_id: int,
    config_id: int,
    config_data: CreateUpdateMCPConfigSchema,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("administrator")),
    db: Session = Depends(get_db)
):
    """
    Create a new MCP config or update an existing one.
    """
    
    try:
        config = MCPConfigService.create_or_update_mcp_config(db, app_id, config_id, config_data)
        
        if config is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=MCP_CONFIG_NOT_FOUND_ERROR
            )
        
        # Return updated config (reuse the GET logic)
        return await get_mcp_config(app_id, config.config_id, auth_context, role, db)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating/updating MCP config: {str(e)}"
        )


@mcp_configs_router.delete("/{config_id}",
                           summary="Delete MCP config",
                           tags=["MCP Configs"])
async def delete_mcp_config(
    app_id: int, 
    config_id: int, 
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("administrator")),
    db: Session = Depends(get_db)
):
    """
    Delete an MCP config.
    """
    
    try:
        success = MCPConfigService.delete_mcp_config(db, app_id, config_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=MCP_CONFIG_NOT_FOUND_ERROR
            )
        
        return {"message": "MCP config deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting MCP config: {str(e)}"
        ) 