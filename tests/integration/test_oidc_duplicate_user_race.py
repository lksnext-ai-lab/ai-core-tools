"""Integration regression tests for the OIDC duplicate-user-creation race.

Bug: two concurrent OIDC first-login requests for a brand-new email could both miss the
SELECT in ``UserService.get_or_create_user`` (plain check-then-insert, no DB-level
uniqueness, no locking) and both proceed to INSERT, creating 2 (or up to 3, if a third
request also raced in) ``User`` rows sharing the same email.

Fix (two parts, both already landed on this branch):
  1. ``alembic/versions/useremail001_dedupe_users_add_unique_email.py`` adds a
     ``uq_user_email`` UNIQUE constraint on ``User.email`` (plus a one-time dedupe of any
     pre-existing duplicate rows).
  2. ``UserService.get_or_create_user`` (``backend/services/user_service.py``) now catches
     the ``IntegrityError`` raised by that constraint when the INSERT loses the race,
     rolls back, and re-fetches the winner's row instead of propagating a 500 or leaving a
     duplicate.

These tests require the REAL Postgres unique constraint to be present -- a pure unit test
with a mocked session cannot trigger a genuine ``IntegrityError`` -- so they live here in
``tests/integration/`` against the real test DB (port 5433) rather than in ``tests/unit/``.
The two tests that actually need the constraint to fire bring it up themselves via the
``ensure_email_unique_constraint`` fixture (see its docstring below) rather than assuming
it is already present -- this repo's test-DB schema is built from ORM metadata
(``Base.metadata.create_all()``), not from the Alembic migration, so the constraint is
NOT guaranteed to exist on a fresh/ephemeral test DB.

Concurrency strategy (deterministic -- no real threads, no flaky timing):
  Two real ``SessionLocal()`` sessions are used directly (mirroring two separate FastAPI
  requests, each with its own ``Depends(get_db)`` session) rather than the standard
  savepoint-rollback ``db`` fixture: the race must be visible as a genuine UNIQUE-constraint
  conflict across two independent DB transactions, which a single shared connection/
  savepoint cannot reproduce.

  Session B is bumped to ``REPEATABLE READ`` *before* its first statement, fixing its MVCC
  snapshot at that point (while the email definitely does not exist yet). Session A ("A"
  wins the race) then runs ``get_or_create_user`` to completion, fully creating and
  committing a new user for that same email. Postgres enforces UNIQUE constraints against
  the actual committed data regardless of a transaction's MVCC snapshot, so when Session
  B's ``get_or_create_user`` re-does its own SELECT (still returns None -- per its frozen
  snapshot, A's commit is invisible to it) and attempts the INSERT, it collides with the
  real ``uq_user_email`` constraint and raises ``IntegrityError`` -- exactly the path the
  fix's ``except IntegrityError`` block exists to recover from.

  Each test commits real rows to the test DB (bypassing the savepoint-rollback fixture,
  same pattern as ``tests/integration/test_crawl_worker_concurrency.py``) and cleans up
  manually in a ``finally`` block.
"""

import uuid

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from db.database import SessionLocal
from models.user import User
from repositories.user_repository import UserRepository
from services.user_service import UserService

_TEST_SCOPED_CONSTRAINT_NAME = "uq_user_email_test_scoped"


@pytest.fixture
def ensure_email_unique_constraint(test_engine):
    """Guarantees a real UNIQUE constraint on ``User.email`` exists for the duration of
    a single test, then removes it again immediately afterward.

    Why this fixture exists (rather than relying on ambient DB state or a permanent
    model change):

    - The session-scoped ``test_engine`` fixture builds the schema via
      ``Base.metadata.create_all()`` (ORM metadata), NOT by running the ``useremail001``
      Alembic migration -- see ``tests/integration/test_localauth001_migration.py``'s
      docstring for the same caveat about this repo's test-DB schema strategy. So
      whether the real ``uq_user_email`` constraint exists here depends entirely on
      whatever state the target Postgres database happened to be in beforehand -- it is
      NOT guaranteed on a fresh/ephemeral test DB. This was confirmed while writing this
      test: a from-scratch schema built purely from ``create_all()`` has no such
      constraint, since ``models/user.py``'s ``email`` column does not declare
      ``unique=True``.
    - Adding ``unique=True`` directly to ``User.email`` in ``backend/models/user.py``
      would make ``create_all()`` always include the constraint -- but this was tried
      and reverted during development of this test: it turns the ``fake_user`` fixture's
      shared, hardcoded email (``"testuser@mattin-test.com"``, reused by dozens of
      unrelated tests across the suite) into a permanent, session-wide lock-contention
      hazard. If any other test's session is ever left open (e.g. a hung fixture
      teardown) while holding that email, every subsequent ``fake_user``-based test
      would then block waiting on the Postgres row lock instead of harmlessly
      coexisting in separate, never-committed transactions like they do today -- this
      produced a full test-suite deadlock, observed firsthand while developing this fix.

    Instead, this fixture adds the constraint (under its own distinct name, if not
    already present) immediately before the single test that needs it runs, and drops
    it again immediately after -- a window of a few milliseconds -- so it cannot collide
    with any other test's use of the shared ``fake_user`` email.
    """
    inspector = inspect(test_engine)
    already_present = any(
        c["name"] == "uq_user_email" for c in inspector.get_unique_constraints("User")
    )

    added_here = False
    if not already_present:
        with test_engine.begin() as conn:
            conn.execute(
                text(
                    f'ALTER TABLE "User" ADD CONSTRAINT {_TEST_SCOPED_CONSTRAINT_NAME} '
                    "UNIQUE (email)"
                )
            )
        added_here = True

    try:
        yield
    finally:
        if added_here:
            with test_engine.begin() as conn:
                conn.execute(
                    text(
                        f'ALTER TABLE "User" DROP CONSTRAINT IF EXISTS '
                        f"{_TEST_SCOPED_CONSTRAINT_NAME}"
                    )
                )


def _unique_email(label: str) -> str:
    return f"oidc-race-{label}-{uuid.uuid4().hex}@mattin-test.com"


def _cleanup(email: str) -> None:
    """Delete any User row(s) left behind for `email` (real commit, real cleanup).

    Uses a brand-new session/connection so it works regardless of the state the
    racing sessions were left in (including a rolled-back or aborted transaction).
    """
    cleanup_session = SessionLocal()
    try:
        cleanup_session.query(User).filter(User.email == email).delete()
        cleanup_session.commit()
    finally:
        cleanup_session.close()


class TestGetOrCreateUserSequential:
    """Basic (non-racing) regression coverage: the IntegrityError handling added for the
    race fix must not have broken the normal, uncontested get-or-create path."""

    def test_second_call_returns_existing_user_not_a_duplicate(self, test_engine):
        email = _unique_email("sequential")
        try:
            session = SessionLocal()
            try:
                user1, created1 = UserService.get_or_create_user(session, email, name="First Login")
                user2, created2 = UserService.get_or_create_user(session, email, name="First Login")
            finally:
                session.close()

            assert created1 is True, "First call for a brand-new email must create the user"
            assert created2 is False, "Second call for the same email must not create a duplicate"
            assert user1.user_id == user2.user_id

            verify_session = SessionLocal()
            try:
                count = verify_session.query(User).filter(User.email == email).count()
            finally:
                verify_session.close()
            assert count == 1
        finally:
            _cleanup(email)


class TestUserRepositoryUniqueConstraint:
    """Sanity check that the real DB constraint is present and fires -- isolates the
    schema half of the fix from the service-level recovery logic tested below."""

    def test_create_raises_integrity_error_on_duplicate_email(
        self, test_engine, ensure_email_unique_constraint
    ):
        email = _unique_email("constraint-sanity")
        session_a = SessionLocal()
        session_b = SessionLocal()
        try:
            UserRepository(session_a).create(email, "First")

            try:
                UserRepository(session_b).create(email, "Second")
                raised = False
            except IntegrityError:
                raised = True
                session_b.rollback()

            assert raised, (
                "UserRepository.create must raise IntegrityError for a duplicate email "
                "-- the uq_user_email constraint is missing or not enforced"
            )
        finally:
            session_a.close()
            session_b.close()
            _cleanup(email)


class TestGetOrCreateUserConcurrentRace:
    """Reproduces the actual race: two separate sessions both miss the SELECT and race to
    INSERT for the same brand-new email.

    FAILS against the pre-fix ``get_or_create_user`` (plain SELECT-then-INSERT, no
    try/except around the INSERT): the loser's real ``IntegrityError`` propagates straight
    out of the call instead of being caught and recovered from.
    """

    def test_concurrent_calls_converge_to_single_user_row(
        self, test_engine, ensure_email_unique_constraint
    ):
        email = _unique_email("concurrent")
        session_a = SessionLocal()
        session_b = SessionLocal()
        try:
            # Session B: elevate isolation *before* its first statement so its MVCC
            # snapshot is fixed here -- simulating a request whose "user not found" read
            # happened concurrently with (before) Session A's INSERT+commit.
            session_b.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
            repo_b = UserRepository(session_b)
            assert repo_b.get_by_email(email) is None, "sanity: email must not pre-exist"

            # Session A "wins" the race: creates and commits the user first.
            user_a, created_a = UserService.get_or_create_user(session_a, email, name="Race Winner")
            assert created_a is True

            # Session B still cannot see Session A's commit (its snapshot predates it), so
            # get_or_create_user's own internal SELECT returns None and it attempts the
            # INSERT -- which now collides with the real uq_user_email constraint and
            # raises IntegrityError. The fix must catch it, roll back, and converge on the
            # winner's row rather than raising or leaving a duplicate.
            user_b, created_b = UserService.get_or_create_user(session_b, email, name="Race Loser")

            assert created_b is False, (
                "Losing call must report created=False (converged on the existing row), "
                "not create a second User row"
            )
            assert user_b.user_id == user_a.user_id, (
                "Both concurrent calls must resolve to the SAME user_id"
            )

            # Exactly one row must exist for this email -- checked via a fresh, independent
            # session so we're not relying on either racing session's own identity map.
            verify_session = SessionLocal()
            try:
                count = verify_session.query(User).filter(User.email == email).count()
            finally:
                verify_session.close()
            assert count == 1, f"Expected exactly 1 User row for {email}, found {count}"
        finally:
            session_a.close()
            session_b.close()
            _cleanup(email)
