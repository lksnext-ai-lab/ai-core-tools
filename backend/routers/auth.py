from fastapi import APIRouter, Request, HTTPException, status, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
import os
import uuid
import httpx
from datetime import datetime, timedelta
import jwt
from urllib.parse import urlencode

# Import models and services
from models.user import User
from services.user_service import UserService
from db.database import SessionLocal
from utils.logger import get_logger
from utils.config import is_omniadmin

logger = get_logger(__name__)

auth_router = APIRouter()

# Import authentication configuration
from utils.auth_config import AuthConfig

# Use configuration from AuthConfig
GOOGLE_CLIENT_ID = AuthConfig.GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET = AuthConfig.GOOGLE_CLIENT_SECRET
GOOGLE_DISCOVERY_URL = AuthConfig.GOOGLE_DISCOVERY_URL
GOOGLE_REDIRECT_URI = AuthConfig.GOOGLE_REDIRECT_URI
FRONTEND_URL = AuthConfig.FRONTEND_URL

# JWT Configuration for session tokens
JWT_SECRET = AuthConfig.JWT_SECRET
JWT_ALGORITHM = AuthConfig.JWT_ALGORITHM
JWT_EXPIRATION_HOURS = AuthConfig.JWT_EXPIRATION_HOURS

# Schemas
class LoginURLResponse(BaseModel):
    login_url: str
    state: str

class LoginModeResponse(BaseModel):
    mode: str
    message: Optional[str] = None
    login_url: Optional[str] = None
    state: Optional[str] = None

class FakeLoginRequest(BaseModel):
    email: str

class FakeLoginResponse(BaseModel):
    access_token: str
    user: dict
    expires_at: str

class AuthCallbackResponse(BaseModel):
    access_token: str
    user: dict
    expires_at: str

class UserInfoResponse(BaseModel):
    user_id: int
    email: str
    name: Optional[str]
    is_authenticated: bool
    is_admin: bool

# ==================== HELPER FUNCTIONS ====================

async def get_google_oauth_config():
    """Get Google OAuth configuration from discovery URL"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(GOOGLE_DISCOVERY_URL)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"Failed to get Google OAuth config: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to configure OAuth"
        )

def create_jwt_token(user_data: dict, expires_delta: timedelta = None) -> str:
    """Create JWT token for user session"""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    
    to_encode = user_data.copy()
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def verify_jwt_token(token: str) -> Optional[dict]:
    """Verify and decode JWT token or check development tokens"""
    # First check if it's a development token
    if AuthConfig.is_development_mode():
        dev_user = AuthConfig.get_dev_user(token)
        if dev_user:
            return dev_user
    
    # Try to verify as JWT token
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    except Exception:
        return None

# ==================== AUTHENTICATION ENDPOINTS ====================

@auth_router.get("/login")
async def login():
    """
    Get login information based on the configured login mode
    Returns different responses for OIDC vs FAKE mode
    """
    # Check if in FAKE login mode
    if AuthConfig.is_fake_login_mode():
        return LoginModeResponse(
            mode="FAKE",
            message="Fake login mode - POST email to /auth/fake-login"
        )
    
    # OIDC mode - proceed with OAuth
    if not AuthConfig.is_oauth_configured():
        if AuthConfig.is_development_mode():
            # In development mode, return info about available tokens
            dev_tokens = list(AuthConfig.DEV_USERS.keys())
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Running in development mode - OAuth not configured",
                    "development_mode": True,
                    "available_tokens": dev_tokens,
                    "instructions": "Use one of the development tokens in Authorization header"
                }
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "message": "Google OAuth not configured",
                    "instructions": "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables, or set DEVELOPMENT_MODE=true for testing"
                }
            )
    
    try:
        # Get Google OAuth configuration
        oauth_config = await get_google_oauth_config()
        authorization_endpoint = oauth_config.get('authorization_endpoint')
        
        if not authorization_endpoint:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid OAuth configuration"
            )
        
        # Generate state parameter for security
        state = str(uuid.uuid4())
        
        # Build authorization URL
        params = {
            'client_id': GOOGLE_CLIENT_ID,
            'redirect_uri': GOOGLE_REDIRECT_URI,
            'scope': 'openid email profile',
            'response_type': 'code',
            'state': state,
            'access_type': 'offline',
            'prompt': 'consent'
        }
        
        login_url = f"{authorization_endpoint}?{urlencode(params)}"
        
        return LoginModeResponse(
            mode="OIDC",
            login_url=login_url,
            state=state
        )
        
    except Exception as e:
        logger.error(f"Error generating login URL: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate login URL"
        )

@auth_router.post("/fake-login", response_model=FakeLoginResponse)
async def fake_login(request: FakeLoginRequest):
    """
    Fake login endpoint for development/testing only.
    Accepts an email and logs in if the user exists in the database.
    Only works when AICT_LOGIN=FAKE
    """
    # Check if fake login mode is enabled
    if not AuthConfig.is_fake_login_mode():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Fake login is not enabled. Set AICT_LOGIN=FAKE in environment variables."
        )
    
    if not request.email or '@' not in request.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Valid email address is required"
        )
    
    session = SessionLocal()
    try:
        # Check if user exists in database
        user = session.query(User).filter(User.email == request.email).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with email {request.email} not found in database. User must exist to use fake login."
            )
        
        logger.info(f"Fake login successful for user: {user.email}")
        
        # Create JWT token for session
        user_data = {
            'user_id': user.user_id,
            'email': user.email,
            'name': user.name,
            'google_id': f'fake-{user.user_id}'
        }
        
        jwt_token = create_jwt_token(user_data)
        expires_at = (datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)).isoformat()
        
        return FakeLoginResponse(
            access_token=jwt_token,
            user={
                'user_id': user.user_id,
                'email': user.email,
                'name': user.name,
                'is_admin': is_omniadmin(user.email)
            },
            expires_at=expires_at
        )
        
    finally:
        session.close()

@auth_router.get("/callback")
async def auth_callback(request: Request):
    """
    Handle Google OAuth callback
    """
    # Get authorization code and state from query parameters
    code = request.query_params.get('code')
    state = request.query_params.get('state')
    error = request.query_params.get('error')
    
    if error:
        logger.error(f"OAuth error: {error}")
        # Redirect to frontend login page with error
        return RedirectResponse(url=f"{FRONTEND_URL}/auth/error?error={error}")
    
    if not code or not state:
        logger.error("Missing code or state in OAuth callback")
        return RedirectResponse(url=f"{FRONTEND_URL}/auth/error?error=missing_parameters")
    
    try:
        # Get Google OAuth configuration
        oauth_config = await get_google_oauth_config()
        token_endpoint = oauth_config.get('token_endpoint')
        userinfo_endpoint = oauth_config.get('userinfo_endpoint')
        
        # Exchange authorization code for access token
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                token_endpoint,
                data={
                    'client_id': GOOGLE_CLIENT_ID,
                    'client_secret': GOOGLE_CLIENT_SECRET,
                    'code': code,
                    'grant_type': 'authorization_code',
                    'redirect_uri': GOOGLE_REDIRECT_URI
                },
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            token_response.raise_for_status()
            token_data = token_response.json()
            
            # Get user information
            access_token = token_data.get('access_token')
            user_response = await client.get(
                userinfo_endpoint,
                headers={'Authorization': f'Bearer {access_token}'}
            )
            user_response.raise_for_status()
            user_info = user_response.json()
        
        # Create or get user in database
        session = SessionLocal()
        try:
            user, created = UserService.get_or_create_user(
                db=session,
                email=user_info.get('email'),
                name=user_info.get('name')
            )
            
            if created:
                logger.info(f"Created new user: {user.email}")
            else:
                logger.info(f"User logged in: {user.email}")
            
            # Create JWT token for session
            user_data = {
                'user_id': user.user_id,
                'email': user.email,
                'name': user.name,
                'google_id': user_info.get('sub')
            }
            
            jwt_token = create_jwt_token(user_data)
            expires_at = (datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)).isoformat()
            
            # Redirect to frontend with token (use /login/success to avoid /auth prefix that goes to backend)
            redirect_url = f"{FRONTEND_URL}/login/success?token={jwt_token}&expires={expires_at}"
            return RedirectResponse(url=redirect_url)
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Error in OAuth callback: {str(e)}")
        return RedirectResponse(url=f"{FRONTEND_URL}/auth/error?error=callback_failed")

@auth_router.post("/verify")
async def verify_token(request: Request):
    """
    Verify JWT token and return user info
    """
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid authorization header"
            )
        
        token = auth_header.split(' ')[1]
        
        # Verify token
        payload = verify_jwt_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )
        
        # Return user info
        return UserInfoResponse(
            user_id=payload.get('user_id'),
            email=payload.get('email'),
            name=payload.get('name'),
            is_authenticated=True
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token verification failed"
        )

@auth_router.post("/logout")
async def logout():
    """
    Logout user (client-side token removal)
    """
    return {"message": "Logged out successfully"}

@auth_router.get("/config")
async def get_auth_config():
    """
    Get authentication configuration status (for debugging)
    """
    return {
        "auth_config": AuthConfig.get_config_summary(),
        "login_mode": AuthConfig.LOGIN_MODE,
        "oauth_configured": AuthConfig.is_oauth_configured(),
        "development_mode": AuthConfig.is_development_mode(),
        "fake_login_enabled": AuthConfig.is_fake_login_mode(),
        "available_dev_tokens": list(AuthConfig.DEV_USERS.keys()) if AuthConfig.is_development_mode() else []
    }

@auth_router.get("/me")
async def get_current_user_info(request: Request):
    """
    Get current user information
    """
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )
        
        token = auth_header.split(' ')[1]
        
        # Verify token
        payload = verify_jwt_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )
        
        # Get fresh user data from database
        session = SessionLocal()
        try:
            user = session.query(User).filter(User.user_id == payload.get('user_id')).first()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )
            
            return UserInfoResponse(
                user_id=user.user_id,
                email=user.email,
                name=user.name,
                is_authenticated=True,
                is_admin=is_omniadmin(user.email)
            )
            
        finally:
            session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user info: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user information"
        )

@auth_router.get("/pending-invitations")
async def get_pending_invitations(request: Request):
    """
    Get pending collaboration invitations for the current user
    """
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )
        
        token = auth_header.split(' ')[1]
        
        # Verify token
        payload = verify_jwt_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )
        
        user_id = payload.get('user_id')
        
        # Get pending invitations using the collaboration service
        from services.app_collaboration_service import AppCollaborationService
        db = SessionLocal()
        try:
            collaboration_service = AppCollaborationService(db)
            invitations = collaboration_service.get_user_pending_invitations(user_id)
        finally:
            db.close()
        
        # Format response
        response = []
        for invitation in invitations:
            response.append({
                'id': invitation.id,
                'app_id': invitation.app_id,
                'app_name': invitation.app.name if invitation.app else 'Unknown App',
                'inviter_email': invitation.inviter.email if invitation.inviter else 'Unknown',
                'inviter_name': invitation.inviter.name if invitation.inviter else None,
                'invited_at': invitation.invited_at.isoformat() if invitation.invited_at else None,
                'role': invitation.role.value if hasattr(invitation.role, 'value') else str(invitation.role)
            })
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting pending invitations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get pending invitations"
        )

@auth_router.post("/invitations/{invitation_id}/respond")
async def respond_to_invitation(invitation_id: int, action: dict, request: Request):
    """
    Accept or decline a collaboration invitation
    """
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )
        
        token = auth_header.split(' ')[1]
        
        # Verify token
        payload = verify_jwt_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )
        
        user_id = payload.get('user_id')
        action_value = action.get('action')
        
        if action_value not in ['accept', 'decline']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Action must be 'accept' or 'decline'"
            )
        
        # Respond to invitation using the collaboration service
        from services.app_collaboration_service import AppCollaborationService
        db = SessionLocal()
        try:
            collaboration_service = AppCollaborationService(db)
            success = collaboration_service.respond_to_invitation(invitation_id, user_id, action_value)
        finally:
            db.close()
        
        if success:
            return {"message": f"Invitation {action_value}ed successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to {action_value} invitation"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error responding to invitation {invitation_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to respond to invitation"
        ) 