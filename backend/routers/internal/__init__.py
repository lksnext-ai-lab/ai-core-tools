from fastapi import APIRouter, Depends

from middleware.csrf import enforce_csrf
from .auth_utils import require_editor_for_writes

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
from .platform_chatbot import platform_chatbot_router
from .capabilities import router as capabilities_router

# CSRF double-submit is internal-only; public/v1 and mcp/v1 use API-key auth.
internal_router = APIRouter(dependencies=[Depends(enforce_csrf)])

internal_router.include_router(
    apps_router,
    prefix="/apps",
    dependencies=[Depends(require_editor_for_writes)],
)
internal_router.include_router(
    collaboration_router,
    prefix="/collaboration",
    dependencies=[Depends(require_editor_for_writes)],
)
internal_router.include_router(admin_router, prefix="/admin")
internal_router.include_router(version_router, prefix="/version")
internal_router.include_router(apps_usage_router, prefix="/usage-stats")
internal_router.include_router(conversations_router)
internal_router.include_router(auth_router, prefix="/auth")
internal_router.include_router(user_router)
internal_router.include_router(marketplace_router)
internal_router.include_router(config_router)
internal_router.include_router(platform_chatbot_router, prefix="/platform-chatbot")
internal_router.include_router(capabilities_router)

from deployment_mode import is_saas_mode
if is_saas_mode():
    from .saas_auth import router as saas_auth_router
    from .subscription import router as subscription_router
    internal_router.include_router(saas_auth_router, prefix="/auth")
    internal_router.include_router(subscription_router)

from utils.auth_config import AuthConfig

# Startup guard: LOCAL+SaaS is an unsupported combination.
if is_saas_mode() and AuthConfig.LOGIN_MODE == "LOCAL":
    raise RuntimeError(
        "Unsupported configuration: AICT_DEPLOYMENT_MODE=saas and AICT_LOGIN=LOCAL "
        "cannot be used together.  LOCAL auth is the self-hosted path; SaaS mode "
        "requires OIDC or the built-in SaaS auth flow.  "
        "Set AICT_LOGIN=OIDC or AICT_DEPLOYMENT_MODE=self_managed."
    )

if AuthConfig.LOGIN_MODE == "LOCAL":
    from .local_auth import router as local_auth_router
    internal_router.include_router(local_auth_router, prefix="/auth")
