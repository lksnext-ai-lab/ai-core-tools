"""Local email+password authentication service for SaaS mode."""
import os
import bcrypt
from datetime import datetime, timedelta
from typing import Optional
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from models.user import User
from repositories.user_repository import UserRepository
from repositories.user_credential_repository import UserCredentialRepository
from repositories.subscription_repository import SubscriptionRepository
from models.subscription import SubscriptionTier
from utils.logger import get_logger

logger = get_logger(__name__)

_TOKEN_SALT_VERIFY = "email-verification"
_TOKEN_SALT_RESET = "password-reset"
_VERIFY_TOKEN_MAX_AGE_SECONDS = 24 * 3600  # 24 hours
_RESET_TOKEN_MAX_AGE_SECONDS = 1 * 3600   # 1 hour


def _get_serializer() -> URLSafeTimedSerializer:
    secret = os.getenv("SECRET_KEY", "change-me")
    return URLSafeTimedSerializer(secret)


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


class LocalAuthService:
    """Handles email+password registration, verification, login, and password reset."""

    @staticmethod
    def register(db: Session, email: str, password: str) -> User:
        """Register a new user with email+password.

        Creates User, UserCredential (unverified), and Free Subscription.
        Sends a verification email via EmailService.
        Raises HTTP 409 if email is already in use.
        """
        user_repo = UserRepository(db)
        existing = user_repo.get_by_email(email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email address already exists.",
            )

        # Create user record
        user = User(
            email=email,
            name=email.split("@")[0],  # Default name from email prefix
            auth_method="local",
            email_verified=False,
            is_active=True,
        )
        db.add(user)
        db.flush()  # Get user_id

        # Create credential
        cred_repo = UserCredentialRepository(db)
        hashed = _hash_password(password)
        cred_repo.create(user_id=user.user_id, hashed_password=hashed)

        # Generate and store verification token
        token = LocalAuthService._generate_verification_token(user.email)
        expiry = datetime.utcnow() + timedelta(seconds=_VERIFY_TOKEN_MAX_AGE_SECONDS)
        cred_repo.set_verification_token(user.user_id, token, expiry)

        # Create Free subscription
        sub_repo = SubscriptionRepository(db)
        sub_repo.create(user_id=user.user_id, tier=SubscriptionTier.FREE)

        db.commit()
        db.refresh(user)

        # Send verification email (best-effort — do not fail registration on email error)
        try:
            from services.email_service import EmailService
            EmailService.send_verification_email(to=email, token=token)
        except Exception as exc:
            logger.warning("Failed to send verification email to %s: %s", email, exc)

        return user

    @staticmethod
    def verify_email(db: Session, token: str) -> User:
        """Validate an email verification token and mark the user as verified.

        Raises HTTP 400 if token is invalid or expired.
        """
        email = LocalAuthService._decode_token(token, salt=_TOKEN_SALT_VERIFY)

        user_repo = UserRepository(db)
        user = user_repo.get_by_email(email)
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token.")

        cred_repo = UserCredentialRepository(db)
        cred = cred_repo.get_by_user_id(user.user_id)
        if not cred or cred.is_verified:
            # Already verified or no credential — treat as success
            if cred and cred.is_verified:
                return user
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token.")

        # Check stored token matches and is not expired
        if cred.verification_token != token:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token.")
        if cred.verification_token_expiry and datetime.utcnow() > cred.verification_token_expiry:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification token has expired.")

        cred_repo.mark_verified(user.user_id)
        user.email_verified = True
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def login(db: Session, email: str, password: str) -> User:
        """Verify email+password credentials and return the User.

        Raises HTTP 401 for invalid credentials or unverified email.
        """
        user_repo = UserRepository(db)
        user = user_repo.get_by_email(email)
        if not user or user.auth_method != "local":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )

        cred_repo = UserCredentialRepository(db)
        cred = cred_repo.get_by_user_id(user.user_id)
        if not cred or not _verify_password(password, cred.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )

        if not cred.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Please verify your email address before logging in.",
            )

        return user

    @staticmethod
    def request_password_reset(db: Session, email: str) -> None:
        """Generate a password reset token and send reset email.

        Always returns silently (even if email not found) to prevent user enumeration.
        """
        user_repo = UserRepository(db)
        user = user_repo.get_by_email(email)
        if not user or user.auth_method != "local":
            return  # Silent: do not reveal whether account exists

        token = LocalAuthService._generate_reset_token(email)
        expiry = datetime.utcnow() + timedelta(seconds=_RESET_TOKEN_MAX_AGE_SECONDS)

        cred_repo = UserCredentialRepository(db)
        cred_repo.set_reset_token(user.user_id, token, expiry)
        db.commit()

        try:
            from services.email_service import EmailService
            EmailService.send_password_reset_email(to=email, token=token)
        except Exception as exc:
            logger.warning("Failed to send password reset email to %s: %s", email, exc)

    @staticmethod
    def complete_password_reset(db: Session, token: str, new_password: str) -> User:
        """Validate a password reset token and update the user's password.

        Raises HTTP 400 if token is invalid or expired.
        """
        email = LocalAuthService._decode_token(token, salt=_TOKEN_SALT_RESET)

        user_repo = UserRepository(db)
        user = user_repo.get_by_email(email)
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token.")

        cred_repo = UserCredentialRepository(db)
        cred = cred_repo.get_by_user_id(user.user_id)
        if not cred or cred.reset_token != token:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token.")
        if cred.reset_token_expiry and datetime.utcnow() > cred.reset_token_expiry:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password reset token has expired.")

        hashed = _hash_password(new_password)
        cred_repo.update_password(user.user_id, hashed)
        db.commit()
        db.refresh(user)
        return user

    # ── Private helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _generate_verification_token(email: str) -> str:
        return _get_serializer().dumps(email, salt=_TOKEN_SALT_VERIFY)

    @staticmethod
    def _generate_reset_token(email: str) -> str:
        return _get_serializer().dumps(email, salt=_TOKEN_SALT_RESET)

    @staticmethod
    def _decode_token(token: str, salt: str) -> str:
        """Decode a signed token; raises HTTP 400 on invalid/expired."""
        try:
            email = _get_serializer().loads(
                token,
                salt=salt,
                max_age=_VERIFY_TOKEN_MAX_AGE_SECONDS if salt == _TOKEN_SALT_VERIFY else _RESET_TOKEN_MAX_AGE_SECONDS,
            )
            return email
        except SignatureExpired:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token has expired.")
        except BadSignature:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token.")
