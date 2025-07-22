from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional

# Import services
from services.silo_service import SiloService

# Import schemas and auth
from .schemas import *
from .auth import get_current_user

silos_router = APIRouter()

# ==================== SILO MANAGEMENT ====================

@silos_router.get("/", 
                  summary="List silos",
                  tags=["Silos"],
                  response_model=List[SiloListItemSchema])
async def list_silos(app_id: int, current_user: dict = Depends(get_current_user)):
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
                type=silo.type.value if silo.type else None,
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
async def get_silo(app_id: int, silo_id: int, current_user: dict = Depends(get_current_user)):
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
            
            return SiloDetailSchema(
                silo_id=silo.silo_id,
                name=silo.name,
                type=silo.type.value if silo.type else None,
                created_at=silo.create_date,
                docs_count=docs_count,
                # Form data
                output_parsers=output_parsers,
                embedding_services=embedding_services
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
    current_user: dict = Depends(get_current_user)
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
        SiloService.create_or_update_silo(form_data)
        
        # Return updated silo (reuse the GET logic)
        return await get_silo(app_id, silo_id if silo_id != 0 else None, current_user)
        
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
async def delete_silo(app_id: int, silo_id: int, current_user: dict = Depends(get_current_user)):
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
async def silo_playground(app_id: int, silo_id: int, current_user: dict = Depends(get_current_user)):
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
    current_user: dict = Depends(get_current_user)
):
    """
    Search for documents in a silo using semantic search.
    """
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        # TODO: Implement actual search using pgVectorTools or similar
        # For now, return a placeholder response
        
        return {
            "query": search_query.query,
            "results": [],
            "total_results": 0,
            "message": "Document search not yet implemented - placeholder response"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error searching silo: {str(e)}"
        ) 