from fastapi import (
    APIRouter, Depends, HTTPException, status,
    UploadFile, File, Query
)
from fastapi.responses import JSONResponse
from typing import List, Optional
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session

# Import schemas and auth
from schemas.mcp_config_schemas import (
    MCPConfigListItemSchema, MCPConfigDetailSchema,
    CreateUpdateMCPConfigSchema
)
from schemas.import_schemas import ConflictMode, ImportResponseSchema
from schemas.export_schemas import MCPConfigExportFileSchema
from .auth_utils import get_current_user_oauth
from routers.controls.role_authorization import require_min_role, AppRole

# Import database and service
from db.database import get_db
from services.mcp_config_service import MCPConfigService
from services.mcp_config_export_service import MCPConfigExportService
from services.mcp_config_import_service import MCPConfigImportService

# Import logger
from utils.logger import get_logger


import json

MCP_CONFIG_NOT_FOUND_ERROR = "MCP config not found"

logger = get_logger(__name__)

mcp_configs_router = APIRouter()

# ==================== STATIC ROUTES (without {config_id} parameter) ====================


@mcp_configs_router.post(
    "/import",
    summary="Import MCP Configuration",
    tags=["MCP Configs", "Export/Import"],
    response_model=ImportResponseSchema,
    status_code=status.HTTP_201_CREATED
)
async def import_mcp_config(
    app_id: int,
    file: UploadFile = File(...),
    conflict_mode: ConflictMode = Query(ConflictMode.FAIL),
    new_name: Optional[str] = Query(None),
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("administrator")),
    db: Session = Depends(get_db)
):
    """Import MCP Configuration from JSON file."""
    try:
        # Parse file
        content = await file.read()
        file_data = json.loads(content)
        export_data = MCPConfigExportFileSchema(**file_data)
        
        # Import
        import_service = MCPConfigImportService(db)
        summary = import_service.import_mcp_config(
            export_data,
            app_id,
            conflict_mode,
            new_name
        )
        
        return ImportResponseSchema(
            success=True,
            message=(
                f"MCP Configuration '{summary.component_name}' "
                f"imported successfully"
            ),
            summary=summary
        )
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON: {str(e)}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON file")
    except ValueError as e:
        logger.warning(f"Import failed: {str(e)}")
        if "already exists" in str(e):
            raise HTTPException(status.HTTP_409_CONFLICT, str(e))
        else:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"Invalid data: {str(e)}"
            )
    except Exception as e:
        logger.error(f"Import error: {str(e)}", exc_info=True)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Import failed"
        )


# ==================== DYNAMIC ROUTES (with {config_id} parameter) ====================


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


@mcp_configs_router.post("/test-connection",
                         summary="Test MCP connection with provided config",
                         tags=["MCP Configs"])
async def test_mcp_connection_with_config(
    app_id: int,
    config_data: CreateUpdateMCPConfigSchema,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("administrator")),
    db: Session = Depends(get_db)
):
    """
    Test connection to MCP server with provided config.
    """
    try:
        # Parse the config string to a dict
        try:
            actual_config = json.loads(config_data.config)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid JSON in config field: {str(e)}"
            )
        
        # Validate config structure
        if not isinstance(actual_config, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Config must be a JSON object (dictionary)"
            )
        
        if not actual_config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Config cannot be empty"
            )
             
        result = await MCPConfigService.test_connection_with_config(actual_config)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing MCP connection for app {app_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error testing MCP connection: {str(e)}"
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


# ==================== EXPORT/IMPORT ENDPOINTS ====================


@mcp_configs_router.post(
    "/import",
    summary="Import MCP Configuration",
    tags=["MCP Configs", "Export/Import"],
    response_model=ImportResponseSchema,
    status_code=status.HTTP_201_CREATED
)
async def import_mcp_config(
    app_id: int,
    file: UploadFile = File(...),
    conflict_mode: ConflictMode = Query(ConflictMode.FAIL),
    new_name: Optional[str] = Query(None),
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("administrator")),
    db: Session = Depends(get_db)
):
    """Import MCP Configuration from JSON file."""
    try:
        # Parse file
        content = await file.read()
        file_data = json.loads(content)
        export_data = MCPConfigExportFileSchema(**file_data)
        
        # Import
        import_service = MCPConfigImportService(db)
        summary = import_service.import_mcp_config(
            export_data,
            app_id,
            conflict_mode,
            new_name
        )
        
        return ImportResponseSchema(
            success=True,
            message=f"MCP Config '{summary.component_name}' imported successfully",
            summary=summary
        )
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON: {str(e)}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON file")
    except ValueError as e:
        logger.warning(f"Import failed: {str(e)}")
        if "already exists" in str(e):
            raise HTTPException(status.HTTP_409_CONFLICT, str(e))
        else:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid data: {str(e)}")
    except Exception as e:
        logger.error(f"Import error: {str(e)}", exc_info=True)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Import failed")


@mcp_configs_router.post(
    "/{config_id}/export",
    summary="Export MCP Configuration",
    tags=["MCP Configs", "Export/Import"],
    status_code=status.HTTP_200_OK
)
async def export_mcp_config(
    app_id: int,
    config_id: int,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("viewer")),
    db: Session = Depends(get_db)
):
    """Export MCP Configuration to JSON file (sanitized)."""
    try:
        export_service = MCPConfigExportService(db)
        export_data = export_service.export_mcp_config(
            config_id,
            app_id,
            getattr(auth_context, 'user_id', None)
        )
        
        filename = (
            f"{export_data.mcp_config.name.replace(' ', '_')}"
            f"_mcp_config.json"
        )
        
        return JSONResponse(
            content=export_data.model_dump(mode='json'),
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except ValueError as e:
        logger.warning(f"Export failed: {str(e)}")
        if "not found" in str(e):
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
        else:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except Exception as e:
        logger.error(f"Export error: {str(e)}", exc_info=True)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Export failed")


@mcp_configs_router.post("/{config_id}/test",
                         summary="Test MCP connection",
                         tags=["MCP Configs"])
async def test_mcp_connection(
    app_id: int,
    config_id: int,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("administrator")),
    db: Session = Depends(get_db)
):
    """
    Test connection to MCP server and list tools.
    """
    try:
        return await MCPConfigService.test_connection(db, app_id, config_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error testing MCP connection: {str(e)}"
        ) 