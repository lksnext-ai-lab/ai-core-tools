from fastapi import APIRouter

# Import internal routers
# Note: Most routers are imported by apps router for /internal/apps/{app_id}/... structure
from .apps import apps_router
from .collaboration import collaboration_router
from .admin import router as admin_router
from .version import version_router

# Create the main internal router
internal_router = APIRouter()

# Include sub-routers based on frontend expectations
# Most routes are nested under apps: /internal/apps/{app_id}/...
# Exceptions: collaboration, admin, version (standalone)
internal_router.include_router(apps_router, prefix="/apps")
internal_router.include_router(collaboration_router, prefix="/collaboration")
internal_router.include_router(admin_router, prefix="/admin")
internal_router.include_router(version_router, prefix="/version")