from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    """Request body for SaaS email+password registration."""
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    """Request body for SaaS email+password login."""
    email: EmailStr
    password: str


class VerifyEmailRequest(BaseModel):
    """Request body for email verification token submission."""
    token: str


class PasswordResetRequest(BaseModel):
    """Request body for initiating a password reset."""
    email: EmailStr


class PasswordResetComplete(BaseModel):
    """Request body for completing a password reset."""
    token: str
    new_password: str
