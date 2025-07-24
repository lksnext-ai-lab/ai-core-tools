from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List, Optional
import json

# Import schemas and auth
from .schemas import *
from .auth_utils import get_current_user_oauth

# Import logger
from utils.logger import get_logger

logger = get_logger(__name__)

mcp_configs_router = APIRouter()

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
                args=json.dumps(config.args) if config.args else "",
                env=json.dumps(config.env) if config.env else "",
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
        from models.mcp_config import MCPConfig, TransportType
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