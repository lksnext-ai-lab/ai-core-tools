"""Bounded delivery of the files a sandbox produced into the turn's local output folder.

Runs in a worker thread (provider SDK calls are blocking and ``read_file`` loads whole files into memory) with:

* per-turn limits: max files, max bytes per file, max total bytes (``SANDBOX_PULL_*`` settings, 0 = no limit);
  sizes come from one ``stat`` call in the sandbox (``SandboxProvider.file_sizes``); a file whose size is unknown
  is read and dropped when it turns out to be over the limit;
* an overall time budget and a small process-wide limiter (``SANDBOX_PULL_MAX_CONCURRENT`` threads);
* safe local names: only the base name is used, never absolute / hidden / control-character names, sandbox
  symlinks are skipped, two remote files with the same base name never overwrite each other, files are written to
  a temp name and moved into place, and a destination that is a symlink is replaced, never followed.

A slow, failing or oversized pull never fails the turn: the caller keeps the answer and just gets a content-free
outcome (counts only). No file name or provider error text is ever logged on a Chat turn.
"""
from __future__ import annotations

import asyncio
import itertools
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Optional

import config as settings
from tools.sandbox.chat_guard import pull_guard, redacted_logs
from utils.logger import get_logger

logger = get_logger(__name__)

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_MAX_NAME_BYTES = 200
_MAX_STAT_PATHS = 200
_MAX_LIST_RESULTS = 5000  # entries of ``list_files`` ever looked at (a sandbox can create millions)

_pool_lock = threading.Lock()
_pool: ThreadPoolExecutor | None = None
_slots: threading.BoundedSemaphore | None = None


def _executor() -> tuple[ThreadPoolExecutor, threading.BoundedSemaphore]:
    """The pull pool and its slot semaphore (a pull is skipped at once when every slot is busy, never queued)."""
    global _pool, _slots
    with _pool_lock:
        if _pool is None:
            workers = max(1, int(getattr(settings, "SANDBOX_PULL_MAX_CONCURRENT", 2)))
            _pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="sandbox_pull")
            _slots = threading.BoundedSemaphore(workers)
        return _pool, _slots


@dataclass(frozen=True)
class PullLimits:
    max_files: int
    max_file_bytes: int
    max_total_bytes: int
    time_budget_s: float

    @classmethod
    def from_settings(cls) -> "PullLimits":
        return cls(
            max_files=max(0, int(getattr(settings, "SANDBOX_PULL_MAX_FILES", 20))),
            max_file_bytes=max(0, int(getattr(settings, "SANDBOX_PULL_MAX_FILE_BYTES", 50 * 1024 * 1024))),
            max_total_bytes=max(0, int(getattr(settings, "SANDBOX_PULL_MAX_TOTAL_BYTES", 100 * 1024 * 1024))),
            time_budget_s=max(0.0, float(getattr(settings, "SANDBOX_PULL_TIME_BUDGET_S", 20.0))),  # 0 = no budget
        )


@dataclass
class PullOutcome:
    """Counts only. ``incomplete`` = a timeout or an error stopped the pull (files may be missing)."""

    pulled: int = 0
    skipped: int = 0
    incomplete: bool = False
    refused: bool = False  # the provider cannot bound a read: nothing was pulled from it

    @property
    def undelivered(self) -> int:
        """What to tell the user: skipped files, or 1 when the pull itself failed / ran out of time."""
        return self.skipped if self.skipped else (1 if self.incomplete else 0)


def safe_local_name(remote_rel: str) -> Optional[str]:
    """Base name usable inside the local output dir, or None. Never a path, hidden file or control characters."""
    name = os.path.basename(str(remote_rel or "").replace("\\", "/"))
    if not name or name in (".", "..") or name.startswith("."):
        return None
    if _CONTROL.search(name) or len(name.encode("utf-8", "ignore")) > _MAX_NAME_BYTES:
        return None
    return name


def unique_name(name: str, used: set) -> str:
    """``name``, or ``stem-2.ext``, ``stem-3.ext``... when already taken in this pull."""
    if name not in used:
        used.add(name)
        return name
    stem, ext = os.path.splitext(name)
    n = 2
    while f"{stem}-{n}{ext}" in used:
        n += 1
    chosen = f"{stem}-{n}{ext}"
    used.add(chosen)
    return chosen


def _write_into(output_dir: str, name: str, data: bytes, cancel: threading.Event) -> bool:
    """Temp file then ``os.replace`` (replaces a symlink at the destination instead of following it)."""
    root = os.path.realpath(output_dir)
    dest = os.path.join(root, name)  # ``name`` is a safe base name: the parent is ``root``; the leaf is never resolved
    tmp = os.path.join(root, f".pull-{uuid.uuid4().hex}.tmp")
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
        if cancel.is_set():  # the budget ran out while writing: the answer is already final
            return False
        os.replace(tmp, dest)
        return True
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _blocking_pull(
    provider: Any,
    handle: Any,
    *,
    is_output_file: Callable[[str], bool],
    to_relative: Callable[[str], str],
    pre_existing: set,
    output_dir: str,
    limits: PullLimits,
    lease: Callable[[], Any],
    cancel: threading.Event,
    chat: bool,
    log_key: str,
) -> PullOutcome:
    outcome = PullOutcome()
    deadline = time.monotonic() + limits.time_budget_s if limits.time_budget_s else None
    with redacted_logs(chat), pull_guard(cancel, deadline):
        try:
            with lease():
                remote_files = list(itertools.islice(provider.list_files(handle), _MAX_LIST_RESULTS))
                candidates: list[tuple[str, str]] = []
                for remote_path in remote_files:
                    if not is_output_file(remote_path):
                        continue
                    rel = to_relative(remote_path)
                    if rel in pre_existing:
                        continue
                    if safe_local_name(rel) is None:
                        outcome.skipped += 1
                        continue
                    candidates.append((remote_path, rel))

                sizes: dict = {}
                if candidates:
                    try:
                        found = provider.file_sizes(handle, [rel for _, rel in candidates[:_MAX_STAT_PATHS]])
                        sizes = found if isinstance(found, dict) else {}
                    except Exception as exc:  # noqa: BLE001
                        _log(chat, "sandbox pull: size lookup failed (%s) key=%s", exc, log_key)

                used: set = set()
                total = 0
                for index, (remote_path, rel) in enumerate(candidates):
                    if cancel.is_set():
                        outcome.incomplete = True
                        break
                    if limits.max_files and outcome.pulled >= limits.max_files:
                        outcome.skipped += 1
                        continue
                    # ``sizes`` come from a shell INSIDE the sandbox (forgeable): a pre-filter that saves a read,
                    # never what bounds memory. The read itself is always bounded.
                    size = sizes.get(rel)
                    if size == -1:  # reported as not a regular file (symlink, ...)
                        outcome.skipped += 1
                        continue
                    if size is not None and (
                        (limits.max_file_bytes and size > limits.max_file_bytes)
                        or (limits.max_total_bytes and total + size > limits.max_total_bytes)
                    ):
                        outcome.skipped += 1
                        continue
                    if limits.max_total_bytes and total >= limits.max_total_bytes:
                        outcome.skipped += 1
                        continue
                    caps = [c for c in (
                        limits.max_file_bytes,
                        (limits.max_total_bytes - total) if limits.max_total_bytes else 0,
                    ) if c]
                    cap = min(caps) if caps else None
                    try:
                        if cap is None:  # an administrator turned every size cap off
                            data = provider.read_file(handle, rel)
                        else:
                            data = provider.read_file_limited(handle, rel, cap)
                    except NotImplementedError:
                        # This provider cannot bound a read: refuse rather than load whole files.
                        outcome.skipped += len(candidates) - index
                        outcome.refused = True
                        break
                    except Exception as exc:  # noqa: BLE001
                        _log(chat, "sandbox pull: read failed (%s) key=%s", exc, log_key)
                        outcome.incomplete = True
                        continue
                    if not isinstance(data, (bytes, bytearray)):
                        outcome.incomplete = True
                        continue
                    if cap is not None and len(data) > cap:
                        outcome.skipped += 1  # more than the cap (or the file grew): dropped, never stored
                        continue
                    name = unique_name(safe_local_name(rel), used)
                    if _write_into(output_dir, name, data, cancel):
                        total += len(data)
                        outcome.pulled += 1
                    else:
                        outcome.skipped += 1
        except Exception as exc:  # noqa: BLE001
            _log(chat, "sandbox pull failed (%s) key=%s", exc, log_key)
            outcome.incomplete = True
    return outcome


def _log(chat: bool, message: str, exc: BaseException, key: str) -> None:
    if chat:
        logger.warning(message, type(exc).__name__, key)  # class name + session key only
    else:
        logger.warning(message + " detail=%s", type(exc).__name__, key, exc)


async def pull_outputs(
    provider: Any,
    handle: Any,
    *,
    is_output_file: Callable[[str], bool],
    to_relative: Callable[[str], str],
    pre_existing: set,
    output_dir: str,
    lease: Callable[[], Any],
    chat: bool,
    log_key: str,
    limits: PullLimits | None = None,
) -> PullOutcome:
    """Run the pull in a worker thread under the overall time budget; never raises (except cancellation)."""
    limits = limits or PullLimits.from_settings()
    cancel = threading.Event()
    loop = asyncio.get_running_loop()
    pool, slots = _executor()
    if not slots.acquire(blocking=False):
        # Every pull slot is busy (hung or slow pulls of other turns): skip now instead of queueing until the budget ends.
        logger.warning("sandbox pull skipped: all pull slots busy key=%s", log_key)
        return PullOutcome(incomplete=True)

    def job() -> PullOutcome:
        try:
            return _blocking_pull(
                provider, handle, is_output_file=is_output_file, to_relative=to_relative, pre_existing=pre_existing,
                output_dir=output_dir, limits=limits, lease=lease, cancel=cancel, chat=chat, log_key=log_key,
            )
        finally:
            slots.release()  # when the worker really ends (a timed-out pull keeps its slot until then)

    try:
        future = loop.run_in_executor(pool, job)
    except BaseException:
        slots.release()
        raise
    try:
        return await asyncio.wait_for(future, timeout=limits.time_budget_s or None)
    except asyncio.TimeoutError:
        cancel.set()
        logger.warning("sandbox pull exceeded %ss; files skipped key=%s", limits.time_budget_s, log_key)
        return PullOutcome(incomplete=True)
    except Exception as exc:  # noqa: BLE001
        cancel.set()
        _log(chat, "sandbox pull failed (%s) key=%s", exc, log_key)
        return PullOutcome(incomplete=True)
