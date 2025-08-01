from fastapi import APIRouter, HTTPException, status, Request
from typing import List, Optional

# Import services
from services.domain_service import DomainService
from services.url_service import UrlService
from tools.scrapTools import scrape_and_index_url, reindex_domain_urls

# Import schemas and auth
from .schemas import *
from routers.auth import verify_jwt_token

# Import logger
from utils.logger import get_logger

logger = get_logger(__name__)

domains_router = APIRouter()

# ==================== AUTHENTICATION HELPER ====================

async def get_current_user(request: Request):
    """
    Get current authenticated user using Google OAuth JWT tokens.
    
    Args:
        request: FastAPI request object
        
    Returns:
        dict: User information from JWT token
        
    Raises:
        HTTPException: If authentication fails
    """
    # Get token from Authorization header
    auth_header = request.headers.get('Authorization')
    logger.info(f"Auth header received: {auth_header[:20] if auth_header else 'None'}...")
    
    if not auth_header:
        logger.error("No Authorization header found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide Authorization header with Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not auth_header.startswith('Bearer '):
        logger.error(f"Invalid Authorization header format: {auth_header[:50]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Use 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = auth_header.split(' ')[1]
    logger.info(f"Token extracted: {token[:20]}...")
    
    # Verify token using Google OAuth system
    payload = verify_jwt_token(token)
    if not payload:
        logger.error("Token verification failed - invalid or expired token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.info(f"Token verified successfully for user: {payload.get('user_id')}")
    return payload

# ==================== DOMAIN MANAGEMENT ====================

@domains_router.get("/", 
                    summary="List domains",
                    tags=["Domains"],
                    response_model=List[DomainListItemSchema])
async def list_domains(app_id: int, request: Request):
    """
    List all domains for a specific app.
    """
    current_user = await get_current_user(request)
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        domains = DomainService.get_domains_by_app_id(app_id)
        
        result = []
        for domain in domains:
            # Count URLs for this domain
            from db.session import SessionLocal
            from models.url import Url
            
            session = SessionLocal()
            try:
                url_count = session.query(Url).filter(Url.domain_id == domain.domain_id).count()
            finally:
                session.close()
            
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
async def get_domain(app_id: int, domain_id: int, request: Request):
    """
    Get detailed information about a specific domain.
    """
    current_user = await get_current_user(request)
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    if domain_id == 0:
        # New domain - return empty template with embedding services
        from db.session import SessionLocal
        from models.embedding_service import EmbeddingService
        
        session = SessionLocal()
        try:
            embedding_services_query = session.query(EmbeddingService).filter(EmbeddingService.app_id == app_id).all()
            embedding_services = [{"service_id": s.service_id, "name": s.name} for s in embedding_services_query]
        finally:
            session.close()
        
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
    domain = DomainService.get_domain(domain_id)
    if not domain:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Domain not found"
        )
    
    # Count URLs for this domain
    from db.session import SessionLocal
    from models.url import Url
    from models.embedding_service import EmbeddingService
    
    session = SessionLocal()
    try:
        url_count = session.query(Url).filter(Url.domain_id == domain.domain_id).count()
        
        # Get embedding services for form data
        embedding_services_query = session.query(EmbeddingService).filter(EmbeddingService.app_id == app_id).all()
        embedding_services = [{"service_id": s.service_id, "name": s.name} for s in embedding_services_query]
        
        # Get current embedding service ID from domain's silo (avoid detached instance)
        embedding_service_id = None
        if domain.silo_id:
            from models.silo import Silo
            silo = session.query(Silo).filter(Silo.silo_id == domain.silo_id).first()
            if silo and silo.embedding_service_id:
                embedding_service_id = silo.embedding_service_id
            
    finally:
        session.close()
    
    return DomainDetailSchema(
        domain_id=domain.domain_id,
        name=domain.name,
        description=domain.description or "",
        base_url=domain.base_url,
        content_tag=domain.content_tag or "body",
        content_class=domain.content_class or "",
        content_id=domain.content_id or "",
        created_at=domain.create_date,
        silo_id=domain.silo_id,
        url_count=url_count,
        embedding_services=embedding_services,
        embedding_service_id=embedding_service_id
    )


@domains_router.post("/{domain_id}",
                     summary="Create or update domain",
                     tags=["Domains"],
                     response_model=DomainDetailSchema)
async def create_or_update_domain(
    app_id: int,
    domain_id: int,
    domain_data: CreateUpdateDomainSchema,
    request: Request
):
    """
    Create a new domain or update an existing one.
    """
    current_user = await get_current_user(request)
    user_id = current_user["user_id"]
    
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
        created_domain_id = DomainService.create_or_update_domain(data, domain_data.embedding_service_id)
        
        # Return updated domain (reuse the GET logic)
        return await get_domain(app_id, created_domain_id, request)
        
    except Exception as e:
        logger.error(f"Error creating/updating domain: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating/updating domain: {str(e)}"
        )


@domains_router.delete("/{domain_id}",
                       summary="Delete domain",
                       tags=["Domains"])
async def delete_domain(app_id: int, domain_id: int, request: Request):
    """
    Delete a domain and its associated silo and URLs.
    """
    current_user = await get_current_user(request)
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        domain = DomainService.get_domain(domain_id)
        if not domain:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Domain not found"
            )
        
        # Delete domain using service (this should also handle silo and URL cleanup)
        DomainService.delete_domain(domain_id)
        
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
    page: int = 1,
    per_page: int = 20
):
    """
    List URLs for a specific domain with pagination.
    """
    current_user = await get_current_user(request)
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        domain, urls, pagination = DomainService.get_domain_with_urls(domain_id, page, per_page)
        
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
    request: Request
):
    """
    Add a new URL to a domain and scrape its content.
    """
    current_user = await get_current_user(request)
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        # Get domain info
        domain = DomainService.get_domain(domain_id)
        if not domain:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Domain not found"
            )
        
        # Clean URL (remove query parameters)
        clean_url = url_data.url.split('?')[0]
        
        # Create URL using service
        url_id = UrlService.create_url(clean_url, domain_id)
        
        # Scrape content and index it
        try:
            success = scrape_and_index_url(domain, clean_url, url_id)
            if success:
                message = "URL added and content indexed successfully"
            else:
                message = "URL added but content scraping failed"
                logger.warning(f"Failed to scrape content for URL: {clean_url}")
        except Exception as e:
            logger.error(f"Error during scraping for URL {clean_url}: {str(e)}")
            message = "URL added but content scraping failed"
        
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
    request: Request
):
    """
    Delete a URL from a domain and remove its indexed content.
    """
    current_user = await get_current_user(request)
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        # Delete URL using service (this should also remove indexed content)
        UrlService.delete_url(url_id, domain_id)
        
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
    request: Request
):
    """
    Re-index content for a specific URL.
    """
    current_user = await get_current_user(request)
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        # Get domain and URL info
        domain = DomainService.get_domain(domain_id)
        if not domain:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Domain not found"
            )
        
        url = UrlService.get_url(url_id)
        if not url or url.domain_id != domain_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="URL not found"
            )
        
        # Remove old content and re-scrape
        from services.silo_service import SiloService
        full_url = domain.base_url + url.url
        SiloService.delete_url(domain.silo_id, full_url)
        
        # Re-scrape and index
        success = scrape_and_index_url(domain, url.url, url_id)
        
        if success:
            message = "URL content re-indexed successfully"
        else:
            message = "URL re-indexing failed - could not scrape content"
        
        return URLActionResponseSchema(
            success=success,
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
    request: Request
):
    """
    Remove URL content from index and mark as unindexed.
    """
    current_user = await get_current_user(request)
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        # Get domain and URL info
        domain = DomainService.get_domain(domain_id)
        if not domain:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Domain not found"
            )
        
        url = UrlService.get_url(url_id)
        if not url or url.domain_id != domain_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="URL not found"
            )
        
        # Unindex the URL
        UrlService.unindex_url(url_id, domain_id)
        
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
    request: Request
):
    """
    Mark URL as rejected (content not suitable for indexing).
    """
    current_user = await get_current_user(request)
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        # Get domain and URL info
        domain = DomainService.get_domain(domain_id)
        if not domain:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Domain not found"
            )
        
        url = UrlService.get_url(url_id)
        if not url or url.domain_id != domain_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="URL not found"
            )
        
        # Reject the URL
        UrlService.reject_url(url_id, domain_id)
        
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
    request: Request
):
    """
    Re-index content for all URLs in a domain.
    """
    current_user = await get_current_user(request)
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        # Get domain info
        domain = DomainService.get_domain(domain_id)
        if not domain:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Domain not found"
            )
        
        # Re-index all URLs
        results = reindex_domain_urls(domain)
        
        return {
            "message": f"Re-indexing complete. Success: {results['success']}, Failed: {results['failed']}, Total: {results['total']}",
            "results": results
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
    request: Request
):
    """
    Get the scraped content for a specific URL.
    """
    current_user = await get_current_user(request)
    user_id = current_user["user_id"]
    
    # TODO: Add app access validation
    
    try:
        # Get domain and URL info
        domain = DomainService.get_domain(domain_id)
        if not domain:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Domain not found"
            )
        
        # Get URL info
        url = UrlService.get_url(url_id)
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
            limit=10
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