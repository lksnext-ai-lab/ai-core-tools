"""Configuration management utilities."""
import os
from typing import Any, Dict, List, Optional, Union
from utils.logger import get_logger
from utils.error_handlers import ValidationError
from utils.secret_key import get_secret_key

logger = get_logger(__name__)


class Config:
    """Centralized configuration management"""

    REQUIRED_DB_VARS = [
        'DATABASE_USER', 'DATABASE_PASSWORD', 'DATABASE_HOST',
        'DATABASE_PORT', 'DATABASE_NAME'
    ]

    REQUIRED_GOOGLE_VARS = [
        'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_DISCOVERY_URL'
    ]

    DEFAULTS = {
        'LOG_LEVEL': 'INFO',
        'LOG_DIR': 'logs',
        'AICT_MODE': 'ONLINE',
        'TMP_BASE_FOLDER': 'data/tmp',
        'DOWNLOADS_PATH': 'data/tmp/downloads/',
        'IMAGES_PATH': 'data/tmp/images/',
        'REPO_BASE_FOLDER': 'data/repositories',
        'PERMANENT_SESSION_LIFETIME_MINUTES': '30',
        'AICT_OMNIADMINS': '',
        # TMP_PERSISTENT_TTL_DAYS mirrors the OpenAI Threads 7-day retention convention.
        # TMP_EPHEMERAL_ORPHAN_HOURS sweeps files left by crashed requests (normally empty).
        'TMP_PERSISTENT_TTL_DAYS': '7',
        'TMP_EPHEMERAL_ORPHAN_HOURS': '1',
        'TMP_CLEANUP_INTERVAL_MINUTES': '60',
        'TMP_CLEANUP_ENABLED': 'True',
    }

    @staticmethod
    def get_env_var(var_name: str, default: Optional[str] = None, required: bool = False) -> str:
        """Get an environment variable, optionally raising on absence.

        Args:
            var_name: Name of the environment variable.
            default: Default value if not set.
            required: Raise ``ValidationError`` when True and value is missing.

        Returns:
            Environment variable value.

        Raises:
            ValidationError: If required and missing.
        """
        value = os.getenv(var_name, default)

        if required and not value:
            raise ValidationError(f"Required environment variable '{var_name}' is not set")

        return value

    @staticmethod
    def get_int_env_var(var_name: str, default: Optional[int] = None, required: bool = False) -> int:
        """Get an integer environment variable.

        Args:
            var_name: Name of the environment variable.
            default: Default value if not set.
            required: Raise ``ValidationError`` when True and value is missing.

        Returns:
            Integer value.

        Raises:
            ValidationError: If required and missing, or value is not a valid integer.
        """
        str_value = Config.get_env_var(var_name, str(default) if default is not None else None, required)

        if not str_value:
            if required:
                raise ValidationError(f"Required environment variable '{var_name}' is not set")
            return default

        try:
            return int(str_value)
        except ValueError:
            raise ValidationError(f"Environment variable '{var_name}' must be an integer, got: {str_value}")

    @staticmethod
    def get_bool_env_var(var_name: str, default: bool = False) -> bool:
        """Get a boolean environment variable. Accepts true/1/yes/on (case-insensitive)."""
        str_value = Config.get_env_var(var_name, str(default)).lower()
        return str_value in ('true', '1', 'yes', 'on')

    @staticmethod
    def validate_required_vars(var_list: List[str]) -> Dict[str, str]:
        """Assert all listed env vars are set and return their values.

        Args:
            var_list: Variable names to validate.

        Returns:
            Mapping of variable name to value.

        Raises:
            ValidationError: If any variable is missing.
        """
        missing_vars = []
        values = {}

        for var_name in var_list:
            value = os.getenv(var_name)
            if not value:
                missing_vars.append(var_name)
            else:
                values[var_name] = value

        if missing_vars:
            raise ValidationError(f"Missing required environment variables: {', '.join(missing_vars)}")

        return values

    @staticmethod
    def get_database_config() -> Dict[str, str]:
        """Return validated database env vars.

        Raises:
            ValidationError: If any required DB variable is missing.
        """
        return Config.validate_required_vars(Config.REQUIRED_DB_VARS)

    @staticmethod
    def get_google_oauth_config() -> Dict[str, str]:
        """Return validated Google OAuth env vars.

        Raises:
            ValidationError: If any required Google OAuth variable is missing.
        """
        return Config.validate_required_vars(Config.REQUIRED_GOOGLE_VARS)

    @staticmethod
    def get_database_url() -> str:
        """Build a synchronous PostgreSQL URL from environment variables."""
        db_config = Config.get_database_config()
        return (f"postgresql+psycopg://{db_config['DATABASE_USER']}:"
                f"{db_config['DATABASE_PASSWORD']}@{db_config['DATABASE_HOST']}:"
                f"{db_config['DATABASE_PORT']}/{db_config['DATABASE_NAME']}")

    @staticmethod
    def get_async_database_url() -> str:
        """Build an async PostgreSQL URL from environment variables."""
        db_config = Config.get_database_config()
        return (f"postgresql+psycopg_async://{db_config['DATABASE_USER']}:"
                f"{db_config['DATABASE_PASSWORD']}@{db_config['DATABASE_HOST']}:"
                f"{db_config['DATABASE_PORT']}/{db_config['DATABASE_NAME']}")

    @staticmethod
    def get_app_config() -> Dict[str, Any]:
        """Return general application configuration from environment variables."""
        return {
            'AICT_MODE': Config.get_env_var('AICT_MODE', Config.DEFAULTS['AICT_MODE']),
            'LOG_LEVEL': Config.get_env_var('LOG_LEVEL', Config.DEFAULTS['LOG_LEVEL']),
            'LOG_DIR': Config.get_env_var('LOG_DIR', Config.DEFAULTS['LOG_DIR']),
            'TMP_BASE_FOLDER': Config.get_env_var('TMP_BASE_FOLDER', Config.DEFAULTS['TMP_BASE_FOLDER']),
            'DOWNLOADS_PATH': Config.get_env_var('DOWNLOADS_PATH', Config.DEFAULTS['DOWNLOADS_PATH']),
            'IMAGES_PATH': Config.get_env_var('IMAGES_PATH', Config.DEFAULTS['IMAGES_PATH']),
            'REPO_BASE_FOLDER': Config.get_env_var('REPO_BASE_FOLDER', Config.DEFAULTS['REPO_BASE_FOLDER']),
            'PERMANENT_SESSION_LIFETIME_MINUTES': Config.get_int_env_var(
                'PERMANENT_SESSION_LIFETIME_MINUTES',
                int(Config.DEFAULTS['PERMANENT_SESSION_LIFETIME_MINUTES'])
            ),
            'SECRET_KEY': get_secret_key(),
            'TMP_PERSISTENT_TTL_DAYS': Config.get_int_env_var(
                'TMP_PERSISTENT_TTL_DAYS',
                int(Config.DEFAULTS['TMP_PERSISTENT_TTL_DAYS']),
            ),
            'TMP_EPHEMERAL_ORPHAN_HOURS': Config.get_int_env_var(
                'TMP_EPHEMERAL_ORPHAN_HOURS',
                int(Config.DEFAULTS['TMP_EPHEMERAL_ORPHAN_HOURS']),
            ),
            'TMP_CLEANUP_INTERVAL_MINUTES': Config.get_int_env_var(
                'TMP_CLEANUP_INTERVAL_MINUTES',
                int(Config.DEFAULTS['TMP_CLEANUP_INTERVAL_MINUTES']),
            ),
            'TMP_CLEANUP_ENABLED': Config.get_bool_env_var(
                'TMP_CLEANUP_ENABLED',
                default=True,
            ),
        }

    @staticmethod
    def validate_all_config() -> Dict[str, Any]:
        """Validate and return all application configuration.

        Raises:
            ValidationError: If any required configuration is missing or invalid.
        """
        logger.info("Validating application configuration...")

        config = {
            'database': Config.get_database_config(),
            'app': Config.get_app_config()
        }

        google_vars_set = any(os.getenv(var) for var in Config.REQUIRED_GOOGLE_VARS)
        if google_vars_set:
            config['google_oauth'] = Config.get_google_oauth_config()

        logger.info("Application configuration validated successfully")
        return config


def get_database_url() -> str:
    """Get database URL"""
    return Config.get_database_url()


def get_async_database_url() -> str:
    """Get async database URL"""
    return Config.get_async_database_url()


def get_app_config() -> Dict[str, Any]:
    """Get application configuration"""
    return Config.get_app_config()


def is_debug_mode() -> bool:
    """Check if debug mode is enabled"""
    return Config.get_bool_env_var('DEBUG', False)


def get_log_level() -> str:
    """Get log level"""
    return Config.get_env_var('LOG_LEVEL', Config.DEFAULTS['LOG_LEVEL'])


def get_aict_mode() -> str:
    """Get AICT mode"""
    return Config.get_env_var('AICT_MODE', Config.DEFAULTS['AICT_MODE'])


def is_self_hosted() -> bool:
    """Check if we're running in self-hosted mode"""
    return get_aict_mode() == 'SELF-HOSTED'


def get_omniadmins() -> List[str]:
    """Return normalised (lowercase, stripped) omniadmin email list from ``AICT_OMNIADMINS``.

    Normalisation ensures case differences in the env var never silently lock
    an operator out of RBAC checks or the bootstrap flow.
    """
    omniadmins_str = Config.get_env_var('AICT_OMNIADMINS', Config.DEFAULTS['AICT_OMNIADMINS'])
    if not omniadmins_str:
        return []
    return [email.strip().lower() for email in omniadmins_str.split(',') if email.strip()]


def is_omniadmin(email: str) -> bool:
    """Return True when ``email`` (any casing) is in the omniadmin set.

    Args:
        email: Email address to test.

    Returns:
        ``True`` when the normalised address is in the omniadmin list.
    """
    if not email:
        return False
    omniadmins = get_omniadmins()
    return email.strip().lower() in omniadmins
