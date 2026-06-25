"""Background sweep that enforces TTL on uploaded files.

Two concerns live here:

- **Ephemeral orphans**: files under ``data/tmp/ephemeral/{session_key}/``
  that the per-request ``finally`` failed to clean up (request crashed,
  worker was killed mid-stream, etc.). These should never be older than
  the duration of a single chat turn; ``TMP_EPHEMERAL_ORPHAN_HOURS``
  (default 1h) is the safety net.

- **Persistent TTL**: files under ``data/tmp/persistent/{session_key}/``
  associated with a memory-enabled conversation. We expire them after
  ``TMP_PERSISTENT_TTL_DAYS`` of inactivity (mtime-based), matching the
  OpenAI Threads convention of "7 days from last activity".

The worker follows the existing ``services.crawl.worker`` pattern:
asyncio task started from ``main.lifespan``, ``asyncio.CancelledError``
for graceful shutdown, no extra dependencies. The actual filesystem
walk is blocking I/O so it runs in a thread (``asyncio.to_thread``) to
keep the event loop free.

**Multi-worker coordination**: uvicorn forks one process per
``UVICORN_WORKERS``, each running its own lifespan. Without coordination
every worker would launch its own sweep loop, all competing to delete
the same files. ``start_file_cleanup_worker()`` therefore acquires a
non-blocking exclusive ``filelock.FileLock`` on
``$TMP_BASE_FOLDER/.cleanup.lock`` (cross-platform: fcntl on POSIX,
msvcrt on Windows). Only the first worker that wins the lock runs the
sweep; others log a notice and return ``None``. The OS releases the lock
automatically on process exit (including SIGKILL) so no manual lockfile
cleanup is needed.

**About the staggered "starting" logs**: with multiple uvicorn workers
each lifespan runs in its own process. The second worker typically
finishes its lifespan ~30 s after the first because the slow steps
(plugin discovery, checkpointer pool initialization) are per-process.
That is normal — only one of those workers will go on to register an
active cleanup sweep; the other will log the "another worker holds the
leader lock" notice.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import List

from filelock import FileLock, Timeout

from utils.logger import get_logger

logger = get_logger(__name__)


def _config() -> dict:
    """Read cleanup config lazily so tests can monkey-patch env vars."""
    from utils.config import get_app_config

    return get_app_config()


def _collect_expired_files(root: str, cutoff: float) -> List[str]:
    """Return paths under ``root`` whose mtime is older than ``cutoff``."""
    victims: List[str] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            full = os.path.join(dirpath, filename)
            try:
                if os.path.getmtime(full) < cutoff:
                    victims.append(full)
            except OSError:
                # File disappeared mid-walk; harmless.
                continue
    return victims


def _remove_files(paths: List[str], label: str) -> int:
    """Best-effort removal; returns count of files actually removed."""
    removed = 0
    for path in paths:
        try:
            os.remove(path)
            removed += 1
        except OSError as exc:
            logger.warning(
                "file_cleanup_worker[%s]: could not remove %s: %s",
                label, path, exc,
            )
    return removed


def _prune_empty_dirs(root: str) -> None:
    """Remove now-empty subdirectories of ``root`` bottom-up."""
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        if dirpath == root:
            continue
        if dirnames or filenames:
            continue
        try:
            os.rmdir(dirpath)
        except OSError:
            # Race with a new upload re-creating the directory; skip.
            pass


def _purge_tree_older_than(root: str, ttl_seconds: int, *, label: str) -> int:
    """Walk ``root`` and remove files whose mtime is older than the TTL.

    After per-file removal, empty directories under ``root`` are removed
    too so the tree does not accumulate empty session_key folders.

    Returns the number of files removed.
    """
    if not os.path.isdir(root):
        return 0

    cutoff = time.time() - ttl_seconds
    try:
        victims = _collect_expired_files(root, cutoff)
        removed = _remove_files(victims, label)
        _prune_empty_dirs(root)
        return removed
    except Exception as exc:
        logger.error(
            "file_cleanup_worker[%s]: unexpected error during sweep: %s",
            label, exc, exc_info=True,
        )
        return 0


def _run_one_sweep_sync() -> None:
    """Single pass over both ephemeral and persistent trees (blocking)."""
    cfg = _config()
    if not cfg.get('TMP_CLEANUP_ENABLED', True):
        logger.debug("file_cleanup_worker: cleanup disabled via TMP_CLEANUP_ENABLED=false")
        return

    tmp_base = cfg['TMP_BASE_FOLDER']
    ephemeral_root = os.path.join(tmp_base, "ephemeral")
    persistent_root = os.path.join(tmp_base, "persistent")
    uploads_root = os.path.join(tmp_base, "uploads")

    ephemeral_ttl_seconds = int(cfg['TMP_EPHEMERAL_ORPHAN_HOURS']) * 3600
    persistent_ttl_seconds = int(cfg['TMP_PERSISTENT_TTL_DAYS']) * 86400

    ephemeral_removed = _purge_tree_older_than(
        ephemeral_root, ephemeral_ttl_seconds, label="ephemeral",
    )
    uploads_removed = _purge_tree_older_than(
        uploads_root, ephemeral_ttl_seconds, label="uploads",
    )
    persistent_removed = _purge_tree_older_than(
        persistent_root, persistent_ttl_seconds, label="persistent",
    )

    if ephemeral_removed or uploads_removed or persistent_removed:
        logger.info(
            "file_cleanup_worker: removed %d ephemeral, %d upload, %d persistent file(s)",
            ephemeral_removed, uploads_removed, persistent_removed,
        )


async def _worker_loop() -> None:
    """Periodic loop. Sleeps between sweeps, cancelable from lifespan.

    The actual sweep is blocking I/O, so it runs in a thread via
    ``asyncio.to_thread`` to avoid stalling the event loop on large trees.
    """
    cfg = _config()
    interval_seconds = max(1, int(cfg['TMP_CLEANUP_INTERVAL_MINUTES']) * 60)

    logger.info(
        "file_cleanup_worker: starting (interval=%ds, persistent_ttl=%dd, ephemeral_orphan=%dh)",
        interval_seconds,
        int(cfg['TMP_PERSISTENT_TTL_DAYS']),
        int(cfg['TMP_EPHEMERAL_ORPHAN_HOURS']),
    )

    while True:
        try:
            await asyncio.to_thread(_run_one_sweep_sync)
        except asyncio.CancelledError:
            logger.info("file_cleanup_worker: shutting down")
            raise
        except Exception as exc:
            logger.error(
                "file_cleanup_worker: sweep failed: %s", exc, exc_info=True,
            )
        try:
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            logger.info("file_cleanup_worker: shutting down")
            raise


# Module-level lock for leader election, held for the lifetime of the leader
# process and released on shutdown. filelock gives cross-process, cross-platform
# locking (fcntl on POSIX, msvcrt on Windows), so this works under Docker,
# bare-metal, and multiple uvicorn workers alike.
_leader_lock: FileLock | None = None


def _try_acquire_leader_lock() -> bool:
    """Try to become the cleanup leader.

    Returns True if this process acquired the lock and should run the sweep;
    False if another worker already holds it. The lock file lives under
    ``$TMP_BASE_FOLDER/.cleanup.lock`` so every worker on the same host sees it.
    """
    global _leader_lock
    cfg = _config()
    lock_dir = cfg['TMP_BASE_FOLDER']
    os.makedirs(lock_dir, exist_ok=True)
    lock_path = os.path.join(lock_dir, '.cleanup.lock')

    lock = FileLock(lock_path)
    try:
        lock.acquire(timeout=0)  # non-blocking; Timeout means another worker leads
    except Timeout:
        return False
    _leader_lock = lock
    return True


def _release_leader_lock() -> None:
    """Release the leader lock if held. Idempotent and exception-safe."""
    global _leader_lock
    if _leader_lock is None:
        return
    try:
        _leader_lock.release()
    except Exception:
        pass
    _leader_lock = None


def start_file_cleanup_worker() -> asyncio.Task | None:
    """Start the cleanup task on the leader worker only.

    With multiple uvicorn workers each lifespan runs in its own process.
    Only the first one to acquire the cleanup leader lock returns an
    asyncio.Task; the others return None and the sweep does not run in
    their event loop. Callers should still pass the (possibly None)
    return value to ``stop_file_cleanup_worker`` during shutdown so the
    lock is released cleanly.
    """
    if not _try_acquire_leader_lock():
        logger.info(
            "file_cleanup_worker: another worker holds the leader lock; "
            "not starting in this process",
        )
        return None
    return asyncio.create_task(_worker_loop(), name="file-cleanup-worker")


async def stop_file_cleanup_worker(task: asyncio.Task | None) -> None:
    """Cancel the cleanup task and release the leader lock.

    Tolerates ``task is None`` (non-leader worker) — in that case there
    is no task to cancel; the lock release is also a no-op since
    non-leaders never acquired it.
    """
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.warning(
                "file_cleanup_worker: unexpected error while awaiting "
                "task shutdown",
                exc_info=True,
            )
    _release_leader_lock()
