"""SaaS authentication endpoints: email+password registration, verification, login, password reset.

These routes are conditionally registered only when AICT_DEPLOYMENT_MODE=saas.
Rate limiting is applied via slowapi (or similar) on all public endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from db.database import get_db
from schemas.saas_auth_schemas import (
    RegisterRequest,
    LoginRequest,
    VerifyEmailRequest,
    PasswordResetRequest,
    PasswordResetComplete,
)
from services.local_auth_service import LocalAuthService
from utils.dev_auth import generate_dev_token
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["saas-auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new account with email and password.

    Sends a verification email before granting access.
    """
    user = LocalAuthService.register(db, email=request.email, password=request.password)
    return {
        "message": "Registration successful. Please check your email to verify your account.",
        "user_id": user.user_id,
        "email": user.email,
    }


@router.post("/verify-email")
async def verify_email(request: VerifyEmailRequest, db: Session = Depends(get_db)):
    """Verify an email address using the token from the verification email."""
    user = LocalAuthService.verify_email(db, token=request.token)
    return {"message": "Email verified successfully. You can now log in.", "email": user.email}


@router.post("/login")
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Log in with email and password. Returns a session token."""
    user = LocalAuthService.login(db, email=request.email, password=request.password)

    # Issue a dev-style token for session management (reuses existing token infrastructure)
    token = generate_dev_token(user.email)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "user_id": user.user_id,
            "email": user.email,
            "name": user.name,
        },
    }


@router.post("/password-reset-request", status_code=status.HTTP_202_ACCEPTED)
async def password_reset_request(request: PasswordResetRequest, db: Session = Depends(get_db)):
    """Initiate a password reset. Always returns 202 to prevent user enumeration."""
    LocalAuthService.request_password_reset(db, email=request.email)
    return {"message": "If an account with that email exists, a password reset link has been sent."}


@router.post("/password-reset")
async def password_reset(request: PasswordResetComplete, db: Session = Depends(get_db)):
    """Complete a password reset using the token from the reset email."""
    user = LocalAuthService.complete_password_reset(db, token=request.token, new_password=request.new_password)
    return {"message": "Password reset successfully. You can now log in with your new password.", "email": user.email}


@router.post("/social/{provider}")
async def social_login(provider: str):
    """Placeholder for social OIDC login (deferred implementation)."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Social login via '{provider}' is not yet implemented.",
    )
