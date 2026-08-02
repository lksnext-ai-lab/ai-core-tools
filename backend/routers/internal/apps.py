from fastapi import APIRouter, Depends, Form, HTTPException, status, UploadFile, File, Query
from typing import List, Tuple, Optional, Annotated
from sqlalchemy.orm import Session
from lks_idprovider.models.auth import AuthContext
import json
import os
from pydantic import ValidationError

from db.database import get_db

from services.app_service import AppService
from services.app_collaboration_service import AppCollaborationService
from services.rate_limit_service import rate_limit_service

from schemas.apps_schemas import (
    AppListItemSchema, AppDetailSchema, CreateAppSchema, UpdateAppSchema, AppUsageStatsSchema,
    LangSmithTestRequestSchema, LangSmithTestResponseSchema,
    OwnershipOfferRequest, OwnershipOfferResponse, OwnershipAcceptResponse,
)
from schemas.common_schemas import MessageResponseSchema
from schemas.export_schemas import AppExportFileSchema
from schemas.import_schemas import (
    ConflictMode,
    FullAppImportResponseSchema,
    AppImportPreviewSchema,
)
from .auth_utils import get_current_user_oauth
from routers.controls.role_authorization import require_min_role, AppRole
from utils.secret_utils import mask_api_key, is_masked_key, normalize_credential_map

from .agents import agents_router
from .silos import silos_router
from .ai_services import ai_services_router
from .api_keys import api_keys_router
from .domains import domains_router
from .embedding_services import embedding_services_router
from .sandbox_services import sandbox_services_router
from .mcp_configs import mcp_configs_router
from .ocr import ocr_router
from .output_parsers import output_parsers_router
from .repositories import repositories_router
from .folders import folders_router
from .mcp_servers import mcp_servers_router
from .skills import skills_router

from utils.logger import get_logger

logger = get_logger(__name__)

apps_router = APIRouter()

DEFAULT_AGENT_RATE_LIMIT = 0
DEFAULT_MAX_FILE_SIZE_MB = 0

APP_NOT_FOUND_MSG = "App not found"

# Static routes must be declared before the /{app_id} dynamic routes.


@apps_router.post(
    "/preview-import",
    response_model=AppImportPreviewSchema,
    summary="Preview app import",
    tags=["Apps", "Export/Import"],
)
async def preview_import_app(
    file: Annotated[UploadFile, File(...)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
):
    """Parse the export file and return a structured preview. Read-only — no database modifications."""
    from services.full_app_import_service import (
        FullAppImportService,
    )

    try:
        contents = await file.read()
        export_dict = json.loads(contents)
        export_data = AppExportFileSchema(**export_dict)

        import_service = FullAppImportService(db)
        user_id = int(auth_context.identity.id)
        return import_service.preview_import(export_data, user_id)
    except (json.JSONDecodeError, ValidationError) as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Invalid export file: {e}",
        )
    except ValueError as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            str(e),
        )
    except Exception as e:
        logger.error(
            f"Preview import error: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Preview failed",
        )


@apps_router.post(
    "/import",
    summary="Import complete app configuration",
    tags=["Apps", "Export/Import"],
    status_code=status.HTTP_201_CREATED,
)
async def import_full_app(
    file: Annotated[UploadFile, File(...)],
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    conflict_mode: Annotated[ConflictMode, Query(
        description="How to handle name conflicts (fail/rename/override)",
    )] = ConflictMode.FAIL,
    new_name: Annotated[Optional[str], Query(
        description="New app name (for rename mode)"
    )] = None,
    component_selection_json: Annotated[Optional[str], Form(
        description=(
            "JSON object mapping singular component-type keys to lists of "
            "names to import. Omit to import all components. "
            "Example: {\"ai_service\":[\"My Service\"]}"
        ),
    )] = None,
    api_keys_json: Annotated[Optional[str], Form(
        description=(
            "JSON object mapping original service names to API keys. "
            "Example: {\"My Service\":\"sk-...\"}"
        ),
    )] = None,
) -> FullAppImportResponseSchema:
    """Import complete app configuration from JSON file. Always creates a new app."""
    from services.full_app_import_service import FullAppImportService

    user_id = int(auth_context.identity.id)

    try:
        contents = await file.read()
        export_dict = json.loads(contents)
        export_data = AppExportFileSchema(**export_dict)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON: {str(e)}",
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid export format: {str(e)}",
        )

    component_selection = None
    if component_selection_json:
        try:
            component_selection = json.loads(component_selection_json)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid component_selection JSON: {e}",
            )

    api_keys = None
    if api_keys_json:
        try:
            api_keys = json.loads(api_keys_json)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid api_keys JSON: {e}",
            )
        # api_keys bypasses the field_validators on CreateUpdateAIServiceSchema
        # because FullAppImportService assigns to the ORM directly. Normalize
        # at this boundary instead — same effect.
        api_keys = normalize_credential_map(api_keys)

    service = FullAppImportService(db)
    try:
        summary = service.import_full_app(
            export_data=export_data,
            user_id=user_id,
            conflict_mode=conflict_mode,
            new_name=new_name,
            component_selection=component_selection,
            api_keys=api_keys,
        )

        logger.info(
            f"User {user_id} imported full app '{summary.app_name}': {summary.total_components} components"
        )

        return FullAppImportResponseSchema(
            success=len(summary.total_errors) == 0,
            message=(
                f"App '{summary.app_name}' imported successfully with {summary.total_components} components"
                if len(summary.total_errors) == 0
                else f"Import completed with {len(summary.total_errors)} errors"
            ),
            summary=summary,
        )
    except HTTPException:
        raise
    except ValueError as e:
        if "already exists" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(e),
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Full app import failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Import failed: {str(e)}",
        )


@apps_router.post(
    "/{app_id}/ownership/offer",
    response_model=OwnershipOfferResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Offer app ownership to another user",
    tags=["Apps", "Ownership"],
    responses={
        400: {"description": "Recipient is invalid (non-existent, inactive, or already owner)"},
        403: {"description": "Insufficient permissions — OWNER required"},
        404: {"description": "App not found"},
    },
)
async def offer_app_ownership(
    app_id: int,
    body: OwnershipOfferRequest,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role(AppRole.OWNER))],
) -> OwnershipOfferResponse:
    """Create a pending ownership offer (idempotent). No ownership change until the recipient accepts."""
    from services.app_ownership_service import AppOwnershipService
    from services.app_ownership_errors import (
        AppNotFoundError,
        TransferRecipientInvalidError,
    )

    actor_user_id: int = int(auth_context.identity.id)

    try:
        offer = AppOwnershipService.offer(
            db,
            app_id=app_id,
            new_owner_id=body.new_owner_id,
            actor_user_id=actor_user_id,
        )
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    except TransferRecipientInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)
    except HTTPException:
        raise
    except Exception:
        logger.error(
            "offer_app_ownership: unexpected error app_id=%s new_owner_id=%s actor=%s",
            app_id,
            body.new_owner_id,
            auth_context.identity.email,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create ownership offer due to an unexpected error.",
        )

    logger.info(
        "apps:offer_ownership app_id=%s new_owner_id=%s collab_id=%s by=%s",
        app_id,
        body.new_owner_id,
        offer.id,
        auth_context.identity.email,
    )

    return OwnershipOfferResponse(
        collaboration_id=offer.id,
        app_id=app_id,
        new_owner_id=body.new_owner_id,
        actor_user_id=actor_user_id,
    )


@apps_router.post(
    "/{app_id}/ownership/accept/{collaboration_id}",
    response_model=OwnershipAcceptResponse,
    status_code=status.HTTP_200_OK,
    summary="Accept an ownership offer (recipient only)",
    tags=["Apps", "Ownership"],
    responses={
        403: {"description": "Actor is not the offer recipient"},
        404: {"description": "Pending ownership offer not found"},
        409: {"description": "Transfer would exceed the recipient's SaaS app-count limit"},
    },
)
async def accept_app_ownership_offer(
    app_id: int,
    collaboration_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
) -> OwnershipAcceptResponse:
    """Accept a pending ownership offer. Previous owner is demoted to ADMINISTRATOR."""
    from services.app_ownership_service import AppOwnershipService
    from services.app_ownership_errors import (
        AppNotFoundError,
        NotOfferRecipientError,
        OwnershipOfferNotFoundError,
        TierLimitExceededError,
        TransferRecipientInvalidError,
    )

    actor_user_id: int = int(auth_context.identity.id)

    try:
        app, previous_owner_id = AppOwnershipService.accept(
            db,
            collaboration_id=collaboration_id,
            actor_user_id=actor_user_id,
            app_id=app_id,
        )
    except OwnershipOfferNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    except NotOfferRecipientError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.message)
    except (TransferRecipientInvalidError, AppNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)
    except TierLimitExceededError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message)
    except HTTPException:
        raise
    except Exception:
        logger.error(
            "accept_app_ownership_offer: unexpected error app_id=%s collab_id=%s actor=%s",
            app_id,
            collaboration_id,
            auth_context.identity.email,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to accept ownership offer due to an unexpected error.",
        )

    logger.info(
        "apps:accept_ownership app_id=%s collab_id=%s new_owner=%s prev_owner=%s by=%s",
        app_id,
        collaboration_id,
        actor_user_id,
        previous_owner_id,
        auth_context.identity.email,
    )

    return OwnershipAcceptResponse(
        app_id=app.app_id,
        name=app.name,
        new_owner_id=actor_user_id,
        previous_owner_id=previous_owner_id,
    )


@apps_router.post(
    "/{app_id}/ownership/decline/{collaboration_id}",
    response_model=MessageResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Decline an ownership offer (recipient only)",
    tags=["Apps", "Ownership"],
    responses={
        403: {"description": "Actor is not the offer recipient"},
        404: {"description": "Pending ownership offer not found"},
    },
)
async def decline_app_ownership_offer(
    app_id: int,
    collaboration_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
) -> MessageResponseSchema:
    """Decline a pending ownership offer. Sets offer status to DECLINED; no ownership change."""
    from services.app_ownership_service import AppOwnershipService
    from services.app_ownership_errors import (
        NotOfferRecipientError,
        OwnershipOfferNotFoundError,
    )

    actor_user_id: int = int(auth_context.identity.id)

    try:
        AppOwnershipService.decline(
            db,
            collaboration_id=collaboration_id,
            actor_user_id=actor_user_id,
            app_id=app_id,
        )
    except OwnershipOfferNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    except NotOfferRecipientError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.message)
    except HTTPException:
        raise
    except Exception:
        logger.error(
            "decline_app_ownership_offer: unexpected error app_id=%s collab_id=%s actor=%s",
            app_id,
            collaboration_id,
            auth_context.identity.email,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to decline ownership offer due to an unexpected error.",
        )

    logger.info(
        "apps:decline_ownership app_id=%s collab_id=%s by=%s",
        app_id,
        collaboration_id,
        auth_context.identity.email,
    )

    return MessageResponseSchema(message="Ownership offer declined.")


@apps_router.delete(
    "/{app_id}/ownership/offer",
    response_model=MessageResponseSchema,
    status_code=status.HTTP_200_OK,
    summary="Cancel pending ownership offer",
    tags=["Apps", "Ownership"],
    responses={
        403: {"description": "Insufficient permissions — OWNER required"},
        404: {"description": "App not found or no pending offer exists"},
    },
)
async def cancel_app_ownership_offer(
    app_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role(AppRole.OWNER))],
) -> MessageResponseSchema:
    """Cancel the pending ownership offer for an app (owner/omniadmin only)."""
    from services.app_ownership_service import AppOwnershipService
    from services.app_ownership_errors import OwnershipOfferNotFoundError

    actor_user_id: int = int(auth_context.identity.id)

    try:
        AppOwnershipService.cancel(
            db,
            app_id=app_id,
            actor_user_id=actor_user_id,
        )
    except OwnershipOfferNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    except HTTPException:
        raise
    except Exception:
        logger.error(
            "cancel_app_ownership_offer: unexpected error app_id=%s actor=%s",
            app_id,
            auth_context.identity.email,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel ownership offer due to an unexpected error.",
        )

    logger.info(
        "apps:cancel_ownership_offer app_id=%s by=%s",
        app_id,
        auth_context.identity.email,
    )

    return MessageResponseSchema(message="Ownership offer cancelled successfully.")


apps_router.include_router(agents_router, prefix="/{app_id}/agents", tags=["Agents"])
apps_router.include_router(silos_router, prefix="/{app_id}/silos", tags=["Silos"])
apps_router.include_router(ai_services_router, prefix="/{app_id}/ai-services", tags=["AI Services"])
apps_router.include_router(api_keys_router, prefix="/{app_id}/api-keys", tags=["API Keys"])
apps_router.include_router(domains_router, prefix="/{app_id}/domains", tags=["Domains"])
apps_router.include_router(embedding_services_router, prefix="/{app_id}/embedding-services", tags=["Embedding Services"])
apps_router.include_router(sandbox_services_router, prefix="/{app_id}/sandbox-services", tags=["Sandbox Services"])
apps_router.include_router(mcp_configs_router, prefix="/{app_id}/mcp-configs", tags=["MCP Configs"])
apps_router.include_router(ocr_router, prefix="/{app_id}/ocr", tags=["OCR"])
apps_router.include_router(output_parsers_router, prefix="/{app_id}/output-parsers", tags=["Output Parsers"])
apps_router.include_router(repositories_router, prefix="/{app_id}/repositories", tags=["Repositories"])
apps_router.include_router(folders_router, prefix="/{app_id}/repositories/{repository_id}/folders", tags=["Folders"])
apps_router.include_router(mcp_servers_router, prefix="/{app_id}/mcp-servers", tags=["MCP Servers"])
apps_router.include_router(skills_router, prefix="/{app_id}/skills", tags=["Skills"])

def get_services(db: Session) -> Tuple[AppService, AppCollaborationService]:
    """Return initialised AppService and AppCollaborationService."""
    app_service = AppService(db)
    collaboration_service = AppCollaborationService(db)
    return app_service, collaboration_service

def _safe_get_count(items) -> int:
    return len(items) if items else 0

def _handle_savepoint_rollback(savepoint, db: Session, app_id: int):
    """Roll back a savepoint, falling back to full transaction rollback on error."""
    try:
        savepoint.rollback()
    except Exception as rollback_error:
        logger.error(f"Error rolling back savepoint for app {app_id}: {str(rollback_error)}")
        _handle_transaction_rollback(db, app_id)

def _handle_transaction_rollback(db: Session, app_id: int):
    try:
        db.rollback()
    except Exception as rollback_error:
        logger.error(f"Error rolling back transaction for app {app_id}: {str(rollback_error)}")

def _get_entity_counts(app_id: int, db: Session, collaboration_service: AppCollaborationService) -> dict:
    from services.agent_service import AgentService
    from services.repository_service import RepositoryService
    from services.domain_service import DomainService
    from services.silo_service import SiloService
    
    agent_service = AgentService()
    agents = agent_service.get_agents(db, app_id)
    repositories = RepositoryService.get_repositories_by_app_id(app_id, db)
    domains = DomainService.get_domains_by_app_id(app_id, db)
    silos = SiloService.get_silos_by_app_id(app_id, db)
    collaborators = collaboration_service.get_app_collaborators(app_id)
    
    return {
        'agent_count': _safe_get_count(agents),
        'repository_count': _safe_get_count(repositories),
        'domain_count': _safe_get_count(domains),
        'silo_count': _safe_get_count(silos),
        'collaborator_count': _safe_get_count(collaborators)
    }

def _get_empty_counts() -> dict:
    return {
        'agent_count': 0,
        'repository_count': 0,
        'domain_count': 0,
        'silo_count': 0,
        'collaborator_count': 0
    }

def calculate_app_entity_counts(app_id: int, db: Session, collaboration_service: AppCollaborationService) -> dict:
    """Return entity counts for an app, falling back to zeros on any DB error."""
    savepoint = None
    try:
        savepoint = db.begin_nested()
        counts = _get_entity_counts(app_id, db, collaboration_service)
        
        if savepoint:
            savepoint.commit()
        return counts
        
    except Exception as e:
        logger.warning(f"Error calculating counts for app {app_id}: {str(e)}")
        
        if savepoint:
            _handle_savepoint_rollback(savepoint, db, app_id)
        else:
            _handle_transaction_rollback(db, app_id)
        
        return _get_empty_counts()


@apps_router.get("/",
                summary="List user's apps",
                tags=["Apps"],
                response_model=List[AppListItemSchema])
async def list_apps(
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)]
):
    user_id = int(auth_context.identity.id)
    app_service, collaboration_service = get_services(db)
    apps = app_service.get_apps(user_id)
    app_list = []
    for app in apps:
        role = collaboration_service.get_user_app_role(user_id, app.app_id) or "owner"
        counts = calculate_app_entity_counts(app.app_id, db, collaboration_service)
        usage_stats = rate_limit_service.get_app_usage_stats(
            app.app_id, 
            app.agent_rate_limit or DEFAULT_AGENT_RATE_LIMIT
        )
        usage_stats_schema = AppUsageStatsSchema(**usage_stats)
        owner_name = None
        owner_email = None
        if app.owner:
            owner_name = app.owner.name
            owner_email = app.owner.email
        app_item = AppListItemSchema(
            app_id=app.app_id,
            name=app.name,
            role=role,
            created_at=app.create_date,
            langsmith_configured=bool(app.langsmith_api_key and app.langsmith_api_key != "CHANGE_ME"),
            owner_id=app.owner_id,
            owner_name=owner_name,
            owner_email=owner_email,
            agent_rate_limit=app.agent_rate_limit or DEFAULT_AGENT_RATE_LIMIT,
            max_file_size_mb=app.max_file_size_mb or DEFAULT_MAX_FILE_SIZE_MB,
            agent_cors_origins=app.agent_cors_origins,
            usage_stats=usage_stats_schema,
            **counts
        )
        app_list.append(app_item)
    return app_list


@apps_router.get("/{app_id}",
                summary="Get app details",
                tags=["Apps"], 
                response_model=AppDetailSchema)
async def get_app(
    app_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
):
    user_id = int(auth_context.identity.id)
    app_service, collaboration_service = get_services(db)
    app = app_service.get_app(app_id)
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=APP_NOT_FOUND_MSG
        )
    
    if not collaboration_service.can_user_access_app(user_id, app_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this app"
        )
    
    user_role = collaboration_service.get_user_app_role(user_id, app_id)
    counts = calculate_app_entity_counts(app_id, db, collaboration_service)
    owner_email = None
    owner_name = None
    if app.owner:
        owner_email = app.owner.email
        owner_name = app.owner.name
    
    return AppDetailSchema(
        app_id=app.app_id,
        name=app.name,
        langsmith_api_key=mask_api_key(app.langsmith_api_key),
        user_role=user_role,
        created_at=app.create_date,
        owner_id=app.owner_id,
        owner_email=owner_email,
        owner_name=owner_name,
        agent_rate_limit=app.agent_rate_limit or DEFAULT_AGENT_RATE_LIMIT,
        max_file_size_mb=app.max_file_size_mb or DEFAULT_MAX_FILE_SIZE_MB,
        agent_cors_origins=app.agent_cors_origins,
        enable_openai_api=app.enable_openai_api,
        onboarding_dismissed=app.onboarding_dismissed or False,
        default_sandbox_service_id=app.default_sandbox_service_id,
        **counts
    )


@apps_router.patch("/{app_id}/onboarding-dismissed",
                   summary="Dismiss getting started checklist",
                   tags=["Apps"],
                   status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_onboarding(
    app_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("editor"))],
):
    """Mark the getting-started checklist as dismissed for the app."""
    app_service, _ = get_services(db)

    app = app_service.get_app(app_id)
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=APP_NOT_FOUND_MSG
        )

    from repositories.app_repository import AppRepository
    repo = AppRepository(db)
    repo.update(app, {'onboarding_dismissed': True})


@apps_router.post("/",
                 summary="Create new app",
                 tags=["Apps"],
                 response_model=AppDetailSchema,
                 status_code=status.HTTP_201_CREATED)
async def create_app(
    app_data: CreateAppSchema,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)]
):
    user_id = int(auth_context.identity.id)
    app_service, _ = get_services(db)
    app_dict = {
        'name': app_data.name,
        'owner_id': user_id,
        'langsmith_api_key': app_data.langsmith_api_key,
        'agent_rate_limit': (app_data.agent_rate_limit or DEFAULT_AGENT_RATE_LIMIT),
        'max_file_size_mb': (app_data.max_file_size_mb or DEFAULT_MAX_FILE_SIZE_MB),
        'agent_cors_origins': app_data.agent_cors_origins
    }
    
    app = app_service.create_or_update_app(app_dict, user_id=user_id)
    owner_email = None
    owner_name = None
    if app.owner:
        owner_email = app.owner.email
        owner_name = app.owner.name
    return AppDetailSchema(
        app_id=app.app_id,
        name=app.name,
        langsmith_api_key=mask_api_key(app.langsmith_api_key),
        user_role="owner",
        created_at=app.create_date,
        owner_id=app.owner_id,
        owner_email=owner_email,
        owner_name=owner_name,
        agent_rate_limit=app.agent_rate_limit or DEFAULT_AGENT_RATE_LIMIT,
        max_file_size_mb=app.max_file_size_mb or DEFAULT_MAX_FILE_SIZE_MB,
        agent_cors_origins=app.agent_cors_origins,
        default_sandbox_service_id=app.default_sandbox_service_id,
    )


@apps_router.put("/{app_id}",
                summary="Update app",
                tags=["Apps"],
                response_model=AppDetailSchema)
async def update_app(
    app_id: int,
    app_data: UpdateAppSchema,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
):
    user_id = int(auth_context.identity.id)
    app_service, collaboration_service = get_services(db)
    app = app_service.get_app(app_id)
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=APP_NOT_FOUND_MSG
        )
    
    if not collaboration_service.can_user_manage_app(user_id, app_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only app owners can update apps"
        )
    
    langsmith_key = app_data.langsmith_api_key
    if is_masked_key(langsmith_key):
        langsmith_key = app.langsmith_api_key

    langsmith_key_rotated = (langsmith_key or "") != (app.langsmith_api_key or "")

    # Validate default_sandbox_service_id references an existing sandbox service that is
    # either system-scoped or belongs to this app (None = inherit system default is always valid).
    if app_data.default_sandbox_service_id is not None:
        from repositories.sandbox_service_repository import SandboxServiceRepository

        sandbox_service = SandboxServiceRepository.get_by_id(db, app_data.default_sandbox_service_id)
        if sandbox_service is None or (
            sandbox_service.app_id is not None and sandbox_service.app_id != app_id
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"default_sandbox_service_id '{app_data.default_sandbox_service_id}' does not "
                    "reference a valid sandbox service for this app."
                ),
            )

    update_dict = {
        'app_id': app_id,
        'name': app_data.name,
        'langsmith_api_key': langsmith_key,
        'agent_rate_limit': app_data.agent_rate_limit or DEFAULT_AGENT_RATE_LIMIT,
        'max_file_size_mb': app_data.max_file_size_mb or DEFAULT_MAX_FILE_SIZE_MB,
        'agent_cors_origins': app_data.agent_cors_origins,
        'enable_openai_api': app_data.enable_openai_api,
        'default_sandbox_service_id': app_data.default_sandbox_service_id,
    }

    updated_app = app_service.create_or_update_app(update_dict)

    if langsmith_key_rotated:
        from tools.langsmith_config import clear_client_cache
        clear_client_cache(app_id)
    owner_email = None
    owner_name = None
    if updated_app.owner:
        owner_email = updated_app.owner.email
        owner_name = updated_app.owner.name
    return AppDetailSchema(
        app_id=updated_app.app_id,
        name=updated_app.name,
        langsmith_api_key=mask_api_key(updated_app.langsmith_api_key),
        user_role="owner",
        created_at=updated_app.create_date,
        owner_id=updated_app.owner_id,
        owner_email=owner_email,
        owner_name=owner_name,
        agent_rate_limit=updated_app.agent_rate_limit or DEFAULT_AGENT_RATE_LIMIT,
        max_file_size_mb=updated_app.max_file_size_mb or DEFAULT_MAX_FILE_SIZE_MB,
        agent_cors_origins=updated_app.agent_cors_origins,
        enable_openai_api=updated_app.enable_openai_api,
        default_sandbox_service_id=updated_app.default_sandbox_service_id,
    )


@apps_router.post(
    "/{app_id}/langsmith/test",
    response_model=LangSmithTestResponseSchema,
    summary="Test LangSmith API key",
    tags=["Apps"],
)
async def test_langsmith_connection(
    app_id: int,
    payload: LangSmithTestRequestSchema,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
):
    """Validate a LangSmith API key against the LangSmith API.

    If ``payload.api_key`` is omitted or is the masked placeholder, the test
    uses the key already stored for the app. The key is never returned in the
    response.
    """
    from tools.langsmith_config import (
        DEFAULT_LANGSMITH_ENDPOINT,
        resolve_langsmith_settings,
        validate_langsmith_key,
    )

    app_service, _ = get_services(db)
    app = app_service.get_app(app_id)
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=APP_NOT_FOUND_MSG,
        )

    candidate_key = payload.api_key
    source: str = "request"
    if not candidate_key or is_masked_key(candidate_key):
        candidate_key = app.langsmith_api_key
        source = "app" if candidate_key else "env"

    project_name: Optional[str] = app.name

    if not candidate_key:
        settings = resolve_langsmith_settings(app)
        if settings is None:
            return LangSmithTestResponseSchema(
                valid=False,
                status="unauthorized",
                message="No LangSmith API key configured for this app and no global fallback is enabled.",
                project_name=None,
                source=None,
            )
        candidate_key = settings.api_key
        project_name = settings.project_name
        source = settings.source

    endpoint = os.getenv("LANGSMITH_ENDPOINT") or DEFAULT_LANGSMITH_ENDPOINT
    result = validate_langsmith_key(candidate_key, endpoint)

    logger.info(
        "LangSmith key test for app_id=%s — valid=%s status=%s source=%s",
        app_id,
        result.valid,
        result.status,
        source,
    )

    return LangSmithTestResponseSchema(
        valid=result.valid,
        status=result.status,
        message=result.message,
        project_name=project_name if result.valid else None,
        source=source if result.valid else None,
    )


@apps_router.delete("/{app_id}",
                   summary="Delete app",
                   tags=["Apps"])
async def delete_app(
    app_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("owner"))],
):
    user_id = int(auth_context.identity.id)
    app_service, collaboration_service = get_services(db)
    app = app_service.get_app(app_id)
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=APP_NOT_FOUND_MSG
        )
    
    if not collaboration_service.can_user_manage_app(user_id, app_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only app owners can delete apps"
        )
    
    success = app_service.delete_app(app_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete app"
        )
    
    return MessageResponseSchema(message="App deleted successfully")


@apps_router.post("/{app_id}/validate-langsmith-key",
                 summary="Validate LangSmith API key (legacy)",
                 tags=["Apps"],
                 response_model=MessageResponseSchema,
                 deprecated=True)
async def validate_langsmith_key(
    app_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("administrator"))],
):
    """Legacy validator preserved for external scripts.

    New clients should call ``POST /internal/apps/{app_id}/langsmith/test``,
    which exposes structured status codes and project metadata.
    """
    from tools.langsmith_config import DEFAULT_LANGSMITH_ENDPOINT, validate_langsmith_key as _validate

    app_service, _ = get_services(db)
    app = app_service.get_app(app_id)
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=APP_NOT_FOUND_MSG,
        )

    if not app.langsmith_api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No LangSmith API key configured for this app",
        )

    endpoint = os.getenv("LANGSMITH_ENDPOINT") or DEFAULT_LANGSMITH_ENDPOINT
    result = _validate(app.langsmith_api_key, endpoint)
    if result.valid:
        return MessageResponseSchema(
            message=(
                f"LangSmith API key is valid. "
                f"Traces will be sent to project '{app.name}'."
            )
        )

    detail_by_status = {
        "unauthorized": (
            "LangSmith API key is invalid or expired. "
            "Generate a new key at https://smith.langchain.com/settings"
        ),
        "network": "Cannot reach LangSmith. Check connectivity and the LANGSMITH_ENDPOINT setting.",
        "unknown": result.message,
    }
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=detail_by_status.get(result.status, result.message),
    )


@apps_router.post("/{app_id}/leave",
                 summary="Leave app collaboration",
                 tags=["Apps"],
                 response_model=MessageResponseSchema)
async def leave_app(
    app_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
):
    user_id = int(auth_context.identity.id)
    _, collaboration_service = get_services(db)
    user_role = collaboration_service.get_user_app_role(user_id, app_id)
    
    if not user_role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="App not found or access denied"
        )
    
    try:
        success = collaboration_service.leave_app_collaboration(app_id, user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to leave app"
            )
        
        logger.info(f"User {user_id} left app {app_id}")
        return MessageResponseSchema(message="Successfully left the app")
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error leaving app {app_id} for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to leave app"
        )


@apps_router.post(
    "/{app_id}/export",
    summary="Export complete app configuration",
    tags=["Apps", "Export/Import"],
)
async def export_full_app(
    app_id: int,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
    role: Annotated[AppRole, Depends(require_min_role("viewer"))],
) -> AppExportFileSchema:
    """Export complete app configuration to JSON (API keys and secrets stripped)."""
    from services.full_app_export_service import FullAppExportService

    user_id = int(auth_context.identity.id)

    try:
        service = FullAppExportService(db)
        export_data = service.export_full_app(app_id=app_id, user_id=user_id)

        logger.info(f"User {user_id} exported app {app_id}")
        return export_data

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error exporting app {app_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}",
        )

