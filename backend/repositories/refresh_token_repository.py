"""RefreshToken data-access layer. All methods flush only; callers own the transaction."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from models.refresh_token import RefreshToken
from utils.logger import get_logger

logger = get_logger(__name__)


class RefreshTokenRepository:

    @staticmethod
    def create(
        db: Session,
        *,
        jti: str,
        user_id: int,
        family_id: str,
        token_hash: str,
        expires_at: datetime,
        user_agent: Optional[str] = None,
        ip: Optional[str] = None,
    ) -> RefreshToken:
        """Persist a new refresh-token record; raw token is never stored."""
        row = RefreshToken(
            jti=jti,
            user_id=user_id,
            family_id=family_id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip=ip,
        )
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def mark_rotated(db: Session, row: RefreshToken) -> None:
        """Set rotated_at; a non-null value on an incoming token signals reuse/theft."""
        row.rotated_at = datetime.now(timezone.utc)
        db.flush()

    @staticmethod
    def revoke_jti(db: Session, jti: str) -> None:
        now = datetime.now(timezone.utc)
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.jti == jti, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        db.flush()

    @staticmethod
    def revoke_family(db: Session, family_id: str) -> int:
        """Revoke all tokens in a rotation family; called on reuse detection to invalidate the entire lineage."""
        now = datetime.now(timezone.utc)
        result = db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        db.flush()
        return result.rowcount

    @staticmethod
    def revoke_all_for_user(db: Session, user_id: int) -> int:
        now = datetime.now(timezone.utc)
        result = db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        db.flush()
        return result.rowcount

    @staticmethod
    def get_by_jti(db: Session, jti: str) -> Optional[RefreshToken]:
        return db.execute(
            select(RefreshToken).where(RefreshToken.jti == jti)
        ).scalar_one_or_none()

    @staticmethod
    def get_by_jti_for_update(db: Session, jti: str) -> Optional[RefreshToken]:
        """Fetch by JTI with a pessimistic row lock; serialises concurrent rotation so only one request succeeds."""
        return db.execute(
            select(RefreshToken)
            .where(RefreshToken.jti == jti)
            .with_for_update()
        ).scalar_one_or_none()
