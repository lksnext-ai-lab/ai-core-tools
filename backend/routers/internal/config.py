"""Runtime configuration endpoint — provides deployment mode info to the frontend."""
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db.database import get_db
from deployment_mode import is_saas_mode
from repositories.tier_config_repository import TierConfigRepository
from utils.auth_config import AuthConfig

router = APIRouter(tags=["config"])

_TIER_RESOURCE_TYPES = ["apps", "agents", "silos", "llm_calls", "collaborators", "mcp_servers"]
_TIERS = ["free", "starter", "pro"]


def _build_tiers(db: Session) -> dict:
    repo = TierConfigRepository(db)
    result = {}
    for tier in _TIERS:
        result[tier] = {rt: repo.get_limit(tier, rt) for rt in _TIER_RESOURCE_TYPES}
    return result


@router.get("/config")
async def get_config(db: Session = Depends(get_db)):
    """Return runtime configuration values for the frontend.

    Currently exposes deployment_mode so the frontend can conditionally
    show SaaS-specific UI (billing pages, registration, quota banner, etc.),
    and auth_mode so it can render the right login (OIDC vs local password).
    In SaaS mode also returns per-tier resource limits fetched from TierConfigRepository.
    """
    saas = is_saas_mode()
    return {
        "deployment_mode": "saas" if saas else "self_managed",
        "auth_mode": AuthConfig.LOGIN_MODE.lower(),
        "tiers": _build_tiers(db) if saas else None,
    }
