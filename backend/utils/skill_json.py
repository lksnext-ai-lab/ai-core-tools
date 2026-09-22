"""Tolerant JSON helpers for the JSON-encoded text columns of ``Skill`` (no DB or FastAPI imports)."""
import json
from typing import Any, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


def load_json(value: Optional[str], default: Any, skill_id: Optional[int] = None, column: str = '') -> Any:
    """Tolerant JSON loader: malformed or wrong-typed stored values log a warning and return ``default``.

    For list defaults, non-string elements are dropped. Never logs the value itself.
    """
    if value is None or value == '':
        return default
    try:
        loaded = json.loads(value)
    except (ValueError, TypeError):
        logger.warning(f"Malformed JSON in Skill {skill_id} column '{column}'; using default")
        return default
    if loaded is None or not isinstance(loaded, type(default)):
        logger.warning(f"Unexpected JSON type in Skill {skill_id} column '{column}'; using default")
        return default
    if isinstance(loaded, list):
        strings = [x for x in loaded if isinstance(x, str)]
        if len(strings) != len(loaded):
            logger.warning(f"Dropped non-string elements in Skill {skill_id} column '{column}'")
        return strings
    return loaded


def dump_json(value: Any) -> Optional[str]:
    """Serialise ``value`` to JSON; ``None`` stays ``None``."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)
