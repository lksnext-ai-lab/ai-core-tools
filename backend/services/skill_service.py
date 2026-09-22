"""Skill service: app-scoped CRUD, merged listing with system skills, admin operations.

FR-15/AC-12 app-private scoping contract — the following three call sites intentionally filter
`Skill.app_id == app_id` (never merged with system skills, where `app_id IS NULL`) and must stay
that way:
  - `backend/services/tier_enforcement_service.py` (`check_resource_limit`, "skills" entry of
    `model_map`) — per-app skill quota counting excludes system skills.
  - `backend/services/freeze_service.py` (`apply_freeze` and `recalculate_on_delete`) — freezing
    excess skills on a tier downgrade only ever touches an app's own skills.
  - `backend/repositories/app_repository.py` (`get_skills_by_app_id`, used by
    `AppService.delete_app()` for cascade deletion) — deleting an app must never delete
    platform-owned system skills.

None of these three should ever be switched to the merged accessor
(`SkillRepository.get_selectable_for_app` / `AgentRepository.get_selectable_skills_for_app`), which
is reserved for read-time "what can this app see" listings (agent skill pickers, prompt building).
"""
import json
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.skill import Skill
from repositories.skill_package_repository import SkillPackageRepository
from repositories.skill_repository import SkillRepository, fold_name
from schemas.skill_schemas import (
    CreateUpdateSkillSchema, SkillDetailSchema, SkillFileInfoSchema, SkillListItemSchema
)
from services.skill_errors import (  # noqa: F401 - re-exported for routers
    SkillBusyError, SkillConflictError, SkillForbiddenError, SkillImportError, SkillPersistenceError,
    SkillValidationError,
)
from utils.logger import get_logger
from utils.skill_frontmatter import SkillFrontmatterError, normalize_skill_name, render_skill_md
from utils.skill_json import dump_json, load_json

logger = get_logger(__name__)

SYSTEM_SKILL_FORBIDDEN_MSG = "System skills are managed by platform administrators"
YAML_SKILL_DELETE_MSG = (
    "This skill is seeded from system_defaults.yaml and would be recreated on the next startup — "
    "disable it instead."
)


class SkillService:
    """Business logic for skills (app-scoped CRUD, merged listing with system skills, admin operations)."""

    # ==================== MAPPERS ====================

    @staticmethod
    def _to_list_item(skill: Skill, file_count: int = 0) -> SkillListItemSchema:
        """Convert a Skill ORM instance to a list item schema."""
        return SkillListItemSchema(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description or "",
            created_at=skill.create_date,
            is_frozen=bool(skill.is_frozen),
            display_name=skill.display_name,
            is_system=skill.is_system,
            is_enabled=True if skill.is_enabled is None else bool(skill.is_enabled),
            source=skill.source or 'admin',
            file_count=file_count,
        )

    @staticmethod
    def _to_detail(skill: Skill, files: List[SkillFileInfoSchema]) -> SkillDetailSchema:
        """Convert a Skill ORM instance plus its file metadata to a detail schema (pure mapper, no DB)."""
        return SkillDetailSchema(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description or "",
            content=skill.content or "",
            created_at=skill.create_date,
            is_frozen=bool(skill.is_frozen),
            display_name=skill.display_name,
            is_system=skill.is_system,
            is_enabled=True if skill.is_enabled is None else bool(skill.is_enabled),
            source=skill.source or 'admin',
            frontmatter=load_json(skill.frontmatter, {}, skill.skill_id, 'frontmatter'),
            allowed_tools=load_json(skill.allowed_tools, [], skill.skill_id, 'allowed_tools'),
            runtime=skill.runtime,
            bootstrap_script_path=skill.bootstrap_script_path,
            runtime_options=load_json(skill.runtime_options, {}, skill.skill_id, 'runtime_options'),
            files=files,
        )

    @staticmethod
    def build_detail(db: Session, skill: Skill) -> SkillDetailSchema:
        """Assemble the detail schema of an already resolved and authorised skill (single place for file metadata)."""
        files = [
            SkillFileInfoSchema(
                path=path,
                media_type=media_type,
                size_bytes=size_bytes,
                checksum_sha256=checksum,
                is_text=is_text,
            )
            for path, media_type, size_bytes, checksum, is_text
            in SkillPackageRepository.list_paths(db, skill.skill_id)
        ]
        return SkillService._to_detail(skill, files)

    @staticmethod
    def _list_items(db: Session, skills: List[Skill]) -> List[SkillListItemSchema]:
        counts = SkillPackageRepository.count_by_skill_ids(db, [s.skill_id for s in skills]) if skills else {}
        return [SkillService._to_list_item(s, counts.get(s.skill_id, 0)) for s in skills]

    # ==================== READ ====================

    @staticmethod
    def list_skills(db: Session, app_id: int) -> List[SkillListItemSchema]:
        """Get the skills visible to an app: its own skills plus enabled system skills.

        Disabled app skills stay listed (flagged is_enabled=False); disabled system skills are absent. A system
        skill whose folded name collides with an app skill is dropped (the app skill wins).
        """
        app_skills = SkillRepository.list_for_app(db, app_id)
        system_skills = SkillRepository.get_system_skills(db, enabled_only=True, light=True)

        app_names = {}
        for skill in app_skills:
            app_names.setdefault(fold_name(skill.name), skill)
        visible_system = []
        for skill in system_skills:
            winner = app_names.get(fold_name(skill.name))
            if winner is not None:
                logger.warning(
                    "Skill name collision in app %s: name=%r app_skill_id=%s system_skill_id=%s — app skill wins",
                    app_id, skill.name, winner.skill_id, skill.skill_id,
                )
                continue
            visible_system.append(skill)

        return SkillService._list_items(db, list(app_skills) + visible_system)

    @staticmethod
    def list_system_skills(db: Session, enabled_only: bool = False) -> List[SkillListItemSchema]:
        """List system skills (admin view), optionally only the enabled ones."""
        return SkillService._list_items(db, SkillRepository.get_system_skills(db, enabled_only=enabled_only, light=True))

    @staticmethod
    def get_skill_detail(db: Session, app_id: int, skill_id: int) -> Optional[SkillDetailSchema]:
        """Get detailed information about an app skill or an enabled system skill"""
        if skill_id == 0:
            # New skill
            return SkillDetailSchema(
                skill_id=0,
                name="",
                description="",
                content="",
                created_at=None
            )

        skill = SkillRepository.get_by_id_and_app_id(db, skill_id, app_id)
        if not skill:
            # Read access to enabled system skills
            skill = SkillRepository.get_system_skill_by_id(db, skill_id, enabled_only=True)

        if not skill:
            return None

        return SkillService.build_detail(db, skill)

    @staticmethod
    def get_system_skill_detail(db: Session, skill_id: int) -> Optional[SkillDetailSchema]:
        """Get a system skill in any enabled state (admin view). None if missing or app-scoped."""
        skill = SkillRepository.get_system_skill_by_id(db, skill_id)
        return SkillService.build_detail(db, skill) if skill else None

    # ==================== WRITE ====================

    @staticmethod
    def _merge_when_to_use(skill: Skill, when_to_use: str) -> None:
        """Merge ``when_to_use`` into the stored frontmatter JSON without clobbering unreadable data."""
        frontmatter: Any = {}
        if skill.frontmatter:
            try:
                frontmatter = json.loads(skill.frontmatter)
            except (ValueError, TypeError):
                frontmatter = None
            if not isinstance(frontmatter, dict):
                # Nothing parseable to preserve: honour the explicit write instead of silently dropping it.
                logger.warning(f"Unreadable frontmatter JSON in Skill {skill.skill_id}; resetting it to write when_to_use")
                frontmatter = {}
        if when_to_use.strip():
            frontmatter['when_to_use'] = when_to_use
        else:
            frontmatter.pop('when_to_use', None)
        skill.frontmatter = dump_json(frontmatter)

    @staticmethod
    def _validate_package_fields(skill_data: CreateUpdateSkillSchema) -> None:
        """Validate the package metadata of a CRUD payload with the same rules as import/export.

        Uses ``render_skill_md`` (the public frontmatter contract) so anything accepted here can be exported and
        re-imported: safe-value checks, string sanity, the 64 KiB frontmatter cap and allowed_tools shape.
        """
        fields = skill_data.model_fields_set
        try:
            render_skill_md(
                name='validation',
                display_name=skill_data.display_name if 'display_name' in fields else None,
                description=skill_data.description,
                when_to_use=skill_data.when_to_use,
                allowed_tools=skill_data.allowed_tools if 'allowed_tools' in fields else None,
                runtime=skill_data.runtime if 'runtime' in fields else None,
                runtime_options=skill_data.runtime_options if 'runtime_options' in fields else None,
                body=skill_data.content or '',
            )
        except SkillFrontmatterError as exc:
            raise SkillValidationError(f"Invalid skill data: {exc}") from None

    @staticmethod
    def _resolve_bootstrap(db: Session, skill: Skill, skill_id: int, raw: Optional[str]) -> Optional[str]:
        """Normalise a bootstrap path and require it to be an existing SkillFile of the skill."""
        if raw is None or not raw.strip():
            return None
        try:
            path = SkillPackageRepository.normalize_path(raw)
        except ValueError:
            raise SkillValidationError("bootstrap_script_path is not a valid package path") from None
        existing = {row[0] for row in SkillPackageRepository.list_paths(db, skill_id)} if skill_id else set()
        if path not in existing:
            raise SkillValidationError("bootstrap_script_path must match an existing file of the skill package")
        return path

    @staticmethod
    def _normalize_target_name(existing: Optional[Skill], skill_data: CreateUpdateSkillSchema) -> tuple:
        """Resolve the normalised target name of a create/update payload.

        Returns:
            ``(new_name, is_create)``. On create the name is always (re-)normalised; on update it is only
            re-normalised when the submitted name differs from the stored one (so an existing, possibly
            legacy-formatted name is never silently rewritten).

        Raises:
            SkillValidationError: The submitted name is not a valid skill name.
        """
        is_create = existing is None
        new_name = existing.name if not is_create else ''
        if is_create or skill_data.name != existing.name:
            try:
                new_name = normalize_skill_name(skill_data.name)
            except SkillFrontmatterError as exc:
                raise SkillValidationError(f"Invalid skill name: {exc}") from None
        return new_name, is_create

    @staticmethod
    def _apply_payload(
        db: Session, skill: Skill, skill_id: int, new_name: str, skill_data: CreateUpdateSkillSchema
    ) -> None:
        """Copy a validated create/update payload onto ``skill`` (no persistence, no name-clash check).

        Package metadata follows the omitted/null/blank semantics documented on CreateUpdateSkillSchema.
        """
        fields_set = skill_data.model_fields_set
        bootstrap = skill.bootstrap_script_path
        if 'bootstrap_script_path' in fields_set:
            bootstrap = SkillService._resolve_bootstrap(db, skill, skill_id, skill_data.bootstrap_script_path)

        skill.name = new_name
        skill.description = skill_data.description
        skill.content = skill_data.content

        for attr in ('display_name', 'runtime'):
            if attr in fields_set:
                value = getattr(skill_data, attr)
                setattr(skill, attr, value if value and value.strip() else None)
        if 'bootstrap_script_path' in fields_set:
            skill.bootstrap_script_path = bootstrap
        for attr in ('allowed_tools', 'runtime_options'):
            if attr in fields_set:
                setattr(skill, attr, dump_json(getattr(skill_data, attr)))
        if skill_data.is_enabled is not None:
            skill.is_enabled = skill_data.is_enabled
        if skill_data.when_to_use is not None:
            SkillService._merge_when_to_use(skill, skill_data.when_to_use)

    @staticmethod
    def create_or_update_skill(
        db: Session,
        app_id: int,
        skill_id: int,
        skill_data: CreateUpdateSkillSchema
    ) -> Optional[SkillDetailSchema]:
        """Create a new skill or update an existing one.

        Optional package fields that are omitted on update preserve the stored value (see
        CreateUpdateSkillSchema). Commits through SkillRepository, so it must NOT be reused by the
        P2 atomic import path.

        Raises:
            SkillForbiddenError: The target is a system skill.
            SkillValidationError: Invalid name or package metadata.
            SkillConflictError: Duplicate name in the app (create or rename).
        """
        if app_id is None:
            raise ValueError("app_id is required: app skills can never be system skills")

        existing = None
        if skill_id != 0:
            existing = SkillRepository.get_by_id_and_app_id(db, skill_id, app_id)
            if not existing:
                if SkillRepository.get_system_skill_by_id(db, skill_id) is not None:
                    raise SkillForbiddenError(SYSTEM_SKILL_FORBIDDEN_MSG)
                return None

        SkillService._validate_package_fields(skill_data)
        new_name, is_create = SkillService._normalize_target_name(existing, skill_data)

        if is_create or new_name != existing.name:
            # Serialise per app so concurrent creates/renames cannot both pass the duplicate/quota checks.
            SkillRepository.lock_app_skills(db, app_id)
            clash = SkillRepository.get_by_name_and_app_id(db, new_name, app_id)
            if clash is not None and (is_create or clash.skill_id != existing.skill_id):
                raise SkillConflictError(f"A skill named {new_name!r} already exists in this app")

        if existing is None:
            # Enforce per-app skill limit before creation (SaaS mode only)
            from services.tier_enforcement_service import TierEnforcementService
            TierEnforcementService.check_resource_limit(db, app_id, 'skills')

            skill = Skill()
            skill.app_id = app_id
            skill.create_date = datetime.now()
        else:
            skill = existing

        SkillService._apply_payload(db, skill, skill_id, new_name, skill_data)

        # Use repository to save
        saved = SkillRepository.create(db, skill) if existing is None else SkillRepository.update(db, skill)
        return SkillService.build_detail(db, saved)

    @staticmethod
    def create_or_update_system_skill(
        db: Session, skill_id: int, skill_data: CreateUpdateSkillSchema
    ) -> Optional[SkillDetailSchema]:
        """Create a new system skill or update an existing one (admin route, ``app_id`` is always NULL).

        Mirrors ``create_or_update_skill`` but scoped to the platform: no per-app advisory lock (system
        name races are closed by the ``uq_skill_system_name`` partial unique index, caught below) and
        never subject to the per-app tier quota. ``source`` is stamped ``'admin'`` once at creation and
        is never touched again — ``CreateUpdateSkillSchema`` has no ``source`` field, so a client can
        never change it through this path.

        Raises:
            SkillValidationError: Invalid name or package metadata.
            SkillConflictError: Duplicate name among system skills (create or rename, including a lost
                race caught by the DB constraint), or a rename/content rewrite of a ``source='yaml'`` skill
                (it would be recreated on the next startup), or the skill is frozen.
        """
        existing = None
        if skill_id != 0:
            existing = SkillRepository.get_system_skill_by_id(db, skill_id)
            if not existing:
                return None

        SkillService._validate_package_fields(skill_data)
        new_name, is_create = SkillService._normalize_target_name(existing, skill_data)

        if not is_create and existing.source == 'yaml' and (
            new_name != existing.name or skill_data.content != existing.content
        ):
            raise SkillConflictError(YAML_SKILL_DELETE_MSG)
        if not is_create and existing.is_frozen:
            raise SkillConflictError("This skill is frozen and cannot be modified.")

        if is_create or new_name != existing.name:
            clash = SkillRepository.get_system_skill_by_name(db, new_name)
            if clash is not None and (is_create or clash.skill_id != existing.skill_id):
                raise SkillConflictError(f"A system skill named {new_name!r} already exists")

        if existing is None:
            skill = Skill()
            skill.app_id = None
            skill.source = 'admin'
            skill.create_date = datetime.now()
        else:
            skill = existing

        SkillService._apply_payload(db, skill, skill_id, new_name, skill_data)

        try:
            saved = SkillRepository.create(db, skill) if existing is None else SkillRepository.update(db, skill)
        except IntegrityError:
            db.rollback()
            raise SkillConflictError(f"A system skill named {new_name!r} already exists") from None
        return SkillService.build_detail(db, saved)

    @staticmethod
    def delete_skill(db: Session, app_id: int, skill_id: int) -> bool:
        """Delete an app skill. System skills are rejected with SkillForbiddenError.

        Raises:
            SkillConflictError: The database refused the delete (skill still referenced somewhere).
        """
        try:
            if SkillRepository.delete_by_id_and_app_id(db, skill_id, app_id):
                return True
        except RuntimeError as exc:
            raise SkillConflictError(str(exc)) from None
        if SkillRepository.get_system_skill_by_id(db, skill_id) is not None:
            raise SkillForbiddenError(SYSTEM_SKILL_FORBIDDEN_MSG)
        return False

    @staticmethod
    def delete_system_skill(db: Session, skill_id: int) -> bool:
        """Delete a system skill (admin route). Returns False when it does not exist.

        Raises:
            SkillConflictError: If the skill is seeded from system_defaults.yaml, frozen, or attached to agents.
        """
        skill = SkillRepository.get_system_skill_by_id(db, skill_id)
        if skill is None:
            return False
        if skill.source == 'yaml':
            raise SkillConflictError(YAML_SKILL_DELETE_MSG)
        if skill.is_frozen:
            raise SkillConflictError("This skill is frozen and cannot be deleted.")
        agents, app_ids = SkillRepository.get_attachment_stats(db, skill_id)
        if agents:
            logger.warning(
                "Refusing to delete system skill %s: attached to %s agents in apps %s", skill_id, agents, app_ids
            )
            raise SkillConflictError(
                f"This skill is attached to {agents} agents in {len(app_ids)} apps — disable it instead."
            )
        try:
            SkillRepository.delete(db, skill)
        except RuntimeError as exc:
            raise SkillConflictError(str(exc)) from None
        return True

    @staticmethod
    def set_enabled_for_app(
        db: Session, app_id: int, skill_id: int, enabled: bool
    ) -> Optional[SkillDetailSchema]:
        """Enable/disable an app-owned skill atomically. Returns None if the app has no such skill.

        Raises:
            SkillForbiddenError: The skill is a system skill.
        """
        if SkillRepository.set_enabled_for_app(db, skill_id, app_id, enabled) == 0:
            if SkillRepository.get_system_skill_by_id(db, skill_id) is not None:
                raise SkillForbiddenError(SYSTEM_SKILL_FORBIDDEN_MSG)
            return None
        logger.info("Skill %s in app %s %s", skill_id, app_id, "enabled" if enabled else "disabled")
        skill = SkillRepository.get_by_id_and_app_id(db, skill_id, app_id)
        return SkillService.build_detail(db, skill) if skill else None

    @staticmethod
    def set_system_skill_enabled(db: Session, skill_id: int, enabled: bool) -> Optional[SkillDetailSchema]:
        """Enable/disable a system skill atomically (admin). Returns None if it does not exist."""
        if SkillRepository.set_enabled_system(db, skill_id, enabled) == 0:
            return None
        agents, app_ids = SkillRepository.get_attachment_stats(db, skill_id)
        logger.info(
            "System skill %s %s: %s agents in %s apps affected",
            skill_id, "enabled" if enabled else "disabled", agents, len(app_ids),
        )
        return SkillService.get_system_skill_detail(db, skill_id)
