"""FastAPI auth dependencies for the internal API (OIDC and LOCAL auth modes)."""

import jwt
from fastapi import Cookie, HTTPException, status, Depends, Request, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from lks_idprovider_fastapi import get_auth_context
from lks_idprovider.models.auth import AuthContext
from lks_idprovider.models.identity import User as LksUser
from lks_idprovider.models.token import TokenInfo
from db.database import get_db
from services.user_service import UserService
from utils.logger import get_logger
from utils.auth_config import AuthConfig
from utils.local_auth_tokens import decode_access_token as decode_local_access_token
from typing import Optional

logger = get_logger(__name__)

http_bearer_scheme = HTTPBearer(auto_error=False)

AuthConfig.load_config()

AUTH_FAILED_MESSAGE = "Authentication failed"


def _create_enriched_auth_context(
    db_user,
    user_email: str,
    auth_context: Optional[AuthContext] = None,
    provider: str = "local",
) -> AuthContext:
    """Build an AuthContext stamped with the database user_id."""
    if auth_context:
        # OIDC path: provider comes from the real token; ignore the parameter.
        enriched_identity = LksUser(
            id=str(db_user.user_id),
            username=auth_context.identity.username or user_email,
            email=user_email,
            name=auth_context.identity.name,
            first_name=auth_context.identity.first_name,
            last_name=auth_context.identity.last_name,
        )
        return AuthContext(
            identity=enriched_identity,
            roles=auth_context.roles,
            token_expires_at=auth_context.token_expires_at,
            refresh_expires_at=auth_context.refresh_expires_at,
            provider=auth_context.provider,
            scopes=auth_context.scopes,
            token_info=auth_context.token_info,
        )
    else:
        enriched_identity = LksUser(
            id=str(db_user.user_id),
            username=user_email,
            email=user_email,
            name=db_user.name,
            first_name=None,
            last_name=None,
        )
        synthetic_issuer = "mattin-local-auth"
        synthetic_audience = "mattin-internal"
        synthetic_token = "local-session"

        synthetic_token_info = TokenInfo(
            token=synthetic_token,
            token_type="access_token",
            subject=user_email,
            audience=synthetic_audience,
            issuer=synthetic_issuer,
            scopes=[],
        )
        return AuthContext(
            identity=enriched_identity,
            roles=[],
            token_expires_at=None,
            refresh_expires_at=None,
            provider=provider,
            scopes=[],
            token_info=synthetic_token_info,
        )


def _enrich_auth_context_with_db_user(
    user_email: str,
    db: Session,
    auth_context: Optional[AuthContext] = None,
    allow_user_creation: bool = True,
    provider: str = "local",
) -> AuthContext:
    """Look up (or create) the DB user by email and return an enriched AuthContext with database user_id."""
    db_user = UserService.get_user_by_email(db, user_email)

    if not db_user:
        if allow_user_creation:
            user_name = (
                auth_context.identity.name if auth_context else user_email
            )
            db_user, created = UserService.get_or_create_user(
                db=db, email=user_email, name=user_name
            )
            if created:
                logger.info(f"Created new user on first login: {user_email}")
            else:
                logger.info(f"User logged in: {user_email}")
        else:
            logger.warning(f"User not found in database: {user_email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=AUTH_FAILED_MESSAGE,
                headers={"WWW-Authenticate": "Bearer"},
            )

    if hasattr(db_user, "is_active") and not db_user.is_active:
        logger.warning(f"Inactive user attempted to access: {user_email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. "
            "Please contact support for assistance.",
        )

    return _create_enriched_auth_context(db_user, user_email, auth_context, provider=provider)


def get_current_user_oidc(
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> AuthContext:
    """Validate OIDC token, sync user to DB on first login, and return enriched AuthContext."""
    try:
        user_email = auth_context.identity.email
        if not user_email:
            logger.error("No email found in authentication token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User email not found in token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        enriched_context = _enrich_auth_context_with_db_user(
            user_email=user_email,
            db=db,
            auth_context=auth_context,
            allow_user_creation=True,
        )
        
        logger.debug(
            f"User authenticated: {user_email} "
            f"(DB ID: {enriched_context.identity.id}, "
            f"EntraID: {auth_context.token_info.subject if auth_context.token_info else 'N/A'})"
        )
        return enriched_context
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in authentication: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTH_FAILED_MESSAGE,
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user_local(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(http_bearer_scheme),
    access_token_cookie: Optional[str] = Cookie(default=None, alias="access_token"),
    db: Session = Depends(get_db),
) -> AuthContext:
    """Get the current authenticated user in LOCAL auth mode (cookie or Bearer).

    Validates a LOCAL-issuer JWT (iss=mattin-local-auth, aud=mattin-internal).
    DEV-mode and OIDC tokens are explicitly rejected by the decoder.

    Token lookup order:
    1. ``access_token`` httpOnly cookie (standard browser session).
    2. ``Authorization: Bearer <token>`` header (Swagger UI, tooling, back-compat).

    LOCAL users are created by an administrator; this dependency does NOT
    auto-provision missing users (``allow_user_creation=False``).

    Args:
        request: FastAPI request used as fallback for the Authorization header.
        credentials: Bearer token parsed by the HTTPBearer security scheme.
        access_token_cookie: Value of the ``access_token`` httpOnly cookie.
        db: Synchronous database session.

    Returns:
        AuthContext enriched with the database ``user_id``.

    Raises:
        HTTPException 401: Token absent, invalid, expired, or user not found.
        HTTPException 403: User account is inactive.
    """
    # Cookie takes precedence over Authorization header.
    raw_token: Optional[str] = None

    if access_token_cookie:
        raw_token = access_token_cookie
        logger.debug("LOCAL auth: token sourced from access_token cookie")
    elif credentials and credentials.scheme and credentials.credentials:
        raw_token = credentials.credentials
        logger.debug("LOCAL auth: token sourced from Authorization Bearer header")
    else:
        authorization = request.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            raw_token = authorization[len("Bearer "):].strip()
            logger.debug("LOCAL auth: token sourced from raw Authorization header")

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTH_FAILED_MESSAGE,
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_local_access_token(raw_token)
    except jwt.ExpiredSignatureError:
        logger.warning("LOCAL auth: access token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTH_FAILED_MESSAGE,
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        logger.warning("LOCAL auth: invalid token — %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTH_FAILED_MESSAGE,
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_email: Optional[str] = payload.get("email")
    if not user_email:
        logger.error("LOCAL auth: token payload missing 'email' claim")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTH_FAILED_MESSAGE,
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        enriched_context = _enrich_auth_context_with_db_user(
            user_email=user_email,
            db=db,
            auth_context=None,
            allow_user_creation=False,
            provider="local",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("LOCAL auth: unexpected error enriching context — %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTH_FAILED_MESSAGE,
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.debug(
        "LOCAL auth: user authenticated — email=%s db_id=%s",
        user_email,
        enriched_context.identity.id,
    )
    return enriched_context


# Dispatch once at import time: LOCAL uses LOCAL-issuer JWTs; all other modes use OIDC.
if AuthConfig.LOGIN_MODE == "LOCAL":
    logger.info("Using LOCAL auth mode (email+password, LOCAL-issuer JWTs)")
    get_current_user_oauth = get_current_user_local
else:
    logger.info("Using OIDC authentication")
    get_current_user_oauth = get_current_user_oidc


from typing import Annotated
from utils.config import is_omniadmin as _is_omniadmin


async def require_editor_for_writes(
    request: Request,
    auth_context: Annotated[AuthContext, Depends(get_current_user_oauth)],
    db: Annotated[Session, Depends(get_db)],
) -> AuthContext:
    """Block viewer-role users from write operations (POST/PUT/PATCH/DELETE).

    Exemptions — viewer-legitimate writes:
      - POST .../invitations/{id}/respond  (accept or decline a collaboration invite)
    """
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return auth_context
    # Viewers may accept/decline their own invitations
    if request.url.path.endswith("/respond"):
        return auth_context
    email = auth_context.identity.email
    if _is_omniadmin(email):
        return auth_context
    user = UserService.get_user_by_email(db, email)
    if user and user.platform_role == 'viewer':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewer role cannot create or modify resources",
        )
    return auth_context
