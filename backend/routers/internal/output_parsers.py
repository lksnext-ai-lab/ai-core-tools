from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional

# Import schemas and auth
from .schemas import *
from .auth import get_current_user

output_parsers_router = APIRouter()

# ==================== OUTPUT PARSER MANAGEMENT ====================

@output_parsers_router.get("/", 
                           summary="List output parsers",
                           tags=["Output Parsers"],
                           response_model=List[OutputParserListItemSchema])
async def list_output_parsers(app_id: int, current_user: dict = Depends(get_current_user)):
    """
    List all output parsers for a specific app.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        from db.session import SessionLocal
        from models.output_parser import OutputParser
        
        session = SessionLocal()
        try:
            parsers = session.query(OutputParser).filter(OutputParser.app_id == app_id).all()
            
            result = []
            for parser in parsers:
                result.append(OutputParserListItemSchema(
                    parser_id=parser.parser_id,
                    name=parser.name,
                    type=getattr(parser, 'type', 'unknown'),
                    created_at=parser.create_date
                ))
            
            return result
            
        finally:
            session.close()
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving output parsers: {str(e)}"
        )


@output_parsers_router.get("/{parser_id}",
                           summary="Get output parser details",
                           tags=["Output Parsers"],
                           response_model=OutputParserDetailSchema)
async def get_output_parser(app_id: int, parser_id: int, current_user: dict = Depends(get_current_user)):
    """
    Get detailed information about a specific output parser.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        from db.session import SessionLocal
        from models.output_parser import OutputParser
        
        session = SessionLocal()
        try:
            if parser_id == 0:
                # New output parser
                return OutputParserDetailSchema(
                    parser_id=0,
                    name="",
                    type="json",
                    instructions="",
                    created_at=None
                )
            
            # Existing output parser
            parser = session.query(OutputParser).filter(
                OutputParser.parser_id == parser_id,
                OutputParser.app_id == app_id
            ).first()
            
            if not parser:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Output parser not found"
                )
            
            return OutputParserDetailSchema(
                parser_id=parser.parser_id,
                name=parser.name,
                type=getattr(parser, 'type', 'unknown'),
                instructions=getattr(parser, 'instructions', ''),
                created_at=parser.create_date
            )
            
        finally:
            session.close()
            
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
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new output parser or update an existing one.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        from db.session import SessionLocal
        from models.output_parser import OutputParser
        from datetime import datetime
        
        session = SessionLocal()
        try:
            if parser_id == 0:
                # Create new output parser
                parser = OutputParser()
                parser.app_id = app_id
                parser.create_date = datetime.now()
            else:
                # Update existing output parser
                parser = session.query(OutputParser).filter(
                    OutputParser.parser_id == parser_id,
                    OutputParser.app_id == app_id
                ).first()
                
                if not parser:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Output parser not found"
                    )
            
            # Update parser data
            parser.name = parser_data.name
            if hasattr(parser, 'type'):
                parser.type = parser_data.type
            if hasattr(parser, 'instructions'):
                parser.instructions = parser_data.instructions
            
            session.add(parser)
            session.commit()
            session.refresh(parser)
            
            # Return updated parser (reuse the GET logic)
            return await get_output_parser(app_id, parser.parser_id, current_user)
            
        finally:
            session.close()
            
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
async def delete_output_parser(app_id: int, parser_id: int, current_user: dict = Depends(get_current_user)):
    """
    Delete an output parser.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        from db.session import SessionLocal
        from models.output_parser import OutputParser
        
        session = SessionLocal()
        try:
            parser = session.query(OutputParser).filter(
                OutputParser.parser_id == parser_id,
                OutputParser.app_id == app_id
            ).first()
            
            if not parser:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Output parser not found"
                )
            
            session.delete(parser)
            session.commit()
            
            return {"message": "Output parser deleted successfully"}
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting output parser: {str(e)}"
        ) 