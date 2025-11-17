"""
Identity Provider Initialization and Management

This module provides singleton access to the EntraID provider instance
and manages its lifecycle for dependency injection in FastAPI.
"""

import os
from typing import Optional
from lks_idprovider_entraid import EntraIDProvider, EntraIDConfig, TokenType
from utils.logger import get_logger

logger = get_logger(__name__)

# Global provider instance (singleton)
_provider_instance: Optional[EntraIDProvider] = None


def get_entra_config() -> EntraIDConfig:
    """Create EntraID configuration from environment variables.
    
    Returns:
        EntraIDConfig instance with settings from environment
        
    Raises:
        ValueError: If required environment variables are missing
    """
    tenant_id = os.getenv("ENTRA_TENANT_ID")
    client_id = os.getenv("ENTRA_CLIENT_ID")
    client_secret = os.getenv("ENTRA_CLIENT_SECRET")
    
    if not tenant_id or not client_id or not client_secret:
        raise ValueError(
            "Missing required EntraID configuration. "
            "Set ENTRA_TENANT_ID, ENTRA_CLIENT_ID, and ENTRA_CLIENT_SECRET"
        )
    
    # Determine token type
    token_type_str = os.getenv("ENTRA_TOKEN_TYPE", "ID_TOKEN").upper()
    token_type = (
        TokenType.ACCESS_TOKEN
        if token_type_str == "ACCESS_TOKEN"
        else TokenType.ID_TOKEN
    )
    
    # Create config
    config = EntraIDConfig(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
        token_type=token_type,
        validate_audience=os.getenv("ENTRA_VALIDATE_AUDIENCE", "true").lower()
        == "true",
        validate_issuer=os.getenv("ENTRA_VALIDATE_ISSUER", "true").lower()
        == "true",
        leeway=int(os.getenv("ENTRA_LEEWAY", "0")),
        api_version=os.getenv("ENTRA_API_VERSION", "v1.0"),
    )
    
    logger.info(f"EntraID config created: tenant={tenant_id}, token_type={token_type}")
    return config


async def initialize_provider() -> EntraIDProvider:
    """Initialize the EntraID provider instance.
    
    This should be called during application startup.
    
    Returns:
        Initialized EntraIDProvider instance
    """
    global _provider_instance
    
    if _provider_instance is not None:
        logger.warning("Provider already initialized, skipping re-initialization")
        return _provider_instance
    
    config = get_entra_config()
    provider = EntraIDProvider(config)
    
    # Initialize async context manager
    await provider.__aenter__()
    
    # Test connection
    try:
        health = await provider.health_check()
        if health.get("status") == "healthy":
            logger.info("✅ EntraID provider initialized and healthy")
        else:
            logger.warning(f"⚠️  EntraID provider initialized but unhealthy: {health}")
    except Exception as e:
        logger.error(f"❌ EntraID provider health check failed: {e}")
    
    _provider_instance = provider
    return provider


async def shutdown_provider():
    """Shutdown the EntraID provider instance.
    
    This should be called during application shutdown.
    """
    global _provider_instance
    
    if _provider_instance is None:
        logger.warning("No provider instance to shutdown")
        return
    
    try:
        await _provider_instance.__aexit__(None, None, None)
        logger.info("EntraID provider shutdown complete")
    except Exception as e:
        logger.error(f"Error shutting down provider: {e}")
    finally:
        _provider_instance = None


def get_provider() -> EntraIDProvider:
    """Get the current provider instance for dependency injection.
    
    This is used as a FastAPI dependency.
    
    Returns:
        Current EntraIDProvider instance
        
    Raises:
        RuntimeError: If provider is not initialized
    """
    if _provider_instance is None:
        raise RuntimeError(
            "Provider not initialized. Call initialize_provider() during startup."
        )
    
    return _provider_instance
