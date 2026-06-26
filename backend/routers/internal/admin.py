from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from lks_idprovider import AuthContext
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db.database import get_db
from models.agent import Agent
from models.api_key import APIKey
from models.app import App
from routers.internal.auth_utils import get_current_user_oauth
from schemas.admin_schemas import (
    AppTransferSummary,
    DeleteUserRequest,
    MarketplaceQuotaResetResponse,
    OwnedAppsConflictResponse,
    OwnedAppConflictItem,
    SetPlatformRoleRequest,
    SystemStatsResponse,
    TransferOwnerRequest,
    UserDetailResponse,
    UserListResponse,
)
from schemas.system_setting_schemas import SystemSettingRead, SystemSettingUpdate
from services.marketplace_quota_service import MarketplaceQuotaService
from services.system_settings_service import SystemSettingsService
from services.user_service import UserService
from utils.config import is_omniadmin
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["admin"])

USER_NOT_FOUND = "User not found"
SYSTEM_AI_SERVICE_NOT_FOUND = "System AI service not found"
SYSTEM_EMBEDDING_SERVICE_NOT_FOUND = "System embedding service not found"


async def require_admin(
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
):
    """Dependency to require omniadmin access (env var or DB platform_role)"""
    email = auth_context.identity.email
    if is_omniadmin(email):
        return auth_context
    user = UserService.get_user_by_email(db, email)
    if user and user.platform_role == 'admin':
        return auth_context
    raise HTTPException(status_code=403, detail="Admin access required")


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
            is_active=user.is_active,
            platform_role=user.platform_role or 'editor',
            is_omniadmin=is_omniadmin(user.email),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving user: {str(e)}")


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Bad request — self-deletion or invalid transfer recipient"},
        403: {"description": "Forbidden — target user is an omniadmin"},
        404: {"description": "User not found"},
        409: {
            "description": "Conflict — user owns apps (mode=block) or tier limit exceeded",
            "model": OwnedAppsConflictResponse,
        },
        501: {"description": "Not implemented — transfer_apps stub not yet wired"},
        500: {"description": "Internal server error"},
    },
)
async def delete_user(
    user_id: int,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    body: Optional[DeleteUserRequest] = None,
    mode: Annotated[
        Optional[str],
        Query(description="Deletion mode: block | cascade_apps | transfer_apps (query-param fallback)"),
    ] = None,
    transfer_to_user_id: Annotated[
        Optional[int],
        Query(description="Recipient user_id for mode=transfer_apps (query-param fallback)"),
    ] = None,
) -> dict:
    """Delete a user account and orchestrate all associated data.

    Body fields take precedence over query-param fallbacks; omitting both defaults to ``mode='block'``.
    Actor identity is always resolved from the session (NFR-1 / IDOR prevention).
    """
    from services.user_deletion_errors import (
        OmniadminDeletionError,
        OwnedAppsPresentError,
        SelfDeletionError,
        UserNotFoundError,
    )
    from services.app_ownership_errors import (
        TierLimitExceededError,
        TransferRecipientInvalidError,
    )

    _VALID_MODES = {"block", "cascade_apps", "transfer_apps"}
    effective_mode: str = "block"
    effective_transfer_to: Optional[int] = None

    if body is not None:
        effective_mode = body.mode
        effective_transfer_to = body.transfer_to_user_id
    elif mode is not None:
        if mode not in _VALID_MODES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid mode '{mode}'. Must be one of: {sorted(_VALID_MODES)}.",
            )
        effective_mode = mode
        effective_transfer_to = transfer_to_user_id
    actor_user_id: int = int(auth_context.identity.id)

    try:
        UserService.delete_user(
            db,
            user_id,
            actor_user_id=actor_user_id,
            mode=effective_mode,  # type: ignore[arg-type]
            transfer_to_user_id=effective_transfer_to,
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    except SelfDeletionError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)
    except OmniadminDeletionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=exc.message)
    except OwnedAppsPresentError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=OwnedAppsConflictResponse(
                detail=exc.message,
                owned_apps=[
                    OwnedAppConflictItem(app_id=a["app_id"], name=a["name"])
                    for a in exc.owned_apps
                ],
            ).model_dump(),
        )
    except TransferRecipientInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)
    except TierLimitExceededError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message)
    except NotImplementedError as exc:
        logger.warning(
            "delete_user: transfer_apps stub hit — user_id=%s actor=%s",
            user_id,
            auth_context.identity.email,
        )
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(exc) or "transfer_apps mode is not yet implemented.",
        )
    except HTTPException:
        raise
    except Exception:
        logger.error(
            "delete_user: unexpected error user_id=%s actor=%s",
            user_id,
            auth_context.identity.email,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user due to an unexpected error.",
        )

    logger.info(
        "admin:delete_user user_id=%s mode=%s actor=%s",
        user_id,
        effective_mode,
        auth_context.identity.email,
    )
    return {"message": f"User {user_id} and all associated data have been deleted successfully"}


@router.post(
    "/apps/{app_id}/transfer",
    response_model=AppTransferSummary,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Recipient user is invalid (inactive, same as current owner, or does not exist)"},
        404: {"description": "App not found"},
        409: {"description": "Transfer would exceed the recipient's SaaS app-count limit"},
    },
)
async def transfer_app_ownership(
    app_id: int,
    body: TransferOwnerRequest,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> AppTransferSummary:
    """Immediately reassign app ownership to another user (OMNIADMIN only, no handshake)."""
    from services.app_ownership_service import AppOwnershipService
    from services.app_ownership_errors import (
        AppNotFoundError,
        TierLimitExceededError,
        TransferRecipientInvalidError,
    )

    actor_user_id: int = int(auth_context.identity.id)

    try:
        app, previous_owner_id = AppOwnershipService.transfer_direct(
            db,
            app_id=app_id,
            new_owner_id=body.new_owner_id,
            actor_user_id=actor_user_id,
        )
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.message)
    except TransferRecipientInvalidError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)
    except TierLimitExceededError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message)
    except HTTPException:
        raise
    except Exception:
        logger.error(
            "transfer_app_ownership: unexpected error app_id=%s new_owner_id=%s actor=%s",
            app_id,
            body.new_owner_id,
            auth_context.identity.email,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Transfer failed due to an unexpected error.")

    logger.info(
        "admin:transfer_app app_id=%s previous_owner_id=%s new_owner_id=%s by=%s",
        app_id,
        previous_owner_id,
        body.new_owner_id,
        auth_context.identity.email,
    )

    return AppTransferSummary(
        app_id=app.app_id,
        name=app.name,
        previous_owner_id=previous_owner_id,
        new_owner_id=app.owner_id,
    )


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
    "/users/{user_id}/set-platform-role",
    responses={
        400: {"description": "Bad request — invalid role value or self-change attempt"},
        403: {"description": "Forbidden — cannot modify an omniadmin"},
        404: {"description": "User not found"},
        500: {"description": "Internal server error"},
    },
)
async def set_user_platform_role(
    user_id: int,
    body: SetPlatformRoleRequest,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """Set a user's platform role (viewer, editor, or admin)"""
    try:
        result = UserService.set_platform_role(db, user_id, body.role, auth_context.identity.email)
        user = result["user"]
        warnings = result["warnings"]
        logger.info(f"Platform role set to '{body.role}' for user {user.email} by {auth_context.identity.email}")
        return {
            "message": f"Platform role updated to '{body.role}' for {user.email}",
            "user_id": user.user_id,
            "platform_role": user.platform_role,
            "warnings": warnings,
        }
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error setting platform role for user {user_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error setting platform role: {str(e)}")


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
    """Reset a user's current-month marketplace quota to 0 (OMNIADMIN only)."""
    try:
        user = UserService.get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail=USER_NOT_FOUND)
        
        previous_count = MarketplaceQuotaService.get_current_month_usage(user_id, db)
        try:
            MarketplaceQuotaService.reset_user_current_month_usage(user_id, db)
        except ValueError:
            # No usage record for the current month — idempotent, already at 0.
            logger.info(
                f"OMNIADMIN {auth_context.identity.email} attempted to reset marketplace quota "
                f"for user {user.email} (ID: {user_id}) but no usage record exists. "
                f"User already has 0 usage for current month."
            )
        
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
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
        user_stats = UserService.get_user_stats(db)
        active_users = UserService.get_active_users_count(db)
        inactive_users = UserService.get_inactive_users_count(db)
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


from schemas.admin_schemas import UserAdminRead, TierOverrideRequest
from schemas.tier_config_schemas import TierConfigRead, TierConfigUpdate
from schemas.ai_service_schemas import AIServiceListItemSchema, AIServiceDetailSchema, CreateUpdateAIServiceSchema
from schemas.provider_models_schemas import (
    ListProviderModelsRequest,
    ListProviderModelsResponse,
)
from services.provider_models_service import (
    PROVIDER_ERROR_STATUS,
    ProviderModelsService,
)
from tools.ai.provider_model_clients import ProviderListingError
from schemas.embedding_service_schemas import (
    EmbeddingServiceListItemSchema,
    EmbeddingServiceDetailSchema,
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


@router.get("/system-ai-services", response_model=List[AIServiceDetailSchema])
async def list_system_ai_services(
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """List all platform-level AI Services (OMNIADMIN only, available in all deployment modes)."""
    from repositories.ai_service_repository import AIServiceRepository
    from utils.secret_utils import mask_api_key
    from tools.aws_bedrock_utils import parse_extra_config
    services = AIServiceRepository.get_system_services(db)
    return [
        AIServiceDetailSchema(
            service_id=svc.service_id,
            name=svc.name,
            provider=svc.provider.value if hasattr(svc.provider, 'value') else svc.provider,
            model_name=svc.description or "",
            api_key=mask_api_key(svc.api_key) if svc.api_key else "",
            base_url=svc.endpoint or "",
            created_at=svc.create_date,
            aws_access_key_id=parse_extra_config(svc.extra_config).get("aws_access_key_id"),
            aws_region=parse_extra_config(svc.extra_config).get("aws_region"),
        )
        for svc in services
    ]


@router.get("/system-ai-services/{service_id}", response_model=AIServiceDetailSchema)
async def get_system_ai_service(
    service_id: int,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """Get a single platform-level AI Service by ID (OMNIADMIN only)."""
    from repositories.ai_service_repository import AIServiceRepository
    from utils.secret_utils import mask_api_key
    from tools.aws_bedrock_utils import parse_extra_config

    svc = AIServiceRepository.get_by_id(db, service_id)
    if not svc or svc.app_id is not None:
        raise HTTPException(status_code=404, detail=SYSTEM_AI_SERVICE_NOT_FOUND)
    extra_cfg = parse_extra_config(svc.extra_config)
    return AIServiceDetailSchema(
        service_id=svc.service_id,
        name=svc.name,
        provider=svc.provider.value if hasattr(svc.provider, 'value') else svc.provider,
        model_name=svc.description or "",
        api_key=mask_api_key(svc.api_key) if svc.api_key else "",
        base_url=svc.endpoint or "",
        created_at=svc.create_date,
        aws_access_key_id=extra_cfg.get("aws_access_key_id"),
        aws_region=extra_cfg.get("aws_region"),
    )


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
    from tools.aws_bedrock_utils import build_extra_config
    from datetime import datetime

    svc = AIService()
    svc.app_id = None
    svc.name = body.name
    svc.provider = body.provider
    svc.description = body.model_name  # stored in description column
    svc.api_key = body.api_key
    svc.endpoint = body.base_url or ""
    svc.extra_config = build_extra_config(body.aws_access_key_id, body.aws_region)
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
    from tools.aws_bedrock_utils import build_extra_config

    svc = AIServiceRepository.get_by_id(db, service_id)
    if not svc or svc.app_id is not None:
        raise HTTPException(status_code=404, detail=SYSTEM_AI_SERVICE_NOT_FOUND)

    svc.name = body.name
    svc.provider = body.provider
    svc.description = body.model_name
    if not is_masked_key(body.api_key):
        svc.api_key = body.api_key
    svc.endpoint = body.base_url or ""
    svc.extra_config = build_extra_config(body.aws_access_key_id, body.aws_region)
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
        raise HTTPException(status_code=404, detail=SYSTEM_AI_SERVICE_NOT_FOUND)
    AIServiceRepository.delete(db, svc)


@router.get("/system-embedding-services", response_model=List[EmbeddingServiceDetailSchema])
async def list_system_embedding_services(
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    """List all platform-level Embedding Services (OMNIADMIN only)."""
    from repositories.embedding_service_repository import EmbeddingServiceRepository
    from utils.secret_utils import mask_api_key
    from tools.aws_bedrock_utils import parse_extra_config
    services = EmbeddingServiceRepository.get_system_services(db)
    return [
        EmbeddingServiceDetailSchema(
            service_id=svc.service_id,
            name=svc.name,
            provider=svc.provider,
            model_name=svc.description or "",
            api_key=mask_api_key(svc.api_key) if svc.api_key else "",
            base_url=svc.endpoint or "",
            api_version=svc.api_version,
            created_at=svc.create_date,
            aws_access_key_id=parse_extra_config(svc.extra_config).get("aws_access_key_id"),
            aws_region=parse_extra_config(svc.extra_config).get("aws_region"),
        )
        for svc in services
    ]


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
    from tools.aws_bedrock_utils import build_extra_config
    from datetime import datetime

    svc = EmbeddingService()
    svc.app_id = None
    svc.name = body.name
    svc.provider = body.provider
    svc.description = body.model_name  # stored in description column
    svc.api_key = body.api_key
    svc.endpoint = body.base_url or ""
    svc.api_version = body.api_version
    svc.extra_config = build_extra_config(body.aws_access_key_id, body.aws_region)
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
    from tools.aws_bedrock_utils import build_extra_config

    svc = EmbeddingServiceRepository.get_by_id(db, service_id)
    if not svc or svc.app_id is not None:
        raise HTTPException(status_code=404, detail=SYSTEM_EMBEDDING_SERVICE_NOT_FOUND)

    svc.name = body.name
    svc.provider = body.provider
    svc.description = body.model_name
    if not is_masked_key(body.api_key):
        svc.api_key = body.api_key
    svc.endpoint = body.base_url or ""
    svc.api_version = body.api_version
    svc.extra_config = build_extra_config(body.aws_access_key_id, body.aws_region)
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
        raise HTTPException(status_code=404, detail=SYSTEM_EMBEDDING_SERVICE_NOT_FOUND)

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
        raise HTTPException(status_code=404, detail=SYSTEM_EMBEDDING_SERVICE_NOT_FOUND)

    db.query(Silo).filter(Silo.embedding_service_id == service_id).update(
        {Silo.embedding_service_id: None}, synchronize_session='fetch'
    )
    EmbeddingServiceRepository.delete(db, svc)


@router.post(
    "/system-ai-services/list-models",
    response_model=ListProviderModelsResponse,
)
async def list_system_ai_service_provider_models(
    body: ListProviderModelsRequest,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
):
    """List models for a provider using the credentials in the body (System AI Service wizard, OMNIADMIN only)."""
    body.purpose = "chat"
    try:
        return ProviderModelsService.list_models(body)
    except ProviderListingError as exc:
        raise HTTPException(
            status_code=PROVIDER_ERROR_STATUS.get(exc.code, 500),
            detail=exc.message,
        )
    except Exception as e:
        logger.error(
            "Unexpected error listing system AI models (provider: %s): %s",
            body.provider,
            type(e).__name__,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to list provider models")


@router.post(
    "/system-embedding-services/list-models",
    response_model=ListProviderModelsResponse,
)
async def list_system_embedding_service_provider_models(
    body: ListProviderModelsRequest,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
):
    """List embedding models for a provider using the credentials in the body (System Embedding Service wizard, OMNIADMIN only)."""
    body.purpose = "embedding"
    try:
        return ProviderModelsService.list_models(body)
    except ProviderListingError as exc:
        raise HTTPException(
            status_code=PROVIDER_ERROR_STATUS.get(exc.code, 500),
            detail=exc.message,
        )
    except Exception as e:
        logger.error(
            "Unexpected error listing system embedding models (provider: %s): %s",
            body.provider,
            type(e).__name__,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to list provider models")


@router.post("/system-ai-services/test-connection")
async def test_system_ai_service_connection_with_config(
    config: CreateUpdateAIServiceSchema,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    service_id: Optional[int] = Query(None, description="Edit-mode: recover stored API key when the request sends a masked placeholder"),
):
    """Test a system AI service connection (OMNIADMIN). Falls back to the stored key when api_key is empty or masked."""
    from services.ai_service_service import AIServiceService
    from repositories.ai_service_repository import AIServiceRepository
    from utils.secret_utils import is_masked_key
    from core.export_constants import PLACEHOLDER_API_KEY
    from tools.aws_bedrock_utils import build_extra_config

    try:
        api_key = config.api_key or ""
        if service_id is not None and (
            not api_key
            or api_key == PLACEHOLDER_API_KEY
            or is_masked_key(api_key)
        ):
            stored = AIServiceRepository.get_by_id(db, service_id)
            # Only use stored key for system services (app_id IS NULL) — never leak an app-scoped key.
            if stored and stored.app_id is None and stored.api_key:
                api_key = stored.api_key

        service_config = {
            "provider": config.provider,
            "description": config.model_name,
            "api_key": api_key,
            "endpoint": config.base_url,
            "api_version": getattr(config, "api_version", None),
            "extra_config": build_extra_config(
                getattr(config, "aws_access_key_id", None),
                getattr(config, "aws_region", None),
            ),
        }
        result = AIServiceService.test_connection_with_config(service_config)
        if isinstance(result, dict) and len(str(result.get("response", ""))) > 500:
            result["response"] = str(result["response"])[:500] + "... (truncated)"
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error testing system AI service connection (provider: %s): %s",
            config.provider,
            type(e).__name__,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Test failed")


from schemas.local_auth_schemas import AdminCreateUserRequest, AdminSetPasswordRequest
from services.auth.credential_service import (
    CredentialError as _CredentialError,
    CredentialService as _CredentialService,
    UserAlreadyExistsError as _UserAlreadyExistsError,
)
from services.auth.refresh_service import RefreshService as _RefreshService
from utils.config import Config as _Config


def _set_password_token_expires_at() -> str:
    """Compute the ISO-8601 expiry timestamp for a set-password token."""
    max_age_hours: int = _Config.get_int_env_var(
        "LOCAL_SET_PASSWORD_TOKEN_MAX_AGE_HOURS", default=48
    )
    return (datetime.now(timezone.utc) + timedelta(hours=max_age_hours)).isoformat()


class _LocalUserCreatedResponse(BaseModel):
    """Response returned to an admin after creating a LOCAL auth user account."""

    user_id: int
    email: str
    name: Optional[str]
    set_password_token: str
    expires_at: str


class _ResetLinkResponse(BaseModel):
    """Response returned to an admin when issuing a reset link."""

    set_password_token: str
    expires_at: str


class _PasswordUpdatedResponse(BaseModel):
    """Response for admin set-password."""

    message: str


class _SessionsRevokedResponse(BaseModel):
    """Response for admin revoke-sessions."""

    message: str


@router.post(
    "/users/local",
    response_model=_LocalUserCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create LOCAL auth user (admin)",
    description=(
        "Create a new LOCAL auth user account and return a one-time set-password "
        "token (FR-C4/FR-D1/AD-12). The token is returned in the response body for "
        "the admin to hand to the user. It is NOT logged."
    ),
)
async def create_local_user(
    body: AdminCreateUserRequest,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> _LocalUserCreatedResponse:
    """Create a LOCAL auth user and issue a first-time set-password token. Returns 404 in OIDC mode."""
    from utils.auth_config import AuthConfig

    if AuthConfig.LOGIN_MODE != "LOCAL":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")

    try:
        user = await _CredentialService.admin_create_user(db, email=str(body.email), name=body.name)
    except _UserAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    try:
        token = _CredentialService.issue_set_password_token(db, user.user_id)
    except _CredentialError as exc:
        logger.error("admin:create_local_user token_issue_failed user_id=%s — %s", user.user_id, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to issue setup link.")
    except Exception as exc:
        logger.error("admin:create_local_user unexpected user_id=%s — %s", user.user_id, type(exc).__name__, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to issue setup link.")

    logger.info(
        "admin:create_local_user user_id=%s email=%s by=%s",
        user.user_id,
        user.email,
        auth_context.identity.email,
    )

    return _LocalUserCreatedResponse(
        user_id=user.user_id,
        email=user.email,
        name=user.name,
        set_password_token=token,
        expires_at=_set_password_token_expires_at(),
    )


@router.post(
    "/users/{user_id}/set-password",
    response_model=_PasswordUpdatedResponse,
    status_code=status.HTTP_200_OK,
    summary="Admin: forcibly set user password",
    description=(
        "Directly set a LOCAL auth user's password (emergency admin reset). "
        "Resets lockout state and revokes all existing sessions."
    ),
)
async def admin_set_user_password(
    user_id: int,
    body: AdminSetPasswordRequest,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> _PasswordUpdatedResponse:
    """Forcibly set a LOCAL auth user's password (admin emergency reset). Returns 404 in OIDC mode."""
    from utils.auth_config import AuthConfig

    if AuthConfig.LOGIN_MODE != "LOCAL":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")

    user = UserService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)

    try:
        await _CredentialService.admin_set_password(
            db, user_id=user_id, new_password=body.new_password.get_secret_value()
        )
    except _CredentialError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    logger.info(
        "admin:set_password user_id=%s by=%s",
        user_id,
        auth_context.identity.email,
    )
    return _PasswordUpdatedResponse(message="Password updated.")


@router.post(
    "/users/{user_id}/reset-link",
    response_model=_ResetLinkResponse,
    status_code=status.HTTP_200_OK,
    summary="Admin: issue set-password reset link",
    description=(
        "Generate a new one-time set-password token for an existing LOCAL auth user. "
        "Returns the token in the response body for the admin to forward to the user."
    ),
)
async def issue_reset_link(
    user_id: int,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> _ResetLinkResponse:
    """Issue a new set-password token for a LOCAL auth user. Returns 404 in OIDC mode."""
    from utils.auth_config import AuthConfig

    if AuthConfig.LOGIN_MODE != "LOCAL":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")

    user = UserService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)

    try:
        token = _CredentialService.issue_set_password_token(db, user_id)
    except _CredentialError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    logger.info(
        "admin:reset_link_issued user_id=%s by=%s",
        user_id,
        auth_context.identity.email,
    )

    return _ResetLinkResponse(set_password_token=token, expires_at=_set_password_token_expires_at())


@router.post(
    "/users/{user_id}/revoke-sessions",
    response_model=_SessionsRevokedResponse,
    status_code=status.HTTP_200_OK,
    summary="Admin: revoke all sessions for a user",
    description="Revoke all refresh tokens for a user, forcing re-authentication on all devices.",
)
async def admin_revoke_sessions(
    user_id: int,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> _SessionsRevokedResponse:
    """Revoke all active refresh tokens for a LOCAL auth user. Returns 404 in OIDC mode."""
    from utils.auth_config import AuthConfig

    if AuthConfig.LOGIN_MODE != "LOCAL":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")

    user = UserService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=USER_NOT_FOUND)

    _RefreshService.revoke_all(db, user_id)

    logger.info(
        "admin:revoke_sessions user_id=%s by=%s",
        user_id,
        auth_context.identity.email,
    )
    return _SessionsRevokedResponse(message=f"All sessions revoked for user {user_id}.")


@router.post("/system-embedding-services/test-connection")
async def test_system_embedding_service_connection_with_config(
    config: CreateUpdateEmbeddingServiceSchema,
    auth_context: Annotated[AuthContext, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
    service_id: Annotated[Optional[int], Query(description="Edit-mode: recover stored API key when the request sends a masked placeholder")] = None,
):
    """Test a system embedding service connection (OMNIADMIN). Falls back to the stored key when api_key is empty or masked."""
    from services.embedding_service_service import EmbeddingServiceService
    from repositories.embedding_service_repository import EmbeddingServiceRepository
    from utils.secret_utils import is_masked_key
    from core.export_constants import PLACEHOLDER_API_KEY
    from tools.aws_bedrock_utils import build_extra_config

    try:
        api_key = config.api_key or ""
        if service_id is not None and (
            not api_key
            or api_key == PLACEHOLDER_API_KEY
            or is_masked_key(api_key)
        ):
            stored = EmbeddingServiceRepository.get_by_id(db, service_id)
            if stored and stored.app_id is None and stored.api_key:
                api_key = stored.api_key

        service_config = {
            "provider": config.provider,
            "description": config.model_name,
            "api_key": api_key,
            "endpoint": config.base_url,
            "api_version": config.api_version,
            "extra_config": build_extra_config(
                getattr(config, "aws_access_key_id", None),
                getattr(config, "aws_region", None),
            ),
        }
        return EmbeddingServiceService.test_connection_with_config(service_config)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error testing system embedding service connection (provider: %s): %s",
            config.provider,
            type(e).__name__,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Test failed")
