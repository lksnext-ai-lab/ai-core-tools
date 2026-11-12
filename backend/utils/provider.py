"""Singleton access to the EntraID provider for OIDC authentication.

Only initialized when AICT_LOGIN=OIDC. In LOCAL mode the provider is not used.
"""

import os
from typing import Optional
from lks_idprovider_entraid import EntraIDProvider, EntraIDConfig, TokenType
from lks_idprovider.protocols import IdentityProvider
from utils.keycloak_provider import KeycloakProvider
from utils.auth_config import AuthConfig
from utils.logger import get_logger

logger = get_logger(__name__)

_provider_instance: Optional[IdentityProvider] = None

# Clock skew tolerated on exp/nbf/iat. 300 s matches Microsoft.IdentityModel's
# default ClockSkew and is the maximum EntraIDConfig accepts.
DEFAULT_LEEWAY_SECONDS = 300


def get_entra_config() -> EntraIDConfig:
    """Build EntraIDConfig from environment variables.

    Raises:
        ValueError: If required env vars are missing when AICT_LOGIN=OIDC.
    """
    tenant_id = os.getenv("ENTRA_TENANT_ID")
    client_id = os.getenv("ENTRA_CLIENT_ID")
    client_secret = os.getenv("ENTRA_CLIENT_SECRET")

    if not tenant_id or not client_id or not client_secret:
        login_mode = os.getenv('AICT_LOGIN', 'OIDC').upper()
        if login_mode != 'OIDC':
            raise ValueError(
                f"EntraID provider initialization attempted while AICT_LOGIN={login_mode}. "
                "This should not happen — check application startup logic."
            )
        raise ValueError(
            "Missing required EntraID configuration for OIDC authentication. "
            "Set ENTRA_TENANT_ID, ENTRA_CLIENT_ID, and ENTRA_CLIENT_SECRET environment variables."
        )

    token_type_str = os.getenv("ENTRA_TOKEN_TYPE", "ID_TOKEN").upper()
    token_type = (
        TokenType.ACCESS_TOKEN
        if token_type_str == "ACCESS_TOKEN"
        else TokenType.ID_TOKEN
    )

    config = EntraIDConfig(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
        token_type=token_type,
        validate_audience=os.getenv("ENTRA_VALIDATE_AUDIENCE", "true").lower()
        == "true",
        validate_issuer=os.getenv("ENTRA_VALIDATE_ISSUER", "true").lower()
        == "true",
        leeway=int(os.getenv("ENTRA_LEEWAY", str(DEFAULT_LEEWAY_SECONDS))),
        api_version=os.getenv("ENTRA_API_VERSION", "v1.0"),
    )

    logger.info(f"EntraID config created: tenant={tenant_id}, token_type={token_type}")
    return config


async def initialize_provider() -> IdentityProvider:
    """Initialize the configured OIDC provider singleton during app startup."""
    global _provider_instance

    if _provider_instance is not None:
        logger.warning("Provider already initialized, skipping re-initialization")
        return _provider_instance

    if AuthConfig.OAUTH_PROVIDER == "KEYCLOAK":
        provider: IdentityProvider = KeycloakProvider(
            issuer=AuthConfig.KEYCLOAK_ISSUER or "",
            client_id=AuthConfig.KEYCLOAK_CLIENT_ID or "",
            discovery_url=AuthConfig.KEYCLOAK_DISCOVERY_URL,
            jwks_url=AuthConfig.KEYCLOAK_JWKS_URL,
            leeway=AuthConfig.KEYCLOAK_LEEWAY,
        )
    else:
        provider = EntraIDProvider(get_entra_config())

    await provider.__aenter__()

    try:
        health = await provider.health_check()
        if health.get("status") == "healthy":
            logger.info("%s provider initialized and healthy", AuthConfig.OAUTH_PROVIDER)
        else:
            logger.warning("%s provider initialized but unhealthy: %s", AuthConfig.OAUTH_PROVIDER, health)
    except Exception as e:
        logger.error("%s provider health check failed: %s", AuthConfig.OAUTH_PROVIDER, e)

    _provider_instance = provider
    return provider


async def shutdown_provider():
    """Shut down the EntraID provider singleton; call during app shutdown."""
    global _provider_instance

    if _provider_instance is None:
        logger.warning("No provider instance to shutdown")
        return

    try:
        await _provider_instance.__aexit__(None, None, None)
        logger.info("%s provider shutdown complete", AuthConfig.OAUTH_PROVIDER)
    except Exception as e:
        logger.error(f"Error shutting down provider: {e}")
    finally:
        _provider_instance = None


def get_provider() -> IdentityProvider:
    """Return the provider singleton for use as a FastAPI dependency.

    Raises:
        RuntimeError: If ``initialize_provider()`` has not been called.
    """
    if _provider_instance is None:
        raise RuntimeError(
            "Provider not initialized. Call initialize_provider() during startup."
        )

    return _provider_instance
