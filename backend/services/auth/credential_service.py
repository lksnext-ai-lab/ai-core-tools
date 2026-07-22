"""Credential lifecycle service for LOCAL auth mode.

Handles password hashing (bcrypt via thread-pool), exponential account lockout,
set-password token issuance/consumption, and change-password flows.  Raises
typed domain exceptions; the HTTP layer maps them to status codes.

Lockout: ``base * 2^(failed_attempts - threshold)`` seconds (default threshold=5,
base=60 s).  Omniadmins are exempt.

SMTP-off bypass: when ``smtp_configured()`` is False the ``is_verified`` gate on
login is skipped, allowing self-hosted deployments without email to work.
"""

import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi.concurrency import run_in_threadpool
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from models.user import User, PlatformRole
from repositories.user_credential_repository import UserCredentialRepository
from repositories.user_repository import UserRepository
from schemas.local_auth_schemas import check_password_not_email
from services.auth.refresh_service import RefreshService
from services.email import smtp_configured
from utils.config import Config, is_omniadmin
from utils.logger import get_logger
from utils.secret_key import get_secret_key

logger = get_logger(__name__)

_LOCKOUT_THRESHOLD: int = Config.get_int_env_var("LOCAL_LOCKOUT_THRESHOLD", default=5)
_LOCKOUT_BASE_SECONDS: int = Config.get_int_env_var("LOCAL_LOCKOUT_BASE_SECONDS", default=60)

_TOKEN_SALT_SET_PASSWORD = "local-set-password-v1"
_SET_PASSWORD_TOKEN_MAX_AGE_SECONDS: int = (
    Config.get_int_env_var("LOCAL_SET_PASSWORD_TOKEN_MAX_AGE_HOURS", default=48) * 3600
)

# Evaluated on every unknown-user attempt to keep timing uniform (anti-enumeration).
_DUMMY_HASH: str = bcrypt.hashpw(b"__dummy_sentinel__", bcrypt.gensalt(rounds=12)).decode("utf-8")



class CredentialError(Exception):
    """Generic credential failure.  Maps to HTTP 401 Unauthorized."""


class AccountLockedError(Exception):
    """Account temporarily locked after excessive failures.  Maps to HTTP 429.

    Attributes:
        locked_until: UTC-aware expiry datetime; use for the ``Retry-After`` header.
    """

    def __init__(self, message: str, locked_until: Optional[datetime] = None) -> None:
        super().__init__(message)
        self.locked_until: Optional[datetime] = locked_until


class TokenError(Exception):
    """Set-password token is invalid, expired, or already used.  Maps to HTTP 400."""


class UserAlreadyExistsError(Exception):
    """Admin create: email already registered.  Maps to HTTP 409 Conflict."""


class PasswordPolicyError(Exception):
    """Password rejected by policy.  Not a subclass of ``CredentialError`` so HTTP
    handlers can distinguish 400 (policy) from 401 (auth failure).
    """


class InactiveAccountError(CredentialError):
    """Account is deactivated.  Maps to HTTP 403 Forbidden."""



def _get_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_secret_key())


def _sync_hash(plain: str) -> str:
    """Synchronous bcrypt hash — dispatched to thread-pool by callers."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def _sync_verify(plain: str, hashed: str) -> bool:
    """Synchronous bcrypt verify — dispatched to thread-pool by callers."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))



async def hash_password(plain: str) -> str:
    """Hash a plaintext password off the event loop."""
    return await run_in_threadpool(_sync_hash, plain)


async def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash off the event loop."""
    return await run_in_threadpool(_sync_verify, plain, hashed)


def _compute_lockout_duration(failed_attempts: int) -> timedelta:
    """Return the exponential backoff duration for the given failed-attempt count."""
    exponent = min(max(0, failed_attempts - _LOCKOUT_THRESHOLD), 10)
    seconds = _LOCKOUT_BASE_SECONDS * (2 ** exponent)
    return timedelta(seconds=seconds)



class CredentialService:
    """Credential lifecycle for LOCAL auth mode.  All methods are async."""

    @staticmethod
    async def authenticate(db: Session, email: str, password: str) -> User:
        """Authenticate by email and password.

        Implements anti-enumeration (dummy bcrypt on unknown users), exponential
        lockout, and the SMTP-off verification bypass.

        Raises:
            AccountLockedError: Account is currently locked out.
            CredentialError: All other failures (wrong password, unknown user,
                unverified, inactive).  Deliberately opaque to callers.
        """
        user_repo = UserRepository(db)
        cred_repo = UserCredentialRepository(db)

        user: Optional[User] = user_repo.get_by_email(email)

        if user is None or user.auth_method != "local":
            # Run a dummy verify to keep timing uniform even when the user does
            # not exist, preventing enumeration via response time.
            await run_in_threadpool(_sync_verify, password, _DUMMY_HASH)
            logger.warning("auth:login_failed reason=unknown_user email=%s", email)
            raise CredentialError("Invalid email or password.")

        cred = cred_repo.get_by_user_id(user.user_id)
        if cred is None:
            await run_in_threadpool(_sync_verify, password, _DUMMY_HASH)
            logger.warning("auth:login_failed reason=no_credential user_id=%s", user.user_id)
            raise CredentialError("Invalid email or password.")

        # Omniadmins are exempt from lockout to prevent self-lockout DoS.
        # Route-level rate limiting provides their brute-force protection instead.
        if not is_omniadmin(email):
            now = datetime.now(timezone.utc)
            locked = cred.locked_until
            if locked is not None and locked.tzinfo is None:
                locked = locked.replace(tzinfo=timezone.utc)
            if locked is not None and locked > now:
                logger.warning(
                    "auth:login_rejected reason=account_locked user_id=%s locked_until=%s",
                    user.user_id,
                    cred.locked_until.isoformat(),
                )
                raise AccountLockedError(
                    "Account is temporarily locked due to too many failed attempts. "
                    "Please try again later.",
                    locked_until=locked,
                )

        password_ok: bool = await run_in_threadpool(_sync_verify, password, cred.hashed_password)

        if not password_ok:
            if cred.failed_attempts is None:
                cred.failed_attempts = 0
            cred.failed_attempts += 1

            if not is_omniadmin(email) and cred.failed_attempts >= _LOCKOUT_THRESHOLD:
                duration = _compute_lockout_duration(cred.failed_attempts)
                cred.locked_until = datetime.now(timezone.utc) + duration
                logger.warning(
                    "auth:account_locked user_id=%s failed_attempts=%s locked_until=%s",
                    user.user_id,
                    cred.failed_attempts,
                    cred.locked_until.isoformat(),
                )
            else:
                logger.warning(
                    "auth:login_failed reason=wrong_password user_id=%s failed_attempts=%s",
                    user.user_id,
                    cred.failed_attempts,
                )

            db.flush()
            db.commit()
            raise CredentialError("Invalid email or password.")

        # SMTP-off bypass: skip is_verified when no outbound email is configured.
        if smtp_configured() and not cred.is_verified:
            logger.warning(
                "auth:login_failed reason=email_not_verified user_id=%s", user.user_id
            )
            raise CredentialError(
                "Please verify your email address before logging in."
            )

        if not user.is_active:
            logger.warning(
                "auth:login_failed reason=inactive_account user_id=%s", user.user_id
            )
            raise InactiveAccountError("This account has been deactivated.")

        cred.failed_attempts = 0
        cred.locked_until = None

        # Promote to platform_role='admin' if this email was added to
        # AICT_OMNIADMINS after the account was originally created.
        if is_omniadmin(email) and user.platform_role != PlatformRole.ADMIN.value:
            user.platform_role = PlatformRole.ADMIN.value

        db.flush()
        db.commit()

        logger.info("auth:login_success user_id=%s", user.user_id)
        return user

    @staticmethod
    async def admin_create_user(db: Session, email: str, name: str) -> User:
        """Create a LOCAL auth user with a placeholder credential (no password set).

        Raises:
            UserAlreadyExistsError: Email already registered.
        """
        user_repo = UserRepository(db)
        existing = user_repo.get_by_email(email)
        if existing is not None:
            raise UserAlreadyExistsError(
                f"A user with email '{email}' already exists."
            )

        user = User(
            email=email,
            name=name,
            auth_method="local",
            is_active=True,
            email_verified=not smtp_configured(),
            platform_role=PlatformRole.ADMIN.value if is_omniadmin(email) else PlatformRole.VIEWER.value,
        )
        db.add(user)
        db.flush()

        # Placeholder hash: random secret that cannot be guessed; replaced on set-password.
        placeholder_hash = await run_in_threadpool(
            _sync_hash, secrets.token_urlsafe(32)
        )
        cred_repo = UserCredentialRepository(db)
        cred_repo.create(user_id=user.user_id, hashed_password=placeholder_hash)

        db.commit()
        db.refresh(user)

        logger.info("auth:admin_create_user user_id=%s email=%s", user.user_id, email)
        return user

    @staticmethod
    async def admin_set_password(db: Session, user_id: int, new_password: str) -> None:
        """Forcibly set a user's password, reset lockout, and revoke all refresh sessions.

        Raises:
            CredentialError: Credential record not found.
        """
        cred_repo = UserCredentialRepository(db)
        cred = cred_repo.get_by_user_id(user_id)
        if cred is None:
            logger.warning("auth:admin_set_password credential_not_found user_id=%s", user_id)
            raise CredentialError("Credential record not found.")

        hashed = await hash_password(new_password)
        cred_repo.update_password(user_id, hashed)

        # Mark verified so bootstrap doesn't re-issue a set-password link on restart.
        cred.is_verified = True
        cred.failed_attempts = 0
        cred.locked_until = None
        db.flush()

        RefreshService.revoke_all(db, user_id)

        db.commit()
        logger.info("auth:admin_set_password user_id=%s", user_id)

    @staticmethod
    def issue_set_password_token(db: Session, user_id: int) -> str:
        """Issue a single-use time-limited set-password token (itsdangerous HMAC).

        Stores the raw token in ``reset_token`` / ``reset_token_expiry`` as a
        single-use marker; cleared on consumption.

        Raises:
            CredentialError: User or credential record not found.
        """
        user_repo = UserRepository(db)
        user = user_repo.get_by_id(user_id)
        if user is None:
            logger.warning("auth:issue_set_password_token user_not_found user_id=%s", user_id)
            raise CredentialError("User not found.")

        cred_repo = UserCredentialRepository(db)
        cred = cred_repo.get_by_user_id(user_id)
        if cred is None:
            logger.warning(
                "auth:issue_set_password_token credential_not_found user_id=%s", user_id
            )
            raise CredentialError("Credential record not found.")

        token = _get_serializer().dumps(user.email, salt=_TOKEN_SALT_SET_PASSWORD)
        expiry = datetime.now(timezone.utc) + timedelta(seconds=_SET_PASSWORD_TOKEN_MAX_AGE_SECONDS)

        cred.reset_token = token
        cred.reset_token_expiry = expiry
        db.flush()
        db.commit()

        logger.info(
            "auth:set_password_token_issued user_id=%s expires_at=%s",
            user_id,
            expiry.isoformat(),
        )
        return token

    @staticmethod
    async def consume_set_password_token(
        db: Session, token: str, new_password: str
    ) -> User:
        """Validate a set-password token, apply the new password, and mark the account verified.

        Raises:
            TokenError: Signature invalid, expired, or token already consumed.
        """
        try:
            email: str = _get_serializer().loads(
                token,
                salt=_TOKEN_SALT_SET_PASSWORD,
                max_age=_SET_PASSWORD_TOKEN_MAX_AGE_SECONDS,
            )
        except SignatureExpired:
            logger.warning("auth:set_password_token_rejected reason=expired")
            raise TokenError("Set-password link has expired.")
        except BadSignature:
            logger.warning("auth:set_password_token_rejected reason=bad_signature")
            raise TokenError("Set-password link is invalid.")

        user_repo = UserRepository(db)
        user = user_repo.get_by_email(email)
        if user is None:
            logger.warning("auth:set_password_token_rejected reason=user_not_found email=%s", email)
            raise TokenError("Set-password link is invalid.")

        cred_repo = UserCredentialRepository(db)
        cred = cred_repo.get_by_user_id(user.user_id)
        if cred is None or not hmac.compare_digest(cred.reset_token or "", token):
            logger.warning(
                "auth:set_password_token_rejected reason=already_used_or_not_found user_id=%s",
                user.user_id,
            )
            raise TokenError("Set-password link has already been used or is invalid.")

        check_password_not_email(new_password, email)

        hashed = await hash_password(new_password)
        cred_repo.update_password(user.user_id, hashed)
        cred_repo.mark_verified(user.user_id)
        cred.failed_attempts = 0
        cred.locked_until = None
        user.email_verified = True
        db.flush()
        db.commit()
        db.refresh(user)

        logger.info("auth:set_password_token_consumed user_id=%s", user.user_id)
        return user

    @staticmethod
    async def change_password(
        db: Session, user: User, current_password: str, new_password: str
    ) -> None:
        """Verify current password, apply new password, and revoke all refresh sessions.

        Raises:
            CredentialError: Current password is incorrect or credential not found.
        """
        cred_repo = UserCredentialRepository(db)
        cred = cred_repo.get_by_user_id(user.user_id)
        if cred is None:
            raise CredentialError("No credential record found for this account.")

        current_ok: bool = await run_in_threadpool(
            _sync_verify, current_password, cred.hashed_password
        )
        if not current_ok:
            logger.warning(
                "auth:change_password_failed reason=wrong_current user_id=%s", user.user_id
            )
            raise CredentialError("Current password is incorrect.")

        check_password_not_email(new_password, user.email)

        hashed = await hash_password(new_password)
        cred_repo.update_password(user.user_id, hashed)
        RefreshService.revoke_all(db, user.user_id)

        db.commit()
        logger.info("auth:change_password_success user_id=%s", user.user_id)
