import hashlib
import json
from typing import Optional, List

from models.skill import Skill
from repositories.skill_repository import SkillRepository
from sqlalchemy.orm import Session
from datetime import datetime
from schemas.skill_schemas import (
    SkillListItemSchema,
    SkillDetailSchema,
    CreateUpdateSkillSchema,
    SkillFileSchema,
)
from utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_field(value) -> list | dict | None:
    """Return a Python object from a JSON text column, or None."""
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def _to_json_text(value) -> Optional[str]:
    """Serialize a list/dict to a JSON string for storage, or None."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _skill_to_detail(skill: Skill) -> SkillDetailSchema:
    files = [
        SkillFileSchema(
            file_id=sf.file_id,
            path=sf.path,
            media_type=sf.media_type,
            content_text=sf.content_text,
            checksum_sha256=sf.checksum_sha256,
        )
        for sf in (skill.files or [])
    ]
    return SkillDetailSchema(
        skill_id=skill.skill_id,
        name=skill.name,
        display_name=skill.display_name,
        description=skill.description or "",
        content=skill.content or "",
        # dependencies omitted — field removed from schema in v2
        allowed_tools=_parse_json_field(skill.allowed_tools),
        runtime=skill.runtime,
        bootstrap_script_path=skill.bootstrap_script_path,
        runtime_options=_parse_json_field(skill.runtime_options),
        is_builtin=skill.is_builtin,
        files=files,
        created_at=skill.create_date,
        is_frozen=skill.is_frozen,
    )


class SkillService:
    @staticmethod
    def list_skills(db: Session, app_id: int) -> List[SkillListItemSchema]:
        """Get all skills visible to an app (owned + builtins) as list items."""
        skills = SkillRepository.get_all_by_app_id(db, app_id)
        return [
            SkillListItemSchema(
                skill_id=skill.skill_id,
                name=skill.name,
                display_name=skill.display_name,
                description=skill.description or "",
                runtime=skill.runtime,
                bootstrap_script_path=skill.bootstrap_script_path,
                file_count=len(skill.files or []),
                is_builtin=skill.is_builtin,
                created_at=skill.create_date,
                is_frozen=skill.is_frozen,
            )
            for skill in skills
        ]

    @staticmethod
    def get_skill_detail(db: Session, app_id: int, skill_id: int) -> Optional[SkillDetailSchema]:
        """Get detailed information about a specific skill."""
        if skill_id == 0:
            return SkillDetailSchema(
                skill_id=0,
                name="",
                description="",
                content="",
                created_at=None,
            )

        skill = SkillRepository.get_by_id_and_app_id(db, skill_id, app_id)
        if not skill:
            return None

        return _skill_to_detail(skill)

    @staticmethod
    def create_or_update_skill(
        db: Session,
        app_id: int,
        skill_id: int,
        skill_data: CreateUpdateSkillSchema,
    ) -> Optional[Skill]:
        """Create a new skill or update an existing one."""
        if skill_id == 0:
            from services.tier_enforcement_service import TierEnforcementService
            TierEnforcementService.check_resource_limit(db, app_id, 'skills')

            skill = Skill()
            skill.app_id = app_id
            skill.create_date = datetime.now()
        else:
            skill = db.query(Skill).filter(
                Skill.skill_id == skill_id,
                Skill.app_id == app_id,  # Strict: only owned skills may be edited
            ).first()
            if not skill:
                return None

        skill.name = skill_data.name
        skill.display_name = skill_data.display_name
        skill.description = skill_data.description
        skill.content = skill_data.content
        # dependencies removed in v2 — not written on create/update
        skill.allowed_tools = _to_json_text(skill_data.allowed_tools)
        skill.runtime = skill_data.runtime
        skill.bootstrap_script_path = skill_data.bootstrap_script_path
        skill.runtime_options = _to_json_text(skill_data.runtime_options)

        if skill_id == 0:
            skill = SkillRepository.create(db, skill)
        else:
            skill = SkillRepository.update(db, skill)

        # Sync inline SkillFile records when provided in the request
        if skill_data.files is not None:
            SkillRepository.delete_skill_files(db, skill.skill_id)
            for file_schema in skill_data.files:
                raw = file_schema.content_text.encode() if file_schema.content_text else b""
                checksum = file_schema.checksum_sha256 or _sha256_hex(raw)
                SkillRepository.upsert_skill_file(
                    db,
                    skill_id=skill.skill_id,
                    path=file_schema.path,
                    media_type=file_schema.media_type,
                    content_text=file_schema.content_text,
                    content_bytes=None,
                    checksum_sha256=checksum,
                )
            db.refresh(skill)

        return skill

    @staticmethod
    def delete_skill(db: Session, app_id: int, skill_id: int) -> bool:
        """Delete a skill (only app-owned skills; builtins cannot be deleted)."""
        return SkillRepository.delete_by_id_and_app_id(db, skill_id, app_id)

    # ------------------------------------------------------------------
    # Import / Export (IT-3)
    # ------------------------------------------------------------------

    @staticmethod
    def export_skill_zip(db: Session, app_id: int, skill_id: int) -> Optional[bytes]:
        """Export a skill as a canonical Agent Skills ZIP package."""
        from repositories.skill_package_repository import SkillPackageRepository

        try:
            return SkillPackageRepository.export_package(db, app_id, skill_id)
        except ValueError:
            return None

    @staticmethod
    def import_skill_zip(db: Session, app_id: int, zip_bytes: bytes) -> Skill:
        """Import a canonical Agent Skills ZIP package, accepting legacy files/ input."""
        from repositories.skill_package_repository import SkillPackageRepository

        return SkillPackageRepository.import_package(db, app_id, zip_bytes)
