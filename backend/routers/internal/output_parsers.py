from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from sqlalchemy.orm import Session

from schemas.output_parser_schemas import (
    OutputParserListItemSchema,
    OutputParserDetailSchema,
    CreateUpdateOutputParserSchema
)

from .auth_utils import get_current_user_oauth

# Import database dependency
from db.database import get_db

# Import service
from services.output_parser_service import OutputParserService

# Import logger
from utils.logger import get_logger

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
    db: Session = Depends(get_db)
):
    """
    List all output parsers (data structures) for a specific app.
    """
    # TODO: Add app access validation
    
    try:
        service = OutputParserService()
        return service.list_output_parsers(db, app_id)
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving output parsers: {str(e)}"
        )


@output_parsers_router.get("/{parser_id}",
                           summary="Get output parser details",
                           tags=["Output Parsers"],
                           response_model=OutputParserDetailSchema)
async def get_output_parser(
    app_id: int, 
    parser_id: int, 
    current_user: dict = Depends(get_current_user_oauth),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific output parser including its fields.
    """
    # TODO: Add app access validation
    
    try:
        service = OutputParserService()
        result = service.get_output_parser_detail(db, app_id, parser_id)
        
        if result is None and parser_id != 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Output parser not found"
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
    db: Session = Depends(get_db)
):
    """
    Create a new output parser or update an existing one.
    """
    # TODO: Add app access validation
    
    try:
        service = OutputParserService()
        parser = service.create_or_update_output_parser(db, app_id, parser_id, parser_data)
        
        if parser is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Output parser not found"
            )
        
        # Return updated parser (reuse the GET logic)
        return await get_output_parser(app_id, parser.parser_id, current_user, db)
            
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
    db: Session = Depends(get_db)
):
    """
    Delete an output parser.
    """
    # TODO: Add app access validation
    
    try:
        service = OutputParserService()
        success = service.delete_output_parser(db, app_id, parser_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Output parser not found"
            )
        
        return {"message": "Output parser deleted successfully"}
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting output parser: {str(e)}"
        ) 