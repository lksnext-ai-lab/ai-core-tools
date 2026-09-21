import json
from typing import Any, Optional, List
from models.skill import Skill
from repositories.skill_repository import SkillRepository
from repositories.skill_package_repository import SkillPackageRepository
from sqlalchemy.orm import Session
from datetime import datetime
from schemas.skill_schemas import (
    SkillListItemSchema, SkillDetailSchema, CreateUpdateSkillSchema, SkillFileInfoSchema
)
from utils.logger import get_logger

logger = get_logger(__name__)


class SkillService:
    @staticmethod
    def _load_json(value: Optional[str], default: Any, skill_id: Optional[int] = None, column: str = '') -> Any:
        """Tolerant JSON loader: malformed or wrong-typed stored values log a warning and return ``default``.

        Never logs the value itself.
        """
        if value is None or value == '':
            return default
        try:
            loaded = json.loads(value)
        except (ValueError, TypeError):
            logger.warning(f"Malformed JSON in Skill {skill_id} column '{column}'; using default")
            return default
        if loaded is None or not isinstance(loaded, type(default)):
            logger.warning(f"Unexpected JSON type in Skill {skill_id} column '{column}'; using default")
            return default
        if isinstance(loaded, list):
            strings = [x for x in loaded if isinstance(x, str)]
            if len(strings) != len(loaded):
                logger.warning(f"Dropped non-string elements in Skill {skill_id} column '{column}'")
            return strings
        return loaded

    @staticmethod
    def _dump_json(value: Any) -> Optional[str]:
        """Serialise ``value`` to JSON; ``None`` stays ``None``."""
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False)

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
            frontmatter=SkillService._load_json(skill.frontmatter, {}, skill.skill_id, 'frontmatter'),
            allowed_tools=SkillService._load_json(skill.allowed_tools, [], skill.skill_id, 'allowed_tools'),
            runtime=skill.runtime,
            bootstrap_script_path=skill.bootstrap_script_path,
            runtime_options=SkillService._load_json(
                skill.runtime_options, {}, skill.skill_id, 'runtime_options'
            ),
            files=files,
        )

    @staticmethod
    def list_skills(db: Session, app_id: int) -> List[SkillListItemSchema]:
        """Get all skills for a specific app as list items"""
        skills = SkillRepository.get_all_by_app_id(db, app_id)
        counts = SkillPackageRepository.count_by_skill_ids(db, [s.skill_id for s in skills]) if skills else {}
        return [SkillService._to_list_item(s, counts.get(s.skill_id, 0)) for s in skills]

    @staticmethod
    def get_skill_detail(db: Session, app_id: int, skill_id: int) -> Optional[SkillDetailSchema]:
        """Get detailed information about a specific skill"""
        if skill_id == 0:
            # New skill
            return SkillDetailSchema(
                skill_id=0,
                name="",
                description="",
                content="",
                created_at=None
            )

        # Existing skill
        skill = SkillRepository.get_by_id_and_app_id(db, skill_id, app_id)

        if not skill:
            return None

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
        skill.frontmatter = SkillService._dump_json(frontmatter)

    @staticmethod
    def create_or_update_skill(
        db: Session,
        app_id: int,
        skill_id: int,
        skill_data: CreateUpdateSkillSchema
    ) -> Optional[Skill]:
        """Create a new skill or update an existing one.

        Optional package fields that are omitted on update preserve the stored value (see
        CreateUpdateSkillSchema). Commits through SkillRepository, so it must NOT be reused by the
        P2 atomic import path.
        """
        if app_id is None:
            raise ValueError("app_id is required: app skills can never be system skills")
        if skill_id == 0:
            # Enforce per-app skill limit before creation (SaaS mode only)
            from services.tier_enforcement_service import TierEnforcementService
            TierEnforcementService.check_resource_limit(db, app_id, 'skills')

            # Create new skill
            skill = Skill()
            skill.app_id = app_id
            skill.create_date = datetime.now()
        else:
            # Update existing skill
            skill = SkillRepository.get_by_id_and_app_id(db, skill_id, app_id)

            if not skill:
                return None

        # Update skill data
        skill.name = skill_data.name
        skill.description = skill_data.description
        skill.content = skill_data.content

        # Package metadata: omitted -> preserve stored value; explicit null clears (except is_enabled)
        fields_set = skill_data.model_fields_set
        for attr in ('display_name', 'runtime', 'bootstrap_script_path'):
            if attr in fields_set:
                value = getattr(skill_data, attr)
                setattr(skill, attr, value if value and value.strip() else None)
        for attr in ('allowed_tools', 'runtime_options'):
            if attr in fields_set:
                setattr(skill, attr, SkillService._dump_json(getattr(skill_data, attr)))
        if skill_data.is_enabled is not None:
            skill.is_enabled = skill_data.is_enabled
        if skill_data.when_to_use is not None:
            SkillService._merge_when_to_use(skill, skill_data.when_to_use)

        # Use repository to save
        if skill_id == 0:
            return SkillRepository.create(db, skill)
        else:
            return SkillRepository.update(db, skill)

    @staticmethod
    def delete_skill(db: Session, app_id: int, skill_id: int) -> bool:
        """Delete a skill"""
        return SkillRepository.delete_by_id_and_app_id(db, skill_id, app_id)
