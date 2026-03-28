from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from models.tier_config import TierConfig
from datetime import datetime
from utils.logger import get_logger
import yaml
import os

logger = get_logger(__name__)


def _load_tier_defaults() -> Dict[tuple, int]:
    """Load tier configuration defaults from system_defaults.yaml."""
    defaults_file = os.path.join(os.path.dirname(__file__), '..', 'system_defaults.yaml')
    try:
        with open(defaults_file, 'r') as f:
            config = yaml.safe_load(f) or {}
        
        tier_config = config.get('tier_config', {})
        defaults = {}
        
        # Convert nested dict to tuple-based dict for backward compatibility
        for tier, resources in tier_config.items():
            for resource_type, limit_value in resources.items():
                defaults[(tier, resource_type)] = limit_value
        
        return defaults
    except Exception as e:
        logger.warning(f"Failed to load tier defaults from YAML: {e}. Using fallback.")
        return {}


# Load defaults from system_defaults.yaml on module import
_TIER_DEFAULTS = _load_tier_defaults()

# Fallback defaults if YAML loading fails (for backward compatibility)
_FALLBACK_DEFAULTS = {
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
    ('pro', 'collaborators'): -1,
    ('pro', 'llm_calls'): -1,
}

# Use loaded defaults if available, otherwise fallback
_HARDCODED_DEFAULTS = _TIER_DEFAULTS if _TIER_DEFAULTS else _FALLBACK_DEFAULTS


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
