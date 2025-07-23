from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List, Optional

# Import schemas and auth
from .schemas import *
# Switch to Google OAuth auth instead of temp token auth
from routers.auth import verify_jwt_token

mcp_configs_router = APIRouter()

# ==================== AUTHENTICATION ====================

async def get_current_user_oauth(request: Request):
    """
    Get current authenticated user using Google OAuth JWT tokens.
    Compatible with the frontend auth system.
    """
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Please provide Authorization header with Bearer token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        token = auth_header.split(' ')[1]
        
        # Verify token using Google OAuth system
        payload = verify_jwt_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return payload
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )

# ==================== MCP CONFIG MANAGEMENT ====================

@mcp_configs_router.get("/", 
                        summary="List MCP configs",
                        tags=["MCP Configs"],
                        response_model=List[MCPConfigListItemSchema])
async def list_mcp_configs(app_id: int, current_user: dict = Depends(get_current_user_oauth)):
    """
    List all MCP configs for a specific app.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        from db.session import SessionLocal
        from models.mcp_config import MCPConfig
        
        session = SessionLocal()
        try:
            configs = session.query(MCPConfig).filter(MCPConfig.app_id == app_id).all()
            
            result = []
            for config in configs:
                result.append(MCPConfigListItemSchema(
                    config_id=config.config_id,
                    name=config.name,
                    transport_type=config.transport_type.value if hasattr(config.transport_type, 'value') else config.transport_type,
                    created_at=config.create_date
                ))
            
            return result
            
        finally:
            session.close()
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving MCP configs: {str(e)}"
        )


@mcp_configs_router.get("/{config_id}",
                        summary="Get MCP config details",
                        tags=["MCP Configs"],
                        response_model=MCPConfigDetailSchema)
async def get_mcp_config(app_id: int, config_id: int, current_user: dict = Depends(get_current_user_oauth)):
    """
    Get detailed information about a specific MCP config.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        from db.session import SessionLocal
        from models.mcp_config import MCPConfig, TransportType
        
        session = SessionLocal()
        try:
            if config_id == 0:
                # New MCP config
                # Get available transport types
                transport_types = [{"value": t.value, "name": t.value} for t in TransportType]
                
                return MCPConfigDetailSchema(
                    config_id=0,
                    name="",
                    transport_type=None,
                    command="",
                    args="",
                    env="",
                    created_at=None,
                    available_transport_types=transport_types
                )
            
            # Existing MCP config
            config = session.query(MCPConfig).filter(
                MCPConfig.config_id == config_id,
                MCPConfig.app_id == app_id
            ).first()
            
            if not config:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="MCP config not found"
                )
            
            # Get available transport types
            transport_types = [{"value": t.value, "name": t.value} for t in TransportType]
            
            return MCPConfigDetailSchema(
                config_id=config.config_id,
                name=config.name,
                transport_type=config.transport_type.value if hasattr(config.transport_type, 'value') else config.transport_type,
                command=config.command or "",
                args=config.args or "",
                env=config.env or "",
                created_at=config.create_date,
                available_transport_types=transport_types
            )
            
        finally:
            session.close()
            
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
    current_user: dict = Depends(get_current_user_oauth)
):
    """
    Create a new MCP config or update an existing one.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        from db.session import SessionLocal
        from models.mcp_config import MCPConfig
        from datetime import datetime
        
        session = SessionLocal()
        try:
            if config_id == 0:
                # Create new MCP config
                config = MCPConfig()
                config.app_id = app_id
                config.create_date = datetime.now()
            else:
                # Update existing MCP config
                config = session.query(MCPConfig).filter(
                    MCPConfig.config_id == config_id,
                    MCPConfig.app_id == app_id
                ).first()
                
                if not config:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="MCP config not found"
                    )
            
            # Update config data
            config.name = config_data.name
            config.transport_type = config_data.transport_type
            config.command = config_data.command
            config.args = config_data.args
            config.env = config_data.env
            
            session.add(config)
            session.commit()
            session.refresh(config)
            
            # Return updated config (reuse the GET logic)
            return await get_mcp_config(app_id, config.config_id, current_user)
            
        finally:
            session.close()
            
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
async def delete_mcp_config(app_id: int, config_id: int, current_user: dict = Depends(get_current_user_oauth)):
    """
    Delete an MCP config.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        from db.session import SessionLocal
        from models.mcp_config import MCPConfig
        
        session = SessionLocal()
        try:
            config = session.query(MCPConfig).filter(
                MCPConfig.config_id == config_id,
                MCPConfig.app_id == app_id
            ).first()
            
            if not config:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="MCP config not found"
                )
            
            session.delete(config)
            session.commit()
            
            return {"message": "MCP config deleted successfully"}
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting MCP config: {str(e)}"
        ) 