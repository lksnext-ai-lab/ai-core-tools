"""Tier enforcement service: limit checks before resource creation.

All methods are no-ops (return immediately) when running in self-managed mode.
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException, status

from deployment_mode import is_self_managed
from models.app import App
from models.agent import Agent
from models.silo import Silo
from models.skill import Skill
from models.mcp_server import MCPServer
from models.app_collaborator import AppCollaborator
from repositories.subscription_repository import SubscriptionRepository
from repositories.tier_config_repository import TierConfigRepository
from repositories.usage_record_repository import UsageRecordRepository
from utils.logger import get_logger

logger = get_logger(__name__)


def _get_effective_tier(db: Session, user_id: int) -> str:
    """Return the user's effective tier string (respecting admin override)."""
    sub_repo = SubscriptionRepository(db)
    sub = sub_repo.get_by_user_id(user_id)
    if not sub:
        return "free"
    if sub.admin_override_tier:
        return sub.admin_override_tier
    return sub.tier.value if sub.tier else "free"


class TierEnforcementService:

    @staticmethod
    def check_app_limit(db: Session, user_id: int) -> None:
        """Raise HTTP 403 if the user has reached their app limit."""
        if is_self_managed():
            return

        tier = _get_effective_tier(db, user_id)
        tier_repo = TierConfigRepository(db)
        limit = tier_repo.get_limit(tier, "apps")

        if limit < 0:  # -1 = unlimited
            return

        current_count = db.query(func.count(App.app_id)).filter(App.owner_id == user_id).scalar() or 0
        if current_count >= limit:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"App limit reached ({current_count}/{limit}) for your {tier} plan. "
                    "Please upgrade to create more apps."
                ),
            )

    @staticmethod
    def check_resource_limit(db: Session, app_id: int, resource_type: str) -> None:
        """Raise HTTP 403 if the app has reached the per-app resource limit.

        resource_type: one of 'agents', 'silos', 'skills', 'mcp_servers', 'collaborators'
        """
        if is_self_managed():
            return

        # Determine the owner of this app to get their tier
        app = db.query(App).filter(App.app_id == app_id).first()
        if not app:
            return

        tier = _get_effective_tier(db, app.owner_id)
        tier_repo = TierConfigRepository(db)
        limit = tier_repo.get_limit(tier, resource_type)

        if limit < 0:  # -1 = unlimited
            return

        # Count current resources
        model_map = {
            "agents": (Agent, Agent.app_id),
            "silos": (Silo, Silo.app_id),
            "skills": (Skill, Skill.app_id),
            "mcp_servers": (MCPServer, MCPServer.app_id),
            "collaborators": (AppCollaborator, AppCollaborator.app_id),
        }
        model_info = model_map.get(resource_type)
        if not model_info:
            return

        model_cls, fk_col = model_info
        current_count = db.query(func.count(model_cls.__mapper__.primary_key[0])).filter(fk_col == app_id).scalar() or 0

        if current_count >= limit:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"{resource_type.replace('_', ' ').title()} limit reached ({current_count}/{limit}) "
                    f"for your {tier} plan. Please upgrade to add more."
                ),
            )

    @staticmethod
    def check_system_llm_quota(db: Session, user_id: int) -> None:
        """Raise HTTP 429 if the user has exhausted their system LLM call quota."""
        if is_self_managed():
            return

        tier = _get_effective_tier(db, user_id)
        tier_repo = TierConfigRepository(db)
        limit = tier_repo.get_limit(tier, "llm_calls")

        if limit < 0:  # -1 = unlimited
            return

        usage_repo = UsageRecordRepository(db)
        usage = usage_repo.get_current(user_id)
        call_count = usage.call_count if usage else 0

        if limit > 0 and call_count >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Monthly system LLM quota exhausted ({call_count}/{limit}). "
                    "Your own AI Service keys are unaffected. Please upgrade to continue."
                ),
            )

    @staticmethod
    def check_ai_service_allowed(db: Session, user_id: int) -> None:
        """Raise HTTP 403 if a Free tier user attempts to create their own AI Service."""
        if is_self_managed():
            return

        tier = _get_effective_tier(db, user_id)
        if tier == "free":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Free tier users cannot create custom AI Service API keys. Please upgrade to Starter or Pro.",
            )
