"""Seed system (platform) skill packages from ``backend/system_skills/`` on startup (FR-32/33, AC-29..32).

Modelled on ``backend/services/tier_config_seeder.py``. **Create-if-missing only** (AC-30): a system skill
already present (matched by name) is never updated, restored or re-enabled by this seeder, even if its YAML
entry or on-disk package contents have since changed — an admin may freely disable or edit a seeded skill and
that change survives every subsequent restart untouched.

Concurrency (AC-32, NFR-4a): the whole run is wrapped in ``try_advisory_lock`` (transaction-scoped, see
``backend/db/advisory_lock.py``'s module docstring — read it before touching this file). Per-package failures
(AC-31) are isolated with ``db.begin_nested()`` (a SAVEPOINT), never a bare ``db.rollback()`` on the outer
session: a bare rollback would silently release the transaction-scoped advisory lock mid-run, letting a second
replica start seeding concurrently for the rest of this run. See the advisory-lock module docstring's "Other
caveats" section for the reproduction of that exact footgun.

Fail-soft: ``seed_system_skills`` never raises. It logs created/skipped/failed counts and, on a per-package
failure, the package path and exception message — never file contents (NFR-7).
"""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from sqlalchemy.orm import Session

import config as settings
from db.advisory_lock import try_advisory_lock
from repositories.skill_repository import SkillRepository
from services.skill_errors import SkillServiceError
from services.skill_package_service import SkillPackageService
from utils.logger import get_logger
from utils.skill_frontmatter import SkillFrontmatterError, parse_skill_md
from utils.skill_paths import normalize_path

logger = get_logger(__name__)

_LOCK_KEY = "mattin:system_skills_seed"
_SKILL_MD = "SKILL.md"
_DEFAULTS_PATH = Path(__file__).resolve().parents[1] / "system_defaults.yaml"
_PACKAGES_ROOT = Path(__file__).resolve().parents[1] / "system_skills"


class _PackageError(Exception):
    """Internal, per-package failure. Never escapes ``_seed_locked``'s per-entry try/except.

    The message must never contain file contents (NFR-7) — only paths, names and short reasons.
    """


def seed_system_skills(db: Session) -> None:
    """Create-if-missing the system skills declared in ``system_defaults.yaml``'s ``skills:`` block.

    Never raises. Skips the whole run (INFO log) if the advisory lock is not acquired — another
    replica/worker is already seeding. See the module docstring for the per-package isolation
    strategy and why it must never use a bare ``db.rollback()``.

    The config is loaded BEFORE the advisory lock is taken (cheap early-out): a no-op run (missing
    or empty ``skills:``) never pays for a pool checkout / lock round-trip / commit.

    Args:
        db: A synchronous SQLAlchemy session (e.g. a fresh ``SessionLocal()`` from the lifespan).
            Must not carry earlier uncommitted work the caller needs to keep — entering the
            advisory lock rolls the session back on a not-acquired/error path.
    """
    entries = _load_skill_entries()
    if entries is None:
        # Distinct from "loaded, zero entries" (M4/production-readiness): a missing/malformed
        # system_defaults.yaml is a config problem, not a clean no-op run.
        logger.error(
            "system_skills_seeder: skipping this run — system_defaults.yaml could not be loaded "
            "(see the error above); this is NOT the same as a clean zero-entry run"
        )
        return
    if not entries:
        logger.info("system_skills_seeder: no system skills configured, nothing to do")
        return

    try:
        with try_advisory_lock(db, _LOCK_KEY) as acquired:
            if not acquired:
                # try_advisory_lock cannot distinguish "another replica holds it" from a DB
                # connection error collapsing to acquired=False — don't claim a specific cause.
                logger.info("system_skills_seeder: advisory lock not acquired — skipping this run")
                return
            _seed_locked(db, entries)
    except Exception:
        logger.error("system_skills_seeder: unexpected error during seeding", exc_info=True)
    finally:
        # Belt-and-braces (reliability): leave the session's transaction state clean regardless of
        # what happened above, rather than relying on the caller's `finally: _db.close()`.
        try:
            db.rollback()
        except Exception:
            logger.warning("system_skills_seeder: rollback after run failed", exc_info=True)


def _seed_locked(db: Session, entries: List[Dict[str, Any]]) -> None:
    """Body of the seed run, executed while the advisory lock is held. Never raises.

    Args:
        entries: The already-loaded, non-empty ``skills:`` list (see ``seed_system_skills``).
    """
    logger.info(
        "system_skills_seeder: starting run — %d package entry(ies) configured, packages root %s",
        len(entries), _PACKAGES_ROOT,
    )
    if not _PACKAGES_ROOT.is_dir():
        # One clear top-level message instead of N confusing per-package "directory not found" errors.
        logger.error(
            "system_skills_seeder: packages root %s does not exist — %d configured package(s) cannot "
            "be seeded",
            _PACKAGES_ROOT, len(entries),
        )
        return

    created_names: List[str] = []
    skipped = 0
    failed = 0

    for entry in entries:
        name, rel_path = _validate_entry(entry)
        if name is None:
            failed += 1
            continue

        try:
            # Existence check moved inside the per-package try (M4): a DB error here must be
            # isolated like any other per-package failure, not abandon the whole run.
            if SkillRepository.get_system_skill_by_name(db, name) is not None:
                skipped += 1
                logger.debug("system_skills_seeder: system skill %r already exists, skipping", name)
                continue

            with db.begin_nested():
                pkg_dir = _resolve_package_dir(rel_path)
                _create_skill_from_package(db, name, pkg_dir)
            created_names.append(name)
        except _PackageError as exc:
            # Expected, already-self-describing (path + reason, never file contents, NFR-7) and,
            # for a permanently-broken package, will re-fail identically on every restart: no
            # exc_info traceback spam on every startup.
            failed += 1
            logger.error("system_skills_seeder: package %s failed: %s", rel_path, exc)
        except SkillServiceError as exc:
            # Raised by SkillPackageService.create_skill_from_parsed; .detail is a curated,
            # content-free message (same contract _PackageError has).
            failed += 1
            logger.error("system_skills_seeder: package %s failed: %s", rel_path, exc.detail)
        except Exception as exc:
            # Genuinely unexpected (e.g. a raw IntegrityError/DataError from the DB layer). Never
            # log str(exc) or exc_info=True here: for these exception types the stringified form
            # (and the traceback's final line) can include the failing statement's bound
            # parameters — i.e. full Skill.content / SkillFile.content_text — which would violate
            # NFR-7. Log only the exception class; an operator can investigate from there.
            failed += 1
            logger.error(
                "system_skills_seeder: package %s failed with unexpected %s", rel_path, type(exc).__name__
            )

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.error("system_skills_seeder: final commit failed, no system skills were seeded", exc_info=True)
        return

    logger.info(
        "system_skills_seeder: done - created=%d skipped=%d failed=%d (total entries=%d) - names=%s",
        len(created_names), skipped, failed, len(entries), created_names,
    )


def _validate_entry(entry: Any) -> Tuple[Any, Any]:
    """Return ``(name, path)`` from one ``skills:`` entry, or ``(None, None)`` (logged) if malformed."""
    if not isinstance(entry, dict):
        logger.error("system_skills_seeder: skill entry is not a mapping (got %s)", type(entry).__name__)
        return None, None
    name = entry.get("name")
    rel_path = entry.get("path")
    if not isinstance(name, str) or not name.strip():
        logger.error("system_skills_seeder: skill entry missing a valid 'name': %r", entry)
        return None, None
    if not isinstance(rel_path, str) or not rel_path.strip():
        logger.error("system_skills_seeder: skill entry %r missing a valid 'path'", name)
        return None, None
    return name.strip(), rel_path.strip()


def _load_skill_entries() -> Optional[List[Dict[str, Any]]]:
    """Read the ``skills:`` list from ``system_defaults.yaml``.

    Returns:
        The (possibly empty) list on success, or ``None`` if the file is missing/unreadable/malformed
        (M4/production-readiness: this must be distinguishable from a genuine zero-entry run by the
        caller's logging).
    """
    if not _DEFAULTS_PATH.exists():
        logger.error("system_skills_seeder: system_defaults.yaml not found at %s", _DEFAULTS_PATH)
        return None
    try:
        with _DEFAULTS_PATH.open("r", encoding="utf-8") as fh:
            parsed = yaml.safe_load(fh) or {}
    except (yaml.YAMLError, OSError) as exc:
        logger.error("system_skills_seeder: failed to read system_defaults.yaml: %s", exc)
        return None
    entries = parsed.get("skills") or []
    if not isinstance(entries, list):
        logger.error("system_skills_seeder: 'skills' key must be a list, got %s", type(entries).__name__)
        return None
    return entries


def _resolve_package_dir(rel_path: str) -> Path:
    """Resolve+validate ``rel_path`` (relative to ``backend/system_skills/``) to a real directory.

    Applies the same path-safety rules as skill package import (``utils.skill_paths.normalize_path``:
    no absolute paths, no ``..`` segments, no control characters, ...), then confirms the resolved
    real path stays inside ``backend/system_skills/`` and is not itself a symlink — this is a local,
    developer-controlled directory (not an untrusted zip), but a badly-behaved package author could
    still craft a ``../`` escape or a symlink pointing outside the package tree.

    Raises:
        _PackageError: If the path is invalid, escapes the packages root, is a symlink, or does not
            resolve to an existing directory.
    """
    try:
        normalized = normalize_path(rel_path)
    except ValueError as exc:
        raise _PackageError(f"invalid package path: {exc}") from exc

    candidate = _PACKAGES_ROOT / normalized
    if candidate.is_symlink():
        raise _PackageError(f"package path is a symlink: {rel_path}")
    try:
        resolved = candidate.resolve(strict=True)
        root_resolved = _PACKAGES_ROOT.resolve(strict=True)
    except OSError as exc:
        raise _PackageError(f"package directory not found: {rel_path}") from exc
    if resolved != root_resolved and not str(resolved).startswith(str(root_resolved) + os.sep):
        raise _PackageError(f"package path escapes system_skills/: {rel_path}")
    if not resolved.is_dir():
        raise _PackageError(f"package path is not a directory: {rel_path}")
    return resolved


def _open_regular_file_nofollow(abs_path: Path, rel_for_error: str) -> int:
    """Open ``abs_path`` for reading, refusing to follow a symlink and never blocking on a FIFO.

    ``O_NONBLOCK`` is critical here (M1): opening a FIFO for read-only WITHOUT it blocks the calling
    thread until a writer opens the other end — with no writer, that's forever, hanging the whole
    FastAPI lifespan while holding the advisory lock, with zero log signal. With ``O_NONBLOCK`` the
    open call itself returns immediately regardless of a FIFO's writer state, so the very next
    ``os.fstat``/``stat.S_ISREG`` check below can reject it loudly instead.

    Raises:
        _PackageError: If the path cannot be opened (including a symlink rejected by ``O_NOFOLLOW``).
    """
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
    try:
        return os.open(abs_path, flags)
    except OSError as exc:
        raise _PackageError(f"could not open {rel_for_error!r}: {exc}") from exc


def _read_regular_file_bounded(abs_path: Path, rel_for_error: str, max_bytes: int) -> bytes:
    """Read a file's bytes, checking its type and size via ``fstat`` BEFORE reading any content.

    Fixes M1 (a FIFO/socket/device file under a package directory hanging the process forever —
    ``Path.read_bytes()`` never returns without checking ``S_ISREG`` first) and the ordering half of
    M2 (a size cap enforced only AFTER the whole file was already buffered defeats the point of a cap
    for a large-file DoS): the type and size are validated from ``fstat`` output before a single byte
    of content is read, and the read loop itself still enforces the cap as a second line of defense.

    Raises:
        _PackageError: If the path cannot be opened, is not a regular file, or exceeds ``max_bytes``.
    """
    fd = _open_regular_file_nofollow(abs_path, rel_for_error)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise _PackageError(f"not a regular file: {rel_for_error!r}")
        if st.st_size > max_bytes:
            raise _PackageError(f"file {rel_for_error!r} exceeds max size (limit {max_bytes} bytes)")

        chunks: List[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise _PackageError(f"file {rel_for_error!r} exceeds max size (limit {max_bytes} bytes)")
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def _walk_package_files(pkg_dir: Path) -> Tuple[str, Dict[str, bytes]]:
    """Read ``SKILL.md`` and every other file of a package, applying the same
    ``SKILL_IMPORT_MAX_FILES`` / ``SKILL_IMPORT_MAX_FILE_BYTES`` / ``SKILL_IMPORT_MAX_TOTAL_BYTES``
    limits enforced for uploaded skill packages, refusing symlinks (files AND subdirectories) and
    any path escaping ``pkg_dir``.

    Every discovered path must already be in its own NFKC-normalised form (H1): a package file whose
    on-disk relative path differs from ``normalize_path(rel)`` — e.g. a fullwidth-Unicode homoglyph
    that NFKC-folds onto a different, already-present file's key — is rejected outright rather than
    silently overwriting the earlier entry. Duplicate normalised paths are rejected case-insensitively
    too, matching ``SkillPackageRepository.replace_files``'s own duplicate rule.

    Returns:
        ``(skill_md_text, {normalised_posix_path: content_bytes})`` — SKILL.md itself is excluded
        from the returned file mapping (it is stored in ``Skill.content``, not as a ``SkillFile``),
        but its bytes DO count toward ``SKILL_IMPORT_MAX_TOTAL_BYTES`` (M2).

    Raises:
        _PackageError: On a missing/unreadable/non-UTF-8/oversized SKILL.md, a non-regular file
            (FIFO/socket/device), a symlinked file or subdirectory, a path escaping the package
            directory, a homoglyph/case collision, or any of the SKILL_IMPORT_* limits being exceeded.
    """
    skill_md_path = pkg_dir / _SKILL_MD
    if skill_md_path.is_symlink() or not skill_md_path.is_file():
        raise _PackageError(f"missing {_SKILL_MD}")
    skill_md_bytes = _read_regular_file_bounded(skill_md_path, _SKILL_MD, settings.SKILL_IMPORT_MAX_FILE_BYTES)
    try:
        skill_md_text = skill_md_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _PackageError(f"{_SKILL_MD} could not be read as UTF-8 text: {exc}") from exc

    root_resolved = pkg_dir.resolve(strict=True)
    files: Dict[str, bytes] = {}
    seen_lower: set = set()
    file_count = 0
    total_bytes = len(skill_md_bytes)
    if total_bytes > settings.SKILL_IMPORT_MAX_TOTAL_BYTES:
        raise _PackageError(f"package exceeds total size limit ({settings.SKILL_IMPORT_MAX_TOTAL_BYTES} bytes)")

    for dirpath, dirnames, filenames in os.walk(pkg_dir, followlinks=False):
        symlinked_dirs = [d for d in dirnames if (Path(dirpath) / d).is_symlink()]
        if symlinked_dirs:
            rel_dir = (Path(dirpath) / sorted(symlinked_dirs)[0]).relative_to(pkg_dir).as_posix()
            raise _PackageError(f"symlinked directory not allowed: {rel_dir}")
        dirnames[:] = sorted(dirnames)

        for fname in sorted(filenames):
            abs_path = Path(dirpath) / fname
            rel = abs_path.relative_to(pkg_dir).as_posix()
            if rel == _SKILL_MD:
                continue
            if abs_path.is_symlink():
                raise _PackageError(f"symlink entry not allowed: {rel}")
            try:
                norm = normalize_path(rel)
            except ValueError as exc:
                raise _PackageError(f"invalid package file path {rel!r}: {exc}") from exc
            if norm != rel:
                # A file in a developer-controlled tree has no legitimate reason to need NFKC
                # folding at all (H1) — treat any such divergence as a hard, loud error rather than
                # silently normalising it (and possibly colliding with another file).
                raise _PackageError(
                    f"package file path {rel!r} is not already in normalised form (normalises to "
                    f"{norm!r}) — rename the on-disk file instead of relying on normalisation"
                )
            lowered = norm.lower()
            if lowered in seen_lower:
                raise _PackageError(f"duplicate package file path (case-insensitive collision): {rel!r}")
            seen_lower.add(lowered)

            try:
                resolved_file = abs_path.resolve(strict=True)
            except OSError as exc:
                raise _PackageError(f"could not resolve {rel!r}: {exc}") from exc
            if not str(resolved_file).startswith(str(root_resolved) + os.sep):
                raise _PackageError(f"path escapes package directory: {rel!r}")

            file_count += 1
            if file_count > settings.SKILL_IMPORT_MAX_FILES:
                raise _PackageError(f"too many files (limit {settings.SKILL_IMPORT_MAX_FILES})")

            data = _read_regular_file_bounded(abs_path, rel, settings.SKILL_IMPORT_MAX_FILE_BYTES)
            total_bytes += len(data)
            if total_bytes > settings.SKILL_IMPORT_MAX_TOTAL_BYTES:
                raise _PackageError(
                    f"package exceeds total size limit ({settings.SKILL_IMPORT_MAX_TOTAL_BYTES} bytes)"
                )
            files[norm] = data

    return skill_md_text, files


def _create_skill_from_package(db: Session, name: str, pkg_dir: Path) -> None:
    """Parse ``pkg_dir`` and persist (flush, no commit) the resulting system ``Skill`` + ``SkillFile`` rows.

    Caller must run this inside a ``db.begin_nested()`` block so a failure here recovers via a SAVEPOINT
    rollback rather than a bare ``db.rollback()`` on the outer (lock-holding) transaction.

    The actual Skill/SkillFile construction is delegated to ``SkillPackageService.create_skill_from_parsed``
    — the same transaction-agnostic seam ``SkillPackageService._import_locked`` uses for admin/app
    imports (H2) — so column defaults (``create_date``), ``source`` validation and DB-constraint ->
    friendly-message mapping never have to be re-implemented and kept in sync here.

    Raises:
        _PackageError: On invalid package content discovered by this module's own path/size/symlink
            checks (never file contents, NFR-7).
        SkillServiceError: (e.g. ``SkillImportError``/``SkillConflictError``/``SkillPersistenceError``)
            raised by ``create_skill_from_parsed`` — its ``.detail`` is a curated, content-free message.
    """
    skill_md_text, files = _walk_package_files(pkg_dir)
    try:
        parsed = parse_skill_md(skill_md_text)
    except SkillFrontmatterError as exc:
        raise _PackageError(f"invalid {_SKILL_MD}: {exc}") from exc
    if parsed.name != name:
        raise _PackageError(
            f"{_SKILL_MD} name {parsed.name!r} does not match the configured skills: entry name {name!r}"
        )

    SkillPackageService.create_skill_from_parsed(db, app_id=None, parsed=parsed, files=files, source="yaml")
