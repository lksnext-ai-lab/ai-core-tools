from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.responses import JSONResponse
from lks_idprovider import AuthContext
from typing import List, Optional
from sqlalchemy.orm import Session
import json

from schemas.output_parser_schemas import (
    OutputParserListItemSchema,
    OutputParserDetailSchema,
    CreateUpdateOutputParserSchema
)
from schemas.import_schemas import ConflictMode, ImportResponseSchema
from schemas.export_schemas import OutputParserExportFileSchema

from .auth_utils import get_current_user_oauth
from routers.controls.role_authorization import require_min_role, AppRole

# Import database dependency
from db.database import get_db

# Import services
from services.output_parser_service import OutputParserService
from services.output_parser_export_service import OutputParserExportService
from services.output_parser_import_service import OutputParserImportService

# Import logger
from utils.logger import get_logger


OUTPUT_PARSER_NOT_FOUND_ERROR = "Output parser not found"

logger = get_logger(__name__)

output_parsers_router = APIRouter()

# ==================== OUTPUT PARSER MANAGEMENT ====================

@output_parsers_router.get("/", 
                           summary="List output parsers",
                           tags=["Output Parsers"],
                           response_model=List[OutputParserListItemSchema])
async def list_output_parsers(
    app_id: int, 
    current_user: dict = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("viewer")),
    db: Session = Depends(get_db)
):
    """
    List all output parsers (data structures) for a specific app.
    """
    try:
        service = OutputParserService()
        return service.list_output_parsers(db, app_id)
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving output parsers: {str(e)}"
        )


# ==================== STATIC ROUTES (without {{parser_id}} parameter) ====================


@output_parsers_router.post(
    "/import",
    summary="Import Output Parser",
    tags=["Output Parsers", "Export/Import"],
    response_model=ImportResponseSchema,
    status_code=status.HTTP_201_CREATED
)
async def import_output_parser(
    app_id: int,
    file: UploadFile = File(...),
    conflict_mode: ConflictMode = Query(ConflictMode.FAIL),
    new_name: Optional[str] = Query(None),
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("administrator")),
    db: Session = Depends(get_db)
):
    """Import Output Parser from JSON file."""
    try:
        # Parse file
        content = await file.read()
        file_data = json.loads(content)
        export_data = OutputParserExportFileSchema(**file_data)
        
        # Import
        import_service = OutputParserImportService(db)
        summary = import_service.import_output_parser(
            export_data,
            app_id,
            conflict_mode,
            new_name
        )
        
        return ImportResponseSchema(
            success=True,
            message=f"Output Parser '{summary.component_name}' imported successfully",
            summary=summary
        )
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON: {str(e)}")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid JSON file")
    except ValueError as e:
        logger.warning(f"Import failed: {str(e)}")
        if "already exists" in str(e):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
        else:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid data: {str(e)}")
    except Exception as e:
        logger.error(f"Import error: {str(e)}", exc_info=True)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Import failed")


# ==================== DYNAMIC ROUTES (with {{parser_id}} parameter) ====================


@output_parsers_router.get("/{parser_id}",
                           summary="Get output parser details",
                           tags=["Output Parsers"],
                           response_model=OutputParserDetailSchema)
async def get_output_parser(
    app_id: int, 
    parser_id: int, 
    current_user: dict = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("viewer")),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific output parser including its fields.
    """  
    try:
        service = OutputParserService()
        result = service.get_output_parser_detail(db, app_id, parser_id)
        
        if result is None and parser_id != 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=OUTPUT_PARSER_NOT_FOUND_ERROR
            )
        
        return result
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving output parser: {str(e)}"
        )


@output_parsers_router.post("/{parser_id}",
                            summary="Create or update output parser",
                            tags=["Output Parsers"],
                            response_model=OutputParserDetailSchema)
async def create_or_update_output_parser(
    app_id: int,
    parser_id: int,
    parser_data: CreateUpdateOutputParserSchema,
    current_user: dict = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("administrator")),
    db: Session = Depends(get_db)
):
    """
    Create a new output parser or update an existing one.
    """
    try:
        service = OutputParserService()
        parser = service.create_or_update_output_parser(db, app_id, parser_id, parser_data)
        
        if parser is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=OUTPUT_PARSER_NOT_FOUND_ERROR
            )
        
        # Return updated parser (reuse the GET logic)
        return await get_output_parser(app_id, parser.parser_id, current_user, role, db)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating/updating output parser: {str(e)}"
        )


@output_parsers_router.delete("/{parser_id}",
                              summary="Delete output parser",
                              tags=["Output Parsers"])
async def delete_output_parser(
    app_id: int, 
    parser_id: int, 
    current_user: dict = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("administrator")),
    db: Session = Depends(get_db)
):
    """
    Delete an output parser.
    """
    try:
        service = OutputParserService()
        success = service.delete_output_parser(db, app_id, parser_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=OUTPUT_PARSER_NOT_FOUND_ERROR
            )
        
        return {"message": "Output parser deleted successfully"}
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting output parser: {str(e)}"
        )


# ==================== EXPORT/IMPORT ENDPOINTS ====================


@output_parsers_router.post(
    "/{parser_id}/export",
    summary="Export Output Parser",
    tags=["Output Parsers", "Export/Import"],
    status_code=status.HTTP_200_OK
)
async def export_output_parser(
    app_id: int,
    parser_id: int,
    auth_context: AuthContext = Depends(get_current_user_oauth),
    role: AppRole = Depends(require_min_role("viewer")),
    db: Session = Depends(get_db)
):
    """Export Output Parser configuration to JSON file."""
    try:
        export_service = OutputParserExportService(db)
        export_data = export_service.export_output_parser(
            parser_id,
            app_id,
            getattr(auth_context, 'user_id', None)
        )
        
        filename = f"{export_data.output_parser.name.replace(' ', '_')}_output_parser.json"
        
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