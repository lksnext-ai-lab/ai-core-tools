"""
Development authentication utilities.

This module provides JWT token generation for development mode,
bypassing OIDC authentication for easier local testing.

SECURITY WARNING: Only use in development environments with DEVELOPMENT_MODE=true
"""

import jwt
from datetime import datetime, timedelta
from typing import Dict, Any
from config import SECRET_KEY

# Constants for dev tokens
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24
DEV_ISSUER = "ia-core-tools-dev"
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
    now = datetime.utcnow()
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
        "expires_at": expiration.isoformat() + "Z",
        "token_type": "Bearer",
    }


def decode_dev_token(token: str) -> Dict[str, Any]:
    """
    Decode and validate a development JWT token.
    
    Args:
        token: The JWT token string
        
    Returns:
        Dict containing the decoded token payload
        
    Raises:
        jwt.InvalidTokenError: If token is invalid, expired, or malformed
        jwt.ExpiredSignatureError: If token has expired
    """
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            audience=DEV_AUDIENCE,
            issuer=DEV_ISSUER,
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise jwt.ExpiredSignatureError("Dev token has expired")
    except jwt.InvalidTokenError as e:
        raise jwt.InvalidTokenError(f"Invalid dev token: {str(e)}")
