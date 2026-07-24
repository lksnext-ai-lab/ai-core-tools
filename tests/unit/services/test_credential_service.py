"""Unit tests for services.auth.credential_service.CredentialService.

Uses an in-memory SQLite session (same pattern as test_refresh_service.py) so
no real PostgreSQL connection is required.  pytest-asyncio asyncio_mode="auto"
(set in pyproject.toml) means async test functions run natively.

Covers:
- authenticate: success resets failed_attempts.
- authenticate: wrong password increments failed_attempts; at threshold sets
  locked_until; subsequent call with correct password raises AccountLockedError.
- authenticate: omniadmin email is exempt from lockout.
- anti-enumeration: unknown email still calls _sync_verify (timing parity) and
  raises the same CredentialError as a wrong password.
- off-loop hashing: hash_password / verify_password delegate to run_in_threadpool.
- SMTP-off bypass: unverified user can log in when smtp_configured() is False;
  blocked when smtp_configured() is True.
- set-password token: issue → consume sets password and marks verified; second
  consume raises TokenError; garbage token raises TokenError.
- admin_create_user: creates User + UserCredential with auth_method='local',
  does NOT create a Subscription row; duplicate email raises UserAlreadyExistsError.
- change_password: verifies current password then rehashes; wrong current raises
  CredentialError.
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import bcrypt
import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Minimum env before any backend import (SECRET_KEY also provided by pytest-env,
# but setdefault is harmless).
os.environ.setdefault("SECRET_KEY", "test-secret-key-32chars-minimum-ok")
os.environ.setdefault("SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")

from db.database import Base
from models.user import User
from models.user_credential import UserCredential
from repositories.user_credential_repository import UserCredentialRepository
from repositories.user_repository import UserRepository
from services.auth.credential_service import (
    CredentialService,
    CredentialError,
    AccountLockedError,
    TokenError,
    UserAlreadyExistsError,
    _LOCKOUT_THRESHOLD,
    _LOCKOUT_BASE_SECONDS,
    _compute_lockout_duration,
    _sync_hash,
    _sync_verify,
    hash_password,
    verify_password,
)


# ---------------------------------------------------------------------------
# In-memory SQLite engine and session fixtures
# ---------------------------------------------------------------------------

_SQLITE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def engine():
    eng = create_engine(_SQLITE_URL, connect_args={"check_same_thread": False})
    import models  # noqa: F401 — registers all ORM models with Base.metadata
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture()
def db(engine):
    """Per-test session with rollback isolation (no FOR UPDATE needed on SQLite)."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", autoflush=True)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


# ---------------------------------------------------------------------------
# Helpers: build ORM rows directly (avoid service side-effects in setup)
# ---------------------------------------------------------------------------

def _make_user(db: Session, email: str = "alice@example.com", is_active: bool = True) -> User:
    user = User(email=email, name="Alice", auth_method="local", is_active=is_active)
    db.add(user)
    db.flush()
    return user


def _make_credential(
    db: Session,
    user: User,
    plain_password: str = "correcthorsebatterystaple",
    is_verified: bool = True,
    failed_attempts: int = 0,
    locked_until: datetime | None = None,
) -> UserCredential:
    hashed = _sync_hash(plain_password)
    # SQLite does not store timezone information.  The service code compares
    # locked_until with datetime.now(timezone.utc) — a tz-aware value.
    # SQLite returns the stored value as a naive datetime, so we strip tz here
    # to match what SQLite will return on query.  The service comparison path
    # is still exercised; only the test fixture mirrors SQLite behaviour.
    locked_until_naive = (
        locked_until.replace(tzinfo=None) if locked_until is not None else None
    )
    cred = UserCredential(
        user_id=user.user_id,
        hashed_password=hashed,
        is_verified=is_verified,
        failed_attempts=failed_attempts,
        locked_until=locked_until_naive,
    )
    db.add(cred)
    db.flush()
    return cred


# ---------------------------------------------------------------------------
# _compute_lockout_duration — pure-function unit tests (no DB needed)
# ---------------------------------------------------------------------------


class TestComputeLockoutDuration:
    def test_at_threshold_is_base_seconds(self):
        duration = _compute_lockout_duration(_LOCKOUT_THRESHOLD)
        assert duration == timedelta(seconds=_LOCKOUT_BASE_SECONDS)

    def test_one_above_threshold_doubles(self):
        duration = _compute_lockout_duration(_LOCKOUT_THRESHOLD + 1)
        assert duration == timedelta(seconds=_LOCKOUT_BASE_SECONDS * 2)

    def test_below_threshold_uses_zero_exponent(self):
        """Any count below threshold still uses 2^0 = base seconds."""
        duration = _compute_lockout_duration(0)
        assert duration == timedelta(seconds=_LOCKOUT_BASE_SECONDS)

    def test_exponential_growth(self):
        d5 = _compute_lockout_duration(_LOCKOUT_THRESHOLD)
        d6 = _compute_lockout_duration(_LOCKOUT_THRESHOLD + 1)
        d7 = _compute_lockout_duration(_LOCKOUT_THRESHOLD + 2)
        assert d6 == d5 * 2
        assert d7 == d5 * 4


# ---------------------------------------------------------------------------
# authenticate — success
# ---------------------------------------------------------------------------


class TestAuthenticateSuccess:
    @pytest.mark.asyncio
    async def test_returns_user_on_correct_password(self, db):
        user = _make_user(db)
        _make_credential(db, user, plain_password="correcthorsebatterystaple")
        result = await CredentialService.authenticate(db, user.email, "correcthorsebatterystaple")
        assert result.user_id == user.user_id

    @pytest.mark.asyncio
    async def test_success_resets_failed_attempts(self, db):
        user = _make_user(db)
        _make_credential(db, user, plain_password="correcthorsebatterystaple", failed_attempts=3)

        await CredentialService.authenticate(db, user.email, "correcthorsebatterystaple")

        cred = db.query(UserCredential).filter_by(user_id=user.user_id).first()
        assert cred.failed_attempts == 0

    @pytest.mark.asyncio
    async def test_success_clears_locked_until(self, db):
        user = _make_user(db)
        # A past lock should not block login; the service coerces a stored naive
        # datetime to UTC-aware before comparing against the real aware now.
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        _make_credential(
            db, user, plain_password="correcthorsebatterystaple", locked_until=past
        )

        await CredentialService.authenticate(db, user.email, "correcthorsebatterystaple")

        cred = db.query(UserCredential).filter_by(user_id=user.user_id).first()
        assert cred.locked_until is None

    @pytest.mark.asyncio
    async def test_promotes_existing_user_to_admin_when_email_added_to_omniadmins(self, db, monkeypatch):
        """A user created before their email was added to AICT_OMNIADMINS must
        be promoted to platform_role='admin' on their next successful login."""
        user = _make_user(db, email="lateomni@example.com")
        assert user.platform_role == "viewer"
        _make_credential(db, user, plain_password="correcthorsebatterystaple")

        monkeypatch.setenv("AICT_OMNIADMINS", "lateomni@example.com")
        await CredentialService.authenticate(db, user.email, "correcthorsebatterystaple")

        assert user.platform_role == "admin"

    @pytest.mark.asyncio
    async def test_does_not_touch_platform_role_for_non_omniadmin(self, db, monkeypatch):
        user = _make_user(db, email="regular@example.com")
        _make_credential(db, user, plain_password="correcthorsebatterystaple")

        monkeypatch.setenv("AICT_OMNIADMINS", "someoneelse@example.com")
        await CredentialService.authenticate(db, user.email, "correcthorsebatterystaple")

        assert user.platform_role == "viewer"


# ---------------------------------------------------------------------------
# authenticate — wrong password → lockout
# ---------------------------------------------------------------------------


class TestAuthenticateLockout:
    @pytest.mark.asyncio
    async def test_wrong_password_increments_failed_attempts(self, db):
        user = _make_user(db)
        _make_credential(db, user, plain_password="correcthorsebatterystaple")

        with pytest.raises(CredentialError):
            await CredentialService.authenticate(db, user.email, "wrongpassword")

        cred = db.query(UserCredential).filter_by(user_id=user.user_id).first()
        assert cred.failed_attempts == 1

    @pytest.mark.asyncio
    async def test_failed_attempts_accumulate(self, db):
        user = _make_user(db)
        _make_credential(db, user, plain_password="correcthorsebatterystaple")

        for _ in range(3):
            with pytest.raises(CredentialError):
                await CredentialService.authenticate(db, user.email, "wrongpassword")

        cred = db.query(UserCredential).filter_by(user_id=user.user_id).first()
        assert cred.failed_attempts == 3

    @pytest.mark.asyncio
    async def test_at_lockout_threshold_sets_locked_until(self, db):
        user = _make_user(db)
        # Pre-populate so the NEXT failure hits the threshold exactly.
        _make_credential(
            db, user,
            plain_password="correcthorsebatterystaple",
            failed_attempts=_LOCKOUT_THRESHOLD - 1,
        )

        with pytest.raises(CredentialError):
            await CredentialService.authenticate(db, user.email, "wrongpassword")

        cred = db.query(UserCredential).filter_by(user_id=user.user_id).first()
        # Reaching the threshold sets a future lockout window.
        assert cred.locked_until is not None

    @pytest.mark.asyncio
    async def test_locked_account_rejects_correct_password(self, db):
        """Even the correct password is rejected while locked_until is in the future."""
        future_lock = datetime.now(timezone.utc) + timedelta(minutes=10)
        user = _make_user(db)
        _make_credential(
            db, user,
            plain_password="correcthorsebatterystaple",
            failed_attempts=_LOCKOUT_THRESHOLD,
            locked_until=future_lock,
        )

        with pytest.raises(AccountLockedError):
            await CredentialService.authenticate(db, user.email, "correcthorsebatterystaple")

    @pytest.mark.asyncio
    async def test_lockout_raises_account_locked_error_not_credential_error(self, db):
        """AccountLockedError is a distinct exception type from CredentialError."""
        future_lock = datetime.now(timezone.utc) + timedelta(minutes=10)
        user = _make_user(db)
        _make_credential(
            db, user,
            plain_password="correcthorsebatterystaple",
            locked_until=future_lock,
        )

        with pytest.raises(AccountLockedError):
            await CredentialService.authenticate(db, user.email, "wrongpassword")

        # Must not be caught by CredentialError alone (AccountLockedError is NOT
        # a subclass of CredentialError per the implementation).
        try:
            await CredentialService.authenticate(db, user.email, "wrongpassword")
        except CredentialError:
            pytest.fail("AccountLockedError should NOT be a subclass of CredentialError")
        except AccountLockedError:
            pass  # correct

    @pytest.mark.asyncio
    async def test_account_locked_error_carries_locked_until(self, db):
        """AccountLockedError exposes locked_until so callers can set Retry-After.

        Finding B fix: the exception must carry the UTC-aware expiry timestamp
        so the HTTP handler can compute Retry-After without an extra DB round-trip.
        """
        future_lock = datetime.now(timezone.utc) + timedelta(minutes=5)
        user = _make_user(db)
        _make_credential(
            db, user,
            plain_password="correcthorsebatterystaple",
            locked_until=future_lock,
        )

        exc_caught: AccountLockedError | None = None
        try:
            await CredentialService.authenticate(db, user.email, "wrongpassword")
        except AccountLockedError as exc:
            exc_caught = exc

        assert exc_caught is not None, "AccountLockedError was not raised"
        assert exc_caught.locked_until is not None, "locked_until must not be None"
        # Must be UTC-aware so the HTTP handler can subtract datetime.now(timezone.utc)
        assert exc_caught.locked_until.tzinfo is not None, "locked_until must be timezone-aware"

    def test_account_locked_error_locked_until_defaults_to_none(self):
        """AccountLockedError can be constructed without locked_until (backward compat)."""
        exc = AccountLockedError("locked")
        assert exc.locked_until is None


# ---------------------------------------------------------------------------
# authenticate — omniadmin lockout exemption
# ---------------------------------------------------------------------------


class TestOmniadminLockoutExemption:
    @pytest.mark.asyncio
    async def test_omniadmin_is_never_locked_out(self, db, monkeypatch):
        """Omniadmin can fail many times without being locked out.

        AICT_OMNIADMINS is set to "admin@test.com" by pytest-env; we use that
        address directly.  monkeypatch is used to ensure the env var is set
        even if the test runs in isolation.
        """
        omniadmin_email = "admin@test.com"
        monkeypatch.setenv("AICT_OMNIADMINS", omniadmin_email)

        # Re-import is_omniadmin after monkeypatching env so the live value is read.
        # The function reads os.getenv at call time, so no re-import is needed.
        user = _make_user(db, email=omniadmin_email)
        _make_credential(db, user, plain_password="correcthorsebatterystaple")

        # Fail more than the lockout threshold.
        for _ in range(_LOCKOUT_THRESHOLD + 3):
            with pytest.raises(CredentialError):
                await CredentialService.authenticate(db, omniadmin_email, "wrongpassword")

        cred = db.query(UserCredential).filter_by(user_id=user.user_id).first()
        # locked_until must NOT be set for an omniadmin.
        assert cred.locked_until is None

    @pytest.mark.asyncio
    async def test_omniadmin_correct_password_succeeds_after_many_failures(self, db, monkeypatch):
        """Omniadmin can always authenticate with the correct password."""
        omniadmin_email = "admin@test.com"
        monkeypatch.setenv("AICT_OMNIADMINS", omniadmin_email)

        user = _make_user(db, email=omniadmin_email)
        _make_credential(db, user, plain_password="correcthorsebatterystaple")

        for _ in range(_LOCKOUT_THRESHOLD + 2):
            with pytest.raises(CredentialError):
                await CredentialService.authenticate(db, omniadmin_email, "wrongpassword")

        result = await CredentialService.authenticate(
            db, omniadmin_email, "correcthorsebatterystaple"
        )
        assert result.user_id == user.user_id


# ---------------------------------------------------------------------------
# authenticate — anti-enumeration / timing
# ---------------------------------------------------------------------------


class TestAntiEnumeration:
    @pytest.mark.asyncio
    async def test_unknown_email_raises_credential_error(self, db):
        """An unregistered email raises CredentialError (same type as wrong password)."""
        with pytest.raises(CredentialError):
            await CredentialService.authenticate(db, "nobody@example.com", "anypassword")

    @pytest.mark.asyncio
    async def test_unknown_email_does_not_raise_account_locked_error(self, db):
        """Anti-enumeration: unknown email must not reveal a distinct error type."""
        try:
            await CredentialService.authenticate(db, "nobody@example.com", "anypassword")
        except CredentialError:
            pass  # correct — same type as wrong-password case
        except AccountLockedError:
            pytest.fail("Unknown-email path must not raise AccountLockedError")

    @pytest.mark.asyncio
    async def test_unknown_email_calls_dummy_verify_for_timing_parity(self, db):
        """_sync_verify is called even for unknown emails to prevent timing enumeration."""
        with patch(
            "services.auth.credential_service._sync_verify",
            wraps=_sync_verify,
        ) as spy:
            with pytest.raises(CredentialError):
                await CredentialService.authenticate(db, "ghost@example.com", "somepassword")

            # _sync_verify must have been called at least once (the dummy hash path).
            assert spy.call_count >= 1

    @pytest.mark.asyncio
    async def test_wrong_password_and_unknown_user_raise_same_exception_type(self, db):
        """Both wrong-password and unknown-user paths raise CredentialError.

        This prevents distinguishing the two cases from client code.
        """
        user = _make_user(db, email="existing@example.com")
        _make_credential(db, user, plain_password="correcthorsebatterystaple")

        wrong_pw_exc = None
        unknown_user_exc = None

        try:
            await CredentialService.authenticate(db, "existing@example.com", "wrongpassword")
        except CredentialError as exc:
            wrong_pw_exc = exc

        try:
            await CredentialService.authenticate(db, "nobody@example.com", "wrongpassword")
        except CredentialError as exc:
            unknown_user_exc = exc

        assert wrong_pw_exc is not None
        assert unknown_user_exc is not None
        assert type(wrong_pw_exc) is type(unknown_user_exc)


# ---------------------------------------------------------------------------
# Off-loop hashing — hash_password / verify_password use run_in_threadpool
# ---------------------------------------------------------------------------


class TestOffLoopHashing:
    @pytest.mark.asyncio
    async def test_hash_password_uses_run_in_threadpool(self):
        """hash_password must dispatch to run_in_threadpool (not block the loop)."""
        with patch(
            "services.auth.credential_service.run_in_threadpool",
            wraps=__import__(
                "fastapi.concurrency", fromlist=["run_in_threadpool"]
            ).run_in_threadpool,
        ) as mock_pool:
            result = await hash_password("correcthorsebatterystaple")

        assert mock_pool.called
        assert isinstance(result, str)
        assert result.startswith("$2b$")  # bcrypt prefix

    @pytest.mark.asyncio
    async def test_verify_password_uses_run_in_threadpool(self):
        """verify_password must dispatch to run_in_threadpool."""
        hashed = _sync_hash("correcthorsebatterystaple")

        with patch(
            "services.auth.credential_service.run_in_threadpool",
            wraps=__import__(
                "fastapi.concurrency", fromlist=["run_in_threadpool"]
            ).run_in_threadpool,
        ) as mock_pool:
            result = await verify_password("correcthorsebatterystaple", hashed)

        assert mock_pool.called
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_password_returns_false_on_mismatch(self):
        hashed = _sync_hash("correcthorsebatterystaple")
        result = await verify_password("wrongpassword", hashed)
        assert result is False


# ---------------------------------------------------------------------------
# SMTP-off verification bypass
# ---------------------------------------------------------------------------


class TestSmtpVerificationBypass:
    @pytest.mark.asyncio
    async def test_unverified_user_can_login_when_smtp_is_off(self, db, monkeypatch):
        """When smtp_configured() is False, is_verified=False does not block login."""
        monkeypatch.delenv("SMTP_HOST", raising=False)
        monkeypatch.delenv("SMTP_FROM", raising=False)

        user = _make_user(db)
        _make_credential(db, user, plain_password="correcthorsebatterystaple", is_verified=False)

        result = await CredentialService.authenticate(db, user.email, "correcthorsebatterystaple")
        assert result.user_id == user.user_id

    @pytest.mark.asyncio
    async def test_unverified_user_is_rejected_when_smtp_is_configured(self, db, monkeypatch):
        """When smtp_configured() is True, is_verified=False blocks login."""
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_FROM", "no-reply@example.com")

        user = _make_user(db)
        _make_credential(db, user, plain_password="correcthorsebatterystaple", is_verified=False)

        with pytest.raises(CredentialError):
            await CredentialService.authenticate(db, user.email, "correcthorsebatterystaple")

    @pytest.mark.asyncio
    async def test_verified_user_can_login_when_smtp_is_configured(self, db, monkeypatch):
        """When smtp_configured() is True, is_verified=True allows login normally."""
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_FROM", "no-reply@example.com")

        user = _make_user(db)
        _make_credential(db, user, plain_password="correcthorsebatterystaple", is_verified=True)

        result = await CredentialService.authenticate(db, user.email, "correcthorsebatterystaple")
        assert result.user_id == user.user_id


# ---------------------------------------------------------------------------
# Set-password token flow
# ---------------------------------------------------------------------------


class TestSetPasswordToken:
    @pytest.mark.asyncio
    async def test_issue_and_consume_sets_password(self, db):
        """issue_set_password_token → consume_set_password_token applies password."""
        user = _make_user(db)
        _make_credential(db, user, plain_password="oldplaceholder")

        token = CredentialService.issue_set_password_token(db, user.user_id)
        assert isinstance(token, str) and len(token) > 10

        updated_user = await CredentialService.consume_set_password_token(
            db, token, "newcorrectpassphrase"
        )
        assert updated_user.user_id == user.user_id

        # The new password must verify correctly.
        cred = db.query(UserCredential).filter_by(user_id=user.user_id).first()
        assert _sync_verify("newcorrectpassphrase", cred.hashed_password)

    @pytest.mark.asyncio
    async def test_consume_marks_user_verified(self, db):
        """Consuming the token marks is_verified=True and email_verified=True."""
        user = _make_user(db)
        _make_credential(db, user, plain_password="oldplaceholder", is_verified=False)

        token = CredentialService.issue_set_password_token(db, user.user_id)
        await CredentialService.consume_set_password_token(db, token, "newcorrectpassphrase")

        cred = db.query(UserCredential).filter_by(user_id=user.user_id).first()
        assert cred.is_verified is True

        db.refresh(user)
        assert user.email_verified is True

    @pytest.mark.asyncio
    async def test_token_is_single_use(self, db):
        """Consuming the same token a second time raises TokenError."""
        user = _make_user(db)
        _make_credential(db, user, plain_password="oldplaceholder")

        token = CredentialService.issue_set_password_token(db, user.user_id)
        await CredentialService.consume_set_password_token(db, token, "newcorrectpassphrase")

        with pytest.raises(TokenError):
            await CredentialService.consume_set_password_token(
                db, token, "anothernewpassphrase"
            )

    @pytest.mark.asyncio
    async def test_garbage_token_raises_token_error(self, db):
        """A random string raises TokenError (bad signature)."""
        with pytest.raises(TokenError):
            await CredentialService.consume_set_password_token(
                db, "not.a.real.token", "newcorrectpassphrase"
            )

    @pytest.mark.asyncio
    async def test_expired_token_raises_token_error(self, db):
        """An expired token raises TokenError.

        We forge a token whose embedded timestamp is 200 hours in the past by
        using itsdangerous directly with a backdated now-time, then consume it
        with the real max_age.  No sleep required.
        """
        from itsdangerous import URLSafeTimedSerializer
        from utils.secret_key import get_secret_key

        user = _make_user(db)
        _make_credential(db, user, plain_password="oldplaceholder")

        # Forge a token whose timestamp is 200 hours ago (well past the 48 h max_age).
        # itsdangerous signs tokens with a timestamp; we make the serializer believe
        # the current time is 200 hours ago so the embedded ts is far in the past.
        past_ts = int((datetime.now(timezone.utc) - timedelta(hours=200)).timestamp())
        serializer = URLSafeTimedSerializer(get_secret_key())

        # Patch time.time inside itsdangerous to return our past timestamp so the
        # token is issued with a past ts.
        import itsdangerous.timed as _itsdangerous_timed
        with patch.object(_itsdangerous_timed, "time") as mock_time:
            mock_time.return_value = past_ts
            stale_token = serializer.dumps(user.email, salt="local-set-password-v1")

        # Store this stale token as the credential's reset_token marker so the
        # single-use check passes but the max_age check fires.
        cred = db.query(UserCredential).filter_by(user_id=user.user_id).first()
        cred.reset_token = stale_token
        db.flush()

        with pytest.raises(TokenError):
            await CredentialService.consume_set_password_token(
                db, stale_token, "newcorrectpassphrase"
            )

    @pytest.mark.asyncio
    async def test_consume_clears_reset_token_marker(self, db):
        """After successful consumption, reset_token is cleared (single-use enforcement)."""
        user = _make_user(db)
        _make_credential(db, user, plain_password="oldplaceholder")

        token = CredentialService.issue_set_password_token(db, user.user_id)
        await CredentialService.consume_set_password_token(db, token, "newcorrectpassphrase")

        cred = db.query(UserCredential).filter_by(user_id=user.user_id).first()
        assert cred.reset_token is None
        assert cred.reset_token_expiry is None


# ---------------------------------------------------------------------------
# admin_create_user
# ---------------------------------------------------------------------------


class TestAdminCreateUser:
    @pytest.mark.asyncio
    async def test_creates_user_with_local_auth_method(self, db):
        user = await CredentialService.admin_create_user(
            db, "newuser@example.com", "New User"
        )
        assert user.auth_method == "local"
        assert user.email == "newuser@example.com"

    @pytest.mark.asyncio
    async def test_creates_user_credential_row(self, db):
        user = await CredentialService.admin_create_user(
            db, "newuser@example.com", "New User"
        )
        cred = db.query(UserCredential).filter_by(user_id=user.user_id).first()
        assert cred is not None
        assert cred.hashed_password is not None

    @pytest.mark.asyncio
    async def test_does_not_create_subscription_row(self, db):
        """admin_create_user must NOT create a Subscription (SaaS concern)."""
        from models.subscription import Subscription

        user = await CredentialService.admin_create_user(
            db, "newuser@example.com", "New User"
        )
        sub = db.query(Subscription).filter_by(user_id=user.user_id).first()
        assert sub is None, (
            "admin_create_user must not create a Subscription row; "
            "subscription lifecycle belongs to the SaaS domain."
        )

    @pytest.mark.asyncio
    async def test_omniadmin_email_gets_admin_platform_role(self, db, monkeypatch):
        monkeypatch.setenv("AICT_OMNIADMINS", "omni@example.com")
        user = await CredentialService.admin_create_user(
            db, "omni@example.com", "Omni Admin"
        )
        assert user.platform_role == "admin"

    @pytest.mark.asyncio
    async def test_regular_email_gets_viewer_platform_role(self, db, monkeypatch):
        monkeypatch.setenv("AICT_OMNIADMINS", "omni@example.com")
        user = await CredentialService.admin_create_user(
            db, "newuser2@example.com", "Regular User"
        )
        assert user.platform_role == "viewer"

    @pytest.mark.asyncio
    async def test_duplicate_email_raises_user_already_exists_error(self, db):
        await CredentialService.admin_create_user(db, "dup@example.com", "First")

        with pytest.raises(UserAlreadyExistsError):
            await CredentialService.admin_create_user(db, "dup@example.com", "Second")

    @pytest.mark.asyncio
    async def test_user_is_active_on_creation(self, db):
        user = await CredentialService.admin_create_user(
            db, "activeuser@example.com", "Active User"
        )
        assert user.is_active is True

    @pytest.mark.asyncio
    async def test_email_verified_reflects_smtp_state_off(self, db, monkeypatch):
        """When SMTP is off, email_verified is True (no verification handshake needed)."""
        monkeypatch.delenv("SMTP_HOST", raising=False)
        monkeypatch.delenv("SMTP_FROM", raising=False)

        user = await CredentialService.admin_create_user(
            db, "noverify@example.com", "No Verify"
        )
        assert user.email_verified is True

    @pytest.mark.asyncio
    async def test_email_verified_false_when_smtp_configured(self, db, monkeypatch):
        """When SMTP is on, email_verified is False until the set-password flow runs."""
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_FROM", "no-reply@example.com")

        user = await CredentialService.admin_create_user(
            db, "pendingverify@example.com", "Pending Verify"
        )
        assert user.email_verified is False


# ---------------------------------------------------------------------------
# change_password
# ---------------------------------------------------------------------------


class TestChangePassword:
    @pytest.mark.asyncio
    async def test_correct_current_password_changes_to_new(self, db):
        user = _make_user(db)
        _make_credential(db, user, plain_password="correcthorsebatterystaple")

        await CredentialService.change_password(
            db, user, "correcthorsebatterystaple", "newhorsebatterystaple"
        )

        cred = db.query(UserCredential).filter_by(user_id=user.user_id).first()
        assert _sync_verify("newhorsebatterystaple", cred.hashed_password)
        assert not _sync_verify("correcthorsebatterystaple", cred.hashed_password)

    @pytest.mark.asyncio
    async def test_wrong_current_password_raises_credential_error(self, db):
        user = _make_user(db)
        _make_credential(db, user, plain_password="correcthorsebatterystaple")

        with pytest.raises(CredentialError):
            await CredentialService.change_password(
                db, user, "wrongcurrentpassword", "newhorsebatterystaple"
            )

    @pytest.mark.asyncio
    async def test_wrong_current_does_not_change_password(self, db):
        """The stored hash must remain unchanged when current password is wrong."""
        user = _make_user(db)
        _make_credential(db, user, plain_password="correcthorsebatterystaple")

        cred_before = db.query(UserCredential).filter_by(user_id=user.user_id).first()
        original_hash = cred_before.hashed_password

        with pytest.raises(CredentialError):
            await CredentialService.change_password(
                db, user, "wrongcurrent", "newhorsebatterystaple"
            )

        cred_after = db.query(UserCredential).filter_by(user_id=user.user_id).first()
        assert cred_after.hashed_password == original_hash

    @pytest.mark.asyncio
    async def test_change_password_revokes_refresh_sessions(self, db):
        """change_password calls RefreshService.revoke_all to invalidate all sessions."""
        user = _make_user(db)
        _make_credential(db, user, plain_password="correcthorsebatterystaple")

        with patch(
            "services.auth.credential_service.RefreshService.revoke_all"
        ) as mock_revoke:
            await CredentialService.change_password(
                db, user, "correcthorsebatterystaple", "newhorsebatterystaple"
            )

        mock_revoke.assert_called_once_with(db, user.user_id)

    @pytest.mark.asyncio
    async def test_missing_credential_raises_credential_error(self, db):
        """If the user has no credential row, change_password raises CredentialError."""
        user = _make_user(db)
        # Deliberately do NOT create a credential row.

        with pytest.raises(CredentialError):
            await CredentialService.change_password(
                db, user, "anypassword", "newhorsebatterystaple"
            )
