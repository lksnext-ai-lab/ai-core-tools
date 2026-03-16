"""FreezeService: apply/remove is_frozen flags when a user's tier changes."""
from sqlalchemy.orm import Session
from sqlalchemy import func

from models.app import App
from models.agent import Agent
from models.silo import Silo
from models.skill import Skill
from models.mcp_server import MCPServer
from models.app_collaborator import AppCollaborator, CollaborationRole
from repositories.tier_config_repository import TierConfigRepository
from repositories.subscription_repository import SubscriptionRepository
from utils.logger import get_logger

logger = get_logger(__name__)


def _effective_tier_for_user(db: Session, user_id: int) -> str:
    sub_repo = SubscriptionRepository(db)
    sub = sub_repo.get_by_user_id(user_id)
    if not sub:
        return "free"
    if sub.admin_override_tier:
        return sub.admin_override_tier
    return sub.tier.value if sub.tier else "free"


def _freeze_resources(resources, limit: int) -> None:
    """Given a list of resources sorted newest-first, freeze any beyond the limit."""
    for i, resource in enumerate(resources):
        should_be_frozen = (limit >= 0) and (i >= limit)
        resource.is_frozen = should_be_frozen


class FreezeService:

    @staticmethod
    def apply_freeze(db: Session, user_id: int, new_tier: str) -> None:
        """Calculate which resources exceed limits for new_tier and set is_frozen accordingly.

        Resources are sorted by created_at DESC — newest frozen first.
        """
        tier_repo = TierConfigRepository(db)

        # ── Apps (per-user) ────────────────────────────────────────────────────
        app_limit = tier_repo.get_limit(new_tier, "apps")
        apps = (
            db.query(App)
            .filter(App.owner_id == user_id)
            .order_by(App.create_date.desc())
            .all()
        )
        _freeze_resources(apps, app_limit)

        # ── Per-app resources ──────────────────────────────────────────────────
        agent_limit = tier_repo.get_limit(new_tier, "agents")
        silo_limit = tier_repo.get_limit(new_tier, "silos")
        skill_limit = tier_repo.get_limit(new_tier, "skills")
        mcp_limit = tier_repo.get_limit(new_tier, "mcp_servers")
        collab_limit = tier_repo.get_limit(new_tier, "collaborators")

        for app in apps:
            agents = (
                db.query(Agent)
                .filter(Agent.app_id == app.app_id)
                .order_by(Agent.create_date.desc())
                .all()
            )
            _freeze_resources(agents, agent_limit)

            silos = (
                db.query(Silo)
                .filter(Silo.app_id == app.app_id)
                .order_by(Silo.create_date.desc())
                .all()
            )
            _freeze_resources(silos, silo_limit)

            skills = (
                db.query(Skill)
                .filter(Skill.app_id == app.app_id)
                .order_by(Skill.create_date.desc())
                .all()
            )
            _freeze_resources(skills, skill_limit)

            mcp_servers = (
                db.query(MCPServer)
                .filter(MCPServer.app_id == app.app_id)
                .order_by(MCPServer.create_date.desc())
                .all()
            )
            _freeze_resources(mcp_servers, mcp_limit)

            # Collaborators: freeze excess (newest by invited_at), skip OWNER
            collaborators = (
                db.query(AppCollaborator)
                .filter(
                    AppCollaborator.app_id == app.app_id,
                    AppCollaborator.role != CollaborationRole.OWNER,
                )
                .order_by(AppCollaborator.invited_at.desc())
                .all()
            )
            _freeze_resources(collaborators, collab_limit - 1 if collab_limit > 0 else collab_limit)

        db.flush()

    @staticmethod
    def recalculate_on_delete(db: Session, user_id: int, resource_type: str, app_id: int = None) -> None:
        """After a resource is deleted, unfreeze the next-in-line if a slot opened up."""
        tier = _effective_tier_for_user(db, user_id)
        tier_repo = TierConfigRepository(db)
        limit = tier_repo.get_limit(tier, resource_type)

        if limit < 0:  # unlimited
            return

        if resource_type == "apps":
            apps = (
                db.query(App)
                .filter(App.owner_id == user_id)
                .order_by(App.create_date.desc())
                .all()
            )
            _freeze_resources(apps, limit)
        elif app_id is not None:
            model_map = {
                "agents": Agent,
                "silos": Silo,
                "skills": Skill,
                "mcp_servers": MCPServer,
            }
            model_cls = model_map.get(resource_type)
            if model_cls:
                resources = (
                    db.query(model_cls)
                    .filter(model_cls.app_id == app_id)
                    .order_by(model_cls.create_date.desc())
                    .all()
                )
                _freeze_resources(resources, limit)

        db.flush()

    @staticmethod
    def recalculate_on_upgrade(db: Session, user_id: int, new_tier: str) -> None:
        """After an upgrade, unfreeze all resources that now fit within the new limits."""
        FreezeService.apply_freeze(db, user_id, new_tier)
