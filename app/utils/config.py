"""
Configuration management utilities
"""
import os
from typing import Any, Dict, List, Optional, Union
from utils.logger import get_logger
from utils.error_handlers import ValidationError

logger = get_logger(__name__)


class Config:
    """Centralized configuration management"""
    
    # Define required environment variables for different components
    REQUIRED_DB_VARS = [
        'DATABASE_USER', 'DATABASE_PASSWORD', 'DATABASE_HOST', 
        'DATABASE_PORT', 'DATABASE_NAME'
    ]
    
    REQUIRED_GOOGLE_VARS = [
        'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GOOGLE_DISCOVERY_URL'
    ]
    
    # Default values for optional environment variables
    DEFAULTS = {
        'LOG_LEVEL': 'INFO',
        'LOG_DIR': 'logs',
        'AICT_MODE': 'ONLINE',
        'DOWNLOADS_PATH': '/app/temp/downloads/',
        'IMAGES_PATH': '/app/temp/images/',
        'REPO_BASE_FOLDER': '/app/repos',
        'PERMANENT_SESSION_LIFETIME_MINUTES': '30'
    }
    
    @staticmethod
    def get_env_var(var_name: str, default: Optional[str] = None, required: bool = False) -> str:
        """
        Get environment variable with validation
        
        Args:
            var_name: Name of the environment variable
            default: Default value if not found
            required: Whether the variable is required
            
        Returns:
            Environment variable value
            
        Raises:
            ValidationError: If required variable is missing
        """
        value = os.getenv(var_name, default)
        
        if required and not value:
            raise ValidationError(f"Required environment variable '{var_name}' is not set")
        
        return value
    
    @staticmethod
    def get_int_env_var(var_name: str, default: Optional[int] = None, required: bool = False) -> int:
        """
        Get integer environment variable with validation
        
        Args:
            var_name: Name of the environment variable
            default: Default value if not found
            required: Whether the variable is required
            
        Returns:
            Integer environment variable value
            
        Raises:
            ValidationError: If required variable is missing or invalid
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
        """
        Get boolean environment variable
        
        Args:
            var_name: Name of the environment variable
            default: Default value if not found
            
        Returns:
            Boolean environment variable value
        """
        str_value = Config.get_env_var(var_name, str(default)).lower()
        return str_value in ('true', '1', 'yes', 'on')
    
    @staticmethod
    def validate_required_vars(var_list: List[str]) -> Dict[str, str]:
        """
        Validate that all required environment variables are set
        
        Args:
            var_list: List of required variable names
            
        Returns:
            Dictionary of variable name to value mappings
            
        Raises:
            ValidationError: If any required variables are missing
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
        """
        Get database configuration with validation
        
        Returns:
            Dictionary with database configuration
            
        Raises:
            ValidationError: If required database variables are missing
        """
        return Config.validate_required_vars(Config.REQUIRED_DB_VARS)
    
    @staticmethod
    def get_google_oauth_config() -> Dict[str, str]:
        """
        Get Google OAuth configuration with validation
        
        Returns:
            Dictionary with Google OAuth configuration
            
        Raises:
            ValidationError: If required Google OAuth variables are missing
        """
        return Config.validate_required_vars(Config.REQUIRED_GOOGLE_VARS)
    
    @staticmethod
    def get_database_url() -> str:
        """
        Build database URL from environment variables
        
        Returns:
            PostgreSQL database URL
        """
        db_config = Config.get_database_config()
        return (f"postgresql+psycopg://{db_config['DATABASE_USER']}:"
                f"{db_config['DATABASE_PASSWORD']}@{db_config['DATABASE_HOST']}:"
                f"{db_config['DATABASE_PORT']}/{db_config['DATABASE_NAME']}")
    
    @staticmethod
    def get_async_database_url() -> str:
        """
        Build async database URL from environment variables
        
        Returns:
            PostgreSQL async database URL
        """
        db_config = Config.get_database_config()
        return (f"postgresql+psycopg_async://{db_config['DATABASE_USER']}:"
                f"{db_config['DATABASE_PASSWORD']}@{db_config['DATABASE_HOST']}:"
                f"{db_config['DATABASE_PORT']}/{db_config['DATABASE_NAME']}")
    
    @staticmethod
    def get_app_config() -> Dict[str, Any]:
        """
        Get general application configuration
        
        Returns:
            Dictionary with application configuration
        """
        return {
            'AICT_MODE': Config.get_env_var('AICT_MODE', Config.DEFAULTS['AICT_MODE']),
            'LOG_LEVEL': Config.get_env_var('LOG_LEVEL', Config.DEFAULTS['LOG_LEVEL']),
            'LOG_DIR': Config.get_env_var('LOG_DIR', Config.DEFAULTS['LOG_DIR']),
            'DOWNLOADS_PATH': Config.get_env_var('DOWNLOADS_PATH', Config.DEFAULTS['DOWNLOADS_PATH']),
            'IMAGES_PATH': Config.get_env_var('IMAGES_PATH', Config.DEFAULTS['IMAGES_PATH']),
            'REPO_BASE_FOLDER': Config.get_env_var('REPO_BASE_FOLDER', Config.DEFAULTS['REPO_BASE_FOLDER']),
            'PERMANENT_SESSION_LIFETIME_MINUTES': Config.get_int_env_var(
                'PERMANENT_SESSION_LIFETIME_MINUTES', 
                int(Config.DEFAULTS['PERMANENT_SESSION_LIFETIME_MINUTES'])
            ),
            'SECRET_KEY': Config.get_env_var('SECRET_KEY', required=False) or 'your-secret-key-SXSCDSDASD'
        }
    
    @staticmethod
    def validate_all_config() -> Dict[str, Any]:
        """
        Validate all application configuration
        
        Returns:
            Dictionary with all validated configuration
            
        Raises:
            ValidationError: If any required configuration is missing or invalid
        """
        logger.info("Validating application configuration...")
        
        config = {
            'database': Config.get_database_config(),
            'app': Config.get_app_config()
        }
        
        # Google OAuth is optional - only validate if any of the vars are set
        google_vars_set = any(os.getenv(var) for var in Config.REQUIRED_GOOGLE_VARS)
        if google_vars_set:
            config['google_oauth'] = Config.get_google_oauth_config()
        
        logger.info("Application configuration validated successfully")
        return config


# Convenience functions for common configuration access
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