"""Import a Claude Code plugin ZIP's skills into an app (FR-8-adjacent, step_035).

A Claude Code plugin bundle can contain several skills, one per top-level directory under
``skills/`` (case-insensitive), optionally wrapped in one common top-level directory (the shape a
``zip -r plugin.zip my-plugin/`` or a GitHub "Download ZIP" of a plugin repo produces):
``[<wrapper>/]skills/<skill-name>/SKILL.md`` (+ optional other files for that skill).
``utils.safe_zip.find_plugin_root`` resolves and strips that optional wrapper; this module then
groups the remaining entries by their top-level ``skills/<name>/`` directory.

Each candidate's ``SKILL.md`` is parsed with the same frontmatter contract as an ordinary skill
import (``utils.skill_frontmatter.parse_skill_md``) and, exactly like
``SkillPackageService._import_locked`` does for a single-skill import, is validated with
``SkillPackageService.validate_parsed_package`` BEFORE any lock/duplicate-name/quota DB round-trip —
so a structurally invalid candidate fails fast as its own defect, never mis-reported as a duplicate
or a quota rejection just because those DB checks happened to run first. Persistence itself goes
through the same shared seam (``SkillPackageService.create_skill_from_parsed``) the single-skill
admin import path and the system-skill seeder use, so quota checks, length limits, duplicate-name
mapping and DB-constraint-to-typed-error translation never have to be reimplemented here.

Only the whole-archive being unreadable, violating the shared safe-zip limits (entry/size/ratio,
path traversal, symlinks, encryption, ...), or exceeding ``SKILL_IMPORT_MAX_PLUGIN_SKILLS`` candidate
skills is a top-level failure (``SkillImportError``, 400, raised before any per-skill DB work starts).
Any problem scoped to a single candidate skill (missing SKILL.md, invalid frontmatter, duplicate
name, quota exceeded, lock contention, or a genuinely unexpected error) is captured as a per-skill
result entry instead of aborting the rest of the plugin's import — see ``import_plugin``.

Per-skill persistence commits independently (one skill at a time), not as a single all-or-nothing
transaction: a later skill failing must never undo an earlier skill that already succeeded. Imported
skills land ``is_enabled=False`` (unlike the single-skill ``/import`` path, an admin bulk-importing N
skills from one archive has not necessarily read each SKILL.md individually) — an admin reviews and
explicitly enables each one afterwards via the existing ``PATCH .../enabled`` route.

Lock contention is bounded ONCE per whole archive, not re-armed per candidate: each per-app advisory
lock acquisition uses a ``SKILL_IMPORT_LOCK_TIMEOUT_SECONDS`` timeout (default 5s), but as soon as ONE
candidate hits that timeout, every remaining un-processed candidate is reported
``failed: "busy, try again"`` directly, without attempting to re-acquire the lock. Retrying the full
timeout budget per remaining candidate would let a 25-skill archive hold the shared, process-wide
import/export bulkhead (``SkillPackageService.io_slot``, 2 permits) for up to
``25 x SKILL_IMPORT_LOCK_TIMEOUT_SECONDS`` seconds under contention — long enough to 429 every other
tenant's import/export requests for the whole time. Failing fast caps one plugin import's worst-case
lock-contention cost at a single timeout window, regardless of archive size.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

import config as settings
from repositories.skill_repository import SkillRepository
from schemas.skill_schemas import ClaudePluginSkillStatus
from services.skill_errors import SkillImportError, SkillServiceError
from services.skill_package_service import SkillPackageService
from services.tier_enforcement_service import TierEnforcementService
from utils.logger import get_logger
from utils.safe_zip import SafeZipError, find_plugin_root, iter_safe_zip
from utils.skill_frontmatter import SkillFrontmatterError, parse_skill_md
from utils.skill_paths import normalize_path

logger = get_logger(__name__)

_SKILLS_PREFIX_LEN = len("skills/")

# Distinct, stable per-skill failure/skip reasons (routers/tests can match on these).
REASON_MISSING_SKILL_MD = "missing SKILL.md"
REASON_DUPLICATE_NAME = "duplicate name"
REASON_UNEXPECTED_ERROR = "unexpected error"
REASON_LOCK_BUSY = "busy, try again"

# PostgreSQL SQLSTATE for "lock_not_available" (a lock_timeout expiry), used to detect a contended
# per-app advisory lock. ``SkillRepository.lock_app_skills(..., timeout_seconds=...)`` bounds how long
# one candidate's duplicate-name/quota check waits for it before giving up — see the module-level
# docstring and ``import_plugin`` for why a SINGLE timeout is enforced across the whole archive rather
# than being re-armed per candidate.
_LOCK_TIMEOUT_SQLSTATE = "55P03"


@dataclass(frozen=True)
class ClaudePluginSkillResult:
    """Outcome of importing one candidate skill directory from a Claude plugin archive."""

    name: str
    status: ClaudePluginSkillStatus
    reason: Optional[str] = None
    skill_id: Optional[int] = None
    bootstrap_script_path: Optional[str] = None
    runtime: Optional[str] = None
    has_bootstrap: bool = False


@dataclass(frozen=True)
class ClaudePluginImportResult:
    """Full outcome of one plugin import: the service builds this, the router only wraps it in its schema."""

    skills: List[ClaudePluginSkillResult] = field(default_factory=list)

    @property
    def imported_count(self) -> int:
        return sum(1 for r in self.skills if r.status == "imported")

    @property
    def skipped_count(self) -> int:
        return sum(1 for r in self.skills if r.status == "skipped")

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.skills if r.status == "failed")


def _strip_skills_prefix(path: str) -> Optional[str]:
    """Return ``path`` with a leading case-insensitive ``skills/`` stripped, or ``None`` if absent."""
    if path[:_SKILLS_PREFIX_LEN].lower() != "skills/":
        return None
    return path[_SKILLS_PREFIX_LEN:]


def _group_skill_candidates(entries: Dict[str, bytes], plugin_root: str) -> Dict[str, Dict[str, bytes]]:
    """Group already-safety-validated archive entries by their top-level ``skills/<name>/`` directory.

    Args:
        entries: ``{normalised_path: content}`` for every file in the archive (as yielded by
            ``iter_safe_zip``), not scoped to any particular skill.
        plugin_root: The wrapping directory to strip first (``find_plugin_root``'s result); ``''`` when
            entries already sit directly under ``skills/`` at the archive root.

    Returns:
        ``{skill_dir_name: {package_relative_path: content}}``, one entry per top-level directory
        found directly under ``skills/`` (case-insensitive: ``skills/`` and ``Skills/`` are the same
        directory). Grouping keys fold case (first-seen casing wins as the reported label) so that,
        e.g., ``skills/Foo/SKILL.md`` and ``skills/foo/helper.sh`` are correctly treated as the SAME
        candidate instead of silently dropping ``helper.sh`` into a second, orphaned group. Archive
        entries outside ``skills/``, or directly under it with no further subdirectory, are ignored —
        they are not Claude Code plugin skills (agents, commands, hooks, manifests, ...).
    """
    candidates: Dict[str, Dict[str, bytes]] = {}
    labels: Dict[str, str] = {}
    for path, content in entries.items():
        if plugin_root:
            prefix = f"{plugin_root}/"
            if not path.startswith(prefix):
                continue
            rel = path[len(prefix):]
        else:
            rel = path
        rest = _strip_skills_prefix(rel)
        if rest is None or "/" not in rest:
            continue  # not under skills/, or a stray file directly under skills/ (not a skill directory)
        skill_dir, rel_path = rest.split("/", 1)
        if not skill_dir or not rel_path:
            continue
        key = skill_dir.lower()
        labels.setdefault(key, skill_dir)
        candidates.setdefault(key, {})[rel_path] = content
    return {labels[key]: files for key, files in candidates.items()}


def _extract_skill_md(files: Dict[str, bytes]) -> Optional[bytes]:
    """Pop and return the candidate's root ``SKILL.md`` bytes (case-insensitive), or ``None`` if absent."""
    for path in list(files):
        if "/" not in path and path.lower() == "skill.md":
            return files.pop(path)
    return None


def _rescope_files(files: Dict[str, bytes]) -> Dict[str, bytes]:
    """Re-normalise each non-SKILL.md path relative to a single candidate's own root.

    ``iter_safe_zip`` only validated paths relative to the WHOLE archive, not re-scoped per candidate.
    Built as an explicit loop (not a dict comprehension) so a normalisation collision between two
    distinct raw paths (e.g. an NFKC or backslash difference) is caught and reported, rather than one
    file silently overwriting the other.

    Raises:
        ValueError: An invalid path, or a normalisation collision between two distinct entries.
    """
    result: Dict[str, bytes] = {}
    for raw_path, content in files.items():
        normalized = normalize_path(raw_path)
        if normalized in result:
            raise ValueError(f"duplicate package file path after normalisation: {normalized!r}")
        result[normalized] = content
    return result


def _is_lock_timeout(exc: DBAPIError) -> bool:
    """True if ``exc`` wraps a PG lock_timeout expiry (SQLSTATE 55P03).

    Checks both ``pgcode`` (psycopg2, the sync driver currently used here) and ``sqlstate`` (psycopg3,
    already used elsewhere in this repo for the async engine) so this keeps working unchanged if the
    sync driver is ever swapped — instead of silently degrading every such failure from a clear
    ``busy, try again`` to an opaque ``unexpected error``.
    """
    orig = getattr(exc, "orig", None)
    code = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
    return code == _LOCK_TIMEOUT_SQLSTATE


def _safe_rollback(db: Session, *, skill_dir: str, app_id: int) -> None:
    """Roll back ``db``, never letting a rollback failure itself propagate.

    Each per-candidate error handler needs to roll back before reporting a ``failed`` result; if the
    connection is already dead, ``db.rollback()`` can itself raise — which must not abort the whole
    plugin import and lose the results already collected for earlier, already-committed candidates.
    """
    try:
        db.rollback()
    except Exception:
        logger.warning(
            "claude_plugin_import_service: rollback failed while handling skill directory %r (app %s)",
            skill_dir, app_id, exc_info=True,
        )


class ClaudePluginImportService:
    """Imports the skills of a Claude Code plugin ZIP into one app, one skill at a time."""

    @staticmethod
    def import_plugin(db: Session, *, app_id: int, data: bytes) -> ClaudePluginImportResult:
        """Import every ``skills/<name>/SKILL.md`` candidate of a plugin archive into ``app_id``.

        Synchronous and CPU-bound (zip parsing): routers must call it through a threadpool, exactly like
        ``SkillPackageService.import_package``. Holds the same process-wide import/export bulkhead
        (``SkillPackageService.io_slot``) for the whole call — a multi-skill plugin archive can hold as
        much data in memory as (or more than) a single skill package.

        Each candidate skill is persisted in its OWN transaction (its own duplicate-name/quota check,
        its own ``db.commit()`` on success or ``db.rollback()`` on failure) rather than one transaction
        for the whole plugin: a later skill failing must never undo an earlier skill already committed,
        and an earlier skill's row must be visible to the duplicate-name check of a later skill in the
        same plugin (so two same-named directories in one plugin are correctly reported as a conflict on
        the second one, not silently double-inserted).

        Args:
            db: Database session.
            app_id: Target app.
            data: Raw ZIP bytes of the plugin archive.

        Returns:
            A ``ClaudePluginImportResult`` (one ``ClaudePluginSkillResult`` per candidate skill
            directory found under ``skills/``, in a stable order, plus derived counts).

        Raises:
            SkillImportError: The archive itself is unreadable, violates the shared safe-zip limits,
                contains no ``skills/<name>/SKILL.md`` candidates at all, or exceeds
                ``SKILL_IMPORT_MAX_PLUGIN_SKILLS`` candidates (400, before any per-skill DB work).
        """
        with SkillPackageService.io_slot():
            try:
                entries = dict(iter_safe_zip(data, require_skill_md=False))
            except SafeZipError as exc:
                raise SkillImportError(f"Invalid Claude plugin package: {exc}") from None

            plugin_root = find_plugin_root(list(entries))
            candidates = _group_skill_candidates(entries, plugin_root)
            if not candidates:
                raise SkillImportError("Claude plugin package contains no skills/<name>/SKILL.md entries")
            if len(candidates) > settings.SKILL_IMPORT_MAX_PLUGIN_SKILLS:
                raise SkillImportError(
                    f"Claude plugin package contains {len(candidates)} skills, exceeding the "
                    f"{settings.SKILL_IMPORT_MAX_PLUGIN_SKILLS}-skill limit per import"
                )

            results: List[ClaudePluginSkillResult] = []
            lock_busy = False
            for skill_dir in sorted(candidates):
                if lock_busy:
                    # Fail fast (see module docstring): once one candidate has exhausted the lock
                    # timeout, every remaining candidate is reported busy WITHOUT re-attempting the
                    # lock, so worst-case lock-contention cost for the whole archive stays bounded to
                    # a single timeout window instead of growing with candidate count.
                    results.append(
                        ClaudePluginSkillResult(name=skill_dir, status="failed", reason=REASON_LOCK_BUSY)
                    )
                    continue
                result = ClaudePluginImportService._import_one_skill(db, app_id, skill_dir, candidates[skill_dir])
                results.append(result)
                if result.status == "failed" and result.reason == REASON_LOCK_BUSY:
                    lock_busy = True
            return ClaudePluginImportResult(skills=results)

    @staticmethod
    def _import_one_skill(
        db: Session, app_id: int, skill_dir: str, files: Dict[str, bytes],
    ) -> ClaudePluginSkillResult:
        """Import exactly one candidate skill directory. Never raises: every failure mode is reported."""
        files = dict(files)  # local copy: _extract_skill_md mutates it
        skill_md_bytes = _extract_skill_md(files)
        if skill_md_bytes is None:
            return ClaudePluginSkillResult(name=skill_dir, status="failed", reason=REASON_MISSING_SKILL_MD)

        try:
            skill_md_text = skill_md_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return ClaudePluginSkillResult(
                name=skill_dir, status="failed", reason="SKILL.md is not valid UTF-8 text",
            )

        try:
            parsed = parse_skill_md(skill_md_text)
        except SkillFrontmatterError as exc:
            return ClaudePluginSkillResult(name=skill_dir, status="failed", reason=f"invalid SKILL.md: {exc}")

        try:
            skill_files = _rescope_files(files)
        except ValueError as exc:
            return ClaudePluginSkillResult(
                name=parsed.name, status="failed", reason=f"invalid package file path: {exc}",
            )

        # Same ordering contract as SkillPackageService._import_locked: validate the structurally-pure,
        # DB-free parts of the candidate BEFORE any lock/duplicate-name/quota round-trip, so a
        # structurally invalid candidate is reported as its own defect rather than being pre-empted by
        # whichever DB check happens to run first (e.g. mis-reported as "duplicate name").
        try:
            SkillPackageService.validate_parsed_package(parsed, skill_files)
        except SkillImportError as exc:
            return ClaudePluginSkillResult(name=parsed.name, status="failed", reason=exc.detail)

        bootstrap = parsed.bootstrap_script_path or None
        runtime = parsed.runtime or None

        try:
            SkillRepository.lock_app_skills(
                db, app_id, timeout_seconds=settings.SKILL_IMPORT_LOCK_TIMEOUT_SECONDS,
            )
            existing = SkillRepository.get_by_name_and_app_id(db, parsed.name, app_id)
            if existing is not None:
                _safe_rollback(db, skill_dir=skill_dir, app_id=app_id)  # releases the advisory lock
                return ClaudePluginSkillResult(
                    name=parsed.name, status="skipped", reason=REASON_DUPLICATE_NAME,
                    bootstrap_script_path=bootstrap, runtime=runtime, has_bootstrap=bootstrap is not None,
                )

            TierEnforcementService.check_resource_limit(db, app_id, "skills")

            skill = SkillPackageService.create_skill_from_parsed(
                db, app_id=app_id, parsed=parsed, files=skill_files, source="admin",
            )
            skill.is_enabled = False  # admin reviews + explicitly enables each imported plugin skill
            db.flush()
            # Capture BEFORE commit — flush() already populated these; no db.refresh() needed (and no
            # DB round-trip must happen after commit that could turn an already-durable success into a
            # reported failure if it were to raise).
            skill_id, name = skill.skill_id, skill.name
            db.commit()
            return ClaudePluginSkillResult(
                name=name, status="imported", skill_id=skill_id,
                bootstrap_script_path=bootstrap, runtime=runtime, has_bootstrap=bootstrap is not None,
            )
        except DBAPIError as exc:
            is_lock_timeout = _is_lock_timeout(exc)
            _safe_rollback(db, skill_dir=skill_dir, app_id=app_id)
            if is_lock_timeout:
                return ClaudePluginSkillResult(name=parsed.name, status="failed", reason=REASON_LOCK_BUSY)
            logger.error(
                "claude_plugin_import_service: DB error importing skill directory %r (app %s)",
                skill_dir, app_id, exc_info=True,
            )
            return ClaudePluginSkillResult(name=parsed.name, status="failed", reason=REASON_UNEXPECTED_ERROR)
        except HTTPException as exc:
            _safe_rollback(db, skill_dir=skill_dir, app_id=app_id)
            return ClaudePluginSkillResult(name=parsed.name, status="failed", reason=str(exc.detail))
        except SkillServiceError as exc:
            _safe_rollback(db, skill_dir=skill_dir, app_id=app_id)
            return ClaudePluginSkillResult(name=parsed.name, status="failed", reason=exc.detail)
        except Exception:
            # Bulkhead: one bad candidate must never abort the rest of the plugin's skills. Never log
            # file contents (NFR-7) — only the candidate's directory/parsed name.
            _safe_rollback(db, skill_dir=skill_dir, app_id=app_id)
            logger.error(
                "claude_plugin_import_service: unexpected error importing skill directory %r (app %s)",
                skill_dir, app_id, exc_info=True,
            )
            return ClaudePluginSkillResult(name=parsed.name, status="failed", reason=REASON_UNEXPECTED_ERROR)
