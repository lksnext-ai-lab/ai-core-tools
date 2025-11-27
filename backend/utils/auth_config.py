"""
Authentication Configuration System
Handles OAuth setup and provides proper error handling for missing configuration.
"""

import os
from typing import Optional, Dict, Any
from utils.logger import get_logger

logger = get_logger(__name__)

class AuthConfig:
    """Centralized authentication configuration"""
    
    # OAuth Provider Configuration
    OAUTH_PROVIDER: str = "ENTRAID"  # Options: GOOGLE, ENTRAID
    
    # Google OAuth Configuration
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_DISCOVERY_URL: str = 'https://accounts.google.com/.well-known/openid-configuration'
    GOOGLE_REDIRECT_URI: str = 'http://localhost:8000/auth/callback'
    
    
    # Common Configuration
    FRONTEND_URL: str = 'http://localhost:5173'
    
    # JWT Configuration
    JWT_SECRET: str = 'your-secret-key-SXSCDSDASD'
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24
    
    # Login Mode Configuration
    LOGIN_MODE: str = "OIDC"  # Options: OIDC, FAKE
    
    # OIDC Configuration
    OIDC_ENABLED: bool = True
    DEV_USERS: Dict[str, Dict[str, Any]] = {}
    
    @classmethod
    def load_config(cls):
        """Load configuration from environment variables"""
        # OAuth Provider Selection
        cls.OAUTH_PROVIDER = os.getenv('OAUTH_PROVIDER', 'ENTRAID').upper()
        if cls.OAUTH_PROVIDER not in ['GOOGLE', 'ENTRAID']:
            logger.warning(f"Invalid OAUTH_PROVIDER value '{cls.OAUTH_PROVIDER}', defaulting to ENTRAID")
            cls.OAUTH_PROVIDER = 'ENTRAID'
        
        # Google OAuth Configuration
        cls.GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
        cls.GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
        cls.GOOGLE_DISCOVERY_URL = os.getenv('GOOGLE_DISCOVERY_URL', cls.GOOGLE_DISCOVERY_URL)
        cls.GOOGLE_REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI', cls.GOOGLE_REDIRECT_URI)
               
        cls.ENTRA_CLIENT_ID = os.getenv('ENTRA_CLIENT_ID')
        cls.ENTRA_CLIENT_SECRET = os.getenv('ENTRA_CLIENT_SECRET')
        cls.ENTRA_TENANT_ID = os.getenv('ENTRA_TENANT_ID')
        cls.ENTRA_REDIRECT_URI = os.getenv('ENTRA_REDIRECT_URI', 'http://localhost:8000/auth/callback')
        # Common Configuration
        cls.FRONTEND_URL = os.getenv('FRONTEND_URL', cls.FRONTEND_URL)
        
        # JWT Configuration
        cls.JWT_SECRET = os.getenv('SECRET_KEY', cls.JWT_SECRET)
        cls.JWT_ALGORITHM = os.getenv('JWT_ALGORITHM', cls.JWT_ALGORITHM)
        cls.JWT_EXPIRATION_HOURS = int(os.getenv('JWT_EXPIRATION_HOURS', cls.JWT_EXPIRATION_HOURS))
        
        # Login Mode Configuration
        cls.LOGIN_MODE = os.getenv('AICT_LOGIN', 'OIDC').upper()
        if cls.LOGIN_MODE not in ['OIDC', 'FAKE']:
            logger.warning(f"Invalid AICT_LOGIN value '{cls.LOGIN_MODE}', defaulting to OIDC")
            cls.LOGIN_MODE = 'OIDC'
        
        # OIDC Configuration
        cls.OIDC_ENABLED = os.getenv('OIDC_ENABLED', 'true').lower() == 'true'
        
        # Setup development users if OIDC is disabled (dev mode)
        if not cls.OIDC_ENABLED:
            cls._setup_dev_users()
        
        cls._log_config_status()
    
    @classmethod
    def _setup_dev_users(cls):
        """Setup development users for testing"""
        cls.DEV_USERS = {
            "dev-token-admin": {
                "user_id": 1,
                "email": "admin@example.com",
                "name": "Admin User",
                "google_id": "dev-google-id-admin",
                "is_admin": True
            },
            "dev-token-user1": {
                "user_id": 2,
                "email": "user1@example.com",
                "name": "User 1",
                "google_id": "dev-google-id-user1",
                "is_admin": False
            },
            "dev-token-user2": {
                "user_id": 3,
                "email": "user2@example.com",
                "name": "User 2",
                "google_id": "dev-google-id-user2",
                "is_admin": False
            }
        }
    
    @classmethod
    def _log_config_status(cls):
        """Log the current configuration status"""
        logger.info(f"[LOCK] Login mode: {cls.LOGIN_MODE}")
        logger.info(f"[KEY] OAuth Provider: {cls.OAUTH_PROVIDER}")
        
        if cls.LOGIN_MODE == 'FAKE':
            logger.warning("[WARN] FAKE LOGIN MODE - For development/testing only!")
            logger.info("   Any existing user email can log in without password")
        elif cls.is_oauth_configured():
            if cls.OAUTH_PROVIDER == 'GOOGLE':
                logger.info("[OK] Google OAuth is properly configured")
            elif cls.OAUTH_PROVIDER == 'ENTRAID':
                logger.info("[OK] EntraID (Azure AD) OAuth is properly configured")
                logger.info(f"   Tenant ID: {cls.ENTRA_TENANT_ID}")
        else:
            if not cls.OIDC_ENABLED:
                logger.warning(f"[WARN] {cls.OAUTH_PROVIDER} OAuth not configured, running in DEVELOPMENT MODE (OIDC_ENABLED=false) with test tokens")
                logger.info("[KEY] Development tokens available:")
                for token, user in cls.DEV_USERS.items():
                    logger.info(f"   {token} -> {user['email']} (ID: {user['user_id']})")
            else:
                logger.error(f"[ERROR] {cls.OAUTH_PROVIDER} OAuth not configured")
                if cls.OAUTH_PROVIDER == 'GOOGLE':
                    logger.error("   Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables")
                elif cls.OAUTH_PROVIDER == 'ENTRAID':
                    logger.error("   Set ENTRA_CLIENT_ID, ENTRA_CLIENT_SECRET, and ENTRA_TENANT_ID environment variables")
                logger.error("   Or set OIDC_ENABLED=false for development mode testing")
    
    @classmethod
    def is_oauth_configured(cls) -> bool:
        """Check if OAuth is properly configured"""
        if cls.OAUTH_PROVIDER == 'GOOGLE':
            return bool(cls.GOOGLE_CLIENT_ID and cls.GOOGLE_CLIENT_SECRET)
        elif cls.OAUTH_PROVIDER == 'ENTRAID':
            return bool(cls.ENTRA_CLIENT_ID and cls.ENTRA_CLIENT_SECRET and cls.ENTRA_TENANT_ID)
        return False
    
    @classmethod
    def is_development_mode(cls) -> bool:
        """Check if running in development mode (OIDC disabled)"""
        return not cls.OIDC_ENABLED
    
    @classmethod
    def is_fake_login_mode(cls) -> bool:
        """Check if running in fake login mode"""
        return cls.LOGIN_MODE == 'FAKE'
    
    @classmethod
    def get_dev_user(cls, token: str) -> Optional[Dict[str, Any]]:
        """Get development user by token"""
        return cls.DEV_USERS.get(token)
    
    @classmethod
    def get_config_summary(cls) -> Dict[str, Any]:
        """Get configuration summary for debugging"""
        summary = {
            "login_mode": cls.LOGIN_MODE,
            "oauth_provider": cls.OAUTH_PROVIDER,
            "oauth_configured": cls.is_oauth_configured(),
            "oidc_enabled": cls.OIDC_ENABLED,
            "development_mode": cls.is_development_mode(),
            "jwt_secret_set": bool(cls.JWT_SECRET and cls.JWT_SECRET != 'your-secret-key-SXSCDSDASD'),
            "frontend_url": cls.FRONTEND_URL,
            "dev_users_count": len(cls.DEV_USERS) if not cls.OIDC_ENABLED else 0
        }
        
        # Add provider-specific redirect URI
        if cls.OAUTH_PROVIDER == 'GOOGLE':
            summary["redirect_uri"] = cls.GOOGLE_REDIRECT_URI
        elif cls.OAUTH_PROVIDER == 'ENTRAID':
            summary["redirect_uri"] = cls.ENTRA_REDIRECT_URI
            summary["tenant_id"] = cls.ENTRA_TENANT_ID
        
        return summary

# Load configuration on module import
AuthConfig.load_config() 