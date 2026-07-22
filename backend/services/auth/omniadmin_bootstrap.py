"""First-boot omniadmin provisioning for LOCAL auth mode.

Called once at application startup when ``AICT_LOGIN=LOCAL`` and
``AUTH_BOOTSTRAP_OMNIADMINS=true`` (default).  The one-time set-password URL is
delivered out-of-band via WARNING-level logs — only an operator with log access
can read it, and the token is single-use + time-limited.

Multi-worker safety: acquires ``pg_try_advisory_lock(_ADVISORY_LOCK_KEY)`` so
exactly one worker runs the loop.

Idempotency: verified accounts are skipped; accounts with a live outstanding
link are skipped; stranded accounts (crash between create and token issuance)
receive a fresh token.
"""

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from models.user import PlatformRole
from services.auth.credential_service import CredentialService, UserAlreadyExistsError
from utils.config import Config, get_omniadmins
from utils.logger import get_logger

logger = get_logger(__name__)

_BOOTSTRAP_ENABLED: bool = Config.get_bool_env_var("AUTH_BOOTSTRAP_OMNIADMINS", default=True)
_TOKEN_MAX_AGE_HOURS: int = Config.get_int_env_var("LOCAL_SET_PASSWORD_TOKEN_MAX_AGE_HOURS", default=48)
_FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Stable 64-bit advisory lock key: int.from_bytes(b"omniadm1", "big").
# MUST NOT change after first deployment — changing it breaks mutual exclusion.
_ADVISORY_LOCK_KEY: int = 0x6F6D6E6961646D31



async def bootstrap_omniadmins(db: Session) -> None:
    """Provision LOCAL omniadmin accounts on startup.

    Acquires a PostgreSQL advisory lock so only one worker runs the loop.
    No-op when ``AUTH_BOOTSTRAP_OMNIADMINS=false``.  Per-email failures are
    caught and logged so one bad entry cannot abort startup.
    """
    if not _BOOTSTRAP_ENABLED:
        logger.debug("omniadmin_bootstrap: AUTH_BOOTSTRAP_OMNIADMINS=false, skipping")
        return

    omniadmins = get_omniadmins()
    if not omniadmins:
        logger.debug("omniadmin_bootstrap: AICT_OMNIADMINS is empty, nothing to bootstrap")
        return

    try:
        locked: bool = db.execute(
            text("SELECT pg_try_advisory_lock(:k)"),
            {"k": _ADVISORY_LOCK_KEY},
        ).scalar()
    except Exception as lock_exc:
        logger.error(
            "omniadmin_bootstrap: could not acquire advisory lock — %s; skipping bootstrap",
            lock_exc,
        )
        return

    if not locked:
        logger.debug(
            "omniadmin_bootstrap: advisory lock held by another worker/replica; "
            "bootstrap skipped (lock key=0x%x)",
            _ADVISORY_LOCK_KEY,
        )
        return

    logger.info(
        "omniadmin_bootstrap: acquired advisory lock (key=0x%x); checking %d omniadmin email(s)",
        _ADVISORY_LOCK_KEY,
        len(omniadmins),
    )

    try:
        for email in omniadmins:
            email = email.strip().lower()  # belt-and-suspenders; get_omniadmins() already normalises
            if not email:
                continue
            await _provision_single_omniadmin(db, email)
    finally:
        try:
            db.execute(
                text("SELECT pg_advisory_unlock(:k)"),
                {"k": _ADVISORY_LOCK_KEY},
            )
        except Exception as unlock_exc:
            logger.warning(
                "omniadmin_bootstrap: advisory unlock failed (non-fatal) — %s",
                unlock_exc,
            )



async def _provision_single_omniadmin(db: Session, email: str) -> None:
    """Provision or crash-recover a single omniadmin account."""
    from repositories.user_credential_repository import UserCredentialRepository
    from repositories.user_repository import UserRepository

    user_repo = UserRepository(db)
    existing = user_repo.get_by_email(email)

    if existing is None:
        try:
            name = email.split("@", 1)[0].capitalize()
            user = await CredentialService.admin_create_user(db, email=email, name=name)
        except UserAlreadyExistsError:
            # Shouldn't happen under the advisory lock, but kept as a guard.
            logger.info(
                "omniadmin_bootstrap: concurrent creation detected for %s, skipping token issuance",
                email,
            )
            return
        except Exception as exc:
            logger.error(
                "omniadmin_bootstrap: failed to create user for %s — %s",
                email,
                exc,
                exc_info=True,
            )
            return

        _issue_and_log(db, user.user_id, email)
        return

    # Promote pre-existing accounts whose email was added to AICT_OMNIADMINS
    # after the account was originally created (platform_role otherwise stays
    # at whatever it was, e.g. the 'viewer' default).
    if existing.platform_role != PlatformRole.ADMIN.value:
        existing.platform_role = PlatformRole.ADMIN.value
        db.commit()
        logger.info(
            "omniadmin_bootstrap: %s (user_id=%s) promoted to platform_role='admin'",
            email,
            existing.user_id,
        )

    cred_repo = UserCredentialRepository(db)
    cred = cred_repo.get_by_user_id(existing.user_id)

    if cred is not None and cred.is_verified:
        logger.info(
            "omniadmin_bootstrap: %s (user_id=%s) is already verified; skipping",
            email,
            existing.user_id,
        )
        return

    now_utc = datetime.now(timezone.utc)
    has_valid_link = _has_valid_outstanding_link(cred, now_utc)

    if has_valid_link:
        logger.info(
            "omniadmin_bootstrap: %s (user_id=%s) has a valid outstanding set-password link; "
            "skipping (link has not been used yet)",
            email,
            existing.user_id,
        )
        return

    # Crash-recovery: user exists but setup incomplete and no valid link outstanding.
    logger.warning(
        "omniadmin_bootstrap: %s (user_id=%s) exists but setup is incomplete "
        "and no valid link is outstanding; re-issuing set-password token (crash-recovery)",
        email,
        existing.user_id,
    )
    _issue_and_log(db, existing.user_id, email)


def _has_valid_outstanding_link(cred, now_utc: datetime) -> bool:
    """Return True when a non-expired set-password token exists on the credential.

    Coerces naive ``reset_token_expiry`` to UTC-aware before comparison (legacy rows).
    """
    if cred is None:
        return False
    if not cred.reset_token:
        return False
    expiry = cred.reset_token_expiry
    if expiry is None:
        return False
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return expiry > now_utc


def _issue_and_log(db: Session, user_id: int, email: str) -> None:
    """Issue a set-password token and log the WARNING link (shared by new-account and crash-recovery paths)."""
    try:
        token = CredentialService.issue_set_password_token(db, user_id)
    except Exception as exc:
        logger.error(
            "omniadmin_bootstrap: failed to issue set-password token for %s (user_id=%s) — %s",
            email,
            user_id,
            exc,
            exc_info=True,
        )
        return

    expires_at = (
        datetime.now(timezone.utc) + timedelta(hours=_TOKEN_MAX_AGE_HOURS)
    ).isoformat()

    set_password_url = f"{_FRONTEND_URL.rstrip('/')}/set-password?token={token}"

    # Intentional WARNING-level log: out-of-band delivery to the operator.
    # Token is single-use and time-limited; only accessible via container logs.
    logger.warning(
        "omniadmin_bootstrap: NEW omniadmin account provisioned.\n"
        "  Email   : %s\n"
        "  User ID : %s\n"
        "  Expires : %s\n"
        "  Link    : %s\n"
        "Open the link above to set the initial password for this account. "
        "This link will not appear again once used or after the account exists on restart.",
        email,
        user_id,
        expires_at,
        set_password_url,
    )
