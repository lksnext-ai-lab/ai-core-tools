"""Single source of truth for SECRET_KEY resolution and validation.

All code needing the secret key must call ``get_secret_key()`` or
``validate_secret_key()`` rather than reading ``os.getenv`` directly.
Free of FastAPI/SQLAlchemy imports to avoid circular-import issues at startup.
"""

import os
from utils.logger import get_logger

logger = get_logger(__name__)

_DENYLIST: frozenset[str] = frozenset({
    "your-secret-key-SXSCDSDASD",
    "change-me",
    "supersecret",
    "your-secret-key-here-change-in-production",
})

_MIN_LENGTH = 32

_GENERATE_CMD = 'python -c "import secrets; print(secrets.token_hex(32))"'


def get_secret_key() -> str:
    """Return the application secret key, failing fast if it is unsafe.

    Reads ``SECRET_KEY`` from the environment. Raises ``RuntimeError`` when
    the value is absent, empty, shorter than 32 characters, or a known insecure
    default.
    """
    value = os.getenv("SECRET_KEY")

    if not value or not value.strip():
        msg = (
            "SECRET_KEY environment variable is not set. "
            "Generate a strong key with: "
            f"{_GENERATE_CMD}"
        )
        logger.error(msg)
        raise RuntimeError(msg)

    value = value.strip()

    if value in _DENYLIST:
        msg = (
            f"SECRET_KEY is set to a known insecure default value "
            f"({value!r}). "
            "Generate a strong key with: "
            f"{_GENERATE_CMD}"
        )
        logger.error(msg)
        raise RuntimeError(msg)

    if len(value) < _MIN_LENGTH:
        msg = (
            f"SECRET_KEY is too short ({len(value)} chars; minimum {_MIN_LENGTH}). "
            "Generate a strong key with: "
            f"{_GENERATE_CMD}"
        )
        logger.error(msg)
        raise RuntimeError(msg)

    return value


def validate_secret_key() -> None:
    """Validate SECRET_KEY at startup; abort with a clear error if invalid."""
    get_secret_key()
    logger.info("SECRET_KEY validation passed.")
