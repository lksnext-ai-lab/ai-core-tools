from fastapi import APIRouter, HTTPException, status, Request, Depends, BackgroundTasks
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session
from typing import List

# Import services
from services.domain_service import DomainService
from services.url_service import UrlService
from tools.scrapTools import scrape_and_index_url, reindex_domain_urls

# Import schemas and auth
from schemas.domain_url_schemas import (
    DomainListItemSchema,
    DomainDetailSchema,
    CreateUpdateDomainSchema,
    URLListItemSchema,
    CreateURLSchema,
    URLActionResponseSchema
)
from routers.internal.auth_utils import get_current_user_oauth

# Import database dependencies
from db.database import get_db

# Import logger
from utils.logger import get_logger

logger = get_logger(__name__)

domains_router = APIRouter()


# ==================== BACKGROUND TASKS ====================

def background_scrape_and_index(domain_id: int, url_path: str, url_id: int):
    """
    Background task to scrape and index a single URL
    """
    from db.database import SessionLocal
    db = SessionLocal()
    try:
        domain = DomainService.get_domain(domain_id, db)
        if domain:
            scrape_and_index_url(domain, url_path, url_id, db)
            logger.info(f"Background indexing completed for URL {url_id}")
        else:
            logger.error(f"Domain {domain_id} not found for background indexing")
    except Exception as e:
        logger.error(f"Background indexing failed for URL {url_id}: {str(e)}")
    finally:
        db.close()


def background_reindex_domain(domain_id: int):
    """
    Background task to reindex all URLs in a domain
    """
    from db.database import SessionLocal
    db = SessionLocal()
    try:
        domain = DomainService.get_domain(domain_id, db)
        if domain:
            results = reindex_domain_urls(domain, db)
            logger.info(f"Background domain reindexing completed for domain {domain_id}: {results}")
        else:
            logger.error(f"Domain {domain_id} not found for background reindexing")
    except Exception as e:
        logger.error(f"Background domain reindexing failed for domain {domain_id}: {str(e)}")
    finally:
        db.close()



# ==================== DOMAIN MANAGEMENT ====================

@domains_router.get("/", 
                    summary="List domains",
                    tags=["Domains"],
                    response_model=List[DomainListItemSchema])
async def list_domains(app_id: int, request: Request, db: Session = Depends(get_db), auth_context: AuthContext = Depends(get_current_user_oauth)):
    """
    List all domains for a specific app.
    """
    
    # TODO: Add app access validation
    
    try:
        domains_with_counts = DomainService.get_domains_with_url_counts(app_id, db)
        
        result = []
        for domain, url_count in domains_with_counts:
            result.append(DomainListItemSchema(
                domain_id=domain.domain_id,
                name=domain.name,
                description=domain.description or "",
                base_url=domain.base_url,
                created_at=domain.create_date,
                url_count=url_count,
                silo_id=domain.silo_id
            ))
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving domains: {str(e)}"
        )


@domains_router.get("/{domain_id}",
                    summary="Get domain details",
                    tags=["Domains"],
                    response_model=DomainDetailSchema)
async def get_domain(app_id: int, domain_id: int, request: Request, db: Session = Depends(get_db), auth_context: AuthContext = Depends(get_current_user_oauth)):
    """
    Get detailed information about a specific domain.
    """
    
    # TODO: Add app access validation
    
    if domain_id == 0:
        # New domain - return empty template with embedding services
        embedding_services = DomainService.get_embedding_services_for_app(app_id, db)
        
        return DomainDetailSchema(
            domain_id=0,
            name="",
            description="",
            base_url="",
            content_tag="body",
            content_class="",
            content_id="",
            created_at=None,
            silo_id=None,
            url_count=0,
            embedding_services=embedding_services,
            embedding_service_id=None
        )
    
    # Existing domain
    domain_detail = DomainService.get_domain_detail(domain_id, app_id, db)
    if not domain_detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Domain not found"
        )
    
    return domain_detail


@domains_router.post("/{domain_id}",
                     summary="Create or update domain",
                     tags=["Domains"],
                     response_model=DomainDetailSchema)
async def create_or_update_domain(
    app_id: int,
    domain_id: int,
    domain_data: CreateUpdateDomainSchema,
    request: Request,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_current_user_oauth)
):
    """
    Create a new domain or update an existing one.
    """
    
    # TODO: Add app access validation
    
    try:
        # Prepare domain data for service
        data = {
            'domain_id': domain_id if domain_id != 0 else None,
            'name': domain_data.name,
            'description': domain_data.description,
            'base_url': domain_data.base_url,
            'content_tag': domain_data.content_tag,
            'content_class': domain_data.content_class,
            'content_id': domain_data.content_id,
            'app_id': app_id
        }
        
        # Create or update domain using service
        created_domain_id = DomainService.create_or_update_domain(data, domain_data.embedding_service_id, db)
        
        # Return updated domain (reuse the GET logic)
        return await get_domain(app_id, created_domain_id, request, db)
        
    except Exception as e:
        logger.error(f"Error creating/updating domain: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating/updating domain: {str(e)}"
        )


@domains_router.delete("/{domain_id}",
                       summary="Delete domain",
                       tags=["Domains"])
async def delete_domain(app_id: int, domain_id: int, request: Request, db: Session = Depends(get_db), auth_context: AuthContext = Depends(get_current_user_oauth)):
    """
    Delete a domain and its associated silo and URLs.
    """
    
    # TODO: Add app access validation
    
    try:
        domain = DomainService.get_domain(domain_id, db)
        if not domain:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Domain not found"
            )
        
        # Delete domain using service (this should also handle silo and URL cleanup)
        DomainService.delete_domain(domain_id, db)
        
        return {"message": "Domain deleted successfully"}
        
    except Exception as e:
        logger.error(f"Error deleting domain: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting domain: {str(e)}"
        )


# ==================== URL MANAGEMENT ====================

@domains_router.get("/{domain_id}/urls",
                    summary="List URLs for domain",
                    tags=["Domains", "URLs"],
                    response_model=List[URLListItemSchema])
async def list_domain_urls(
    app_id: int,
    domain_id: int,
    request: Request,
    db: Session = Depends(get_db),
    page: int = 1,
    per_page: int = 20,
    auth_context: AuthContext = Depends(get_current_user_oauth)
):
    """
    List URLs for a specific domain with pagination.
    """
    
    # TODO: Add app access validation
    
    try:
        domain, urls, pagination = DomainService.get_domain_with_urls(domain_id, db, page, per_page)
        
        result = []
        for url in urls:
            result.append(URLListItemSchema(
                url_id=url.url_id,
                url=url.url,
                created_at=url.created_at,
                updated_at=url.updated_at,
                status=url.status
            ))
        
        return result
        
    except Exception as e:
        logger.error(f"Error retrieving URLs for domain {domain_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving URLs: {str(e)}"
        )


@domains_router.post("/{domain_id}/urls",
                     summary="Add URL to domain",
                     tags=["Domains", "URLs"],
                     response_model=URLActionResponseSchema)
async def add_url_to_domain(
    app_id: int,
    domain_id: int,
    url_data: CreateURLSchema,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_current_user_oauth)
):
    """
    Add a new URL to a domain and scrape its content.
    """
    
    # TODO: Add app access validation
    
    try:
        # Get domain info
        domain = DomainService.get_domain(domain_id, db)
        if not domain:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Domain not found"
            )
        
        # Clean URL (remove query parameters)
        clean_url = url_data.url.split('?')[0]
        
        # Create URL using service
        url_id = UrlService.create_url(clean_url, domain_id, db)
        
        # Add background task for scraping and indexing
        background_tasks.add_task(background_scrape_and_index, domain_id, clean_url, url_id)
        
        message = "URL added and indexing started in background"
        
        return URLActionResponseSchema(
            success=True,
            message=message,
            url_id=url_id
        )
        
    except Exception as e:
        logger.error(f"Error adding URL to domain {domain_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error adding URL: {str(e)}"
        )


@domains_router.delete("/{domain_id}/urls/{url_id}",
                       summary="Delete URL from domain",
                       tags=["Domains", "URLs"],
                       response_model=URLActionResponseSchema)
async def delete_url_from_domain(
    app_id: int,
    domain_id: int,
    url_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_current_user_oauth)
):
    """
    Delete a URL from a domain and remove its indexed content.
    """
    
    # TODO: Add app access validation
    
    try:
        # Delete URL using service (this should also remove indexed content)
        UrlService.delete_url(url_id, domain_id, db)
        
        return URLActionResponseSchema(
            success=True,
            message="URL deleted successfully"
        )
        
    except Exception as e:
        logger.error(f"Error deleting URL {url_id} from domain {domain_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting URL: {str(e)}"
        )


@domains_router.post("/{domain_id}/urls/{url_id}/reindex",
                     summary="Re-index URL content",
                     tags=["Domains", "URLs"],
                     response_model=URLActionResponseSchema)
async def reindex_url(
    app_id: int,
    domain_id: int,
    url_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_current_user_oauth)
):
    """
    Re-index content for a specific URL.
    """
    
    # TODO: Add app access validation
    
    try:
        # Get domain and URL info
        domain = DomainService.get_domain(domain_id, db)
        if not domain:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Domain not found"
            )
        
        url = UrlService.get_url(url_id, db)
        if not url or url.domain_id != domain_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="URL not found"
            )
        
        # Remove old content first
        from services.silo_service import SiloService
        full_url = domain.base_url + url.url
        SiloService.delete_url(domain.silo_id, full_url, db)
        
        # Add background task for re-scraping and indexing
        background_tasks.add_task(background_scrape_and_index, domain_id, url.url, url_id)
        
        message = "URL re-indexing started in background"
        
        return URLActionResponseSchema(
            success=True,
            message=message,
            url_id=url_id
        )
        
    except Exception as e:
        logger.error(f"Error re-indexing URL {url_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error re-indexing URL: {str(e)}"
        )


@domains_router.post("/{domain_id}/urls/{url_id}/unindex",
                     summary="Unindex URL content",
                     tags=["Domains", "URLs"],
                     response_model=URLActionResponseSchema)
async def unindex_url(
    app_id: int,
    domain_id: int,
    url_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_current_user_oauth)
):
    """
    Remove URL content from index and mark as unindexed.
    """
    
    # TODO: Add app access validation
    
    try:
        # Get domain and URL info
        domain = DomainService.get_domain(domain_id, db)
        if not domain:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Domain not found"
            )
        
        url = UrlService.get_url(url_id, db)
        if not url or url.domain_id != domain_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="URL not found"
            )
        
        # Unindex the URL
        UrlService.unindex_url(url_id, db, domain_id)
        
        return URLActionResponseSchema(
            success=True,
            message="URL unindexed successfully",
            url_id=url_id
        )
        
    except Exception as e:
        logger.error(f"Error unindexing URL {url_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error unindexing URL: {str(e)}"
        )


@domains_router.post("/{domain_id}/urls/{url_id}/reject",
                     summary="Reject URL",
                     tags=["Domains", "URLs"],
                     response_model=URLActionResponseSchema)
async def reject_url(
    app_id: int,
    domain_id: int,
    url_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_current_user_oauth)
):
    """
    Mark URL as rejected (content not suitable for indexing).
    """
    current_user = await get_current_user_oauth(request, db)
    user_id = auth_context.identity.id
    
    # TODO: Add app access validation
    
    try:
        # Get domain and URL info
        domain = DomainService.get_domain(domain_id, db)
        if not domain:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Domain not found"
            )
        
        url = UrlService.get_url(url_id, db)
        if not url or url.domain_id != domain_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="URL not found"
            )
        
        # Reject the URL
        UrlService.reject_url(url_id, db, domain_id)
        
        return URLActionResponseSchema(
            success=True,
            message="URL rejected successfully",
            url_id=url_id
        )
        
    except Exception as e:
        logger.error(f"Error rejecting URL {url_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error rejecting URL: {str(e)}"
        )


@domains_router.post("/{domain_id}/reindex",
                     summary="Re-index all domain URLs",
                     tags=["Domains", "URLs"])
async def reindex_domain(
    app_id: int,
    domain_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_current_user_oauth)
):
    """
    Re-index content for all URLs in a domain.
    """
    
    # TODO: Add app access validation
    
    try:
        # Get domain info
        domain = DomainService.get_domain(domain_id, db)
        if not domain:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Domain not found"
            )
        
        # Add background task for re-indexing all URLs
        background_tasks.add_task(background_reindex_domain, domain_id)
        
        return {
            "message": "Domain re-indexing started in background",
            "status": "started"
        }
        
    except Exception as e:
        logger.error(f"Error re-indexing domain {domain_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error re-indexing domain: {str(e)}"
        )


@domains_router.get("/{domain_id}/urls/{url_id}/content",
                    summary="Get URL content preview",
                    tags=["Domains", "URLs"])
async def get_url_content(
    app_id: int,
    domain_id: int,
    url_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth_context: AuthContext = Depends(get_current_user_oauth)
):
    """
    Get the scraped content for a specific URL.
    """
    
    # TODO: Add app access validation
    
    try:
        # Get domain and URL info
        domain = DomainService.get_domain(domain_id, db)
        if not domain:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Domain not found"
            )
        
        # Get URL info
        url = UrlService.get_url(url_id, db)
        if not url or url.domain_id != domain_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="URL not found"
            )
        
        # Get content from silo
        if not domain.silo_id:
            return {
                "url": domain.base_url + url.url,
                "content": None,
                "message": "No silo associated with this domain"
            }
        
        # Query the silo for content related to this URL
        from services.silo_service import SiloService
        full_url = domain.base_url + url.url
        
        # Search for content with this URL in metadata
        results = SiloService.search_in_silo(
            silo_id=domain.silo_id,
            query=full_url,  # Search for the URL itself
            limit=10,
            db=db
        )
        
        # Extract content from results
        content_pieces = []
        for result in results:
            if hasattr(result, 'page_content'):
                content_pieces.append(result.page_content)
            elif hasattr(result, 'content'):
                content_pieces.append(result.content)
        
        content = "\n\n".join(content_pieces) if content_pieces else None
        
        return {
            "url": full_url,
            "content": content,
            "message": "Content retrieved successfully" if content else "No content found for this URL"
        }
        
    except Exception as e:
        logger.error(f"Error retrieving URL content: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving URL content: {str(e)}"
        ) 