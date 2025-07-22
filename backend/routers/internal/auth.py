from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any

# TODO: Replace with Google OAuth implementation
# For now, using a simple bearer token system as placeholder

security = HTTPBearer(auto_error=False)

# Placeholder user database (will be replaced with actual Google OAuth + DB lookup)
TEMP_USERS = {
    "temp-token-123": {
        "user_id": 2,  # Try user_id 2
        "email": "admin@example.com",
        "name": "Admin User",
        "google_id": "temp-google-id"
    },
    "temp-token-456": {
        "user_id": 1,  # Fallback user_id 1
        "email": "user1@example.com", 
        "name": "User 1",
        "google_id": "temp-google-id-1"
    },
    "temp-token-789": {
        "user_id": 3,  # Try user_id 3
        "email": "user3@example.com",
        "name": "User 3", 
        "google_id": "temp-google-id-3"
    }
}

async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Dict[Any, Any]:
    """
    Get current authenticated user.
    
    TODO: Replace this with Google OAuth implementation
    - Verify Google JWT token
    - Extract user info from token
    - Create/update user in database
    - Return user information
    
    For now, using a simple bearer token lookup as placeholder.
    """
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide Authorization header with Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    # TODO: Replace with Google OAuth token verification
    user = TEMP_USERS.get(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


def require_admin(current_user: Dict[Any, Any] = Depends(get_current_user)) -> Dict[Any, Any]:
    """
    Require admin privileges.
    
    TODO: Implement proper admin role checking
    """
    # For now, assume user_id 1 is admin
    if current_user.get("user_id") != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    
    return current_user 