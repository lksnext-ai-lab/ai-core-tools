"""Keycloak OIDC provider used to validate bearer tokens."""

import json
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
import jwt
from lks_idprovider.models.auth import AuthContext
from lks_idprovider.models.identity import User
from lks_idprovider.models.role import Role
from lks_idprovider.models.token import TokenInfo, TokenValidationResult
from utils.logger import get_logger

logger = get_logger(__name__)

_JWKS_CACHE_SECONDS = 300


class KeycloakProvider:
    """Validate Keycloak JWTs against the realm discovery document and JWKS."""

    def __init__(
        self,
        issuer: str,
        client_id: str,
        discovery_url: Optional[str] = None,
        jwks_url: Optional[str] = None,
        leeway: int = 60,
    ) -> None:
        if not issuer or not client_id:
            raise ValueError("KEYCLOAK_ISSUER and KEYCLOAK_CLIENT_ID are required")
        if leeway < 0:
            raise ValueError("KEYCLOAK_LEEWAY must not be negative")

        self.issuer = issuer.rstrip("/")
        self.client_id = client_id
        self.discovery_url = discovery_url or (
            f"{self.issuer}/.well-known/openid-configuration"
        )
        self._jwks_url = jwks_url
        self._jwks: dict[str, Any] = {}
        self._jwks_loaded_at = 0.0
        self._leeway = leeway
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "KeycloakProvider":
        self._client = httpx.AsyncClient(timeout=10.0)
        try:
            response = await self._client.get(self.discovery_url)
            response.raise_for_status()
            discovery = response.json()
            if discovery.get("issuer", "").rstrip("/") != self.issuer:
                raise ValueError("Keycloak discovery issuer does not match KEYCLOAK_ISSUER")
            if not self._jwks_url:
                self._jwks_url = discovery.get("jwks_uri")
            if not self._jwks_url:
                raise ValueError("Keycloak discovery document does not contain jwks_uri")
            await self._refresh_jwks()
            return self
        except Exception:
            await self.__aexit__(None, None, None)
            raise

    async def __aexit__(self, *_: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _refresh_jwks(self) -> None:
        if self._client is None or self._jwks_url is None:
            raise RuntimeError("Keycloak provider is not initialized")
        response = await self._client.get(self._jwks_url)
        response.raise_for_status()
        document = response.json()
        keys = document.get("keys", [])
        if not isinstance(keys, list):
            raise ValueError("Invalid Keycloak JWKS response")
        self._jwks = {
            key["kid"]: key for key in keys
            if isinstance(key, dict) and isinstance(key.get("kid"), str)
        }
        self._jwks_loaded_at = time.monotonic()

    async def _signing_key(self, token: str) -> Any:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256":
            raise jwt.InvalidTokenError("Unsupported Keycloak signing algorithm")
        key_id = header.get("kid")
        key = self._jwks.get(key_id)
        if key is None or time.monotonic() - self._jwks_loaded_at > _JWKS_CACHE_SECONDS:
            await self._refresh_jwks()
            key = self._jwks.get(key_id)
        if key is None:
            raise jwt.InvalidTokenError("Keycloak signing key not found")
        return jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))

    async def _claims(self, token: str) -> dict[str, Any]:
        key = await self._signing_key(token)
        claims = jwt.decode(
            token,
            key=key,
            algorithms=["RS256"],
            audience=self.client_id,
            issuer=self.issuer,
            leeway=self._leeway,
            options={"require": ["iss", "sub", "aud", "iat", "exp"]},
        )
        if claims.get("azp") and claims["azp"] != self.client_id:
            raise jwt.InvalidTokenError("Keycloak authorized party does not match client")
        return claims

    @staticmethod
    def _date(value: Any) -> Optional[datetime]:
        return (
            datetime.fromtimestamp(value, tz=timezone.utc)
            if isinstance(value, (int, float))
            else None
        )

    def _token_info(self, token: str, claims: dict[str, Any]) -> TokenInfo:
        audience = claims.get("aud")
        if isinstance(audience, list):
            audience = " ".join(str(item) for item in audience)
        return TokenInfo(
            token=token,
            token_type="id_token",
            expires_at=self._date(claims.get("exp")),
            issued_at=self._date(claims.get("iat")),
            issuer=claims.get("iss"),
            audience=audience if isinstance(audience, str) else None,
            subject=claims.get("sub"),
            scopes=claims.get("scope", "").split()
            if isinstance(claims.get("scope"), str) else [],
        )

    @staticmethod
    def _user(claims: dict[str, Any]) -> User:
        email = claims.get("email")
        username = claims.get("preferred_username") or email or claims["sub"]
        name = claims.get("name") or username
        return User(
            id=claims["sub"],
            name=name,
            username=username,
            email=email if isinstance(email, str) else None,
            first_name=claims.get("given_name"),
            last_name=claims.get("family_name"),
            email_verified=claims.get("email_verified") is True,
            preferred_username=claims.get("preferred_username"),
        )

    @staticmethod
    def _roles(claims: dict[str, Any]) -> list[Role]:
        roles: list[Role] = []
        realm_access = claims.get("realm_access", {})
        for role in realm_access.get("roles", []) if isinstance(realm_access, dict) else []:
            if isinstance(role, str):
                roles.append(Role(name=role))
        resource_access = claims.get("resource_access", {})
        if isinstance(resource_access, dict):
            for client, access in resource_access.items():
                if not isinstance(client, str) or not isinstance(access, dict):
                    continue
                for role in access.get("roles", []):
                    if isinstance(role, str):
                        roles.append(Role(name=role, client=client))
        return roles

    async def validate_token(self, token: str) -> TokenValidationResult:
        try:
            claims = await self._claims(token)
        except jwt.InvalidTokenError as exc:
            return TokenValidationResult(is_valid=False, error=str(exc))
        return TokenValidationResult(
            is_valid=True,
            token_info=self._token_info(token, claims),
        )

    async def get_auth_context(self, token: str) -> AuthContext:
        claims = await self._claims(token)
        token_info = self._token_info(token, claims)
        return AuthContext(
            identity=self._user(claims),
            roles=self._roles(claims),
            token_expires_at=token_info.expires_at,
            provider="keycloak",
            scopes=token_info.scopes,
            token_info=token_info,
        )

    async def health_check(self) -> dict[str, Any]:
        return {
            "status": "healthy" if self._jwks else "unhealthy",
            "issuer": self.issuer,
        }

    async def get_user_info(self, token: str) -> User:
        return self._user(await self._claims(token))

    async def get_user_roles(self, token: str) -> list[Role]:
        return self._roles(await self._claims(token))

    def get_provider_info(self) -> dict[str, str]:
        return {"provider": "keycloak", "issuer": self.issuer}
