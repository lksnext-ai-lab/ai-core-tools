"""
Development authentication utilities.

This module provides JWT token generation for development mode,
bypassing OIDC authentication for easier local testing.

SECURITY WARNING: Only use in development environments with OIDC_ENABLED=false
"""

import jwt
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from config import SECRET_KEY

# Constants for dev tokens
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24
DEV_ISSUER = "ia-core-tools-dev"
LOCAL_AUTH_ISSUER = "ia-core-tools-local-auth"
DEV_AUDIENCE = "ia-core-tools-api"


def generate_dev_token(email: str, name: str = None) -> Dict[str, Any]:
    """
    Generate a development JWT token for a user.
    
    This creates a simple JWT token with email and name claims,
    signed with the application's SECRET_KEY. Used for dev mode
    authentication bypassing OIDC.
    
    Args:
        email: User's email address
        name: User's display name (optional)
        
    Returns:
        Dict containing:
            - access_token: The JWT token string
            - expires_at: ISO format expiration timestamp
            - token_type: "Bearer"
            
    Example:
        >>> result = generate_dev_token("dev@example.com", "Dev User")
        >>> result["access_token"]
        'eyJ0eXAiOiJKV1QiLCJhbGc...'
    """
    now = datetime.now(timezone.utc)
    expiration = now + timedelta(hours=JWT_EXPIRATION_HOURS)
    
    # Build JWT payload with minimal claims
    payload = {
        "sub": f"dev-user-{email}",  # Subject (unique user identifier)
        "email": email,              # User's email (primary claim)
        "name": name or email,       # Display name (fallback to email)
        "iat": now,                  # Issued at
        "exp": expiration,           # Expiration time
        "iss": DEV_ISSUER,          # Issuer
        "aud": DEV_AUDIENCE,        # Audience
    }
    
    # Generate the token
    token = jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)
    
    return {
        "access_token": token,
        "expires_at": expiration.replace(tzinfo=None).isoformat() + "Z",
        "token_type": "Bearer",
    }


def generate_local_auth_token(email: str, name: str = None) -> Dict[str, Any]:
    """Generate a production JWT token for SaaS local (email+password) auth.

    Uses a distinct issuer so local-auth tokens are distinguishable from
    dev-mode tokens and cannot be issued by the dev-login bypass endpoint.
    """
    now = datetime.now(timezone.utc)
    expiration = now + timedelta(hours=JWT_EXPIRATION_HOURS)
    payload = {
        "sub": email,
        "email": email,
        "name": name or email,
        "iat": now,
        "exp": expiration,
        "iss": LOCAL_AUTH_ISSUER,
        "aud": DEV_AUDIENCE,
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)
    return {
        "access_token": token,
        "expires_at": expiration.replace(tzinfo=None).isoformat() + "Z",
        "token_type": "Bearer",
    }


def decode_dev_token(token: str) -> Dict[str, Any]:
    """Decode and validate a development or local-auth JWT token.

    Accepts tokens from both DEV_ISSUER (FAKE login) and LOCAL_AUTH_ISSUER
    (SaaS email+password login). Raises jwt.InvalidTokenError on failure.
    """
    last_error: Exception = jwt.InvalidTokenError("Invalid token")
    for issuer in (DEV_ISSUER, LOCAL_AUTH_ISSUER):
        try:
            return jwt.decode(
                token,
                SECRET_KEY,
                algorithms=[JWT_ALGORITHM],
                audience=DEV_AUDIENCE,
                issuer=issuer,
            )
        except jwt.ExpiredSignatureError:
            raise jwt.ExpiredSignatureError("Token has expired")
        except jwt.InvalidTokenError as e:
            last_error = e
    raise jwt.InvalidTokenError(f"Invalid token: {last_error}")
