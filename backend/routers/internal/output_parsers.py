from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List, Optional

# Import schemas and auth
from .schemas import *
# Switch to Google OAuth auth instead of temp token auth
from routers.auth import verify_jwt_token

output_parsers_router = APIRouter()

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

# ==================== OUTPUT PARSER MANAGEMENT ====================

@output_parsers_router.get("/", 
                           summary="List output parsers",
                           tags=["Output Parsers"],
                           response_model=List[OutputParserListItemSchema])
async def list_output_parsers(app_id: int, current_user: dict = Depends(get_current_user_oauth)):
    """
    List all output parsers (data structures) for a specific app.
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
                field_count = len(parser.fields) if parser.fields else 0
                result.append(OutputParserListItemSchema(
                    parser_id=parser.parser_id,
                    name=parser.name,
                    description=parser.description,
                    field_count=field_count,
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
async def get_output_parser(app_id: int, parser_id: int, current_user: dict = Depends(get_current_user_oauth)):
    """
    Get detailed information about a specific output parser including its fields.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        from db.session import SessionLocal
        from models.output_parser import OutputParser
        
        session = SessionLocal()
        try:
            # Get available parsers for references (excluding current parser to prevent self-reference)
            available_parsers_query = session.query(OutputParser).filter(
                OutputParser.app_id == app_id
            )
            if parser_id != 0:
                available_parsers_query = available_parsers_query.filter(
                    OutputParser.parser_id != parser_id
                )
            
            available_parsers = [
                {"value": p.parser_id, "name": p.name}
                for p in available_parsers_query.all()
            ]
            
            if parser_id == 0:
                # New output parser
                return OutputParserDetailSchema(
                    parser_id=0,
                    name="",
                    description="",
                    fields=[],
                    created_at=None,
                    available_parsers=available_parsers
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
            
            # Convert JSON fields to schema format
            fields = []
            if parser.fields:
                for field_data in parser.fields:
                    fields.append(OutputParserFieldSchema(
                        name=field_data.get('name', ''),
                        type=field_data.get('type', 'str'),
                        description=field_data.get('description', ''),
                        parser_id=field_data.get('parser_id'),
                        list_item_type=field_data.get('list_item_type'),
                        list_item_parser_id=field_data.get('list_item_parser_id')
                    ))
            
            return OutputParserDetailSchema(
                parser_id=parser.parser_id,
                name=parser.name,
                description=parser.description,
                fields=fields,
                created_at=parser.create_date,
                available_parsers=available_parsers
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
    current_user: dict = Depends(get_current_user_oauth)
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
            parser.description = parser_data.description
            
            # Convert fields to JSON format
            fields_json = []
            for field_data in parser_data.fields:
                if not field_data.name:  # Skip empty field names
                    continue
                    
                field_dict = {
                    'name': field_data.name,
                    'type': field_data.type,
                    'description': field_data.description
                }
                
                if field_data.type == 'parser' and field_data.parser_id:
                    field_dict['parser_id'] = field_data.parser_id
                elif field_data.type == 'list':
                    if field_data.list_item_type:
                        field_dict['list_item_type'] = field_data.list_item_type
                    if field_data.list_item_type == 'parser' and field_data.list_item_parser_id:
                        field_dict['list_item_parser_id'] = field_data.list_item_parser_id
                
                fields_json.append(field_dict)
            
            parser.fields = fields_json
            
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
async def delete_output_parser(app_id: int, parser_id: int, current_user: dict = Depends(get_current_user_oauth)):
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