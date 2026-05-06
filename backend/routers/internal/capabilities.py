from fastapi import APIRouter, Depends
from lks_idprovider.models.auth import AuthContext
from routers.internal.auth_utils import get_current_user_oauth
from plugins.registry import plugin_registry

router = APIRouter(tags=["Capabilities"])


@router.get("/capabilities")
async def get_capabilities(
    auth_context: AuthContext = Depends(get_current_user_oauth),
):
    """Return installed plugin capabilities. Requires authentication."""
    return plugin_registry.all()
