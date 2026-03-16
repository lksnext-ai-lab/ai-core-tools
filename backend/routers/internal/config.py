"""Runtime configuration endpoint — provides deployment mode info to the frontend."""
from fastapi import APIRouter
from deployment_mode import is_saas_mode

router = APIRouter(tags=["config"])


@router.get("/config")
async def get_config():
    """Return runtime configuration values for the frontend.

    Currently exposes deployment_mode so the frontend can conditionally
    show SaaS-specific UI (billing pages, registration, quota banner, etc.).
    """
    return {
        "deployment_mode": "saas" if is_saas_mode() else "self_managed",
    }
