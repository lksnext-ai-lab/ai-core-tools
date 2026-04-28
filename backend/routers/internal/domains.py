from fastapi import APIRouter, HTTPException, status, Request, Depends, Query
from fastapi.responses import JSONResponse
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session
from typing import List, Annotated, Optional
import json

# Import services
from services.domain_service import DomainService
from services.domain_export_service import DomainExportService
from services.domain_import_service import DomainImportService
from services.crawl_policy_service import CrawlPolicyService
from services.crawl_job_service import CrawlJobService, ConflictError
from services.domain_url_service import DomainUrlService

# Import schemas and auth
from schemas.domain_url_schemas import (
    DomainListItemSchema,
    DomainDetailSchema,
    CreateUpdateDomainSchema,
    CreateDomainSchema,
    UpdateDomainSchema,
)
from schemas.crawl_schemas import (
    CrawlPolicySchema,
    CrawlPolicyResponseSchema,
    CrawlJobResponseSchema,
    TriggerCrawlResponseSchema,
    CrawlJobListResponseSchema,
    DomainUrlListResponseSchema,
    DomainUrlDetailSchema,
    AddDomainUrlSchema,
    DomainUrlActionResponseSchema,
)
from schemas.import_schemas import ConflictMode, ImportResponseSchema
from schemas.export_schemas import DomainExportFileSchema
from routers.internal.auth_utils import get_current_user_oauth
from routers.controls.role_authorization import require_min_role, AppRole

# Import database dependencies
from db.database import get_db

# Import logger
from utils.logger import get_logger
from utils.error_handlers import ValidationError
from utils.vector_db_immutability import assert_vector_db_type_immutable, assert_embedding_service_immutable
from tools.vector_store_factory import VectorStoreFactory
from fastapi import File, UploadFile

logger = get_logger(__name__)

DOMAIN_NOT_FOUND = "Domain not found"
URL_NOT_FOUND = "URL not found"

domains_router = APIRouter()


# ==================== DOMAIN MANAGEMENT ====================

@domains_router.post(
    "/import",
    summary="Import Domain",
    tags=["Domains", "Export/Import"],
    response_model=ImportResponseSchema,
    status_code=status.HTTP_201_CREATED,
)
async def import_domain(
    app_id: int,
    file: Annotated[UploadFile, File(...)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
    conflict_mode: Annotated[ConflictMode, Query()] = ConflictMode.FAIL,
    new_name: Annotated[Optional[str], Query()] = None,
    selected_embedding_service_id: Annotated[Optional[int], Query()] = None,
):
    """Import Domain from JSON file."""
    try:
        content = await file.read()
        file_data = json.loads(content)
        export_data = DomainExportFileSchema(**file_data)

        import_service = DomainImportService(db)
        import_service.validate_import(export_data, app_id)

        summary = import_service.import_domain(
            export_data,
            app_id,
            conflict_mode,
            new_name,
            selected_embedding_service_id=selected_embedding_service_id,
        )

        return ImportResponseSchema(
            success=True,
            message=f"Domain '{summary.component_name}' imported successfully",
            summary=summary,
        )
    except HTTPException:
        raise
    except ValueError as e:
        if "already exists" in str(e):
            raise HTTPException(status.HTTP_409_CONFLICT, str(e))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except Exception as e:
        logger.error(f"Import error: {str(e)}", exc_info=True)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Import failed")


@domains_router.get("/",
                    summary="List domains",
                    tags=["Domains"],
                    response_model=List[DomainListItemSchema])
async def list_domains(
    app_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
):
    """List all domains for a specific app."""
    try:
        domains_with_counts = DomainService.get_domains_with_url_counts(app_id, db)

        result = []
        for domain, url_count in domains_with_counts:
            if domain.silo and getattr(domain.silo, 'vector_db_type', None):
                domain_vector_db_type = domain.silo.vector_db_type
            else:
                domain_vector_db_type = 'PGVECTOR'
            result.append(DomainListItemSchema(
                domain_id=domain.domain_id,
                name=domain.name,
                description=domain.description or "",
                base_url=domain.base_url,
                created_at=domain.create_date,
                url_count=url_count,
                silo_id=domain.silo_id,
                vector_db_type=domain_vector_db_type,
            ))
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving domains: {str(e)}",
        )


@domains_router.get("/{domain_id}",
                    summary="Get domain details",
                    tags=["Domains"],
                    response_model=DomainDetailSchema)
async def get_domain(
    app_id: int,
    domain_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
):
    """Get detailed information about a specific domain."""
    if domain_id == 0:
        embedding_services = DomainService.get_embedding_services_for_app(app_id, db)
        vector_db_options = VectorStoreFactory.get_available_type_options()
        return DomainDetailSchema(
            domain_id=0, name="", description="", base_url="",
            content_tag="body", content_class="", content_id="",
            created_at=None, silo_id=None, url_count=0,
            embedding_services=embedding_services, embedding_service_id=None,
            vector_db_type='PGVECTOR', vector_db_options=vector_db_options,
        )

    domain_detail = DomainService.get_domain_detail(domain_id, app_id, db)
    if not domain_detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=DOMAIN_NOT_FOUND)
    return domain_detail


@domains_router.post("/",
                     summary="Create domain",
                     tags=["Domains"],
                     response_model=DomainDetailSchema,
                     status_code=status.HTTP_201_CREATED)
async def create_domain(
    app_id: int,
    domain_data: CreateDomainSchema,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
):
    """Create a new domain."""
    try:
        data = {
            'domain_id': None,
            'name': domain_data.name,
            'description': domain_data.description,
            'base_url': domain_data.base_url,
            'content_tag': domain_data.content_tag,
            'content_class': domain_data.content_class,
            'content_id': domain_data.content_id,
            'app_id': app_id,
            'vector_db_type': domain_data.vector_db_type,
        }
        created_domain_id = DomainService.create_or_update_domain(data, domain_data.embedding_service_id, db)
        return await get_domain(app_id, created_domain_id, request, db, auth_context, role)
    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating domain: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@domains_router.put("/{domain_id}",
                    summary="Update domain",
                    tags=["Domains"],
                    response_model=DomainDetailSchema)
async def update_domain(
    app_id: int,
    domain_id: int,
    domain_data: UpdateDomainSchema,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
):
    """Update an existing domain."""
    try:
        raw_body = await request.json()
        existing_domain = DomainService.get_domain(domain_id, db)
        if existing_domain and existing_domain.silo:
            assert_vector_db_type_immutable(existing_domain.silo.vector_db_type, raw_body.get('vector_db_type'), "domain")
            assert_embedding_service_immutable(existing_domain.silo.embedding_service_id, raw_body.get('embedding_service_id'), "domain")

        data = {
            'domain_id': domain_id,
            'name': domain_data.name,
            'description': domain_data.description,
            'base_url': domain_data.base_url,
            'content_tag': domain_data.content_tag,
            'content_class': domain_data.content_class,
            'content_id': domain_data.content_id,
            'app_id': app_id,
            'vector_db_type': None,
        }
        updated_domain_id = DomainService.create_or_update_domain(data, None, db)
        return await get_domain(app_id, updated_domain_id, request, db, auth_context, role)
    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating domain: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@domains_router.delete("/{domain_id}",
                       summary="Delete domain",
                       tags=["Domains"])
async def delete_domain(
    app_id: int,
    domain_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
):
    """Delete a domain and its associated silo and URLs."""
    try:
        domain = DomainService.get_domain(domain_id, db)
        if not domain:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=DOMAIN_NOT_FOUND)
        DomainService.delete_domain(domain_id, db)
        return {"message": "Domain deleted successfully"}
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting domain: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error deleting domain: {str(e)}")


@domains_router.post(
    "/{domain_id}/export",
    summary="Export Domain",
    tags=["Domains", "Export/Import"],
    status_code=status.HTTP_200_OK,
)
async def export_domain(
    app_id: int,
    domain_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
    include_dependencies: Annotated[bool, Query(description="Bundle silo and its dependencies")] = True,
):
    """Export Domain configuration to JSON file."""
    try:
        export_service = DomainExportService(db)
        export_data = export_service.export_domain(
            domain_id, app_id, getattr(auth_context, "user_id", None), include_dependencies,
        )
        filename = f"{export_data.domain.name.replace(' ', '_')}_domain.json"
        return JSONResponse(
            content=export_data.model_dump(mode="json"),
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as e:
        logger.warning(f"Export failed: {str(e)}")
        if "not found" in str(e):
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except Exception as e:
        logger.error(f"Export error: {str(e)}", exc_info=True)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Export failed")


# ==================== URL MANAGEMENT ====================

@domains_router.get("/{domain_id}/urls",
                    summary="List URLs for domain",
                    tags=["Domains", "URLs"],
                    response_model=DomainUrlListResponseSchema)
async def list_domain_urls(
    app_id: int,
    domain_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=200),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    discovered_via: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
):
    """List DomainUrl rows for a specific domain with optional filters and pagination."""
    try:
        urls, pagination = DomainUrlService.list_urls(
            domain_id=domain_id, db=db, page=page, per_page=per_page,
            status=status_filter, discovered_via=discovered_via, q=q,
        )
        return DomainUrlListResponseSchema(
            items=urls,
            page=pagination['page'],
            per_page=pagination['per_page'],
            total=pagination['total'],
        )
    except Exception as e:
        logger.error(f"Error retrieving URLs for domain {domain_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error retrieving URLs: {str(e)}")


@domains_router.post("/{domain_id}/urls",
                     summary="Add URL to domain",
                     tags=["Domains", "URLs"],
                     response_model=DomainUrlActionResponseSchema,
                     status_code=status.HTTP_201_CREATED)
async def add_domain_url(
    app_id: int,
    domain_id: int,
    url_data: AddDomainUrlSchema,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
):
    """Add a URL to a domain manually (queued for next crawl)."""
    try:
        domain = DomainService.get_domain(domain_id, db)
        if not domain:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=DOMAIN_NOT_FOUND)
        domain_url = DomainUrlService.add_manual_url(url_data.url, domain_id, db)
        return DomainUrlActionResponseSchema(
            success=True,
            message="URL added successfully",
            url_id=domain_url.id,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding URL to domain {domain_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error adding URL: {str(e)}")


@domains_router.get("/{domain_id}/urls/{url_id}",
                    summary="Get URL detail",
                    tags=["Domains", "URLs"],
                    response_model=DomainUrlDetailSchema)
async def get_domain_url(
    app_id: int,
    domain_id: int,
    url_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
):
    """Get detailed information about a specific domain URL."""
    try:
        domain_url = DomainUrlService.get_url(url_id, db)
        if not domain_url or domain_url.domain_id != domain_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=URL_NOT_FOUND)
        return domain_url
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving URL {url_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error retrieving URL: {str(e)}")


@domains_router.delete("/{domain_id}/urls/{url_id}",
                       summary="Delete URL from domain",
                       tags=["Domains", "URLs"],
                       response_model=DomainUrlActionResponseSchema)
async def delete_domain_url(
    app_id: int,
    domain_id: int,
    url_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
):
    """Delete a URL from a domain and remove its indexed content."""
    try:
        deleted = DomainUrlService.delete_url(url_id, domain_id, db)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=URL_NOT_FOUND)
        return DomainUrlActionResponseSchema(success=True, message="URL deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting URL {url_id} from domain {domain_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error deleting URL: {str(e)}")


@domains_router.post("/{domain_id}/urls/{url_id}/recrawl",
                     summary="Force re-crawl a URL",
                     tags=["Domains", "URLs"],
                     response_model=DomainUrlActionResponseSchema)
async def recrawl_url(
    app_id: int,
    domain_id: int,
    url_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
):
    """Mark a URL for immediate re-crawl on the next job run."""
    try:
        found = DomainUrlService.mark_for_recrawl(url_id, domain_id, db)
        if not found:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=URL_NOT_FOUND)
        return DomainUrlActionResponseSchema(success=True, message="URL marked for re-crawl", url_id=url_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking URL {url_id} for re-crawl: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error: {str(e)}")


@domains_router.get("/{domain_id}/urls/{url_id}/content",
                    summary="Get URL content preview",
                    tags=["Domains", "URLs"])
async def get_url_content(
    app_id: int,
    domain_id: int,
    url_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
):
    """Get the indexed content for a specific URL."""
    try:
        domain = DomainService.get_domain(domain_id, db)
        if not domain:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=DOMAIN_NOT_FOUND)

        domain_url = DomainUrlService.get_url(url_id, db)
        if not domain_url or domain_url.domain_id != domain_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=URL_NOT_FOUND)

        if not domain.silo_id:
            return {"url": domain_url.url, "content": None, "message": "No silo associated with this domain"}

        from services.silo_service import SiloService
        results = SiloService.search_in_silo(
            silo_id=domain.silo_id,
            query=domain_url.url,
            limit=10,
            db=db,
        )

        content_pieces = []
        for result in results:
            if hasattr(result, 'page_content'):
                content_pieces.append(result.page_content)
            elif hasattr(result, 'content'):
                content_pieces.append(result.content)

        content = "\n\n".join(content_pieces) if content_pieces else None
        return {
            "url": domain_url.url,
            "content": content,
            "message": "Content retrieved successfully" if content else "No content found for this URL",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving URL content: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error retrieving URL content: {str(e)}")


# ==================== CRAWL POLICY ====================

@domains_router.get("/{domain_id}/crawl-policy",
                    summary="Get crawl policy",
                    tags=["Domains", "Crawl"],
                    response_model=CrawlPolicyResponseSchema)
async def get_crawl_policy(
    app_id: int,
    domain_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
):
    """Get the crawl policy for a domain."""
    policy = CrawlPolicyService.get_policy(domain_id, db)
    if not policy:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crawl policy not found")
    return policy


@domains_router.put("/{domain_id}/crawl-policy",
                    summary="Create or update crawl policy",
                    tags=["Domains", "Crawl"],
                    response_model=CrawlPolicyResponseSchema)
async def upsert_crawl_policy(
    app_id: int,
    domain_id: int,
    policy_data: CrawlPolicySchema,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
):
    """Create or update the crawl policy for a domain."""
    try:
        policy = CrawlPolicyService.upsert_policy(domain_id, policy_data, db)
        return policy
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Error upserting crawl policy for domain {domain_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


# ==================== CRAWL JOBS ====================

@domains_router.post("/{domain_id}/crawl-jobs",
                     summary="Trigger a crawl job",
                     tags=["Domains", "Crawl"],
                     response_model=TriggerCrawlResponseSchema,
                     status_code=status.HTTP_202_ACCEPTED)
async def trigger_crawl(
    app_id: int,
    domain_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
):
    """Enqueue a manual crawl job for a domain."""
    domain = DomainService.get_domain(domain_id, db)
    if not domain:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=DOMAIN_NOT_FOUND)

    try:
        user_id = getattr(auth_context, 'user_id', None)
        job = CrawlJobService.enqueue(domain_id, user_id, db)
        return TriggerCrawlResponseSchema(job_id=job.id, status="QUEUED")
    except ConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "A job is already queued or running", "job_id": e.job_id},
        )
    except Exception as e:
        logger.error(f"Error triggering crawl for domain {domain_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@domains_router.get("/{domain_id}/crawl-jobs",
                    summary="List crawl jobs",
                    tags=["Domains", "Crawl"],
                    response_model=CrawlJobListResponseSchema)
async def list_crawl_jobs(
    app_id: int,
    domain_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=200),
):
    """List crawl jobs for a domain, newest first."""
    jobs, pagination = CrawlJobService.list_jobs(domain_id, db, page, per_page)
    return CrawlJobListResponseSchema(
        items=jobs,
        page=pagination['page'],
        per_page=pagination['per_page'],
        total=pagination['total'],
    )


@domains_router.get("/{domain_id}/crawl-jobs/{job_id}",
                    summary="Get crawl job",
                    tags=["Domains", "Crawl"],
                    response_model=CrawlJobResponseSchema)
async def get_crawl_job(
    app_id: int,
    domain_id: int,
    job_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
):
    """Get a specific crawl job."""
    job = CrawlJobService.get_job(job_id, domain_id, db)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crawl job not found")
    return job


@domains_router.post("/{domain_id}/crawl-jobs/{job_id}/cancel",
                     summary="Cancel a crawl job",
                     tags=["Domains", "Crawl"],
                     response_model=CrawlJobResponseSchema)
async def cancel_crawl_job(
    app_id: int,
    domain_id: int,
    job_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
):
    """Cancel a queued or running crawl job."""
    try:
        job = CrawlJobService.cancel(job_id, domain_id, db)
        return job
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        logger.error(f"Error cancelling crawl job {job_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
