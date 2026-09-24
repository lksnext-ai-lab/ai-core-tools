import contextlib
import io
import mimetypes
import threading
import zipfile
from datetime import datetime
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, Union

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import config as settings
from models.skill import Skill, SkillFile
from repositories.skill_package_repository import SkillPackageRepository
from repositories.skill_repository import SkillRepository
from schemas.skill_package_payload import SkillPackagePayload
from schemas.skill_schemas import SkillDetailSchema
from services.skill_errors import (
    SkillBusyError, SkillConflictError, SkillImportError, SkillPersistenceError, SkillValidationError,
)
from services.skill_service import SkillService
from utils.logger import get_logger
from utils.safe_zip import SafeZipError, read_safe_zip
from utils.skill_frontmatter import (
    DECLARED_FIELDS, SkillFrontmatterError, normalize_skill_name, parse_skill_md, render_skill_md
)
from utils.skill_json import dump_json, load_json

logger = get_logger(__name__)

_VALID_SOURCES = ('admin', 'yaml')
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
_SYSTEM_NAME_CONSTRAINT = 'uq_skill_system_name'

# Bulkhead: imports hold the whole archive plus its decompressed files in memory.
_IMPORT_SEMAPHORE = threading.BoundedSemaphore(settings.SKILL_IMPORT_MAX_CONCURRENCY)

# Separate admission gate, sized the same as _IMPORT_SEMAPHORE. Routers must hold this slot while
# streaming the upload into memory (before any bytes are buffered), not just while import_package()
# runs — read_upload_bounded() happens first and is what actually allocates the up-to-25MB buffer.
# A second semaphore (rather than reusing _IMPORT_SEMAPHORE) avoids one request needing two permits
# from the same pool (router-level admission + import_package()'s own acquire), which would let two
# concurrent requests exhaust a 2-permit semaphore on the outer hold alone and reject themselves.
_UPLOAD_ADMISSION_SEMAPHORE = threading.BoundedSemaphore(settings.SKILL_IMPORT_MAX_CONCURRENCY)


def _limit(column: str) -> int:
    """Length limit of a Skill string column, derived from the model."""
    return Skill.__table__.c[column].type.length


def _is_declared(key: str) -> bool:
    return key.replace('-', '_') in DECLARED_FIELDS


def _file_bytes(f: SkillFile) -> bytes:
    """Content of a SkillFile row as bytes (text rows encoded UTF-8, binary verbatim)."""
    if f.content_text is not None:
        return f.content_text.encode('utf-8')
    return bytes(f.content_bytes or b'')


def _constraint_name(exc: IntegrityError) -> Optional[str]:
    diag = getattr(getattr(exc, 'orig', None), 'diag', None)
    return getattr(diag, 'constraint_name', None)


class SkillPackageService:
    """Import, export and payload building for skill packages (ZIP with SKILL.md + resource files)."""

    # ==================== IMPORT ====================

    @staticmethod
    def import_package(
        db: Session,
        *,
        app_id: Optional[int],
        data: bytes,
        source: Literal['admin', 'yaml'] = 'admin',
    ) -> SkillDetailSchema:
        """Import a skill package atomically.

        Synchronous and CPU-bound (zip parsing): routers must call it through a threadpool. Either the Skill and
        all its files are persisted in one commit, or nothing is (the session is rolled back). App-scoped imports
        take a per-app advisory lock before the duplicate-name and quota checks so concurrent imports cannot
        bypass either.

        Args:
            db: Database session.
            app_id: Target app, or None for a system skill (system skills are not quota'd).
            data: Raw ZIP bytes.
            source: 'admin' or 'yaml'.

        Raises:
            SkillImportError: Invalid package (400).
            SkillConflictError: Duplicate name in the target scope (409).
            SkillBusyError: Too many concurrent imports (429).
            SkillPersistenceError: Unexpected constraint failure (500).
            HTTPException: 403 from the tier quota check (app scope only).
        """
        if source not in _VALID_SOURCES:
            raise ValueError(f"Unsupported skill source: {source!r}")
        SkillPackageService._acquire_io_slot()
        try:
            return SkillPackageService._import_locked(db, app_id, data, source)
        finally:
            _IMPORT_SEMAPHORE.release()

    @staticmethod
    def _import_locked(db: Session, app_id: Optional[int], data: bytes, source: str) -> SkillDetailSchema:
        # ---- Pure validation (no DB access) ----
        try:
            package = read_safe_zip(data)
        except SafeZipError as exc:
            raise SkillImportError(f"Invalid skill package: {exc}") from None
        try:
            skill_md_text = package.skill_md.decode('utf-8')
        except UnicodeDecodeError:
            raise SkillImportError("Invalid SKILL.md: must be UTF-8 text") from None
        try:
            parsed = parse_skill_md(skill_md_text)
        except SkillFrontmatterError as exc:
            raise SkillImportError(f"Invalid SKILL.md: {exc}") from None
        # Validate BEFORE entering the transaction/lock below — a structurally invalid package
        # (length limits, unresolvable bootstrap path) must fail fast with 400, not get relabelled
        # as a 409/403 by whichever DB check happens to run first. Pure/idempotent, so
        # create_skill_from_parsed's own call to the same validator below is free.
        SkillPackageService.validate_parsed_package(parsed, package.files)

        # ---- Persistence: one transaction ----
        try:
            if app_id is not None:
                # Serialise per app BEFORE the duplicate-name and quota checks (closes the check-then-act race).
                SkillRepository.lock_app_skills(db, app_id)
                existing = SkillRepository.get_by_name_and_app_id(db, parsed.name, app_id)
            else:
                existing = SkillRepository.get_system_skill_by_name(db, parsed.name)
            if existing is not None:
                scope = "system" if app_id is None else "this app"
                raise SkillConflictError(f"A skill named {parsed.name!r} already exists in {scope}")

            if app_id is not None:
                from services.tier_enforcement_service import TierEnforcementService
                TierEnforcementService.check_resource_limit(db, app_id, 'skills')

            skill = SkillPackageService.create_skill_from_parsed(
                db, app_id=app_id, parsed=parsed, files=package.files, source=source,
            )

            db.commit()
            db.refresh(skill)
            return SkillService.build_detail(db, skill)
        except IntegrityError as exc:
            # Safety net: create_skill_from_parsed already maps IntegrityError to a typed error, so this
            # branch should be unreachable in practice — kept in case a future DB write is added here
            # outside the shared seam.
            db.rollback()
            constraint = _constraint_name(exc)
            if constraint == _SYSTEM_NAME_CONSTRAINT:
                raise SkillConflictError(
                    f"A skill named {parsed.name!r} already exists in system"
                ) from None
            logger.error("Skill import failed on constraint %r", constraint)
            raise SkillPersistenceError("Skill package could not be saved") from None
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def validate_parsed_package(parsed: Any, files: Dict[str, bytes]) -> Optional[str]:
        """Pure (no DB access) validation of an already-parsed SKILL.md against its package files.

        Returns the resolved ``bootstrap_script_path`` (or ``None``). Raises ``SkillImportError``
        for a length-limit violation or an unresolvable bootstrap path.

        Callers should run this BEFORE entering any transaction/advisory-lock/quota-check, so a
        structurally invalid package fails fast with its own error rather than being pre-empted by
        an unrelated DB-level check (e.g. a duplicate-name 409 or a quota 403) that happens to run
        first. It is pure and idempotent, so ``create_skill_from_parsed`` calling it again internally
        is free — do not skip the upfront call just because the seam also performs it.
        """
        SkillPackageService._check_lengths(parsed)
        return SkillPackageService._resolve_bootstrap(parsed.bootstrap_script_path, files)

    @staticmethod
    def create_skill_from_parsed(
        db: Session,
        *,
        app_id: Optional[int],
        parsed: Any,
        files: Dict[str, bytes],
        source: str,
    ) -> Skill:
        """Build and persist (flush only, never commit/rollback) a ``Skill`` + its files from an
        already-parsed SKILL.md.

        Transaction-agnostic seam shared by ``_import_locked`` (app/admin imports, commit-based flow)
        and ``system_skills_seeder._create_skill_from_package`` (create-if-missing, ``db.begin_nested()``
        SAVEPOINT flow): this method only calls ``db.flush()`` (via ``SkillRepository.persist`` /
        ``SkillPackageRepository.replace_files``) — it never commits or rolls back, so either caller's
        own transaction-boundary handling stays correct.

        The caller must already have performed any duplicate-name / quota / advisory-lock checks
        appropriate to its own scope (app-scoped vs system) before calling this.

        Args:
            db: Session positioned inside the caller's own transaction (or SAVEPOINT).
            app_id: Target app, or ``None`` for a system skill.
            parsed: Already-parsed SKILL.md (``utils.skill_frontmatter.parse_skill_md`` result).
            files: ``{normalised_path: content_bytes}`` — SKILL.md itself excluded (stored in
                ``Skill.content``, not as a ``SkillFile``).
            source: ``'admin'`` or ``'yaml'`` — validated against ``_VALID_SOURCES``.

        Returns:
            The persisted (flushed, not committed) ``Skill``.

        Raises:
            SkillImportError: Invalid frontmatter-derived values (length limits, unresolvable
                bootstrap path, unsupported ``source``, or an invalid package file).
            SkillConflictError: A DB-level unique-name collision (``uq_skill_system_name``).
            SkillPersistenceError: Any other DB constraint failure at flush time.
        """
        if source not in _VALID_SOURCES:
            raise SkillImportError(f"Unsupported skill source: {source!r}")

        bootstrap = SkillPackageService.validate_parsed_package(parsed, files)

        frontmatter: Dict[str, Any] = dict(parsed.extra)
        if parsed.when_to_use:
            frontmatter['when_to_use'] = parsed.when_to_use
        if parsed.disable_model_invocation:
            frontmatter['disable_model_invocation'] = True

        skill = Skill()
        skill.app_id = app_id
        skill.name = parsed.name
        skill.display_name = parsed.display_name
        skill.description = parsed.description
        skill.content = parsed.body
        skill.frontmatter = dump_json(frontmatter) if frontmatter else None
        skill.allowed_tools = dump_json(parsed.allowed_tools) if parsed.allowed_tools else None
        skill.runtime = parsed.runtime
        skill.bootstrap_script_path = bootstrap
        skill.runtime_options = dump_json(parsed.runtime_options) if parsed.runtime_options else None
        skill.source = source
        skill.is_enabled = True
        skill.create_date = datetime.now()

        try:
            SkillRepository.persist(db, skill)
            SkillPackageRepository.replace_files(
                db,
                skill.skill_id,
                [(path, content, mimetypes.guess_type(path)[0]) for path, content in files.items()],
            )
        except IntegrityError as exc:
            constraint = _constraint_name(exc)
            if constraint == _SYSTEM_NAME_CONSTRAINT:
                raise SkillConflictError(
                    f"A skill named {parsed.name!r} already exists in system"
                ) from None
            logger.error("Skill persistence failed on constraint %r", constraint)
            raise SkillPersistenceError("Skill package could not be saved") from None
        except ValueError as exc:
            raise SkillImportError(f"Invalid package file: {exc}") from None
        return skill

    @staticmethod
    def _check_lengths(parsed: Any) -> None:
        """Reject values that would overflow their columns (would otherwise surface as a DB error)."""
        for label, value in (
            ('description', parsed.description),
            ('display_name', parsed.display_name),
            ('runtime', parsed.runtime),
            ('bootstrap_script_path', parsed.bootstrap_script_path),
        ):
            limit = _limit(label)
            if value is not None and len(value) > limit:
                raise SkillImportError(f"Invalid SKILL.md: {label} must be at most {limit} characters")

    @staticmethod
    def _resolve_bootstrap(path: Optional[str], files: Dict[str, bytes]) -> Optional[str]:
        """Return the normalised bootstrap path, requiring it to be an actual package entry."""
        if not path:
            return None
        try:
            normalized = SkillPackageRepository.normalize_path(path)
        except ValueError:
            raise SkillImportError(
                f"Invalid SKILL.md: bootstrap_script_path {path[:200]!r} is not a valid package path"
            ) from None
        if normalized not in files:
            raise SkillImportError(
                f"Invalid SKILL.md: bootstrap_script_path {path[:200]!r} does not match a file in the package"
            )
        return normalized

    # ==================== EXPORT ====================

    @staticmethod
    def _render_skill_md(skill: Skill) -> str:
        """Render SKILL.md from the Skill columns and the frontmatter JSON blob."""
        fm = load_json(skill.frontmatter, {}, skill.skill_id, 'frontmatter')
        extra = {k: v for k, v in fm.items() if not _is_declared(k)}
        when_to_use = fm.get('when_to_use')
        try:
            return render_skill_md(
                name=skill.name,
                display_name=skill.display_name or None,
                description=skill.description or None,
                when_to_use=when_to_use if isinstance(when_to_use, str) and when_to_use else None,
                disable_model_invocation=fm.get('disable_model_invocation') is True,
                allowed_tools=load_json(skill.allowed_tools, [], skill.skill_id, 'allowed_tools'),
                runtime=skill.runtime or None,
                bootstrap_script_path=skill.bootstrap_script_path or None,
                runtime_options=load_json(skill.runtime_options, {}, skill.skill_id, 'runtime_options'),
                extra=extra,
                body=skill.content or '',
            )
        except SkillFrontmatterError as exc:
            raise SkillValidationError(f"Skill cannot be exported: {exc}") from None

    @staticmethod
    def export_package(db: Session, skill: Skill) -> Tuple[str, bytes]:
        """Build the skill's ZIP in memory.

        The caller must already have resolved AND authorised the skill (app scope / enabled system skill);
        use ``export_for_app`` or ``export_system_skill`` from routers.

        Returns:
            ``(filename, zip_bytes)`` where filename is ``<slug>.zip``.

        Raises:
            SkillValidationError: If the stored skill cannot be rendered as a valid SKILL.md.
        """
        skill_md = SkillPackageService._render_skill_md(skill)  # also validates the name
        files = SkillPackageRepository.list_files(db, skill.skill_id)

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            SkillPackageService._write_entry(zf, 'SKILL.md', skill_md.encode('utf-8'))
            for f in files:
                SkillPackageService._write_entry(zf, f.path, _file_bytes(f))

        # normalize_skill_name output is already restricted to [a-z0-9._-]
        return f"{normalize_skill_name(skill.name)}.zip", buffer.getvalue()

    @staticmethod
    @contextlib.contextmanager
    def upload_admission_slot():
        """Bound concurrent buffered uploads: hold this while reading an upload into memory.

        Routers must wrap ``read_upload_bounded(...)`` (and the subsequent ``import_package`` call)
        in this context manager, so an over-limit request is rejected with SkillBusyError (429)
        *before* the archive is streamed into the process heap, not only once ``import_package``
        itself tries to acquire its own (separate) bulkhead slot.
        """
        if not _UPLOAD_ADMISSION_SEMAPHORE.acquire(blocking=False):
            raise SkillBusyError("Too many skill imports in progress; retry shortly")
        try:
            yield
        finally:
            _UPLOAD_ADMISSION_SEMAPHORE.release()

    @staticmethod
    def _acquire_io_slot() -> None:
        """Acquire a slot in the shared import/export bulkhead, or raise SkillBusyError (429).

        Export shares the import bulkhead: both hold a whole skill's files in memory at once, and there is no
        reason to size them independently for a first cut.
        """
        if not _IMPORT_SEMAPHORE.acquire(blocking=False):
            raise SkillBusyError("Too many skill package operations in progress; retry shortly")

    @staticmethod
    def export_for_app(db: Session, app_id: int, skill_id: int) -> Optional[Tuple[str, bytes]]:
        """Export an own-app skill or an ENABLED system skill (same visibility as get_skill_detail).

        Returns None when the skill is not visible to the app.

        Raises:
            SkillBusyError: Too many concurrent package operations (429).
        """
        skill = SkillRepository.get_by_id_and_app_id(db, skill_id, app_id)
        if skill is None:
            skill = SkillRepository.get_system_skill_by_id(db, skill_id, enabled_only=True)
        if skill is None:
            return None
        SkillPackageService._acquire_io_slot()
        try:
            return SkillPackageService.export_package(db, skill)
        finally:
            _IMPORT_SEMAPHORE.release()

    @staticmethod
    def export_system_skill(db: Session, skill_id: int) -> Optional[Tuple[str, bytes]]:
        """Export a system skill in any enabled state (admin). None if missing or app-scoped.

        Raises:
            SkillBusyError: Too many concurrent package operations (429).
        """
        skill = SkillRepository.get_system_skill_by_id(db, skill_id)
        if skill is None:
            return None
        SkillPackageService._acquire_io_slot()
        try:
            return SkillPackageService.export_package(db, skill)
        finally:
            _IMPORT_SEMAPHORE.release()

    @staticmethod
    def _write_entry(zf: zipfile.ZipFile, path: str, content: bytes) -> None:
        info = zipfile.ZipInfo(path, date_time=_ZIP_EPOCH)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        zf.writestr(info, content)

    # ==================== PAYLOAD ====================

    @staticmethod
    def build_payload(db: Session, skill: Skill) -> SkillPackagePayload:
        """Build the detached payload consumed by sandbox providers (no ORM objects).

        The caller must already have resolved AND authorised the skill (and checked it is enabled).
        """
        try:
            name = normalize_skill_name(skill.name)
        except SkillFrontmatterError as exc:
            raise SkillValidationError(f"Skill name is not a valid package name: {exc}") from None
        files = tuple((f.path, _file_bytes(f)) for f in SkillPackageRepository.list_files(db, skill.skill_id))
        return SkillPackagePayload(
            skill_id=skill.skill_id,
            name=name,
            display_name=skill.display_name or None,
            files=files,
            bootstrap_script_path=skill.bootstrap_script_path or None,
            runtime=skill.runtime or None,
            runtime_options=load_json(skill.runtime_options, {}, skill.skill_id, 'runtime_options'),
        )


# ==================== TOOL PROVIDER FACTORY (step_019, AD-7) ====================
#
# ``backend/tools/skill_tools.py`` must never import a service/repository/DB session
# directly (tools/** stays DB-free). Callers building the ``load_skill`` /
# ``read_skill_file`` tools (agent execution / agentTools.py) instead ask this module
# for a small set of closures, and pass those in.
#
# Each closure opens (and closes) its own short-lived ``SessionLocal()`` per call rather
# than closing over one ``Session`` passed in at construction time: the returned tools can
# be invoked much later in the same conversation turn (across several LLM tool-call round
# trips), well after any request-scoped session used to build the agent would have been
# closed — the same reason ``get_retriever_tool``/``_build_temp_retrievers`` in
# ``tools/agentTools.py`` never hold a ``Session`` open across a tool's lifetime either.
SkillPathRow = Tuple[str, Optional[str], int, str, bool]


def build_skill_tool_providers() -> Tuple[
    Callable[[int], SkillPackagePayload],
    Callable[[int], List[SkillPathRow]],
    Callable[[int, str], Optional[Tuple[bool, Union[str, bytes]]]],
]:
    """Build the DB-bound callables ``tools/skill_tools.py`` needs, without it importing
    ``SkillPackageService``/``SkillPackageRepository``/``db.database`` itself.

    Returns ``(payload_provider, list_paths_provider, file_content_provider)``:
      - ``payload_provider(skill_id) -> SkillPackagePayload``: same contract as
        ``SkillPackageService.build_payload`` — caller must have already resolved+authorised
        the skill (and confirmed it is enabled) before invoking the returned tool.
      - ``list_paths_provider(skill_id) -> [(path, media_type, size_bytes, checksum, is_text), ...]``:
        never loads file blobs (``SkillPackageRepository.list_paths``); used to validate a
        requested path and to report available paths without pulling binary content.
      - ``file_content_provider(skill_id, path) -> (is_text, content) | None``: loads exactly one
        already-validated, already-normalised file's content (``path`` must be a value returned
        by ``list_paths_provider`` for the *same* skill — this function does not re-validate or
        re-scope it). Returns ``None`` if the row no longer exists (rare import/delete race).

    All three are keyed by ``skill_id`` (a plain int), never a live ``Skill`` ORM instance
    (H1, round-2 fix): a ``Skill`` loaded by a request-scoped caller session is neither
    guaranteed-valid nor thread-safe by the time these closures actually run — LangChain's
    tool executor can invoke them from a worker thread, well after that session could be
    expired or closed, and a lazy attribute read on it there can corrupt the session or
    raise ``DetachedInstanceError``/``InvalidRequestError`` uncaught. Each closure instead
    opens its own fresh session and re-fetches the ``Skill``/``SkillFile`` rows it needs by
    id — it never re-authorises the id (the caller already resolved+authorised the skill for
    this agent before capturing its id into a snapshot; see ``tools.skill_tools.SkillSnapshot``).
    """
    from db.database import SessionLocal

    def payload_provider(skill_id: int) -> SkillPackagePayload:
        with SessionLocal() as db:
            # get_by_id_unscoped's docstring restricts it to omniadmin-guarded routes —
            # safe here too because no fresh authorisation decision is being made from
            # this id: it was already resolved+authorised for this agent/app earlier in
            # the same turn (resolve_agent_skills), before being captured into the
            # SkillSnapshot the tool closure holds. This call only re-fetches the same
            # already-authorised skill's current row in a fresh session (H1).
            skill = SkillRepository.get_by_id_unscoped(db, skill_id)
            if skill is None:
                raise SkillValidationError(f"Skill {skill_id} no longer exists")
            return SkillPackageService.build_payload(db, skill)

    def list_paths_provider(skill_id: int) -> List[SkillPathRow]:
        with SessionLocal() as db:
            return SkillPackageRepository.list_paths(db, skill_id)

    def file_content_provider(skill_id: int, path: str) -> Optional[Tuple[bool, Union[str, bytes]]]:
        with SessionLocal() as db:
            skill_file = SkillPackageRepository.get_file(db, skill_id, path)
            if skill_file is None:
                return None
            if skill_file.content_text is not None:
                return True, skill_file.content_text
            return False, bytes(skill_file.content_bytes or b'')

    return payload_provider, list_paths_provider, file_content_provider
