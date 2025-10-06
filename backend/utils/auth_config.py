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
    
    # OAuth Configuration
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_DISCOVERY_URL: str = 'https://accounts.google.com/.well-known/openid-configuration'
    GOOGLE_REDIRECT_URI: str = 'http://localhost:8000/auth/callback'
    FRONTEND_URL: str = 'http://localhost:5173'
    
    # JWT Configuration
    JWT_SECRET: str = 'your-secret-key-SXSCDSDASD'
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24
    
    # Login Mode Configuration
    LOGIN_MODE: str = "OIDC"  # Options: OIDC, FAKE
    
    # Development Mode
    DEVELOPMENT_MODE: bool = False
    DEV_USERS: Dict[str, Dict[str, Any]] = {}
    
    @classmethod
    def load_config(cls):
        """Load configuration from environment variables"""
        # OAuth Configuration
        cls.GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
        cls.GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
        cls.GOOGLE_DISCOVERY_URL = os.getenv('GOOGLE_DISCOVERY_URL', cls.GOOGLE_DISCOVERY_URL)
        cls.GOOGLE_REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI', cls.GOOGLE_REDIRECT_URI)
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
        
        # Development Mode
        cls.DEVELOPMENT_MODE = os.getenv('DEVELOPMENT_MODE', 'false').lower() == 'true'
        
        # Setup development users if in development mode
        if cls.DEVELOPMENT_MODE:
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
        logger.info(f"🔐 Login mode: {cls.LOGIN_MODE}")
        
        if cls.LOGIN_MODE == 'FAKE':
            logger.warning("⚠️  FAKE LOGIN MODE - For development/testing only!")
            logger.info("   Any existing user email can log in without password")
        elif cls.is_oauth_configured():
            logger.info("✅ Google OAuth is properly configured")
        else:
            if cls.DEVELOPMENT_MODE:
                logger.warning("⚠️  Google OAuth not configured, running in DEVELOPMENT MODE with test tokens")
                logger.info("🔑 Development tokens available:")
                for token, user in cls.DEV_USERS.items():
                    logger.info(f"   {token} -> {user['email']} (ID: {user['user_id']})")
            else:
                logger.error("❌ Google OAuth not configured and not in development mode")
                logger.error("   Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables")
                logger.error("   Or set DEVELOPMENT_MODE=true for testing")
    
    @classmethod
    def is_oauth_configured(cls) -> bool:
        """Check if OAuth is properly configured"""
        return bool(cls.GOOGLE_CLIENT_ID and cls.GOOGLE_CLIENT_SECRET)
    
    @classmethod
    def is_development_mode(cls) -> bool:
        """Check if running in development mode"""
        return cls.DEVELOPMENT_MODE
    
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
        return {
            "login_mode": cls.LOGIN_MODE,
            "oauth_configured": cls.is_oauth_configured(),
            "development_mode": cls.is_development_mode(),
            "jwt_secret_set": bool(cls.JWT_SECRET and cls.JWT_SECRET != 'your-secret-key-SXSCDSDASD'),
            "frontend_url": cls.FRONTEND_URL,
            "redirect_uri": cls.GOOGLE_REDIRECT_URI,
            "dev_users_count": len(cls.DEV_USERS) if cls.DEVELOPMENT_MODE else 0
        }

# Load configuration on module import
AuthConfig.load_config() 