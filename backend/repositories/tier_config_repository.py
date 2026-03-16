from typing import Optional, List
from sqlalchemy.orm import Session
from models.tier_config import TierConfig
from datetime import datetime
from utils.logger import get_logger

logger = get_logger(__name__)

# Hardcoded defaults used when no DB row exists for a given tier/resource_type
_HARDCODED_DEFAULTS = {
    ('free', 'apps'): 1,
    ('free', 'agents'): 3,
    ('free', 'silos'): 2,
    ('free', 'skills'): 1,
    ('free', 'mcp_servers'): 0,
    ('free', 'collaborators'): 1,
    ('free', 'llm_calls'): 100,
    ('starter', 'apps'): 2,
    ('starter', 'agents'): 10,
    ('starter', 'silos'): 5,
    ('starter', 'skills'): 3,
    ('starter', 'mcp_servers'): 1,
    ('starter', 'collaborators'): 5,
    ('starter', 'llm_calls'): 1000,
    ('pro', 'apps'): 10,
    ('pro', 'agents'): 50,
    ('pro', 'silos'): 20,
    ('pro', 'skills'): 10,
    ('pro', 'mcp_servers'): 5,
    ('pro', 'collaborators'): -1,  # -1 = unlimited
    ('pro', 'llm_calls'): -1,  # -1 = unlimited
}


class TierConfigRepository:

    def __init__(self, db: Session):
        self.db = db

    def get_limit(self, tier: str, resource_type: str) -> int:
        """Return the configured limit for a tier+resource_type, falling back to hardcoded defaults."""
        row = (
            self.db.query(TierConfig)
            .filter(TierConfig.tier == tier, TierConfig.resource_type == resource_type)
            .first()
        )
        if row:
            return row.limit_value
        return _HARDCODED_DEFAULTS.get((tier, resource_type), 0)

    def get_all(self) -> List[TierConfig]:
        """Return all TierConfig rows."""
        return self.db.query(TierConfig).order_by(TierConfig.tier, TierConfig.resource_type).all()

    def upsert(self, tier: str, resource_type: str, limit_value: int) -> TierConfig:
        """Create or update a TierConfig row."""
        row = (
            self.db.query(TierConfig)
            .filter(TierConfig.tier == tier, TierConfig.resource_type == resource_type)
            .first()
        )
        if row:
            row.limit_value = limit_value
            row.updated_at = datetime.utcnow()
        else:
            row = TierConfig(tier=tier, resource_type=resource_type, limit_value=limit_value)
            self.db.add(row)
        self.db.flush()
        return row
