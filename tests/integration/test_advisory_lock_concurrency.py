"""
Real-DB integration tests for backend/db/advisory_lock.py (AD-8).

Verifies the transaction-scoped advisory lock behaves correctly against a real Postgres
connection pool — something a MagicMock session double cannot exercise. In particular:
  - the lock is genuinely released the moment the acquiring transaction commits (not merely
    when the `with` block exits, and not leaked into the connection pool);
  - a second, independently-connected session sees the release correctly (pg_try_advisory_xact_lock
    semantics: released on commit, so a second attempt AFTER the first's commit succeeds);
  - an exception inside the locked block still releases the lock (via rollback);
  - after any of the above, `pg_locks` shows zero leftover advisory locks tied to this test's
    connections.

All tests use real `SessionLocal()` sessions bound to genuinely separate connections (never
the savepoint-wrapped `db` fixture, which would not exercise real commit/rollback semantics).
"""

from sqlalchemy import text

from db.advisory_lock import _derive_lock_key, try_advisory_lock
from db.database import SessionLocal


def _count_advisory_locks_for_key(db, key: str) -> int:
    """Count currently-held Postgres advisory locks matching this specific lock `key`.

    Scoped by the same key our own lock would use (reconstructing the original signed
    bigint from pg_locks' split classid/objid columns via bit concatenation — verified
    against a real advisory lock before use), rather than a DB-wide total, so this test
    can't flake under a concurrent holder from an unrelated test/connection (e.g.
    SkillRepository.lock_app_skills running elsewhere).
    """
    lock_key = _derive_lock_key(key)
    return db.execute(
        text(
            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
            "AND (classid::int::bit(32) || objid::int::bit(32))::bit(64)::bigint = :lock_key"
        ),
        {"lock_key": lock_key},
    ).scalar()


def test_second_session_acquires_after_first_commits(test_engine):
    """AC-32-style scenario: commit-inside-the-block (step_033's exact pattern), then a second,
    independently-connected session tries the same key. Because the lock is transaction-scoped,
    it is released the instant the first session commits — so the second acquire succeeds.
    """
    key = "test:advisory_lock:concurrency:commit_then_second"

    db1 = SessionLocal()
    try:
        with try_advisory_lock(db1, key) as acquired1:
            assert acquired1 is True
            # Simulate step_033's seeder: commit once, inside the block.
            db1.commit()
    finally:
        db1.close()

    # A second, genuinely independent session/connection now attempts the same key.
    db2 = SessionLocal()
    try:
        with try_advisory_lock(db2, key) as acquired2:
            # Lock was released by db1's commit — db2 must succeed, not be blocked out.
            assert acquired2 is True
            db2.commit()
    finally:
        db2.close()


def test_no_leftover_advisory_locks_after_clean_exit(test_engine):
    """After a clean acquire + commit, pg_locks shows no advisory locks left behind."""
    key = "test:advisory_lock:concurrency:no_leftover_clean"

    db1 = SessionLocal()
    try:
        with try_advisory_lock(db1, key) as acquired:
            assert acquired is True
            db1.commit()
    finally:
        db1.close()

    checker = SessionLocal()
    try:
        remaining = _count_advisory_locks_for_key(checker, key)
        assert remaining == 0, f"expected zero advisory locks for key={key!r} after commit, found {remaining}"
    finally:
        checker.close()


def test_body_exception_still_releases_lock_via_rollback(test_engine):
    """If the caller's body raises, rolling back the session must still release the
    transaction-scoped lock — confirmed via pg_locks afterward.
    """
    key = "test:advisory_lock:concurrency:body_raises"

    db1 = SessionLocal()
    try:
        try:
            with try_advisory_lock(db1, key) as acquired:
                assert acquired is True
                raise RuntimeError("simulated failure inside the locked block")
        except RuntimeError:
            db1.rollback()
    finally:
        db1.close()

    checker = SessionLocal()
    try:
        remaining = _count_advisory_locks_for_key(checker, key)
        assert remaining == 0, f"expected zero advisory locks for key={key!r} after rollback, found {remaining}"
    finally:
        checker.close()

    # And a fresh session can now acquire the same key without contention.
    db2 = SessionLocal()
    try:
        with try_advisory_lock(db2, key) as acquired2:
            assert acquired2 is True
            db2.commit()
    finally:
        db2.close()


def test_lock_held_by_uncommitted_transaction_blocks_second_session(test_engine):
    """While the first session's transaction is still open (no commit/rollback yet), a second,
    independent session trying the SAME key must get acquired=False — proving the lock is real
    mutual exclusion, not a no-op.
    """
    key = "test:advisory_lock:concurrency:blocks_while_open"

    db1 = SessionLocal()
    db2 = SessionLocal()
    try:
        with try_advisory_lock(db1, key) as acquired1:
            assert acquired1 is True
            # db1's transaction is still open — do not commit/rollback yet.
            with try_advisory_lock(db2, key) as acquired2:
                assert acquired2 is False
        db1.commit()
    finally:
        db1.close()
        db2.close()


def test_not_acquired_path_does_not_leave_session_idle_in_transaction(test_engine):
    """A losing (not-acquired) call must not pin an idle-in-transaction connection — the
    failed pg_try_advisory_xact_lock call still autobegins a transaction on `db`, which the
    helper must roll back on the not-acquired path, not just on the exception path.
    """
    key = "test:advisory_lock:concurrency:not_acquired_no_idle_tx"

    holder = SessionLocal()
    loser = SessionLocal()
    try:
        with try_advisory_lock(holder, key) as acquired_holder:
            assert acquired_holder is True
            with try_advisory_lock(loser, key) as acquired_loser:
                assert acquired_loser is False
            # The losing session must already be out of a transaction — not left
            # idle-in-transaction pinning a connection/snapshot for no reason.
            assert loser.in_transaction() is False
        holder.commit()
    finally:
        holder.close()
        loser.close()


def test_savepoint_recovery_keeps_lock_held_but_bare_rollback_releases_it(test_engine):
    """Documents and pins the exact footgun the module docstring warns about: a bare
    `db.rollback()` partway through the guarded block silently releases the transaction-scoped
    lock (since Postgres ties it to the transaction, not the `with` block), while recovering
    via `db.begin_nested()` (a SAVEPOINT) does not — the outer transaction, and the lock riding
    on it, survive a savepoint rollback intact.
    """
    savepoint_key = "test:advisory_lock:concurrency:savepoint_recovery"
    bare_rollback_key = "test:advisory_lock:concurrency:bare_rollback_footgun"

    # --- Savepoint recovery: the lock survives a per-item failure. ---
    db1 = SessionLocal()
    other = SessionLocal()
    try:
        with try_advisory_lock(db1, savepoint_key) as acquired:
            assert acquired is True
            try:
                with db1.begin_nested():
                    raise RuntimeError("simulated per-item failure")
            except RuntimeError:
                pass  # recovered via the savepoint, outer transaction (and the lock) intact
            # A second session must still be locked out — the savepoint rollback did not
            # release the outer, lock-holding transaction.
            with try_advisory_lock(other, savepoint_key) as still_locked_out:
                assert still_locked_out is False
        db1.commit()
    finally:
        db1.close()
        other.close()

    # --- Bare rollback: the documented footgun — the lock is lost mid-block. ---
    db2 = SessionLocal()
    other2 = SessionLocal()
    try:
        with try_advisory_lock(db2, bare_rollback_key) as acquired:
            assert acquired is True
            db2.rollback()  # releases the xact lock immediately, per the docstring warning
            # A second session can now acquire the "same" lock while db2 still believes
            # (per the stale `acquired` value bound above) that it holds it.
            with try_advisory_lock(other2, bare_rollback_key) as should_have_been_blocked:
                assert should_have_been_blocked is True, (
                    "this assertion documents the footgun: mutual exclusion is genuinely lost "
                    "after a bare rollback, which is exactly why the docstring tells callers to "
                    "use db.begin_nested() instead for per-item recovery"
                )
                other2.commit()
    finally:
        db2.close()
        other2.close()
