from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List, Optional

# Import services
from services.silo_service import SiloService

# Import schemas and auth
from .schemas import *
# Switch to Google OAuth auth instead of temp token auth
from routers.auth import verify_jwt_token

# Import logger
from utils.logger import get_logger

logger = get_logger(__name__)

silos_router = APIRouter()

# ==================== AUTHENTICATION ====================

async def get_current_user_oauth(request: Request):
    """
    Get current authenticated user using Google OAuth JWT tokens.
    Compatible with the frontend auth system.
    """
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        logger.info(f"Auth header received: {auth_header[:20] + '...' if auth_header and len(auth_header) > 20 else auth_header}")
        
        if not auth_header or not auth_header.startswith('Bearer '):
            logger.error("No Authorization header or invalid format")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required. Please provide Authorization header with Bearer token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        token = auth_header.split(' ')[1]
        logger.info(f"Token extracted: {token[:20] + '...' if len(token) > 20 else token}")
        
        # Verify token using Google OAuth system
        payload = verify_jwt_token(token)
        if not payload:
            logger.error("Token verification failed - invalid or expired token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        logger.info(f"Token verified successfully for user: {payload.get('user_id')}")
        return payload
        
    except HTTPException:
        logger.error("HTTPException in authentication, re-raising")
        raise
    except Exception as e:
        logger.error(f"Error in authentication: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )

# ==================== SILO MANAGEMENT ====================

@silos_router.get("/", 
                  summary="List silos",
                  tags=["Silos"],
                  response_model=List[SiloListItemSchema])
async def list_silos(app_id: int, current_user: dict = Depends(get_current_user_oauth)):
    """
    List all silos for a specific app.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        # Get silos using the service
        silos = SiloService.get_silos_by_app_id(app_id)
        
        result = []
        for silo in silos:
            # Get document count
            docs_count = SiloService.count_docs_in_silo(silo.silo_id)
            
            result.append(SiloListItemSchema(
                silo_id=silo.silo_id,
                name=silo.name,
                type=silo.silo_type if silo.silo_type else None,
                created_at=silo.create_date,
                docs_count=docs_count
            ))
        
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving silos: {str(e)}"
        )


@silos_router.get("/{silo_id}",
                  summary="Get silo details",
                  tags=["Silos"],
                  response_model=SiloDetailSchema)
async def get_silo(app_id: int, silo_id: int, current_user: dict = Depends(get_current_user_oauth)):
    """
    Get detailed information about a specific silo including form data for editing.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        from db.session import SessionLocal
        from models.silo import Silo
        from models.output_parser import OutputParser
        from models.embedding_service import EmbeddingService
        
        session = SessionLocal()
        try:
            if silo_id == 0:
                # New silo
                return SiloDetailSchema(
                    silo_id=0,
                    name="",
                    type=None,
                    created_at=None,
                    docs_count=0,
                    # Form data
                    output_parsers=[],
                    embedding_services=[]
                )
            
            # Existing silo
            silo = SiloService.get_silo(silo_id)
            if not silo:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Silo not found"
                )
            
            # Get document count
            docs_count = SiloService.count_docs_in_silo(silo_id)
            
            # Get form data
            # Output parsers
            parsers_query = session.query(OutputParser).filter(OutputParser.app_id == app_id).all()
            output_parsers = [{"parser_id": p.parser_id, "name": p.name} for p in parsers_query]
            
            # Embedding services
            embedding_services_query = session.query(EmbeddingService).filter(EmbeddingService.app_id == app_id).all()
            embedding_services = [{"service_id": s.service_id, "name": s.name} for s in embedding_services_query]
            
            # Get metadata definition fields if silo has one
            metadata_fields = None
            if silo.metadata_definition_id:
                metadata_parser = session.query(OutputParser).filter(OutputParser.parser_id == silo.metadata_definition_id).first()
                if metadata_parser and metadata_parser.fields:
                    metadata_fields = [
                        {
                            "name": field.get("name", ""),
                            "type": field.get("type", "str"),
                            "description": field.get("description", "")
                        }
                        for field in metadata_parser.fields
                    ]
            
            return SiloDetailSchema(
                silo_id=silo.silo_id,
                name=silo.name,
                type=silo.silo_type if silo.silo_type else None,
                created_at=silo.create_date,
                docs_count=docs_count,
                # Current values for editing
                metadata_definition_id=silo.metadata_definition_id,
                embedding_service_id=silo.embedding_service_id,
                # Form data
                output_parsers=output_parsers,
                embedding_services=embedding_services,
                # Metadata definition fields for playground
                metadata_fields=metadata_fields
            )
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving silo: {str(e)}"
        )


@silos_router.post("/{silo_id}",
                   summary="Create or update silo",
                   tags=["Silos"],
                   response_model=SiloDetailSchema)
async def create_or_update_silo(
    app_id: int,
    silo_id: int,
    silo_data: CreateUpdateSiloSchema,
    current_user: dict = Depends(get_current_user_oauth)
):
    """
    Create a new silo or update an existing one.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        # Prepare form data for the service
        form_data = {
            'silo_id': silo_id,
            'name': silo_data.name,
            'app_id': app_id,
            'type': silo_data.type,
            'output_parser_id': silo_data.output_parser_id,
            'embedding_service_id': silo_data.embedding_service_id
        }
        
        # Create or update using the service
        silo = SiloService.create_or_update_silo(form_data)
        
        # Return updated silo (reuse the GET logic)
        return await get_silo(app_id, silo.silo_id, current_user)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating/updating silo: {str(e)}"
        )


@silos_router.delete("/{silo_id}",
                     summary="Delete silo",
                     tags=["Silos"])
async def delete_silo(app_id: int, silo_id: int, current_user: dict = Depends(get_current_user_oauth)):
    """
    Delete a silo and all its documents.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        from db.session import SessionLocal
        from models.silo import Silo
        
        session = SessionLocal()
        try:
            silo = session.query(Silo).filter(Silo.silo_id == silo_id).first()
            if not silo:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Silo not found"
                )
            
            # Delete silo (should cascade delete documents)
            session.delete(silo)
            session.commit()
            
            return {"message": "Silo deleted successfully"}
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting silo: {str(e)}"
        )


# ==================== SILO PLAYGROUND ====================

@silos_router.get("/{silo_id}/playground",
                  summary="Get silo playground",
                  tags=["Silos", "Playground"])
async def silo_playground(app_id: int, silo_id: int, current_user: dict = Depends(get_current_user_oauth)):
    """
    Get silo playground interface for testing document search.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        # Get silo info
        silo = SiloService.get_silo(silo_id)
        if not silo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Silo not found"
            )
        
        docs_count = SiloService.count_docs_in_silo(silo_id)
        
        return {
            "silo_id": silo.silo_id,
            "name": silo.name,
            "docs_count": docs_count,
            "message": "Silo playground - ready for document search testing"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error accessing silo playground: {str(e)}"
        )


@silos_router.post("/{silo_id}/search",
                   summary="Search documents in silo",
                   tags=["Silos", "Playground"])
async def search_silo_documents(
    app_id: int,
    silo_id: int,
    search_query: SiloSearchSchema,
    current_user: dict = Depends(get_current_user_oauth)
):
    """
    Search for documents in a silo using semantic search with optional metadata filtering.
    """
    logger.info(f"Search request received - app_id: {app_id}, silo_id: {silo_id}, user_id: {current_user.get('user_id')}")
    logger.info(f"Search query: {search_query.query}, limit: {search_query.limit}, filter_metadata: {search_query.filter_metadata}")
    
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        logger.info(f"Getting silo {silo_id} for validation")
        # Get silo to validate it exists
        silo = SiloService.get_silo(silo_id)
        if not silo:
            logger.error(f"Silo {silo_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Silo not found"
            )
        
        logger.info(f"Silo {silo_id} found, performing search")
        # Perform the search with metadata filtering
        results = SiloService.find_docs_in_collection(
            silo_id, 
            search_query.query, 
            filter_metadata=search_query.filter_metadata
        )
        
        logger.info(f"Search completed, found {len(results)} results")
        # Convert results to response format
        response_results = []
        for doc in results:
            response_results.append({
                "page_content": doc.page_content,
                "metadata": doc.metadata,
                "score": getattr(doc, 'score', None)  # Include score if available
            })
        
        logger.info(f"Returning {len(response_results)} results to frontend")
        return {
            "query": search_query.query,
            "results": response_results,
            "total_results": len(response_results),
            "filter_metadata": search_query.filter_metadata
        }
        
    except HTTPException:
        logger.error("HTTPException in search_silo_documents, re-raising")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in search_silo_documents: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error searching silo: {str(e)}"
        ) 