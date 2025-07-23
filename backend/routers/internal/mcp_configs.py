from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional

# Import schemas and auth
from .schemas import *
from .auth import get_current_user

mcp_configs_router = APIRouter()

# ==================== MCP CONFIG MANAGEMENT ====================

@mcp_configs_router.get("/", 
                        summary="List MCP configs",
                        tags=["MCP Configs"],
                        response_model=List[MCPConfigListItemSchema])
async def list_mcp_configs(app_id: int, current_user: dict = Depends(get_current_user)):
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
async def get_mcp_config(app_id: int, config_id: int, current_user: dict = Depends(get_current_user)):
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
            
            # Handle command/url field mapping
            command_value = ""
            if config.transport_type.value == "stdio":
                command_value = config.command or ""
            elif config.transport_type.value == "sse":
                command_value = config.url or ""
            
            # Convert JSON fields to strings for frontend
            args_str = ""
            if config.args:
                if isinstance(config.args, str):
                    args_str = config.args
                else:
                    import json
                    args_str = json.dumps(config.args)
            
            env_str = ""
            if config.env:
                if isinstance(config.env, str):
                    env_str = config.env
                else:
                    import json
                    env_str = json.dumps(config.env)
            
            return MCPConfigDetailSchema(
                config_id=config.config_id,
                name=config.name,
                transport_type=config.transport_type.value if hasattr(config.transport_type, 'value') else config.transport_type,
                command=command_value,
                args=args_str,
                env=env_str,
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
    current_user: dict = Depends(get_current_user)
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
            # Convert string to enum
            from models.mcp_config import TransportType
            if config_data.transport_type == "stdio":
                config.transport_type = TransportType.STDIO
            elif config_data.transport_type == "sse":
                config.transport_type = TransportType.SSE
            config.server_name = config_data.name  # Use name as server_name for simplicity
            
            # Handle command/url field mapping
            if config_data.transport_type == "stdio":
                config.command = config_data.command
                config.url = None
            elif config_data.transport_type == "sse":
                config.url = config_data.command
                config.command = None
            
            # Convert string JSON to actual JSON for storage
            import json
            try:
                if config_data.args.strip():
                    config.args = json.loads(config_data.args)
                else:
                    config.args = []
            except (json.JSONDecodeError, AttributeError):
                config.args = []
            
            try:
                if config_data.env.strip():
                    config.env = json.loads(config_data.env)
                else:
                    config.env = {}
            except (json.JSONDecodeError, AttributeError):
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
async def delete_mcp_config(app_id: int, config_id: int, current_user: dict = Depends(get_current_user)):
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