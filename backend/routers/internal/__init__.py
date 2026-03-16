from fastapi import APIRouter

# Import internal routers
# Note: Most routers are imported by apps router for /internal/apps/{app_id}/... structure
from .apps import apps_router
from .collaboration import collaboration_router
from .admin import router as admin_router
from .version import version_router
from .apps_usage import router as apps_usage_router
from .conversations import router as conversations_router
from .auth import router as auth_router
from .user import router as user_router
from .marketplace import marketplace_router
from .config import router as config_router

# Create the main internal router
internal_router = APIRouter()

# Include sub-routers based on frontend expectations
# Most routes are nested under apps: /internal/apps/{app_id}/...
# Exceptions: collaboration, admin, version, apps_usage, conversations, auth, user (standalone)
internal_router.include_router(apps_router, prefix="/apps")
internal_router.include_router(collaboration_router, prefix="/collaboration")
internal_router.include_router(admin_router, prefix="/admin")
internal_router.include_router(version_router, prefix="/version")
internal_router.include_router(apps_usage_router, prefix="/usage-stats")
internal_router.include_router(conversations_router)
internal_router.include_router(auth_router, prefix="/auth")
internal_router.include_router(user_router)
internal_router.include_router(marketplace_router)
internal_router.include_router(config_router)

# SaaS-specific routers (conditionally registered based on deployment mode)
from deployment_mode import is_saas_mode
if is_saas_mode():
    from .saas_auth import router as saas_auth_router
    from .subscription import router as subscription_router
    internal_router.include_router(saas_auth_router, prefix="/auth")
    internal_router.include_router(subscription_router)
