"""Platform system prompt of the hidden internal chat agent (``system_defaults.yaml``)."""
from functools import lru_cache
from pathlib import Path

import yaml

from utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULTS_PATH = Path(__file__).resolve().parents[2] / "system_defaults.yaml"

_FALLBACK_SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer clearly and accurately. When the question refers to the "
    "knowledge base and a search tool is available, use it, cite the sources you used and do not "
    "invent information that is not supported by them."
)


@lru_cache(maxsize=1)
def get_internal_chat_system_prompt() -> str:
    """Return ``internal_chat.system_prompt`` from ``system_defaults.yaml`` (cached; user independent).

    Falls back to a built-in prompt (with a WARNING) when the file or the key is unusable, so a
    broken defaults file never takes the Chat down.
    """
    try:
        with _DEFAULTS_PATH.open("r", encoding="utf-8") as fh:
            parsed = yaml.safe_load(fh) or {}
        prompt = (parsed.get("internal_chat") or {}).get("system_prompt")
    except (OSError, yaml.YAMLError, AttributeError) as exc:
        logger.warning("Could not read internal_chat.system_prompt from system_defaults.yaml: %s", exc)
        return _FALLBACK_SYSTEM_PROMPT
    if not isinstance(prompt, str) or not prompt.strip():
        logger.warning("internal_chat.system_prompt missing in system_defaults.yaml; using the built-in prompt")
        return _FALLBACK_SYSTEM_PROMPT
    return prompt.strip()
