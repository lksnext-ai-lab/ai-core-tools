"""Refresh-token lifecycle service for LOCAL auth mode.

Wire format (httpOnly cookie): ``"<jti>.<opaque_secret>"``.
Only the SHA-256 digest of ``opaque_secret`` is persisted; the raw value is
never logged.

Rotation: ``rotate()`` uses a ``SELECT FOR UPDATE`` row lock so concurrent
requests for the same token serialise — the second sees ``rotated_at IS NOT NULL``
and triggers full family revocation.
"""

import hashlib
import hmac
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from models.user import User
from repositories.refresh_token_repository import RefreshTokenRepository
from repositories.user_repository import UserRepository
from utils.local_auth_tokens import mint_access_token
from utils.logger import get_logger

logger = get_logger(__name__)

_REFRESH_TTL_DAYS: int = int(os.getenv("LOCAL_REFRESH_TTL_DAYS", "14"))
#: Shared with auth_cookies.py so the cookie max-age has a single source of truth.
REFRESH_TTL_DAYS: int = _REFRESH_TTL_DAYS
_OPAQUE_BYTES: int = 48  # 64 url-safe base64 chars


class RefreshTokenError(Exception):
    """Presented refresh token cannot be accepted.  Maps to HTTP 401."""


def _new_opaque() -> str:
    return secrets.token_urlsafe(_OPAQUE_BYTES)


def _new_jti() -> str:
    return uuid.uuid4().hex


def _hash_opaque(opaque: str) -> str:
    return hashlib.sha256(opaque.encode()).hexdigest()


def _compose_wire(jti: str, opaque: str) -> str:
    # Dot separator is safe: JTI is hex (no dots), opaque is url-safe base64 (no dots).
    return f"{jti}.{opaque}"


def _parse_wire(wire: str) -> tuple[str, str]:
    """Split wire value into (jti, opaque).

    Raises:
        RefreshTokenError: Invalid format.
    """
    parts = wire.split(".", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise RefreshTokenError("Invalid refresh token format.")
    return parts[0], parts[1]


def _load_user(db: Session, user_id: int) -> User:
    """Fetch active user by ID or raise ``RefreshTokenError``."""
    user_repo = UserRepository(db)
    user: Optional[User] = user_repo.get_by_id(user_id)
    if not user or not user.is_active:
        raise RefreshTokenError("User account not found or deactivated.")
    return user


class RefreshService:
    """Refresh-token issuance, rotation, and revocation."""

    @staticmethod
    def issue_session(
        db: Session,
        user: User,
        *,
        user_agent: Optional[str] = None,
        ip: Optional[str] = None,
    ) -> tuple[str, str, datetime]:
        """Issue a new access + refresh token pair, starting a new rotation family.

        Returns:
            ``(access_token, refresh_wire, refresh_expires_at)``
        """
        access_token, _ = mint_access_token(
            user_id=user.user_id,
            email=user.email,
            name=user.name,
        )

        family_id = uuid.uuid4().hex
        jti = _new_jti()
        opaque = _new_opaque()
        refresh_expires_at = datetime.now(timezone.utc) + timedelta(days=_REFRESH_TTL_DAYS)

        RefreshTokenRepository.create(
            db,
            jti=jti,
            user_id=user.user_id,
            family_id=family_id,
            token_hash=_hash_opaque(opaque),
            expires_at=refresh_expires_at,
            user_agent=user_agent,
            ip=ip,
        )
        db.commit()

        logger.info(
            "auth:session_issued user_id=%s family_id=%s",
            user.user_id,
            family_id,
        )

        return access_token, _compose_wire(jti, opaque), refresh_expires_at

    @staticmethod
    def rotate(
        db: Session,
        presented_refresh_plain: str,
        *,
        user_agent: Optional[str] = None,
        ip: Optional[str] = None,
    ) -> tuple[str, str, datetime]:
        """Exchange a valid refresh token for a new token pair (rotate-on-use).

        Uses ``SELECT FOR UPDATE`` to serialise concurrent rotations and detect
        reuse (``rotated_at IS NOT NULL`` → revoke entire family).

        Raises:
            RefreshTokenError: Token missing, expired, revoked, reused, or hash mismatch.
        """
        jti, opaque = _parse_wire(presented_refresh_plain)

        row = RefreshTokenRepository.get_by_jti_for_update(db, jti)

        if row is None:
            logger.warning("auth:rotate_rejected reason=not_found jti=%s", jti)
            raise RefreshTokenError("Refresh token not found.")

        now = datetime.now(timezone.utc)

        # Coerce naive datetime (Postgres DateTime column) to UTC-aware.
        expires_at = row.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at < now:
            logger.warning(
                "auth:rotate_rejected reason=expired user_id=%s family_id=%s",
                row.user_id,
                row.family_id,
            )
            raise RefreshTokenError("Refresh token has expired.")

        if row.revoked_at is not None:
            logger.warning(
                "auth:rotate_rejected reason=revoked user_id=%s family_id=%s",
                row.user_id,
                row.family_id,
            )
            raise RefreshTokenError("Refresh token has been revoked.")

        if row.rotated_at is not None:
            # Reuse detected: revoke the entire family to force re-authentication.
            revoked_count = RefreshTokenRepository.revoke_family(db, row.family_id)
            db.commit()
            logger.warning(
                "auth:reuse_detected user_id=%s family_id=%s revoked=%s",
                row.user_id,
                row.family_id,
                revoked_count,
            )
            raise RefreshTokenError("Refresh token reuse detected; session invalidated.")

        if not hmac.compare_digest(_hash_opaque(opaque), row.token_hash):
            logger.warning(
                "auth:rotate_rejected reason=hash_mismatch user_id=%s",
                row.user_id,
            )
            raise RefreshTokenError("Refresh token is invalid.")

        RefreshTokenRepository.mark_rotated(db, row)
        user = _load_user(db, row.user_id)

        access_token, _ = mint_access_token(
            user_id=user.user_id,
            email=user.email,
            name=user.name,
        )

        new_jti = _new_jti()
        new_opaque = _new_opaque()
        refresh_expires_at = now + timedelta(days=_REFRESH_TTL_DAYS)

        RefreshTokenRepository.create(
            db,
            jti=new_jti,
            user_id=user.user_id,
            family_id=row.family_id,
            token_hash=_hash_opaque(new_opaque),
            expires_at=refresh_expires_at,
            user_agent=user_agent,
            ip=ip,
        )
        db.commit()

        logger.info(
            "auth:token_rotated user_id=%s family_id=%s",
            user.user_id,
            row.family_id,
        )

        return access_token, _compose_wire(new_jti, new_opaque), refresh_expires_at

    @staticmethod
    def revoke_current(db: Session, presented_refresh_plain: str) -> None:
        """Revoke a single token (single-device logout); leaves the rest of the family active."""
        try:
            jti, _ = _parse_wire(presented_refresh_plain)
        except RefreshTokenError:
            return  # Malformed token — nothing to revoke.

        RefreshTokenRepository.revoke_jti(db, jti)
        db.commit()
        logger.info("auth:logout jti=%s", jti)

    @staticmethod
    def revoke_all(db: Session, user_id: int) -> None:
        """Revoke all refresh tokens for a user (logout-all / account suspension)."""
        count = RefreshTokenRepository.revoke_all_for_user(db, user_id)
        db.commit()
        logger.info("auth:logout_all user_id=%s revoked=%s", user_id, count)
