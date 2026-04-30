from pydantic import BaseModel, EmailStr, field_validator


def _strip_token(v):
    # Tokens are long random strings copy-pasted from links / emails — trim
    # whitespace. Passwords are intentionally NOT stripped (could contain
    # legitimate leading/trailing spaces) per OWASP password storage guidance.
    return v.strip() if isinstance(v, str) else v


class RegisterRequest(BaseModel):
    """Request body for SaaS email+password registration."""
    email: EmailStr
    password: str  # not stripped on purpose — see _strip_token note


class LoginRequest(BaseModel):
    """Request body for SaaS email+password login."""
    email: EmailStr
    password: str  # not stripped on purpose


class VerifyEmailRequest(BaseModel):
    """Request body for email verification token submission."""
    token: str

    @field_validator("token", mode="before")
    @classmethod
    def _normalize_token(cls, v):
        return _strip_token(v)


class PasswordResetRequest(BaseModel):
    """Request body for initiating a password reset."""
    email: EmailStr


class PasswordResetComplete(BaseModel):
    """Request body for completing a password reset."""
    token: str
    new_password: str  # not stripped on purpose

    @field_validator("token", mode="before")
    @classmethod
    def _normalize_token(cls, v):
        return _strip_token(v)
