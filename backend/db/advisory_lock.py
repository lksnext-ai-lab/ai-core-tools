"""Generic Postgres transaction-scoped advisory lock helper (AD-8).

``try_advisory_lock`` wraps ``pg_try_advisory_xact_lock`` — a Postgres primitive with no
SQLAlchemy ORM table equivalent, invoked here via ``sqlalchemy.func`` (ORM-native function
call, no raw SQL) — behind a contextmanager that yields whether the lock was actually
acquired. This is intentionally **try, don't block**: callers that fail to acquire the lock
(e.g. a losing replica during multi-worker startup seeding) get ``acquired=False`` and are
expected to skip their work gracefully rather than wait. There is no lock-wait/timeout tuning
to get wrong, and no risk of a startup deadlock.

This module already has a correct in-repo precedent for the transaction-scoped variant:
``backend/repositories/skill_repository.py``'s ``lock_app_skills`` uses
``select(func.pg_advisory_xact_lock(...))`` the same way. Do not generalize the raw-SQL
``text()`` justification from ``backend/services/auth/omniadmin_bootstrap.py``'s hand-rolled
session-level lock to other code — that module predates this one, has a known bug (it commits
while still holding its lock — see "Why xact-scoped, not session-scoped" below), and should
migrate to this helper in a follow-up; it is out of scope here.

## Why transaction-scoped (``_xact``), not session-scoped

An earlier version of this module used ``pg_try_advisory_lock`` / ``pg_advisory_unlock``
(session-scoped: bound to the physical connection, released only by an explicit unlock or the
connection closing). That is unsafe with a SQLAlchemy ``Session``: ``Session.commit()`` (and
``rollback()``/``close()``) returns the underlying DBAPI connection to the pool while the
advisory lock stays held ON that pooled connection. A *different*, logically unrelated
``Session`` can then be handed that same pooled connection and "acquire" the same lock
(session-scoped advisory locks are reentrant per-connection, so it just increments a hold
count) — two callers both believe they hold exclusive access. This was independently
reproduced live against the test DB. It is exactly the failure mode the system-skills seeder
(step_033) would hit, since it commits once at the end of the locked block.

``pg_try_advisory_xact_lock`` avoids this entirely: the lock is tied to the *current
transaction* and is released automatically and unconditionally by Postgres the instant that
transaction ends — on **commit or rollback**, whichever happens first, with no manual unlock
call needed and no way to leak it via connection pooling.

**This changes the release timing contract that a naive reader of a ``with`` block might
expect.** The lock is NOT released when the ``with try_advisory_lock(...):`` block exits; it
is released when the CALLER's surrounding transaction on ``db`` next commits or rolls back —
which may happen after the ``with`` block has already exited (e.g. the caller does more work
on ``db`` afterward and commits later), or, more commonly for this module's intended use
(single commit at the end of the locked block, nothing after), effectively coincides with the
end of the block. Callers must not assume the lock is free immediately after the ``with``
block exits unless they have also committed or rolled back ``db`` by that point.

## Other caveats callers must know

- **Sync only.** This helper does synchronous I/O on a synchronous ``Session``. It is intended
  for startup/worker-thread call sites (e.g. seeders run from the FastAPI lifespan on a
  ``SessionLocal()``). Never call it directly from an async request-handler code path — wrap
  it in a threadpool (e.g. ``run_in_threadpool``) if that is ever needed.
- **Reentrancy is per-transaction, not global.** Because the lock is transaction-scoped,
  re-entering ``try_advisory_lock`` with the same key on the SAME ``db`` session/transaction
  will trivially "succeed" again (Postgres advisory locks are reentrant within the connection
  that holds them) — it does not provide mutual exclusion against your own nested calls, only
  against genuinely different connections/transactions.
- **Keys are opaque and un-namespaced.** This module treats ``key`` as a single global string;
  it has no built-in tenant/app dimension. If a lock needs to be per-tenant, the caller must
  bake the tenant identifier into ``key`` itself (e.g. ``f"mattin:my_lock:{app_id}"``).
- **``key`` must be a developer-controlled constant**, never derived from request or tenant
  data — it is logged verbatim on acquisition failure.
- **Do not call ``db.rollback()`` (or ``db.commit()``) partway through the guarded block and
  then keep working on ``db``.** Because the lock is transaction-scoped, a rollback (or commit)
  releases it immediately — Postgres does not know or care that you're still inside the
  ``with`` block. This was reproduced live: a caller that recovers from a per-item failure with
  a bare ``db.rollback()`` and continues its loop silently loses mutual exclusion for the rest
  of the block, with no error and no log signal, while still holding a stale ``acquired=True``.
  A loop that must recover from individual item failures **without** releasing the lock should
  wrap each item in a SAVEPOINT instead of rolling back the whole transaction:
  ``with db.begin_nested(): ...`` per item — a savepoint rollback undoes only that nested
  transaction and leaves the outer (locked) transaction, and the advisory lock, intact.

The lock key Postgres expects is a signed 64-bit integer (``bigint``). Callers pass an
arbitrary string key instead; it is deterministically folded down to a signed 64-bit int via
``blake2b(key, digest_size=8)`` interpreted as big-endian, two's-complement signed.
"""

import hashlib
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from utils.logger import get_logger

logger = get_logger(__name__)


def _derive_lock_key(key: str) -> int:
    """Deterministically derive a signed 64-bit Postgres advisory-lock key from a string.

    Uses blake2b with an 8-byte digest so the same string key always maps to the same
    integer (stable across processes/replicas), then reinterprets those 8 bytes as a
    big-endian, two's-complement signed integer — the type ``pg_try_advisory_xact_lock``
    expects.

    Args:
        key: Arbitrary caller-chosen lock namespace, e.g. ``"mattin:system_skills_seed"``.

    Returns:
        A signed 64-bit integer suitable for ``pg_try_advisory_xact_lock``.
    """
    digest = hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, byteorder="big", signed=True)


@contextmanager
def try_advisory_lock(db: Session, key: str) -> Iterator[bool]:
    """Try (non-blocking) to acquire a Postgres transaction-scoped advisory lock.

    Yields ``True`` if the lock was acquired, ``False`` otherwise — either because another
    transaction already holds it, or because the acquisition attempt itself failed (e.g. a
    connection error). Acquisition failures never raise out of this contextmanager; they are
    logged at WARNING and treated as ``acquired=False`` so callers degrade gracefully
    ("skip this run, don't crash").

    Release semantics (read carefully — this differs from a naive ``try/finally`` unlock):
    the lock is **transaction-scoped** (``pg_try_advisory_xact_lock``), so Postgres releases
    it automatically, unconditionally, when the CALLER's transaction on ``db`` next commits or
    rolls back — not necessarily when this ``with`` block exits. For the intended usage
    (acquire, do work, commit once at the end of the block, nothing after) these two points
    coincide in practice. There is no manual unlock call and nothing to leak: even if the
    caller's process crashes mid-transaction, Postgres drops the lock when the connection's
    transaction is abandoned.

    Args:
        db: SQLAlchemy session bound to a Postgres connection. The lock rides on this
            session's current transaction — do not pass a session whose transaction outlives
            the logical scope you want the lock held for. If the acquisition attempt itself
            raises, this session is rolled back before yielding ``False`` (to clear any
            poisoned-transaction state left by the failed statement) — do not enter this
            contextmanager with earlier uncommitted work on ``db`` that you need to keep.
        key: Arbitrary string identifying the lock namespace (e.g. ``"mattin:system_skills_seed"``).
            Must be a developer-controlled constant (see module docstring) — it is logged.

    Yields:
        bool: Whether the lock was acquired.

    Raises:
        TypeError: If ``key`` is not a ``str`` — a programmer error, not a runtime condition;
            this is a deliberate fail-fast exception to the "never raises" contract above,
            which otherwise only covers acquisition/connection failures.
    """
    if not isinstance(key, str):
        raise TypeError(f"try_advisory_lock: key must be a str, got {type(key).__name__!r}")

    lock_key = _derive_lock_key(key)
    acquired = False

    try:
        acquired = bool(db.execute(select(func.pg_try_advisory_xact_lock(lock_key))).scalar())
        if not acquired:
            # The failed pg_try_advisory_xact_lock call still autobegins a transaction on `db`.
            # Roll it back so a losing caller doesn't leave an idle-in-transaction connection
            # (and its snapshot) pinned for the rest of the session's lifetime.
            try:
                db.rollback()
            except Exception as rollback_exc:
                logger.warning(
                    "try_advisory_lock: failed to roll back session after a not-acquired "
                    "result for key=%r — %s",
                    key,
                    rollback_exc,
                )
    except Exception as exc:
        logger.warning(
            "try_advisory_lock: failed to acquire advisory lock for key=%r (lock_key=%d) — %s; "
            "treating as not acquired",
            key,
            lock_key,
            exc,
        )
        acquired = False
        try:
            db.rollback()
        except Exception as rollback_exc:
            logger.warning(
                "try_advisory_lock: failed to roll back session after acquisition error for "
                "key=%r — %s",
                key,
                rollback_exc,
            )

    yield acquired
