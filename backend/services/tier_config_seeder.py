"""Seed default tier configuration values on startup (SaaS mode only)."""
from sqlalchemy.orm import Session
from repositories.tier_config_repository import TierConfigRepository, _HARDCODED_DEFAULTS
from utils.logger import get_logger

logger = get_logger(__name__)


def seed_default_tier_configs(db: Session) -> None:
    """Insert default TierConfig rows if not already present.

    Uses the same defaults as TierConfigRepository._HARDCODED_DEFAULTS.
    Skips any row that already exists (upsert = update only on explicit admin change).
    """
    repo = TierConfigRepository(db)
    inserted = 0

    for (tier, resource_type), limit_value in _HARDCODED_DEFAULTS.items():
        from models.tier_config import TierConfig
        existing = (
            db.query(TierConfig)
            .filter(TierConfig.tier == tier, TierConfig.resource_type == resource_type)
            .first()
        )
        if not existing:
            repo.upsert(tier, resource_type, limit_value)
            inserted += 1

    if inserted > 0:
        db.commit()
        logger.info("Seeded %d default tier config entries", inserted)
    else:
        logger.debug("Tier config already seeded — no changes")
