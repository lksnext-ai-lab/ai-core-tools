"""
Authentication utilities for internal API endpoints.

This module provides FastAPI dependencies for authentication using lks-idprovider
or development mode JWT tokens.
"""

import os
import jwt
from fastapi import HTTPException, status, Depends, Request, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from lks_idprovider_fastapi import get_auth_context
from lks_idprovider.models.auth import AuthContext
from lks_idprovider.models.identity import User as LksUser
from lks_idprovider.models.token import TokenInfo
from db.database import get_db
from services.user_service import UserService
from utils.logger import get_logger
from utils.dev_auth import decode_dev_token
from utils.auth_config import AuthConfig
from typing import Optional

logger = get_logger(__name__)

# Shared HTTP bearer scheme for Swagger docs
http_bearer_scheme = HTTPBearer(auto_error=False)

# Load authentication configuration
AuthConfig.load_config()

# Authentication error message constant
AUTH_FAILED_MESSAGE = "Authentication failed"


def _create_enriched_auth_context(
    db_user,
    user_email: str,
    auth_context: Optional[AuthContext] = None,
) -> AuthContext:
    """
    Create enriched AuthContext with database user information.
    
    Args:
        db_user: Database user object
        user_email: User's email address
        auth_context: Optional existing AuthContext (for OIDC flow)
        
    Returns:
        AuthContext: Enriched with database user_id
    """
    if auth_context:
        # Use existing auth context data
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
        # Create minimal auth context (dev mode)
        enriched_identity = LksUser(
            id=str(db_user.user_id),
            username=user_email,
            email=user_email,
            name=db_user.name,
            first_name=None,
            last_name=None,
        )
        # Create minimal TokenInfo for dev mode
        dev_token_info = TokenInfo(
            token="dev-token",
            token_type="access_token",
            subject=user_email,
            audience="dev",
            issuer="dev",
            scopes=[]
        )
        return AuthContext(
            identity=enriched_identity,
            roles=[],
            token_expires_at=None,
            refresh_expires_at=None,
            provider="dev",
            scopes=[],
            token_info=dev_token_info,
        )


def _enrich_auth_context_with_db_user(
    user_email: str,
    db: Session,
    auth_context: Optional[AuthContext] = None,
    allow_user_creation: bool = True,
) -> AuthContext:
    """
    Helper function to enrich AuthContext with database user information.
    
    This function handles the common logic of:
    1. Looking up user by email
    2. Creating user if allowed and not found
    3. Checking if user is active
    4. Creating enriched AuthContext with database user_id
    
    Args:
        user_email: User's email address
        db: Database session
        auth_context: Optional existing AuthContext (for OIDC flow)
        allow_user_creation: Whether to create user if not found
        
    Returns:
        AuthContext: Enriched with database user_id
        
    Raises:
        HTTPException: If user not found/inactive or other errors
    """
    # Get or create user in database
    db_user = UserService.get_user_by_email(db, user_email)
    
    if not db_user:
        if allow_user_creation:
            # First time login - create user
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
                detail="User not found in database",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    # Check if user is active
    if hasattr(db_user, "is_active") and not db_user.is_active:
        logger.warning(f"Inactive user attempted to access: {user_email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. "
            "Please contact support for assistance.",
        )
    
    # Create enriched identity with database user_id
    return _create_enriched_auth_context(db_user, user_email, auth_context)


def get_current_user_oidc(
    auth_context: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> AuthContext:
    """
    Get current authenticated user context with database user_id using OIDC.
    
    This dependency:
    1. Validates the token using lks-idprovider (via login_required)
    2. Syncs the user to the database (creates if first login)
    3. Checks if user is active
    4. Updates AuthContext.identity.id with database user_id
    5. Returns the enriched AuthContext
    
    Args:
        auth_context: Authentication context from lks-idprovider
        db: Database session
        
    Returns:
        AuthContext: Enhanced with database user_id in identity.id
        
    Raises:
        HTTPException: If authentication fails, user is inactive, or email is missing
    """
    try:
        # Extract email from auth context
        user_email = auth_context.identity.email
        if not user_email:
            logger.error("No email found in authentication token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User email not found in token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Use helper to enrich context with database user
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


def get_current_user_dev(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(http_bearer_scheme),
    db: Session = Depends(get_db),
) -> AuthContext:
    """
    Get current authenticated user in development mode.
    
    This dependency validates development JWT tokens and looks up
    the user in the database. Used only when AICT_LOGIN=FAKE.
    
    Security constraints:
    - Only works with dev tokens generated by utils.dev_auth
    - User must exist in database (no auto-creation)
    - Checks user is_active status
    
    Args:
        request: FastAPI request providing headers
        credentials: Bearer token parsed by Swagger/HTTPBearer
        db: Database session
        
    Returns:
        AuthContext: Enriched with database user_id in identity.id
        
    Raises:
        HTTPException: If token invalid, expired, or user not found
    """
    authorization = None
    if credentials and credentials.scheme and credentials.credentials:
        authorization = f"{credentials.scheme} {credentials.credentials}"
        logger.debug("Authorization extracted via HTTPBearer security dependency")
    else:
        authorization = request.headers.get("Authorization")
        if authorization:
            logger.debug("Authorization taken directly from headers")

    try:
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization header format",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        token = authorization.replace("Bearer ", "").strip()
        
        # Decode and validate dev token
        try:
            payload = decode_dev_token(token)
        except jwt.ExpiredSignatureError:
            logger.warning("Dev token expired")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid dev token: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Extract email from token
        user_email = payload.get("email")
        if not user_email:
            logger.error("No email in dev token payload")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing email",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Use helper to enrich context with database user
        # Dev mode: no auto-creation of users
        enriched_context = _enrich_auth_context_with_db_user(
            user_email=user_email,
            db=db,
            auth_context=None,
            allow_user_creation=False,
        )
        
        logger.debug(
            f"Dev mode user authenticated: {user_email} "
            f"(DB ID: {enriched_context.identity.id})"
        )
        
        return enriched_context
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in dev authentication: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTH_FAILED_MESSAGE,
            headers={"WWW-Authenticate": "Bearer"},
        )


# Create the authentication dependency based on mode
# This is evaluated once at import time
if AuthConfig.LOGIN_MODE == "FAKE":
    logger.info("🔓 Using FAKE login mode authentication (development/testing only)")
    get_current_user_oauth = get_current_user_dev
else:
    logger.info("🔐 Using OIDC authentication")
    get_current_user_oauth = get_current_user_oidc