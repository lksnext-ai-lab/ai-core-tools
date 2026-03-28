from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Annotated, Optional
from lks_idprovider import AuthContext
from sqlalchemy.orm import Session
from db.database import get_db
from models.app import App
from models.agent import Agent
from models.api_key import APIKey
from services.user_service import UserService
from services.system_settings_service import SystemSettingsService
from services.marketplace_quota_service import MarketplaceQuotaService
from utils.config import is_omniadmin
from routers.internal.auth_utils import get_current_user_oauth
from schemas.admin_schemas import UserListResponse, UserDetailResponse, SystemStatsResponse, MarketplaceQuotaResetResponse
from schemas.system_setting_schemas import SystemSettingRead, SystemSettingUpdate
from utils.logger import get_logger
from datetime import datetime, timezone

logger = get_logger(__name__)

router = APIRouter(tags=["admin"])

USER_NOT_FOUND = "User not found"


def require_admin(auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)]):
    """Dependency to require admin access"""
    if not is_omniadmin(auth_context.identity.email):
        raise HTTPException(status_code=403, detail="Admin access required")
    return auth_context


@router.get(
    "/users",
    response_model=UserListResponse,
    responses={500: {"description": "Internal server error"}},
)
async def list_users(
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    per_page: Annotated[int, Query(ge=1, le=100, description="Users per page")] = 10,
    search: Annotated[Optional[str], Query(description="Search query for name or email")] = None,
):
    """List all users with pagination and optional search"""
    try:
        if search:
            users, total = UserService.search_users(db, search, page, per_page)
        else:
            users, total = UserService.get_all_users(db, page, per_page)
        
        total_pages = (total + per_page - 1) // per_page
        
        return UserListResponse(
            users=users,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving users: {str(e)}")


@router.get(
    "/users/{user_id}",
    response_model=UserDetailResponse,
    responses={
        404: {"description": "User not found"},
        500: {"description": "Internal server error"},
    },
)
async def get_user(
    user_id: int,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """Get detailed user information"""
    try:
        user = UserService.get_user_by_id_with_relations(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail=USER_NOT_FOUND)
        
        return UserDetailResponse(
            user_id=user.user_id,
            email=user.email,
            name=user.name,
            created_at=user.created_at.isoformat(),
            owned_apps_count=len(user.owned_apps) if user.owned_apps else 0,
            api_keys_count=len(user.api_keys) if user.api_keys else 0,
            is_active=user.is_active
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving user: {str(e)}")


@router.delete(
    "/users/{user_id}",
    responses={
        404: {"description": "User not found"},
        500: {"description": "Internal server error"},
    },
)
async def delete_user(
    user_id: int,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """Delete a user and all associated data"""
    try:
        user = UserService.get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail=USER_NOT_FOUND)
        
        success = UserService.delete_user(db, user_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete user")
        
        return {"message": f"User {user.email} and all associated data have been deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting user: {str(e)}")


@router.post(
    "/users/{user_id}/activate",
    responses={
        400: {"description": "Bad request"},
        500: {"description": "Internal server error"},
    },
)
async def activate_user(
    user_id: int,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """Activate a user account"""
    try:
        user = UserService.activate_user(db, user_id, auth_context.identity.email)
        logger.info(f"User {user.email} activated by admin {auth_context.identity.email}")
        return {
            "message": f"User {user.email} has been activated successfully",
            "user_id": user.user_id,
            "is_active": user.is_active
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error activating user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error activating user: {str(e)}")


@router.post(
    "/users/{user_id}/deactivate",
    responses={
        400: {"description": "Bad request"},
        500: {"description": "Internal server error"},
    },
)
async def deactivate_user(
    user_id: int,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """Deactivate a user account"""
    try:
        user = UserService.deactivate_user(db, user_id, auth_context.identity.email)
        logger.info(f"User {user.email} deactivated by admin {auth_context.identity.email}")
        return {
            "message": f"User {user.email} has been deactivated successfully",
            "user_id": user.user_id,
            "is_active": user.is_active
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error deactivating user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deactivating user: {str(e)}")


@router.post(
    "/users/{user_id}/reset-marketplace-quota",
    response_model=MarketplaceQuotaResetResponse,
    responses={
        404: {"description": "User not found"},
        500: {"description": "Internal server error"},
    },
)
async def reset_user_marketplace_quota(
    user_id: int,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)]
):
    """
    Reset a user's current month marketplace quota to 0.
    
    This endpoint is only accessible to OMNIADMIN users and is used for:
    - Granting additional quota when a user reports counting errors
    - Providing extra quota to VIP users
    - Testing/debugging purposes
    
    The reset only affects the current UTC month; previous months remain unchanged.
    """
    try:
        # Get the target user and validate exists
        user = UserService.get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail=USER_NOT_FOUND)
        
        # Get current usage before reset
        previous_count = MarketplaceQuotaService.get_current_month_usage(user_id, db)
        
        # Perform the reset (handle case where no record exists - idempotent behavior)
        try:
            MarketplaceQuotaService.reset_user_current_month_usage(user_id, db)
        except ValueError:
            # No usage record exists for current month - user already at 0, which is desired state
            # Log this and return success anyway (idempotent)
            logger.info(
                f"OMNIADMIN {auth_context.identity.email} attempted to reset marketplace quota "
                f"for user {user.email} (ID: {user_id}) but no usage record exists. "
                f"User already has 0 usage for current month."
            )
        
        # Get current timestamp
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        # Log the reset action for audit trail
        logger.info(
            f"OMNIADMIN {auth_context.identity.email} (email) reset marketplace quota "
            f"for user {user.email} (ID: {user_id}). Previous count: {previous_count}, New count: 0. "
            f"Timestamp: {timestamp}"
        )
        
        return MarketplaceQuotaResetResponse(
            message="Marketplace quota reset successfully",
            user_id=user_id,
            user_email=user.email,
            previous_count=previous_count,
            new_count=0,
            reset_by=auth_context.identity.email,
            timestamp=timestamp
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting marketplace quota for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error resetting marketplace quota: {str(e)}")


@router.get(
    "/stats",
    response_model=SystemStatsResponse,
    responses={500: {"description": "Internal server error"}},
)
async def get_system_stats(
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """Get system-wide statistics"""
    try:
        # Get user stats
        user_stats = UserService.get_user_stats(db)
        active_users = UserService.get_active_users_count(db)
        inactive_users = UserService.get_inactive_users_count(db)
        
        # Get other counts using the same db session
        total_apps = db.query(App).count()
        total_agents = db.query(Agent).count()
        total_api_keys = db.query(APIKey).count()
        active_api_keys = db.query(APIKey).filter(APIKey.is_active == True).count()
        
        return SystemStatsResponse(
            total_users=user_stats['total_users'],
            active_users=active_users,
            inactive_users=inactive_users,
            total_apps=total_apps,
            total_agents=total_agents,
            total_api_keys=total_api_keys,
            active_api_keys=active_api_keys,
            inactive_api_keys=total_api_keys - active_api_keys,
            recent_users=user_stats['recent_users_list'],
            users_with_apps=user_stats['users_with_apps']
        )
    except Exception as e:
        logger.error(f"Error retrieving system stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving system stats: {str(e)}")


@router.get(
    "/settings",
    response_model=list[SystemSettingRead],
    responses={500: {"description": "Internal server error"}},
)
async def list_settings(
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """List all system settings with resolved values and metadata"""
    try:
        service = SystemSettingsService(db)
        settings = service.get_all_settings()
        return [SystemSettingRead(**setting) for setting in settings]
    except Exception as e:
        logger.error(f"Error retrieving system settings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving system settings: {str(e)}")


@router.put(
    "/settings/{key}",
    response_model=SystemSettingRead,
    responses={
        404: {"description": "Setting not found"},
        422: {"description": "Validation error"},
        500: {"description": "Internal server error"},
    },
)
async def update_setting(
    key: str,
    update: SystemSettingUpdate,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """Update a system setting value"""
    try:
        service = SystemSettingsService(db)
        service.update_setting(key, update.value)
        
        # Get full setting with resolved value for response
        all_settings = service.get_all_settings()
        updated_setting = next((s for s in all_settings if s["key"] == key), None)
        
        if updated_setting is None:
            raise HTTPException(status_code=500, detail="Failed to retrieve updated setting")
        
        logger.info(f"Setting '{key}' updated by admin {auth_context.identity.email}")
        return SystemSettingRead(**updated_setting)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating setting '{key}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating setting: {str(e)}")


@router.delete(
    "/settings/{key}",
    responses={
        404: {"description": "Setting not found"},
        500: {"description": "Internal server error"},
    },
)
async def reset_setting(
    key: str,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """Reset a system setting to its default value"""
    try:
        service = SystemSettingsService(db)
        service.reset_setting(key)
        logger.info(f"Setting '{key}' reset to default by admin {auth_context.identity.email}")
        return {"message": f"Setting '{key}' has been reset to its default value"}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error resetting setting '{key}': {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error resetting setting: {str(e)}")


# ==================== SAAS ADMIN ENDPOINTS ====================
# These endpoints are always registered but guarded by OMNIADMIN requirement.
# SaaS-specific functionality is a no-op / returns empty data in self-managed mode.

from schemas.admin_schemas import UserAdminRead, TierOverrideRequest
from schemas.tier_config_schemas import TierConfigRead, TierConfigUpdate
from schemas.ai_service_schemas import AIServiceListItemSchema, CreateUpdateAIServiceSchema
from schemas.embedding_service_schemas import (
    EmbeddingServiceListItemSchema,
    CreateUpdateEmbeddingServiceSchema,
    SystemEmbeddingServiceImpactSchema,
)
from typing import List


@router.get("/saas/users", response_model=List[UserAdminRead])
async def list_saas_users(
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """List all users with tier, billing status, and usage stats (OMNIADMIN only)."""
    from models.user import User
    from repositories.subscription_repository import SubscriptionRepository
    from repositories.usage_record_repository import UsageRecordRepository
    from repositories.tier_config_repository import TierConfigRepository

    users = db.query(User).order_by(User.create_date.desc()).all()
    sub_repo = SubscriptionRepository(db)
    usage_repo = UsageRecordRepository(db)
    tier_repo = TierConfigRepository(db)
    result = []
    for user in users:
        sub = sub_repo.get_by_user_id(user.user_id)
        tier = "free"
        billing_status = "none"
        stripe_customer_id = None
        if sub:
            tier = sub.admin_override_tier or (sub.tier.value if sub.tier else "free")
            billing_status = sub.billing_status.value if sub.billing_status else "none"
            stripe_customer_id = sub.stripe_customer_id

        usage = usage_repo.get_current(user.user_id)
        call_count = usage.call_count if usage else 0
        call_limit = tier_repo.get_limit(tier, "llm_calls")
        owned_apps = db.query(App).filter(App.owner_id == user.user_id).count()

        result.append(UserAdminRead(
            user_id=user.user_id,
            email=user.email or "",
            name=user.name,
            is_active=user.is_active,
            auth_method=getattr(user, 'auth_method', 'oidc'),
            email_verified=getattr(user, 'email_verified', True),
            tier=tier,
            billing_status=billing_status,
            stripe_customer_id=stripe_customer_id,
            call_count=call_count,
            call_limit=call_limit,
            owned_apps_count=owned_apps,
        ))
    return result


@router.put("/saas/users/{user_id}/tier")
async def override_user_tier(
    user_id: int,
    body: TierOverrideRequest,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """Manually override a user's subscription tier (OMNIADMIN only)."""
    from repositories.subscription_repository import SubscriptionRepository
    from services.freeze_service import FreezeService

    sub_repo = SubscriptionRepository(db)
    sub = sub_repo.get_by_user_id(user_id)
    if not sub:
        sub = sub_repo.create(user_id)

    sub_repo.set_admin_override(user_id, body.tier)
    db.commit()

    # Recalculate freeze state based on new effective tier
    try:
        FreezeService.apply_freeze(db, user_id, body.tier)
        db.commit()
    except Exception as exc:
        logger.error("FreezeService failed after tier override for user %s: %s", user_id, exc)

    return {"message": f"Tier overridden to '{body.tier}' for user {user_id}"}


@router.get("/saas/tier-config", response_model=List[TierConfigRead])
async def get_tier_config(
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """Return all tier limit configuration entries (OMNIADMIN only)."""
    from repositories.tier_config_repository import TierConfigRepository
    repo = TierConfigRepository(db)
    return repo.get_all()


@router.put("/saas/tier-config")
async def update_tier_config(
    body: TierConfigUpdate,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """Create or update a tier limit configuration entry (OMNIADMIN only)."""
    from repositories.tier_config_repository import TierConfigRepository
    repo = TierConfigRepository(db)
    row = repo.upsert(body.tier, body.resource_type, body.limit_value)
    db.commit()
    return {"id": row.id, "tier": row.tier, "resource_type": row.resource_type, "limit_value": row.limit_value}


@router.get("/system-ai-services", response_model=List[AIServiceListItemSchema])
async def list_system_ai_services(
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """List all platform-level AI Services (OMNIADMIN only, available in all deployment modes)."""
    from repositories.ai_service_repository import AIServiceRepository
    from services.ai_service_service import AIServiceService
    services = AIServiceRepository.get_system_services(db)
    return [AIServiceService._to_list_item(svc, is_system=True) for svc in services]


@router.post("/system-ai-services", response_model=AIServiceListItemSchema, status_code=201)
async def create_system_ai_service(
    body: CreateUpdateAIServiceSchema,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """Create a new platform-level AI Service (OMNIADMIN only, available in all deployment modes)."""
    from models.ai_service import AIService
    from repositories.ai_service_repository import AIServiceRepository
    from services.ai_service_service import AIServiceService
    from datetime import datetime

    svc = AIService()
    svc.app_id = None  # NULL = system/platform service
    svc.name = body.name
    svc.provider = body.provider
    svc.description = body.model_name  # model name stored in description
    svc.api_key = body.api_key
    svc.endpoint = body.base_url or ""
    svc.create_date = datetime.now()
    svc = AIServiceRepository.create(db, svc)
    return AIServiceService._to_list_item(svc, is_system=True)


@router.put("/system-ai-services/{service_id}", response_model=AIServiceListItemSchema)
async def update_system_ai_service(
    service_id: int,
    body: CreateUpdateAIServiceSchema,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """Update a platform-level AI Service (OMNIADMIN only, available in all deployment modes)."""
    from repositories.ai_service_repository import AIServiceRepository
    from services.ai_service_service import AIServiceService
    from utils.secret_utils import is_masked_key

    svc = AIServiceRepository.get_by_id(db, service_id)
    if not svc or svc.app_id is not None:
        raise HTTPException(status_code=404, detail="System AI service not found")

    svc.name = body.name
    svc.provider = body.provider
    svc.description = body.model_name
    if not is_masked_key(body.api_key):
        svc.api_key = body.api_key
    svc.endpoint = body.base_url or ""
    svc = AIServiceRepository.update(db, svc)
    return AIServiceService._to_list_item(svc, is_system=True)


@router.delete("/system-ai-services/{service_id}", status_code=204)
async def delete_system_ai_service(
    service_id: int,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """Delete a platform-level AI Service (OMNIADMIN only, available in all deployment modes)."""
    from repositories.ai_service_repository import AIServiceRepository

    svc = AIServiceRepository.get_by_id(db, service_id)
    if not svc or svc.app_id is not None:
        raise HTTPException(status_code=404, detail="System AI service not found")
    AIServiceRepository.delete(db, svc)


@router.get("/system-embedding-services", response_model=List[EmbeddingServiceListItemSchema])
async def list_system_embedding_services(
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """List all platform-level Embedding Services (OMNIADMIN only)."""
    from repositories.embedding_service_repository import EmbeddingServiceRepository
    from services.embedding_service_service import EmbeddingServiceService
    services = EmbeddingServiceRepository.get_system_services(db)
    return [EmbeddingServiceService._to_list_item(svc, is_system=True) for svc in services]


@router.post("/system-embedding-services", response_model=EmbeddingServiceListItemSchema, status_code=201)
async def create_system_embedding_service(
    body: CreateUpdateEmbeddingServiceSchema,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """Create a new platform-level Embedding Service (OMNIADMIN only)."""
    from models.embedding_service import EmbeddingService
    from repositories.embedding_service_repository import EmbeddingServiceRepository
    from services.embedding_service_service import EmbeddingServiceService
    from datetime import datetime

    svc = EmbeddingService()
    svc.app_id = None  # NULL = system/platform service
    svc.name = body.name
    svc.provider = body.provider
    svc.description = body.model_name  # model name stored in description
    svc.api_key = body.api_key
    svc.endpoint = body.base_url or ""
    svc.create_date = datetime.now()
    svc = EmbeddingServiceRepository.create(db, svc)
    return EmbeddingServiceService._to_list_item(svc, is_system=True)


@router.put("/system-embedding-services/{service_id}", response_model=EmbeddingServiceListItemSchema)
async def update_system_embedding_service(
    service_id: int,
    body: CreateUpdateEmbeddingServiceSchema,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """Update a platform-level Embedding Service (OMNIADMIN only)."""
    from repositories.embedding_service_repository import EmbeddingServiceRepository
    from services.embedding_service_service import EmbeddingServiceService
    from utils.secret_utils import is_masked_key

    svc = EmbeddingServiceRepository.get_by_id(db, service_id)
    if not svc or svc.app_id is not None:
        raise HTTPException(status_code=404, detail="System embedding service not found")

    svc.name = body.name
    svc.provider = body.provider
    svc.description = body.model_name
    if not is_masked_key(body.api_key):
        svc.api_key = body.api_key
    svc.endpoint = body.base_url or ""
    svc = EmbeddingServiceRepository.update(db, svc)
    return EmbeddingServiceService._to_list_item(svc, is_system=True)


@router.get("/system-embedding-services/{service_id}/impact", response_model=SystemEmbeddingServiceImpactSchema)
async def get_system_embedding_service_impact(
    service_id: int,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """Get deletion impact for a platform-level Embedding Service (OMNIADMIN only)."""
    from repositories.embedding_service_repository import EmbeddingServiceRepository
    from schemas.embedding_service_schemas import AffectedSiloSchema
    from models.silo import Silo
    from models.app import App

    svc = EmbeddingServiceRepository.get_by_id(db, service_id)
    if not svc or svc.app_id is not None:
        raise HTTPException(status_code=404, detail="System embedding service not found")

    rows = db.query(Silo, App).join(App, Silo.app_id == App.app_id).filter(
        Silo.embedding_service_id == service_id
    ).all()

    affected_silos = [
        AffectedSiloSchema(
            silo_id=silo.silo_id,
            silo_name=silo.name,
            app_id=app.app_id,
            app_name=app.name,
        )
        for silo, app in rows
    ]
    affected_apps_count = len({s.app_id for s in affected_silos})

    return SystemEmbeddingServiceImpactSchema(
        service_id=svc.service_id,
        service_name=svc.name,
        affected_silos_count=len(affected_silos),
        affected_apps_count=affected_apps_count,
        affected_silos=affected_silos,
    )


@router.delete("/system-embedding-services/{service_id}", status_code=204)
async def delete_system_embedding_service(
    service_id: int,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """Delete a platform-level Embedding Service (OMNIADMIN only)."""
    from repositories.embedding_service_repository import EmbeddingServiceRepository
    from models.silo import Silo

    svc = EmbeddingServiceRepository.get_by_id(db, service_id)
    if not svc or svc.app_id is not None:
        raise HTTPException(status_code=404, detail="System embedding service not found")

    # Nullify references in silos before deleting
    db.query(Silo).filter(Silo.embedding_service_id == service_id).update(
        {Silo.embedding_service_id: None}, synchronize_session='fetch'
    )
    EmbeddingServiceRepository.delete(db, svc)
