"""Unit tests for services.auth.refresh_service.

All database operations are performed against an in-memory SQLite database
(created via Base.metadata.create_all).  No external DB connection is required.

Covers:
- issue_session: new family created, tokens returned, DB row persisted.
- rotate: success path, new token issued, old row marked rotated (AC-6).
- rotate: reuse detection → family revoked, RefreshTokenError raised (AC-6).
- rotate: expired token rejected.
- rotate: revoked token rejected.
- rotate: hash mismatch rejected.
- rotate: concurrent rotation does not false-positive (rotated_at logic).
- revoke_current: single JTI revoked.
- revoke_all: all user tokens revoked.
"""

import os
import hashlib

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Minimum env before any import
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-only-32chars!")
os.environ.setdefault("SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
os.environ.setdefault("LOCAL_ACCESS_TTL_MINUTES", "15")
os.environ.setdefault("LOCAL_TOKEN_LEEWAY_SECONDS", "0")
os.environ.setdefault("LOCAL_REFRESH_TTL_DAYS", "14")

from db.database import Base
from models.user import User
from models.refresh_token import RefreshToken
from repositories.refresh_token_repository import RefreshTokenRepository
from services.auth.refresh_service import (
    RefreshService,
    RefreshTokenError,
    _compose_wire,
    _hash_opaque,
    _new_jti,
    _new_opaque,
    _parse_wire,
)


# ---------------------------------------------------------------------------
# In-memory SQLite test DB
# ---------------------------------------------------------------------------

# SQLite does not support FOR UPDATE; we patch get_by_jti_for_update to delegate
# to get_by_jti so rotation logic can be exercised without PostgreSQL.
_SQLITE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def engine():
    eng = create_engine(_SQLITE_URL, connect_args={"check_same_thread": False})
    # Import all models so metadata is populated
    import models  # noqa: F401
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture()
def db(engine):
    """Per-test session with rollback isolation."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", autoflush=True)
    # Patch FOR UPDATE to plain get_by_jti so SQLite doesn't error
    with patch.object(
        RefreshTokenRepository,
        "get_by_jti_for_update",
        side_effect=lambda db, jti: RefreshTokenRepository.get_by_jti(db, jti),
    ):
        yield session
    session.close()
    transaction.rollback()
    connection.close()


# ---------------------------------------------------------------------------
# Fixtures: a minimal User
# ---------------------------------------------------------------------------


@pytest.fixture()
def active_user(db) -> User:
    user = User(email="bob@example.com", name="Bob", is_active=True)
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def inactive_user(db) -> User:
    user = User(email="gone@example.com", name="Gone", is_active=False)
    db.add(user)
    db.flush()
    return user


# ---------------------------------------------------------------------------
# _parse_wire / _compose_wire unit tests (pure functions, no DB)
# ---------------------------------------------------------------------------


class TestWireFormat:
    def test_round_trip(self):
        jti = _new_jti()
        opaque = _new_opaque()
        wire = _compose_wire(jti, opaque)
        parsed_jti, parsed_opaque = _parse_wire(wire)
        assert parsed_jti == jti
        assert parsed_opaque == opaque

    def test_invalid_wire_raises(self):
        with pytest.raises(RefreshTokenError):
            _parse_wire("nodotsatall")

    def test_empty_parts_raise(self):
        with pytest.raises(RefreshTokenError):
            _parse_wire(".opaque")

        with pytest.raises(RefreshTokenError):
            _parse_wire("jti.")


# ---------------------------------------------------------------------------
# issue_session
# ---------------------------------------------------------------------------


class TestIssueSession:
    def test_returns_three_tuple(self, db, active_user):
        access, refresh_wire, refresh_exp = RefreshService.issue_session(db, active_user)
        assert isinstance(access, str)
        assert "." in refresh_wire  # wire format contains dot separator
        assert refresh_exp.tzinfo is not None

    def test_refresh_token_row_persisted(self, db, active_user):
        _, refresh_wire, _ = RefreshService.issue_session(db, active_user)
        jti, _ = _parse_wire(refresh_wire)
        row = RefreshTokenRepository.get_by_jti(db, jti)
        assert row is not None
        assert row.user_id == active_user.user_id
        assert row.rotated_at is None
        assert row.revoked_at is None

    def test_raw_opaque_not_stored(self, db, active_user):
        _, refresh_wire, _ = RefreshService.issue_session(db, active_user)
        jti, opaque = _parse_wire(refresh_wire)
        row = RefreshTokenRepository.get_by_jti(db, jti)
        # The raw opaque must NOT be in the DB
        assert row.token_hash != opaque
        # But the hash must match
        assert row.token_hash == _hash_opaque(opaque)

    def test_expires_at_is_approximately_14_days(self, db, active_user):
        before = datetime.now(timezone.utc)
        _, _, refresh_exp = RefreshService.issue_session(db, active_user)
        after = datetime.now(timezone.utc)
        assert before + timedelta(days=13, hours=23) < refresh_exp < after + timedelta(days=14, seconds=5)


# ---------------------------------------------------------------------------
# rotate — success path
# ---------------------------------------------------------------------------


class TestRotateSuccess:
    def test_returns_new_tokens(self, db, active_user):
        _, refresh_wire, _ = RefreshService.issue_session(db, active_user)
        new_access, new_refresh_wire, new_exp = RefreshService.rotate(db, refresh_wire)
        assert isinstance(new_access, str)
        assert "." in new_refresh_wire
        assert new_exp.tzinfo is not None

    def test_old_jti_marked_rotated(self, db, active_user):
        _, refresh_wire, _ = RefreshService.issue_session(db, active_user)
        old_jti, _ = _parse_wire(refresh_wire)
        RefreshService.rotate(db, refresh_wire)
        old_row = RefreshTokenRepository.get_by_jti(db, old_jti)
        assert old_row.rotated_at is not None

    def test_new_token_in_same_family(self, db, active_user):
        _, refresh_wire, _ = RefreshService.issue_session(db, active_user)
        old_jti, _ = _parse_wire(refresh_wire)
        _, new_refresh_wire, _ = RefreshService.rotate(db, refresh_wire)
        new_jti, _ = _parse_wire(new_refresh_wire)

        old_row = RefreshTokenRepository.get_by_jti(db, old_jti)
        new_row = RefreshTokenRepository.get_by_jti(db, new_jti)
        assert old_row.family_id == new_row.family_id

    def test_new_jti_is_distinct(self, db, active_user):
        _, refresh_wire, _ = RefreshService.issue_session(db, active_user)
        old_jti, _ = _parse_wire(refresh_wire)
        _, new_refresh_wire, _ = RefreshService.rotate(db, refresh_wire)
        new_jti, _ = _parse_wire(new_refresh_wire)
        assert old_jti != new_jti


# ---------------------------------------------------------------------------
# rotate — rejection cases
# ---------------------------------------------------------------------------


class TestRotateRejected:
    def test_expired_token_raises(self, db, active_user):
        _, refresh_wire, _ = RefreshService.issue_session(db, active_user)
        jti, _ = _parse_wire(refresh_wire)
        # Manually expire the row
        row = RefreshTokenRepository.get_by_jti(db, jti)
        row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.flush()

        with pytest.raises(RefreshTokenError, match="expired"):
            RefreshService.rotate(db, refresh_wire)

    def test_revoked_token_raises(self, db, active_user):
        _, refresh_wire, _ = RefreshService.issue_session(db, active_user)
        jti, _ = _parse_wire(refresh_wire)
        RefreshTokenRepository.revoke_jti(db, jti)
        db.commit()

        with pytest.raises(RefreshTokenError, match="revoked"):
            RefreshService.rotate(db, refresh_wire)

    def test_hash_mismatch_raises(self, db, active_user):
        _, refresh_wire, _ = RefreshService.issue_session(db, active_user)
        jti, opaque = _parse_wire(refresh_wire)
        # Present a wire value with a wrong opaque
        wrong_wire = _compose_wire(jti, _new_opaque())

        with pytest.raises(RefreshTokenError, match="invalid"):
            RefreshService.rotate(db, wrong_wire)

    def test_nonexistent_jti_raises(self, db, active_user):
        bogus_wire = _compose_wire(_new_jti(), _new_opaque())
        with pytest.raises(RefreshTokenError, match="not found"):
            RefreshService.rotate(db, bogus_wire)

    def test_inactive_user_raises(self, db, inactive_user):
        """Token for a deactivated account must be rejected on rotation."""
        # Manually insert a valid refresh row for the inactive user
        jti = _new_jti()
        opaque = _new_opaque()
        RefreshTokenRepository.create(
            db,
            jti=jti,
            user_id=inactive_user.user_id,
            family_id=_new_jti(),
            token_hash=_hash_opaque(opaque),
            expires_at=datetime.now(timezone.utc) + timedelta(days=14),
        )
        db.commit()
        wire = _compose_wire(jti, opaque)

        with pytest.raises(RefreshTokenError, match="deactivated"):
            RefreshService.rotate(db, wire)


# ---------------------------------------------------------------------------
# Reuse detection — AC-6
# ---------------------------------------------------------------------------


class TestReuseDetection:
    def test_reuse_revokes_entire_family(self, db, active_user):
        """Presenting an already-rotated token revokes all tokens in its family."""
        _, refresh_wire, _ = RefreshService.issue_session(db, active_user)
        original_jti, _ = _parse_wire(refresh_wire)

        # First rotation — legitimate
        _, new_wire, _ = RefreshService.rotate(db, refresh_wire)
        new_jti, _ = _parse_wire(new_wire)

        # Re-present the original (already rotated) token → reuse
        with pytest.raises(RefreshTokenError, match="reuse"):
            RefreshService.rotate(db, refresh_wire)

        # Both the old and new rows must now be revoked
        old_row = RefreshTokenRepository.get_by_jti(db, original_jti)
        new_row = RefreshTokenRepository.get_by_jti(db, new_jti)
        assert old_row.revoked_at is not None
        assert new_row.revoked_at is not None

    def test_concurrent_rotation_does_not_false_positive(self, db, active_user):
        """After a successful rotation the successor token can still be rotated.

        This verifies that setting rotated_at on the *old* token does not affect
        the *new* token (which has rotated_at=NULL until it is itself used).
        """
        _, refresh_wire, _ = RefreshService.issue_session(db, active_user)

        # First rotation
        _, second_wire, _ = RefreshService.rotate(db, refresh_wire)
        # Second rotation using the new token — must succeed, not raise
        _, third_wire, _ = RefreshService.rotate(db, second_wire)

        third_jti, _ = _parse_wire(third_wire)
        third_row = RefreshTokenRepository.get_by_jti(db, third_jti)
        assert third_row is not None
        assert third_row.rotated_at is None


# ---------------------------------------------------------------------------
# revoke_current
# ---------------------------------------------------------------------------


class TestRevokeCurrent:
    def test_jti_is_revoked(self, db, active_user):
        _, refresh_wire, _ = RefreshService.issue_session(db, active_user)
        jti, _ = _parse_wire(refresh_wire)
        RefreshService.revoke_current(db, refresh_wire)
        row = RefreshTokenRepository.get_by_jti(db, jti)
        assert row.revoked_at is not None

    def test_malformed_wire_does_not_raise(self, db, active_user):
        # Should silently return rather than propagate
        RefreshService.revoke_current(db, "nodotsatall")


# ---------------------------------------------------------------------------
# revoke_all
# ---------------------------------------------------------------------------


class TestRevokeAll:
    def test_all_user_tokens_revoked(self, db, active_user):
        # Issue two sessions
        _, w1, _ = RefreshService.issue_session(db, active_user)
        _, w2, _ = RefreshService.issue_session(db, active_user)
        jti1, _ = _parse_wire(w1)
        jti2, _ = _parse_wire(w2)

        RefreshService.revoke_all(db, active_user.user_id)

        r1 = RefreshTokenRepository.get_by_jti(db, jti1)
        r2 = RefreshTokenRepository.get_by_jti(db, jti2)
        assert r1.revoked_at is not None
        assert r2.revoked_at is not None
